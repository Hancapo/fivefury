from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ..authoring import BuildContext, ValidationReport
from ..cut.model import CutFile
from ..cut.pso import read_cut
from ..cut.scene.base import CutScene
from ..game_target import GameTarget, coerce_game_target
from ..metahash import MetaHash
from ..resource import ResourceHeader
from ..vector import (
    Quaternion,
    Vector3,
    lerp,
)
from .channel_policy import YcdChannelEncoding, YcdChannelEncodingPolicy
from .model import (
    Ycd,
    YcdAnimation,
    YcdAnimationBoneId,
    YcdCameraAnimationSample,
    YcdClipAnimation,
    YcdClipType,
    YcdSequence,
)
from .sequence_channels import (
    YcdAnimSequence,
    YcdCachedQuaternionChannel,
    YcdChannelType,
    YcdQuantizeFloatChannel,
    YcdRawFloatChannel,
    YcdStaticFloatChannel,
    YcdStaticQuaternionChannel,
    YcdStaticVector3Channel,
)
from .sequence_tracks import (
    YcdAnimationTrack,
    YcdTrackFormat,
    get_ycd_track_format,
    is_ycd_rotation_track,
)

YCD_CUTSCENE_DEFAULT_FPS = 30.0
YCD_CUTSCENE_DEFAULT_VERSION = 46
YCD_CUTSCENE_SEQUENCE_FRAME_LIMIT = 287
_DEFAULT_CHANNEL_POLICY = YcdChannelEncodingPolicy()


class YcdQuaternionEncoding(StrEnum):
    RETAIL_CACHED = "retail_cached"
    EXPLICIT = "explicit"


YcdTrackSample = float | Vector3 | Quaternion


def _track_component_count(
    track: int | YcdAnimationTrack, format: int | YcdTrackFormat | None = None
) -> int:
    resolved = (
        get_ycd_track_format(int(track))
        if format is None
        else YcdTrackFormat(int(format))
    )
    return {
        YcdTrackFormat.FLOAT: 1,
        YcdTrackFormat.VECTOR3: 3,
        YcdTrackFormat.QUATERNION: 4,
    }[resolved]


def _coerce_sample(value: object, track_format: YcdTrackFormat) -> YcdTrackSample:
    if track_format is YcdTrackFormat.FLOAT:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            raise TypeError("Float tracks require float samples, not sequences")
        return float(value)
    if track_format is YcdTrackFormat.VECTOR3:
        if not isinstance(value, Vector3):
            raise TypeError(
                f"Vector3 tracks require Vector3 samples, got {type(value).__name__}"
            )
        return value
    if not isinstance(value, Quaternion):
        raise TypeError(
            f"Quaternion tracks require Quaternion samples, got {type(value).__name__}"
        )
    return value.normalized_strict()


def _interpolate_values(
    start: YcdTrackSample,
    end: YcdTrackSample,
    alpha: float,
) -> YcdTrackSample:
    if type(start) is not type(end):
        raise TypeError("YCD interpolation endpoints must have the same sample type")
    if isinstance(start, Quaternion):
        return start.nlerp(end, alpha)  # type: ignore[arg-type]
    if isinstance(start, Vector3):
        return start.lerp(end, alpha)  # type: ignore[arg-type]
    return lerp(float(start), float(end), alpha)


def _is_per_frame_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, Vector3, Quaternion)
    )


def _sample_track_values(
    source: object,
    *,
    track_format: YcdTrackFormat,
    frame_count: int,
    fps: float,
) -> list[YcdTrackSample]:
    if frame_count <= 0:
        return []

    if isinstance(source, Mapping):
        if not source:
            raise ValueError("Keyframe mapping cannot be empty")
        keyed = []
        for key, value in source.items():
            frame = round(float(key) * fps)
            frame = min(max(frame, 0), frame_count - 1)
            keyed.append((frame, _coerce_sample(value, track_format)))
        keyed.sort(key=lambda item: item[0])
        deduped: list[tuple[int, YcdTrackSample]] = []
        for frame, value in keyed:
            if deduped and deduped[-1][0] == frame:
                deduped[-1] = (frame, value)
            else:
                deduped.append((frame, value))
        result = [deduped[0][1]] * frame_count
        if len(deduped) == 1:
            return list(result)
        for (start_frame, start_value), (end_frame, end_value) in itertools.pairwise(
            deduped
        ):
            span = max(end_frame - start_frame, 1)
            for frame in range(start_frame, min(end_frame, frame_count - 1) + 1):
                alpha = float(frame - start_frame) / float(span)
                result[frame] = _interpolate_values(
                    start_value, end_value, alpha
                )
        last_frame, last_value = deduped[-1]
        for frame in range(last_frame, frame_count):
            result[frame] = last_value
        return Quaternion.make_continuous(result) if track_format is YcdTrackFormat.QUATERNION else result  # type: ignore[arg-type]

    if _is_per_frame_sequence(source):
        if len(source) != frame_count:  # type: ignore[arg-type]
            raise ValueError(
                f"Expected {frame_count} per-frame samples, got {len(source)}"
            )  # type: ignore[arg-type]
        result = [_coerce_sample(item, track_format) for item in source]  # type: ignore[arg-type]
        return Quaternion.make_continuous(result) if track_format is YcdTrackFormat.QUATERNION else result  # type: ignore[arg-type]

    constant = _coerce_sample(source, track_format)
    result = [constant for _ in range(frame_count)]
    return Quaternion.make_continuous(result) if track_format is YcdTrackFormat.QUATERNION else result  # type: ignore[arg-type]


