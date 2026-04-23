from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from ..cut import CutFile, CutScene, read_cut, read_cut_scene
from ..metahash import MetaHash
from ..resource import ResourceHeader
from .model import Ycd, YcdAnimation, YcdAnimationBoneId, YcdClipAnimation, YcdClipType, YcdSequence
from .sequence_channels import YcdAnimSequence, YcdChannelType, YcdRawFloatChannel, YcdStaticFloatChannel
from .sequence_tracks import YcdAnimationTrack, get_ycd_track_format


YCD_CUTSCENE_DEFAULT_FPS = 30.0
YCD_CUTSCENE_DEFAULT_VERSION = 46

_SCALAR_TRACKS = {
    int(YcdAnimationTrack.CAMERA_FIELD_OF_VIEW),
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

_VECTOR3_TRACKS = {
    int(YcdAnimationTrack.BONE_TRANSLATION),
    int(YcdAnimationTrack.MOVER_TRANSLATION),
    int(YcdAnimationTrack.CAMERA_TRANSLATION),
    int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD),
}

_QUATERNION_TRACKS = {
    int(YcdAnimationTrack.BONE_ROTATION),
    int(YcdAnimationTrack.MOVER_ROTATION),
    int(YcdAnimationTrack.CAMERA_ROTATION),
}


def _lerp(a: float, b: float, alpha: float) -> float:
    return float(a + ((b - a) * alpha))


def _lerp_tuple(a: tuple[float, ...], b: tuple[float, ...], alpha: float) -> tuple[float, ...]:
    return tuple(_lerp(va, vb, alpha) for va, vb in zip(a, b, strict=True))


def _normalize_quaternion(value: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x, y, z, w = (float(component) for component in value)
    length = (x * x) + (y * y) + (z * z) + (w * w)
    if length <= 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    scale = length ** -0.5
    return (x * scale, y * scale, z * scale, w * scale)


def _nlerp_quaternion(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    alpha: float,
) -> tuple[float, float, float, float]:
    ax, ay, az, aw = _normalize_quaternion(a)
    bx, by, bz, bw = _normalize_quaternion(b)
    dot = (ax * bx) + (ay * by) + (az * bz) + (aw * bw)
    if dot < 0.0:
        bx, by, bz, bw = -bx, -by, -bz, -bw
    return _normalize_quaternion(
        (
            _lerp(ax, bx, alpha),
            _lerp(ay, by, alpha),
            _lerp(az, bz, alpha),
            _lerp(aw, bw, alpha),
        )
    )


def _track_component_count(track: int | YcdAnimationTrack) -> int:
    value = int(track)
    if value in _SCALAR_TRACKS:
        return 1
    if value in _VECTOR3_TRACKS:
        return 3
    if value in _QUATERNION_TRACKS:
        return 4
    raise ValueError(f"Unsupported cutscene YCD track {value}")


def _coerce_tuple(value: object, component_count: int) -> tuple[float, ...]:
    if component_count == 1:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if len(value) != 1:
                raise ValueError(f"Expected 1 component, got {len(value)}")
            return (float(value[0]),)
        return (float(value),)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"Expected {component_count} components, got scalar {value!r}")
    if len(value) != component_count:
        raise ValueError(f"Expected {component_count} components, got {len(value)}")
    result = tuple(float(component) for component in value)
    if component_count == 4:
        return _normalize_quaternion(result)  # type: ignore[arg-type]
    return result


def _interpolate_values(
    start: tuple[float, ...],
    end: tuple[float, ...],
    alpha: float,
    *,
    is_quaternion: bool,
) -> tuple[float, ...]:
    if is_quaternion:
        return _nlerp_quaternion(start, end, alpha)  # type: ignore[arg-type]
    return _lerp_tuple(start, end, alpha)


def _is_per_frame_sequence(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False
    if not value:
        return False
    first = value[0]
    return isinstance(first, Mapping) or isinstance(first, Sequence) and not isinstance(first, (str, bytes, bytearray))


def _sample_track_values(
    source: object,
    *,
    component_count: int,
    frame_count: int,
    fps: float,
    is_quaternion: bool,
) -> list[tuple[float, ...]]:
    if frame_count <= 0:
        return []

    if isinstance(source, Mapping):
        if not source:
            raise ValueError("Keyframe mapping cannot be empty")
        keyed = []
        for key, value in source.items():
            frame = int(round(float(key) * fps))
            frame = min(max(frame, 0), frame_count - 1)
            keyed.append((frame, _coerce_tuple(value, component_count)))
        keyed.sort(key=lambda item: item[0])
        deduped: list[tuple[int, tuple[float, ...]]] = []
        for frame, value in keyed:
            if deduped and deduped[-1][0] == frame:
                deduped[-1] = (frame, value)
            else:
                deduped.append((frame, value))
        result = [deduped[0][1]] * frame_count
        if len(deduped) == 1:
            return list(result)
        for (start_frame, start_value), (end_frame, end_value) in zip(deduped, deduped[1:]):
            span = max(end_frame - start_frame, 1)
            for frame in range(start_frame, min(end_frame, frame_count - 1) + 1):
                alpha = float(frame - start_frame) / float(span)
                result[frame] = _interpolate_values(start_value, end_value, alpha, is_quaternion=is_quaternion)
        last_frame, last_value = deduped[-1]
        for frame in range(last_frame, frame_count):
            result[frame] = last_value
        return result

    if _is_per_frame_sequence(source):
        if len(source) != frame_count:  # type: ignore[arg-type]
            raise ValueError(f"Expected {frame_count} per-frame samples, got {len(source)}")  # type: ignore[arg-type]
        return [_coerce_tuple(item, component_count) for item in source]  # type: ignore[arg-type]

    constant = _coerce_tuple(source, component_count)
    return [constant for _ in range(frame_count)]


def _make_channels(samples: list[tuple[float, ...]]) -> list[YcdStaticFloatChannel | YcdRawFloatChannel]:
    if not samples:
        return []
    component_count = len(samples[0])
    channels: list[YcdStaticFloatChannel | YcdRawFloatChannel] = []
    for component_index in range(component_count):
        values = [float(sample[component_index]) for sample in samples]
        if all(abs(value - values[0]) <= 1e-9 for value in values[1:]):
            channels.append(
                YcdStaticFloatChannel(
                    channel_type=YcdChannelType.STATIC_FLOAT,
                    channel_index=component_index,
                    value=float(values[0]),
                )
            )
            continue
        channels.append(
            YcdRawFloatChannel(
                channel_type=YcdChannelType.RAW_FLOAT,
                channel_index=component_index,
                values=values,
            )
        )
    return channels


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
    samples: list[tuple[float, ...]]


@dataclass(slots=True)
class YcdCutsceneBoneAnimation:
    position: object | None = None
    rotation: object | None = None


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
        fps: float = YCD_CUTSCENE_DEFAULT_FPS,
        version: int = YCD_CUTSCENE_DEFAULT_VERSION,
    ) -> None:
        self.name = str(name)
        self.duration = float(duration)
        self.fps = float(fps)
        self.version = int(version)
        self.camera_cuts = self._normalize_camera_cuts(camera_cuts or [])
        self._clips: dict[str, YcdCutsceneClip] = {}

    @classmethod
    def create(
        cls,
        name: str,
        *,
        duration: float,
        camera_cuts: Sequence[float] | None = None,
        fps: float = YCD_CUTSCENE_DEFAULT_FPS,
        version: int = YCD_CUTSCENE_DEFAULT_VERSION,
    ) -> YcdCutsceneBuilder:
        return cls(name, duration=duration, camera_cuts=camera_cuts, fps=fps, version=version)

    @classmethod
    def from_cut(
        cls,
        source: str | Path | CutFile | CutScene,
        *,
        name: str | None = None,
        fps: float = YCD_CUTSCENE_DEFAULT_FPS,
        version: int = YCD_CUTSCENE_DEFAULT_VERSION,
    ) -> YcdCutsceneBuilder:
        if isinstance(source, CutScene):
            resolved_name = name or "cutscene"
            camera_cuts = [event.start for event in source.timeline if event.event_name == "camera_cut" and event.start > 0.0]
            return cls(resolved_name, duration=source.duration, camera_cuts=camera_cuts, fps=fps, version=version)

        if isinstance(source, CutFile):
            cut = source
            source_name = name or Path(getattr(cut, "path", "") or "cutscene").stem or "cutscene"
        else:
            source_path = Path(source)
            source_name = name or source_path.stem
            cut = read_cut(source_path)

        root = cut.root
        duration = float(root.fields.get("fTotalDuration", 0.0))
        camera_cuts = [float(value) for value in root.fields.get("cameraCutList", []) if float(value) > 0.0]
        return cls(source_name, duration=duration, camera_cuts=camera_cuts, fps=fps, version=version)

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
        return max(int(round(self.duration * self.fps)) + 1, 1)

    @property
    def sections(self) -> list[YcdCutsceneSection]:
        boundaries = [0.0, *self.camera_cuts, self.duration]
        sections: list[YcdCutsceneSection] = []
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            start_frame = int(round(start * self.fps))
            end_frame = int(round(end * self.fps))
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

    def add_track(
        self,
        name: str,
        *,
        track: int | YcdAnimationTrack,
        samples: object,
        bone_id: int = 0,
    ) -> YcdCutsceneBuilder:
        track_value = int(track)
        component_count = _track_component_count(track_value)
        clip = self._get_or_create_clip(name)
        if any(existing.track == track_value and existing.bone_id == int(bone_id) for existing in clip.tracks):
            raise ValueError(f"Clip '{name}' already has track {track_value} for bone_id {bone_id}")
        clip.tracks.append(
            YcdCutsceneTrack(
                track=track_value,
                bone_id=int(bone_id),
                samples=_sample_track_values(
                    samples,
                    component_count=component_count,
                    frame_count=self.total_frames,
                    fps=self.fps,
                    is_quaternion=component_count == 4,
                ),
            )
        )
        return self

    def add_camera(
        self,
        name: str = "exportcamera",
        *,
        position: object | None = None,
        rotation: object | None = None,
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
                self.add_track(name, track=track, samples=samples, bone_id=0)
        return self

    def add_object(
        self,
        name: str,
        *,
        position: object | None = None,
        rotation: object | None = None,
        mover_position: object | None = None,
        mover_rotation: object | None = None,
        bone_id: int = 0,
        bones: Mapping[int, YcdCutsceneBoneAnimation | Mapping[str, object]] | None = None,
    ) -> YcdCutsceneBuilder:
        track_map = {
            YcdAnimationTrack.BONE_TRANSLATION: position,
            YcdAnimationTrack.BONE_ROTATION: rotation,
            YcdAnimationTrack.MOVER_TRANSLATION: mover_position,
            YcdAnimationTrack.MOVER_ROTATION: mover_rotation,
        }
        for track, samples in track_map.items():
            if samples is not None:
                self.add_track(name, track=track, samples=samples, bone_id=bone_id)
        if bones:
            for current_bone_id, animation in bones.items():
                bone_animation = _coerce_bone_animation(animation)
                self.add_bone_animation(
                    name,
                    bone_id=int(current_bone_id),
                    position=bone_animation.position,
                    rotation=bone_animation.rotation,
                )
        return self

    def add_prop(self, name: str, **kwargs: object) -> YcdCutsceneBuilder:
        return self.add_object(name, **kwargs)

    def add_ped(self, name: str, **kwargs: object) -> YcdCutsceneBuilder:
        return self.add_object(name, **kwargs)

    def add_vehicle(self, name: str, **kwargs: object) -> YcdCutsceneBuilder:
        return self.add_object(name, **kwargs)

    def add_bone_animation(
        self,
        name: str,
        *,
        bone_id: int,
        position: object | None = None,
        rotation: object | None = None,
    ) -> YcdCutsceneBuilder:
        if position is not None:
            self.add_track(name, track=YcdAnimationTrack.BONE_TRANSLATION, samples=position, bone_id=bone_id)
        if rotation is not None:
            self.add_track(name, track=YcdAnimationTrack.BONE_ROTATION, samples=rotation, bone_id=bone_id)
        return self

    def build_section(self, index: int) -> Ycd:
        section = self.sections[int(index)]
        clips: list[YcdClipAnimation] = []
        animations: list[YcdAnimation] = []
        for clip_spec in self._clips.values():
            if not clip_spec.tracks:
                continue
            short_name = f"{clip_spec.name}-{section.index}"
            animation_hash = MetaHash(short_name)
            anim_sequences: list[YcdAnimSequence] = []
            bone_ids: list[YcdAnimationBoneId] = []
            for track_spec in clip_spec.tracks:
                frame_samples = track_spec.samples[section.start_frame : section.end_frame + 1]
                if not frame_samples:
                    continue
                bone = YcdAnimationBoneId(bone_id=track_spec.bone_id, track=track_spec.track, format=get_ycd_track_format(track_spec.track))
                bone_ids.append(bone)
                anim_sequences.append(
                    YcdAnimSequence(
                        bone_id=bone,
                        channels=_make_channels(frame_samples),
                    )
                )
            if not anim_sequences:
                continue
            animation = YcdAnimation(
                hash=animation_hash,
                frames=section.frame_count,
                sequence_frame_limit=section.frame_count,
                duration=section.duration,
                usage_count=1,
                sequence_count=1,
                bone_id_count=len(bone_ids),
                sequences=[
                    YcdSequence(
                        hash=MetaHash(f"{short_name}_seq"),
                        data_length=0,
                        frame_offset=0,
                        root_motion_refs_offset=0,
                        num_frames=section.frame_count,
                        frame_length=0,
                        indirect_quantize_float_num_ints=0,
                        quantize_float_value_bits=0,
                        chunk_size=0,
                        root_motion_ref_counts=0,
                        raw_data=b"",
                        anim_sequences=anim_sequences,
                    )
                ],
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
            header=ResourceHeader(version=self.version, system_flags=0, graphics_flags=0),
            clips=clips,
            animations=animations,
            path=f"{self.name}-{section.index}.ycd",
        )
        return ycd.build()

    def build_ycds(self) -> list[Ycd]:
        if not self._clips:
            return []
        return [self.build_section(section.index) for section in self.sections]

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
    return YcdCutsceneBuilder("cutscene", duration=duration, camera_cuts=camera_cuts or [], fps=fps).sections


def build_cutscene_ycds(
    name: str,
    *,
    duration: float,
    camera_cuts: Sequence[float] | None = None,
    fps: float = YCD_CUTSCENE_DEFAULT_FPS,
    version: int = YCD_CUTSCENE_DEFAULT_VERSION,
) -> YcdCutsceneBuilder:
    return YcdCutsceneBuilder(name, duration=duration, camera_cuts=camera_cuts, fps=fps, version=version)


__all__ = [
    "YCD_CUTSCENE_DEFAULT_FPS",
    "YCD_CUTSCENE_DEFAULT_VERSION",
    "YcdCutsceneBoneAnimation",
    "YcdCutsceneBuilder",
    "YcdCutsceneClip",
    "YcdCutsceneSection",
    "YcdCutsceneTrack",
    "build_cutscene_sections",
    "build_cutscene_ycds",
]