def _sample_components(sample: YcdTrackSample) -> tuple[float, ...]:
    if isinstance(sample, (Vector3, Quaternion)):
        return sample.components
    return (float(sample),)


def _make_quantize_channel(
    component_index: int, values: list[float]
) -> YcdQuantizeFloatChannel:
    minimum = min(values)
    maximum = max(values)
    span = max(maximum - minimum, 0.0)
    quantum = (span / 65535.0) if span > 1e-12 else (1.0 / 65535.0)
    return YcdQuantizeFloatChannel(
        channel_type=YcdChannelType.QUANTIZE_FLOAT,
        channel_index=component_index,
        value_bits=16,
        quantum=quantum,
        offset=minimum,
        values=values,
    )


def _make_component_channels(
    samples: list[YcdTrackSample],
    *,
    encoding: YcdChannelEncoding,
    retail_quantized: bool,
) -> list[YcdStaticFloatChannel | YcdQuantizeFloatChannel | YcdRawFloatChannel]:
    channels: list[
        YcdStaticFloatChannel | YcdQuantizeFloatChannel | YcdRawFloatChannel
    ] = []
    component_count = len(_sample_components(samples[0]))
    for component_index in range(component_count):
        values = [float(_sample_components(sample)[component_index]) for sample in samples]
        if all(abs(value - values[0]) <= 1e-9 for value in values[1:]):
            channels.append(
                YcdStaticFloatChannel(
                    channel_type=YcdChannelType.STATIC_FLOAT,
                    channel_index=component_index,
                    value=float(values[0]),
                )
            )
        elif encoding is YcdChannelEncoding.RETAIL and retail_quantized:
            channels.append(_make_quantize_channel(component_index, values))
        else:
            channels.append(
                YcdRawFloatChannel(
                    channel_type=YcdChannelType.RAW_FLOAT,
                    channel_index=component_index,
                    values=values,
                )
            )
    return channels


def _orient_cached_quaternion_window(
    samples: list[Quaternion],
) -> tuple[int, list[Quaternion]]:
    candidates: list[tuple[float, float, float, int]] = []
    for component_index in range(4):
        magnitudes = [
            abs(sample.components[component_index]) for sample in samples
        ]
        minimum_magnitude = min(magnitudes)
        mean_square = sum(value * value for value in magnitudes) / len(magnitudes)
        peak = max(magnitudes)
        candidates.append((minimum_magnitude, mean_square, peak, -component_index))
    omitted_component = -max(candidates)[3]
    oriented = [
        sample
        if sample.components[omitted_component] >= 0.0
        else -sample
        for sample in samples
    ]
    return omitted_component, oriented


def _make_cached_quaternion_channels(
    samples: list[Quaternion],
    *,
    encoding: YcdChannelEncoding,
    retail_quantized: bool,
) -> list[
    YcdStaticFloatChannel
    | YcdQuantizeFloatChannel
    | YcdRawFloatChannel
    | YcdCachedQuaternionChannel
]:
    omitted_component, samples = _orient_cached_quaternion_window(samples)
    explicit_samples = [
        Vector3.from_iterable(
            component
            for component_index, component in enumerate(sample.components)
            if component_index != omitted_component
        )
        for sample in samples
    ]
    channels = _make_component_channels(
        explicit_samples,
        encoding=encoding,
        retail_quantized=retail_quantized,
    )
    channels.append(
        YcdCachedQuaternionChannel(
            channel_type=YcdChannelType.CACHED_QUATERNION1,
            channel_index=3,
            quat_index=omitted_component,
        )
    )
    return channels


def _make_channels(
    samples: list[YcdTrackSample],
    *,
    track: int | YcdAnimationTrack | None = None,
    quaternion_encoding: YcdQuaternionEncoding = YcdQuaternionEncoding.RETAIL_CACHED,
    channel_encoding: YcdChannelEncoding = YcdChannelEncoding.RETAIL,
) -> list[
    YcdStaticFloatChannel
    | YcdStaticVector3Channel
    | YcdStaticQuaternionChannel
    | YcdQuantizeFloatChannel
    | YcdRawFloatChannel
    | YcdCachedQuaternionChannel
]:
    if not samples:
        return []
    component_count = len(_sample_components(samples[0]))
    track_value = None if track is None else int(track)
    retail_quantized = track_value in {
        int(YcdAnimationTrack.BONE_TRANSLATION),
        int(YcdAnimationTrack.BONE_ROTATION),
        int(YcdAnimationTrack.MOVER_TRANSLATION),
        int(YcdAnimationTrack.MOVER_ROTATION),
    }
    if all(sample == samples[0] for sample in samples[1:]):
        value = samples[0]
        if component_count == 3:
            if not isinstance(value, Vector3):
                raise TypeError("Vector3 channel received a non-Vector3 sample")
            return [
                YcdStaticVector3Channel(
                    channel_type=YcdChannelType.STATIC_VECTOR3,
                    channel_index=0,
                    value=value,
                )
            ]
        if component_count == 4:
            if not isinstance(value, Quaternion):
                raise TypeError("Quaternion channel received a non-Quaternion sample")
            value = value.canonicalized()
            return [
                YcdStaticQuaternionChannel(
                    channel_type=YcdChannelType.STATIC_QUATERNION,
                    channel_index=0,
                    value=value,
                )
            ]
        return [
            YcdStaticFloatChannel(
                channel_type=YcdChannelType.STATIC_FLOAT,
                channel_index=0,
                value=float(value),
            )
        ]

    if (
        component_count == 4
        and track_value is not None
        and is_ycd_rotation_track(track_value)
        and quaternion_encoding is YcdQuaternionEncoding.RETAIL_CACHED
    ):
        return _make_cached_quaternion_channels(
            samples,  # type: ignore[arg-type]
            encoding=channel_encoding,
            retail_quantized=retail_quantized,
        )
    return _make_component_channels(
        samples,
        encoding=channel_encoding,
        retail_quantized=retail_quantized,
    )


def _cutscene_track_sort_key(track_spec: YcdCutsceneTrack) -> tuple[int, int, int]:
    order = {
        int(YcdAnimationTrack.BONE_TRANSLATION): 0,
        int(YcdAnimationTrack.BONE_ROTATION): 1,
        int(YcdAnimationTrack.MOVER_TRANSLATION): 2,
        int(YcdAnimationTrack.MOVER_ROTATION): 3,
    }
    return (
        order.get(int(track_spec.track), 100 + int(track_spec.track)),
        int(track_spec.bone_id),
        int(track_spec.track),
    )


def _iter_sequence_sample_windows(
    samples: list[YcdTrackSample],
    *,
    frame_limit: int = YCD_CUTSCENE_SEQUENCE_FRAME_LIMIT,
) -> list[tuple[int, list[YcdTrackSample]]]:
    if not samples:
        return []
    max_step = max(int(frame_limit), 1)
    max_count = max_step + 1
    if len(samples) <= max_count:
        return [(0, samples)]
    windows: list[tuple[int, list[YcdTrackSample]]] = []
    start = 0
    while start < len(samples):
        chunk = samples[start : min(start + max_count, len(samples))]
        if not chunk:
            break
        windows.append((start, chunk))
        if start + len(chunk) >= len(samples):
            break
        start += max_step
    return windows


def _is_camera_track_id(track: int) -> bool:
    return int(track) in {
        int(YcdAnimationTrack.CAMERA_TRANSLATION),
        int(YcdAnimationTrack.CAMERA_ROTATION),
        int(YcdAnimationTrack.CAMERA_FIELD_OF_VIEW),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH),
        int(YcdAnimationTrack.CAMERA_MOTION_BLUR),
        int(YcdAnimationTrack.CAMERA_COC),
        int(YcdAnimationTrack.CAMERA_FOCUS),
        int(YcdAnimationTrack.CAMERA_NIGHT_COC),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE),
    }


@dataclass(slots=True)
class YcdCutsceneSection:
    index: int
    start_time: float
    end_time: float
    start_frame: int
    end_frame: int

    @property
    def duration(self) -> float:
        return max(0.0, float(self.end_time) - float(self.start_time))

    @property
    def frame_count(self) -> int:
        return max(0, int(self.end_frame) - int(self.start_frame) + 1)


@dataclass(slots=True)
class YcdCutsceneTrack:
    track: int
    bone_id: int
    format: YcdTrackFormat
    samples: list[YcdTrackSample]
    channel_policy: YcdChannelEncodingPolicy | None = None


@dataclass(slots=True)
class YcdCutsceneBoneAnimation:
    position: Vector3 | Mapping[float, Vector3] | Sequence[Vector3] | None = None
    rotation: Quaternion | Mapping[float, Quaternion] | Sequence[Quaternion] | None = None


@dataclass(slots=True)
class YcdFacialTrackSamples:
    samples: object
    format: YcdTrackFormat | int | None = None


@dataclass(slots=True)
class YcdFacialTrackSet:
    blend_shapes: Mapping[int, object | YcdFacialTrackSamples] = field(
        default_factory=dict
    )
    visemes: Mapping[int, object | YcdFacialTrackSamples] = field(default_factory=dict)
    animated_normal_maps: Mapping[int, object | YcdFacialTrackSamples] = field(
        default_factory=dict
    )
    controls: Mapping[int, object | YcdFacialTrackSamples] = field(default_factory=dict)
    translations: Mapping[int, object | YcdFacialTrackSamples] = field(
        default_factory=dict
    )
    rotations: Mapping[int, object | YcdFacialTrackSamples] = field(
        default_factory=dict
    )
    scales: Mapping[int, object | YcdFacialTrackSamples] = field(default_factory=dict)
    tinting: object | YcdFacialTrackSamples | None = None


@dataclass(slots=True)
class YcdCutsceneClip:
    name: str
    tracks: list[YcdCutsceneTrack] = field(default_factory=list)


def _coerce_bone_animation(value: object) -> YcdCutsceneBoneAnimation:
    if isinstance(value, YcdCutsceneBoneAnimation):
        return value
    if isinstance(value, Mapping):
        return YcdCutsceneBoneAnimation(
            position=value.get("position"),
            rotation=value.get("rotation"),
        )
    raise TypeError(f"Unsupported cutscene bone animation payload: {value!r}")


class YcdCutsceneBuilder:
    def __init__(
        self,
        name: str,
        *,
        duration: float,
        camera_cuts: Sequence[float] | None = None,
        section_index_start: int = 0,
        fps: float = YCD_CUTSCENE_DEFAULT_FPS,
        version: int = YCD_CUTSCENE_DEFAULT_VERSION,
        game: str | GameTarget = GameTarget.GTA5,
        quaternion_encoding: YcdQuaternionEncoding = YcdQuaternionEncoding.RETAIL_CACHED,
        channel_policy: YcdChannelEncodingPolicy = _DEFAULT_CHANNEL_POLICY,
    ) -> None:
        self.name = str(name)
        self.duration = float(duration)
        self.fps = float(fps)
        self.version = int(version)
        self.game = coerce_game_target(game)
        if not isinstance(quaternion_encoding, YcdQuaternionEncoding):
            raise TypeError("quaternion_encoding must be a YcdQuaternionEncoding")
        self.quaternion_encoding = quaternion_encoding
        if not isinstance(channel_policy, YcdChannelEncodingPolicy):
            raise TypeError("channel_policy must be a YcdChannelEncodingPolicy")
        self.channel_policy = channel_policy
        self.section_index_start = int(section_index_start)
        if self.section_index_start < 0:
            raise ValueError("section_index_start cannot be negative")
        self.camera_cuts = self._normalize_camera_cuts(camera_cuts or [])
        self._clips: dict[str, YcdCutsceneClip] = {}

    @classmethod
    def create(
        cls,
        name: str,
        *,
        duration: float,
        camera_cuts: Sequence[float] | None = None,
        section_index_start: int = 0,
        fps: float = YCD_CUTSCENE_DEFAULT_FPS,
        version: int = YCD_CUTSCENE_DEFAULT_VERSION,
        game: str | GameTarget = GameTarget.GTA5,
        quaternion_encoding: YcdQuaternionEncoding = YcdQuaternionEncoding.RETAIL_CACHED,
        channel_policy: YcdChannelEncodingPolicy = _DEFAULT_CHANNEL_POLICY,
    ) -> YcdCutsceneBuilder:
        return cls(
            name,
            duration=duration,
            camera_cuts=camera_cuts,
            section_index_start=section_index_start,
            fps=fps,
            version=version,
            game=game,
            quaternion_encoding=quaternion_encoding,
            channel_policy=channel_policy,
        )

    @classmethod
    def from_cut(
        cls,
        source: str | Path | CutFile | CutScene,
        *,
        name: str | None = None,
        fps: float = YCD_CUTSCENE_DEFAULT_FPS,
        version: int = YCD_CUTSCENE_DEFAULT_VERSION,
        game: str | GameTarget = GameTarget.GTA5,
        quaternion_encoding: YcdQuaternionEncoding = YcdQuaternionEncoding.RETAIL_CACHED,
        channel_policy: YcdChannelEncodingPolicy = _DEFAULT_CHANNEL_POLICY,
    ) -> YcdCutsceneBuilder:
        if isinstance(source, CutScene):
            resolved_name = name or "cutscene"
            camera_cuts = (
                list(source.camera_cut_list)
                if source.camera_cut_list is not None
                else [
                    event.start
                    for event in source.timeline
                    if event.event_name == "camera_cut" and event.start > 0.0
                ]
            )
            return cls(
                resolved_name,
                duration=source.duration,
                camera_cuts=camera_cuts,
                fps=fps,
                version=version,
                game=game,
                quaternion_encoding=quaternion_encoding,
                channel_policy=channel_policy,
            )

        if isinstance(source, CutFile):
            cut = source
            source_name = (
                name or Path(getattr(cut, "path", "") or "cutscene").stem or "cutscene"
            )
        else:
            source_path = Path(source)
            source_name = name or source_path.stem
            cut = read_cut(source_path)

        root = cut.root
        duration = float(root.fields.get("fTotalDuration", 0.0))
        camera_cuts = [
            float(value)
            for value in root.fields.get("cameraCutList", [])
            if float(value) > 0.0
        ]
        return cls(
            source_name,
            duration=duration,
            camera_cuts=camera_cuts,
            fps=fps,
            version=version,
            game=game,
            quaternion_encoding=quaternion_encoding,
            channel_policy=channel_policy,
        )

    def _normalize_camera_cuts(self, camera_cuts: Sequence[float]) -> list[float]:
        result: list[float] = []
        for value in camera_cuts:
            time_value = float(value)
            if time_value <= 0.0 or time_value >= self.duration:
                continue
            if result and abs(result[-1] - time_value) <= 1e-6:
                continue
            result.append(time_value)
        result.sort()
        normalized: list[float] = []
        for value in result:
            if normalized and abs(normalized[-1] - value) <= 1e-6:
                continue
            normalized.append(value)
        return normalized

    @property
    def total_frames(self) -> int:
        return max(round(self.duration * self.fps) + 1, 1)

    @property
    def sections(self) -> list[YcdCutsceneSection]:
        boundaries = [0.0, *self.camera_cuts, self.duration]
        sections: list[YcdCutsceneSection] = []
        for index, (start, end) in enumerate(itertools.pairwise(boundaries)):
            start_frame = round(start * self.fps)
            end_frame = round(end * self.fps)
            sections.append(
                YcdCutsceneSection(
                    index=index,
                    start_time=float(start),
                    end_time=float(end),
                    start_frame=start_frame,
                    end_frame=end_frame,
                )
            )
        return sections

    def _get_or_create_clip(self, name: str) -> YcdCutsceneClip:
        key = str(name)
        clip = self._clips.get(key)
        if clip is None:
            clip = YcdCutsceneClip(name=key)
            self._clips[key] = clip
        return clip

    def sample_camera(self, name: str, time: float) -> YcdCameraAnimationSample:
        clip = self._clips.get(str(name))
        if clip is None:
            return YcdCameraAnimationSample()
        frame = min(max(float(time) * self.fps, 0.0), self.total_frames - 1)
        values: dict[int, YcdTrackSample] = {}
        for track in clip.tracks:
            track_id = int(track.track)
            if not _is_camera_track_id(track_id) or not track.samples:
                continue
            frame_start = int(frame)
            frame_end = min(frame_start + 1, len(track.samples) - 1)
            start_value = track.samples[frame_start]
            end_value = track.samples[frame_end]
            values[track_id] = _interpolate_values(
                start_value,
                end_value,
                frame - frame_start,
            )

        def scalar(track: YcdAnimationTrack) -> float | None:
            value = values.get(int(track))
            return float(value) if isinstance(value, float) else None

        def vector3(
            track: YcdAnimationTrack,
        ) -> Vector3 | None:
            value = values.get(int(track))
            return value if isinstance(value, Vector3) else None

        rotation = values.get(int(YcdAnimationTrack.CAMERA_ROTATION))

        return YcdCameraAnimationSample(
            position=vector3(YcdAnimationTrack.CAMERA_TRANSLATION),
            rotation=rotation if isinstance(rotation, Quaternion) else None,
            field_of_view=scalar(YcdAnimationTrack.CAMERA_FIELD_OF_VIEW),
            depth_of_field=vector3(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD),
            depth_of_field_strength=scalar(
                YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH
            ),
            motion_blur=scalar(YcdAnimationTrack.CAMERA_MOTION_BLUR),
            coc=scalar(YcdAnimationTrack.CAMERA_COC),
            focus=scalar(YcdAnimationTrack.CAMERA_FOCUS),
            night_coc=scalar(YcdAnimationTrack.CAMERA_NIGHT_COC),
            near_out_of_focus_plane=scalar(
                YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE
            ),
            near_in_focus_plane=scalar(
                YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE
            ),
            far_out_of_focus_plane=scalar(
                YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE
            ),
            far_in_focus_plane=scalar(
                YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE
            ),
        )

    def track(
        self,
        name: str,
        *,
        track: int | YcdAnimationTrack,
        samples: object,
        bone_id: int = 0,
        format: int | YcdTrackFormat | None = None,
        channel_policy: YcdChannelEncodingPolicy | None = None,
    ) -> YcdCutsceneBuilder:
        if channel_policy is not None and not isinstance(
            channel_policy, YcdChannelEncodingPolicy
        ):
            raise TypeError("channel_policy must be a YcdChannelEncodingPolicy")
        track_value = int(track)
        track_format = (
            get_ycd_track_format(track_value)
            if format is None
            else YcdTrackFormat(int(format))
        )
        clip = self._get_or_create_clip(name)
        if any(
            existing.track == track_value and existing.bone_id == int(bone_id)
            for existing in clip.tracks
        ):
            raise ValueError(
                f"Clip '{name}' already has track {track_value} for bone_id {bone_id}"
            )
        clip.tracks.append(
            YcdCutsceneTrack(
                track=track_value,
                bone_id=int(bone_id),
                format=track_format,
                samples=_sample_track_values(
                    samples,
                    track_format=track_format,
                    frame_count=self.total_frames,
                    fps=self.fps,
                ),
                channel_policy=channel_policy,
            )
        )
        return self

    def camera(
        self,
        name: str = "exportcamera",
        *,
        position: Vector3 | Mapping[float, Vector3] | Sequence[Vector3] | None = None,
        rotation: Quaternion | Mapping[float, Quaternion] | Sequence[Quaternion] | None = None,
        field_of_view: object | None = None,
        depth_of_field: object | None = None,
        depth_of_field_strength: object | None = None,
        motion_blur: object | None = None,
        coc: object | None = None,
        focus: object | None = None,
        night_coc: object | None = None,
        near_out_of_focus_plane: object | None = None,
        near_in_focus_plane: object | None = None,
        far_out_of_focus_plane: object | None = None,
        far_in_focus_plane: object | None = None,
    ) -> YcdCutsceneBuilder:
        track_map = {
            YcdAnimationTrack.CAMERA_TRANSLATION: position,
            YcdAnimationTrack.CAMERA_ROTATION: rotation,
            YcdAnimationTrack.CAMERA_FIELD_OF_VIEW: field_of_view,
            YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD: depth_of_field,
            YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH: depth_of_field_strength,
            YcdAnimationTrack.CAMERA_MOTION_BLUR: motion_blur,
            YcdAnimationTrack.CAMERA_COC: coc,
            YcdAnimationTrack.CAMERA_FOCUS: focus,
            YcdAnimationTrack.CAMERA_NIGHT_COC: night_coc,
            YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE: near_out_of_focus_plane,
            YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE: near_in_focus_plane,
            YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE: far_out_of_focus_plane,
            YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE: far_in_focus_plane,
        }
        for track, samples in track_map.items():
            if samples is not None:
                self.track(name, track=track, samples=samples, bone_id=0)
        return self

    def object(
        self,
        name: str,
        *,
        position: Vector3 | Mapping[float, Vector3] | Sequence[Vector3] | None = None,
        rotation: Quaternion | Mapping[float, Quaternion] | Sequence[Quaternion] | None = None,
        mover_position: Vector3 | Mapping[float, Vector3] | Sequence[Vector3] | None = None,
        mover_rotation: Quaternion | Mapping[float, Quaternion] | Sequence[Quaternion] | None = None,
        bone_id: int = 0,
        bones: Mapping[int, YcdCutsceneBoneAnimation | Mapping[str, object]]
        | None = None,
    ) -> YcdCutsceneBuilder:
        if bones:
            if mover_position is None:
                mover_position = Vector3()
            if mover_rotation is None:
                mover_rotation = Quaternion()
        track_map = {
            YcdAnimationTrack.BONE_TRANSLATION: position,
            YcdAnimationTrack.BONE_ROTATION: rotation,
            YcdAnimationTrack.MOVER_TRANSLATION: mover_position,
            YcdAnimationTrack.MOVER_ROTATION: mover_rotation,
        }
        for track, samples in track_map.items():
            if samples is not None:
                self.track(name, track=track, samples=samples, bone_id=bone_id)
        if bones:
            for current_bone_id, animation in bones.items():
                bone_animation = _coerce_bone_animation(animation)
                self.bone_animation(
                    name,
                    bone_id=int(current_bone_id),
                    position=bone_animation.position,
                    rotation=bone_animation.rotation,
                )
        return self

    def prop(self, name: str, **kwargs: object) -> YcdCutsceneBuilder:
        return self.object(name, **kwargs)

    def ped(
        self,
        name: str,
        *,
        facial: YcdFacialTrackSet | None = None,
        **kwargs: object,
    ) -> YcdCutsceneBuilder:
        clip_name = self.combined_facial_clip_name(name) if facial is not None else name
        self.object(clip_name, **kwargs)
        if facial is not None:
            self.facial_animation(clip_name, facial, merged=False)
        return self

    @staticmethod
    def combined_facial_clip_name(name: str) -> str:
        value = str(name)
        return value if value.endswith("_dual") else f"{value}_dual"

    @staticmethod
    def _facial_samples(
        value: object | YcdFacialTrackSamples,
    ) -> tuple[object, int | YcdTrackFormat | None]:
        if isinstance(value, YcdFacialTrackSamples):
            return value.samples, value.format
        return value, None

    def facial_animation(
        self,
        name: str,
        facial: YcdFacialTrackSet,
        *,
        merged: bool = True,
    ) -> YcdCutsceneBuilder:
        target_name = self.combined_facial_clip_name(name) if merged else str(name)
        source_name = str(name)
        if target_name != source_name and source_name in self._clips:
            source = self._clips.pop(source_name)
            target = self._clips.get(target_name)
            if target is None:
                source.name = target_name
                self._clips[target_name] = source
            else:
                target.tracks.extend(source.tracks)

        mappings = (
            (YcdAnimationTrack.BLEND_SHAPE, facial.blend_shapes),
            (YcdAnimationTrack.VISEMES, facial.visemes),
            (YcdAnimationTrack.ANIMATED_NORMAL_MAPS, facial.animated_normal_maps),
            (YcdAnimationTrack.FACIAL_CONTROL, facial.controls),
            (YcdAnimationTrack.FACIAL_TRANSLATION, facial.translations),
            (YcdAnimationTrack.FACIAL_ROTATION, facial.rotations),
            (YcdAnimationTrack.FACIAL_SCALE, facial.scales),
        )
        for track, values in mappings:
            for control_id, value in values.items():
                samples, format = self._facial_samples(value)
                self.track(
                    target_name,
                    track=track,
                    samples=samples,
                    bone_id=int(control_id),
                    format=format,
                )
        if facial.tinting is not None:
            samples, format = self._facial_samples(facial.tinting)
            self.track(
                target_name,
                track=YcdAnimationTrack.FACIAL_TINTING,
                samples=samples,
                bone_id=0,
                format=format,
            )
        return self

    def vehicle(self, name: str, **kwargs: object) -> YcdCutsceneBuilder:
        return self.object(name, **kwargs)

    def bone_animation(
        self,
        name: str,
        *,
        bone_id: int,
        position: Vector3 | Mapping[float, Vector3] | Sequence[Vector3] | None = None,
        rotation: Quaternion | Mapping[float, Quaternion] | Sequence[Quaternion] | None = None,
    ) -> YcdCutsceneBuilder:
        if position is not None:
            self.track(
                name,
                track=YcdAnimationTrack.BONE_TRANSLATION,
                samples=position,
                bone_id=bone_id,
            )
        if rotation is not None:
            self.track(
                name,
                track=YcdAnimationTrack.BONE_ROTATION,
                samples=rotation,
                bone_id=bone_id,
            )
        return self

    def _build_section(self, index: int) -> Ycd:
        section = self.sections[int(index)]
        output_index = self.section_index_start + section.index
        clips: list[YcdClipAnimation] = []
        animations: list[YcdAnimation] = []
        for clip_spec in self._clips.values():
            if not clip_spec.tracks:
                continue
            short_name = f"{clip_spec.name}-{output_index}"
            animation_hash = MetaHash(short_name)
            bone_ids: list[YcdAnimationBoneId] = []
            track_windows: list[
                tuple[YcdCutsceneTrack, list[tuple[int, list[YcdTrackSample]]]]
            ] = []
            sequence_limit = min(
                YCD_CUTSCENE_SEQUENCE_FRAME_LIMIT,
                max(section.frame_count, 1),
            )
            sample_frame_limit = sequence_limit
            uses_camera_tracks = any(
                _is_camera_track_id(track_spec.track) for track_spec in clip_spec.tracks
            )
            sorted_tracks = list(clip_spec.tracks)
            if not uses_camera_tracks:
                # GTA cutscene YCDs group object tracks by semantic track id,
                # then by bone id. The runtime is stricter than the parser here.
                sorted_tracks.sort(key=_cutscene_track_sort_key)
            for track_spec in sorted_tracks:
                frame_samples = track_spec.samples[
                    section.start_frame : section.end_frame + 1
                ]
                if not frame_samples:
                    continue
                bone = YcdAnimationBoneId(
                    bone_id=track_spec.bone_id,
                    track=track_spec.track,
                    format=track_spec.format,
                )
                bone_ids.append(bone)
                track_windows.append(
                    (
                        track_spec,
                        _iter_sequence_sample_windows(
                            frame_samples, frame_limit=sample_frame_limit
                        ),
                    )
                )
            if not track_windows:
                continue
            sequence_count = max(
                (len(windows) for _, windows in track_windows), default=0
            )
            sequences: list[YcdSequence] = []
            for sequence_index in range(sequence_count):
                anim_sequences: list[YcdAnimSequence] = []
                sequence_frame_count = 0
                for track_index, (_track_spec, windows) in enumerate(track_windows):
                    if sequence_index >= len(windows):
                        continue
                    _start_frame, frame_samples = windows[sequence_index]
                    sequence_frame_count = max(sequence_frame_count, len(frame_samples))
                    anim_sequences.append(
                        YcdAnimSequence(
                            bone_id=bone_ids[track_index],
                            channels=_make_channels(
                                frame_samples,
                                track=_track_spec.track,
                                quaternion_encoding=self.quaternion_encoding,
                                channel_encoding=(
                                    _track_spec.channel_policy or self.channel_policy
                                ).encoding,
                            ),
                        )
                    )
                if not anim_sequences:
                    continue
                sequences.append(
                    YcdSequence(
                        hash=MetaHash(f"{short_name}_seq{sequence_index}"),
                        data_length=0,
                        frame_offset=0,
                        root_motion_refs_offset=0,
                        num_frames=sequence_frame_count,
                        frame_length=0,
                        indirect_quantize_float_num_ints=0,
                        quantize_float_value_bits=0,
                        chunk_size=0,
                        root_motion_ref_counts=0,
                        raw_data=b"",
                        anim_sequences=anim_sequences,
                    )
                )
            if not sequences:
                continue
            animation = YcdAnimation(
                hash=animation_hash,
                frames=section.frame_count,
                sequence_frame_limit=sequence_limit,
                duration=section.duration,
                usage_count=1,
                sequence_count=len(sequences),
                bone_id_count=len(bone_ids),
                sequences=sequences,
                bone_ids=bone_ids,
            )
            animations.append(animation)
            clips.append(
                YcdClipAnimation(
                    hash=MetaHash(short_name),
                    name=short_name,
                    short_name=short_name,
                    clip_type=YcdClipType.ANIMATION,
                    animation_hash=animation.hash,
                    start_time=0.0,
                    end_time=section.duration,
                    rate=1.0,
                    animation=animation,
                )
            )

        ycd = Ycd(
            header=ResourceHeader(
                version=self.version, system_flags=0, graphics_flags=0
            ),
            clips=clips,
            animations=animations,
            game=self.game,
            path=f"{self.name}-{output_index}.ycd",
        )
        return ycd.build()

    def _validate_section_precision(
        self, section: YcdCutsceneSection, report: ValidationReport
    ) -> None:
        from .channel_validation import validate_cutscene_section_precision

        validate_cutscene_section_precision(self, section, report)

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        del context
        report = ValidationReport()
        for section in self.sections:
            self._validate_section_precision(section, report)
        return report

    def build_section(self, index: int) -> Ycd:
        section = self.sections[int(index)]
        report = ValidationReport()
        self._validate_section_precision(section, report)
        report.raise_for_errors()
        return self._build_section(section.index)

    def build_ycds(self) -> list[Ycd]:
        if not self._clips:
            return []
        self.validate().raise_for_errors()
        return [self._build_section(section.index) for section in self.sections]

    def save(self, directory: str | Path) -> list[Path]:
        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for ycd in self.build_ycds():
            path = target_dir / (ycd.path or f"{self.name}.ycd")
            ycd.save(path)
            saved.append(path)
        return saved


def build_cutscene_sections(
    duration: float,
    camera_cuts: Sequence[float] | None = None,
    *,
    fps: float = YCD_CUTSCENE_DEFAULT_FPS,
) -> list[YcdCutsceneSection]:
    return YcdCutsceneBuilder(
        "cutscene", duration=duration, camera_cuts=camera_cuts or [], fps=fps
    ).sections


def build_cutscene_ycds(
    name: str,
    *,
    duration: float,
    camera_cuts: Sequence[float] | None = None,
    fps: float = YCD_CUTSCENE_DEFAULT_FPS,
    version: int = YCD_CUTSCENE_DEFAULT_VERSION,
    game: str | GameTarget = GameTarget.GTA5,
    quaternion_encoding: YcdQuaternionEncoding = YcdQuaternionEncoding.RETAIL_CACHED,
    channel_policy: YcdChannelEncodingPolicy = _DEFAULT_CHANNEL_POLICY,
) -> YcdCutsceneBuilder:
    return YcdCutsceneBuilder(
        name,
        duration=duration,
        camera_cuts=camera_cuts,
        fps=fps,
        version=version,
        game=game,
        quaternion_encoding=quaternion_encoding,
        channel_policy=channel_policy,
    )


__all__ = [
    "YCD_CUTSCENE_DEFAULT_FPS",
    "YCD_CUTSCENE_DEFAULT_VERSION",
    "YCD_CUTSCENE_SEQUENCE_FRAME_LIMIT",
    "YcdChannelEncoding",
    "YcdChannelEncodingPolicy",
    "YcdCutsceneBoneAnimation",
    "YcdCutsceneBuilder",
    "YcdCutsceneClip",
    "YcdCutsceneSection",
    "YcdCutsceneTrack",
    "YcdFacialTrackSamples",
    "YcdFacialTrackSet",
    "YcdQuaternionEncoding",
    "build_cutscene_sections",
    "build_cutscene_ycds",
]
