from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
import math

from ..metahash import MetaHash
from ..resource import ResourceHeader
from .sequences import (
    YcdAnimSequence,
    YcdAnimationTrack,
    YcdCachedQuaternionChannel,
    YcdChannelType,
    YcdSequenceRootChannelRef,
    YcdTrackFormat,
    get_ycd_track_format,
    is_ycd_camera_track,
    is_ycd_facial_track,
    get_ycd_track_name,
    is_ycd_object_track,
    is_ycd_position_track,
    is_ycd_rotation_track,
    is_ycd_root_motion_track,
    is_ycd_uv_track,
)


YCD_UV_CLIP_MARKER = "_uv_"
YCD_UV_UNKNOWN1C = 0x6B002400


def _normalize_ycd_clip_name(value: str) -> str:
    normalized = str(value or "").replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    return normalized.lower()


def build_ycd_uv_clip_name(object_name: str, slot_index: int) -> str:
    base_name = _normalize_ycd_clip_name(object_name)
    if not base_name:
        raise ValueError("YCD UV clip object_name cannot be empty")
    slot = int(slot_index)
    if slot < 0:
        raise ValueError("YCD UV clip slot_index cannot be negative")
    return f"{base_name}{YCD_UV_CLIP_MARKER}{slot}"


def build_ycd_uv_clip_hash(object_name: str, slot_index: int) -> MetaHash:
    slot = int(slot_index)
    if slot < 0:
        raise ValueError("YCD UV clip slot_index cannot be negative")
    return MetaHash((MetaHash(_normalize_ycd_clip_name(object_name)).uint + slot + 1) & 0xFFFFFFFF)


@dataclass(slots=True)
class YcdUvClipBinding:
    object_name: str
    slot_index: int

    @property
    def clip_name(self) -> str:
        return build_ycd_uv_clip_name(self.object_name, self.slot_index)

    @property
    def clip_hash(self) -> MetaHash:
        return build_ycd_uv_clip_hash(self.object_name, self.slot_index)


def parse_ycd_uv_clip_binding(value: str | None) -> YcdUvClipBinding | None:
    normalized = _normalize_ycd_clip_name(str(value or ""))
    if not normalized:
        return None
    base, separator, suffix = normalized.rpartition(YCD_UV_CLIP_MARKER)
    if not separator or not suffix.isdigit():
        return None
    return YcdUvClipBinding(object_name=base, slot_index=int(suffix))


def _ycd_hash_candidates(value: int | str | MetaHash) -> tuple[int, ...]:
    if isinstance(value, MetaHash):
        return (value.uint,)
    if isinstance(value, int):
        return (int(value),)

    text = str(value)
    candidates = [MetaHash(text).uint]
    binding = parse_ycd_uv_clip_binding(text)
    if binding is not None:
        candidates.append(binding.clip_hash.uint)
    return tuple(dict.fromkeys(candidates))


class YcdClipType(IntEnum):
    ANIMATION = 1
    ANIMATION_LIST = 2


class YcdClipPropertyAttributeType(IntEnum):
    FLOAT = 1
    INT = 2
    BOOL = 3
    STRING = 4
    VECTOR3 = 6
    VECTOR4 = 8
    HASH_STRING = 12


@dataclass(slots=True)
class YcdAnimationBoneId:
    bone_id: int
    track: int
    format: int | YcdTrackFormat | None = None

    def __post_init__(self) -> None:
        self.bone_id = int(self.bone_id)
        self.track = int(self.track)
        if self.format is None:
            self.format = get_ycd_track_format(self.track)
        else:
            self.format = YcdTrackFormat(int(self.format))

    @property
    def track_name(self) -> str:
        return get_ycd_track_name(self.track)

    @property
    def format_name(self) -> str:
        return YcdTrackFormat(int(self.format)).name

    @property
    def is_uv_track(self) -> bool:
        return is_ycd_uv_track(self.track)

    @property
    def is_object_track(self) -> bool:
        return is_ycd_object_track(self.track)

    @property
    def is_camera_track(self) -> bool:
        return is_ycd_camera_track(self.track)

    @property
    def is_root_motion_track(self) -> bool:
        return is_ycd_root_motion_track(self.track)

    @property
    def is_facial_track(self) -> bool:
        return is_ycd_facial_track(self.track)

    @property
    def is_position_track(self) -> bool:
        return is_ycd_position_track(self.track)

    @property
    def is_rotation_track(self) -> bool:
        return is_ycd_rotation_track(self.track)


@dataclass(slots=True)
class YcdSequence:
    hash: MetaHash
    data_length: int
    frame_offset: int
    root_motion_refs_offset: int
    num_frames: int
    frame_length: int
    indirect_quantize_float_num_ints: int
    quantize_float_value_bits: int
    chunk_size: int
    root_motion_ref_counts: int
    raw_data: bytes
    vft: int = 0
    unused_08h: int = 0
    unused_14h: int = 0
    anim_sequences: list[YcdAnimSequence] = field(default_factory=list)
    root_position_refs: list[YcdSequenceRootChannelRef] = field(default_factory=list)
    root_rotation_refs: list[YcdSequenceRootChannelRef] = field(default_factory=list)

    @property
    def root_position_ref_count(self) -> int:
        return (int(self.root_motion_ref_counts) >> 4) & 0xF

    @property
    def root_rotation_ref_count(self) -> int:
        return int(self.root_motion_ref_counts) & 0xF

    def get_anim_sequence(self, index: int) -> YcdAnimSequence | None:
        index = int(index)
        if index < 0 or index >= len(self.anim_sequences):
            return None
        return self.anim_sequences[index]

    @property
    def has_root_motion(self) -> bool:
        return bool(self.root_position_refs or self.root_rotation_refs)


@dataclass(slots=True)
class YcdFramePosition:
    frame0: int
    frame1: int
    alpha0: float
    alpha1: float


@dataclass(slots=True)
class YcdTransformSample:
    position: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float, float] | None = None
    scale: float | None = None


@dataclass(slots=True)
class YcdUvTransformSample:
    uv0: tuple[float, float, float] | None = None
    uv1: tuple[float, float, float] | None = None

    @property
    def slide_u(self) -> tuple[float, float, float] | None:
        return self.uv0

    @property
    def slide_v(self) -> tuple[float, float, float] | None:
        return self.uv1


YcdUvAnimationSample = YcdUvTransformSample


@dataclass(slots=True)
class YcdFacialAnimationSample:
    control: float | None = None
    translation: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float, float] | None = None


@dataclass(slots=True)
class YcdCameraAnimationSample:
    position: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float, float] | None = None
    field_of_view: float | None = None
    depth_of_field: tuple[float, float, float] | None = None
    depth_of_field_strength: float | None = None
    motion_blur: float | None = None
    coc: float | None = None
    focus: float | None = None
    night_coc: float | None = None
    near_out_of_focus_plane: float | None = None
    near_in_focus_plane: float | None = None
    far_out_of_focus_plane: float | None = None
    far_in_focus_plane: float | None = None
    tracks: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)


@dataclass(slots=True)
class YcdAnimation:
    hash: MetaHash
    frames: int
    sequence_frame_limit: int
    duration: float
    usage_count: int
    sequence_count: int
    bone_id_count: int
    vft: int = 0
    flags: int = 0
    max_seq_block_length: int = 0
    raw_unknown_hash: MetaHash = field(default_factory=MetaHash)
    sequences: list[YcdSequence] = field(default_factory=list)
    bone_ids: list[YcdAnimationBoneId] = field(default_factory=list)

    @property
    def name(self) -> str | None:
        return self.hash.text

    def find_bone(self, bone_id: int, track: int | None = None) -> YcdAnimationBoneId | None:
        for item in self.bone_ids:
            if item.bone_id != int(bone_id):
                continue
            if track is not None and item.track != int(track):
                continue
            return item
        return None

    def find_sequences(self, *, bone_id: int | None = None, track: int | YcdAnimationTrack | None = None) -> list[YcdAnimSequence]:
        result: list[YcdAnimSequence] = []
        track_value = None if track is None else int(track)
        bone_value = None if bone_id is None else int(bone_id)
        for sequence in self.sequences:
            for anim_sequence in sequence.anim_sequences:
                current_bone = getattr(anim_sequence, "bone_id", None)
                if current_bone is None:
                    continue
                if bone_value is not None and int(current_bone.bone_id) != bone_value:
                    continue
                if track_value is not None and int(current_bone.track) != track_value:
                    continue
                result.append(anim_sequence)
        return result

    def normalize_channel_layout(self) -> YcdAnimation:
        for sequence in self.sequences:
            for anim_sequence_index, anim_sequence in enumerate(sequence.anim_sequences):
                next_channel_index = 0
                for channel in anim_sequence.channels:
                    channel.sequence_index = anim_sequence_index
                    if isinstance(channel, YcdCachedQuaternionChannel):
                        channel.channel_index = 3 if channel.channel_type is YcdChannelType.CACHED_QUATERNION1 else 4
                        channel.parent_sequence = anim_sequence
                        continue
                    channel.channel_index = next_channel_index
                    next_channel_index += int(channel.component_count)
        return self

    def synchronize_bone_ids(self) -> YcdAnimation:
        expected_count = max((len(sequence.anim_sequences) for sequence in self.sequences), default=0)
        if expected_count <= 0:
            self.bone_ids = []
            self.bone_id_count = 0
            self.sequence_count = len(self.sequences)
            return self

        resolved_bone_ids: list[YcdAnimationBoneId] = []
        existing_bone_ids = list(self.bone_ids)

        for index in range(expected_count):
            resolved = existing_bone_ids[index] if index < len(existing_bone_ids) else None
            for sequence in self.sequences:
                if index >= len(sequence.anim_sequences):
                    continue
                anim_sequence = sequence.anim_sequences[index]
                bone_id = anim_sequence.bone_id
                if bone_id is None:
                    if resolved is not None:
                        anim_sequence.bone_id = resolved
                    continue
                if resolved is None:
                    resolved = YcdAnimationBoneId(
                        bone_id=int(bone_id.bone_id),
                        track=int(bone_id.track),
                        format=int(bone_id.format),
                    )
                elif (
                    int(resolved.bone_id) != int(bone_id.bone_id)
                    or int(resolved.track) != int(bone_id.track)
                    or int(resolved.format) != int(bone_id.format)
                ):
                    raise ValueError(
                        f"YCD animation '{self.name or self.hash.uint:#x}' has inconsistent bone binding at sequence index {index}"
                    )
                anim_sequence.bone_id = resolved
            if resolved is None:
                raise ValueError(
                    f"YCD animation '{self.name or self.hash.uint:#x}' is missing bone binding metadata for sequence index {index}"
                )
            resolved_bone_ids.append(resolved)

        self.bone_ids = resolved_bone_ids
        for bone_id in self.bone_ids:
            bone_id.format = get_ycd_track_format(bone_id.track)
        self.bone_id_count = len(resolved_bone_ids)
        self.sequence_count = len(self.sequences)
        return self

    def prepare_for_export(self) -> YcdAnimation:
        self.normalize_channel_layout()
        self.synchronize_bone_ids()
        self.raw_unknown_hash = self._default_raw_unknown_hash()
        self.sequence_count = len(self.sequences)
        return self

    def _default_raw_unknown_hash(self) -> MetaHash:
        current = MetaHash(self.raw_unknown_hash)
        if current.uint != 0:
            return current

        tracks = {int(bone.track) for bone in self.bone_ids}
        if not tracks:
            return current
        if tracks.issubset({int(YcdAnimationTrack.SHADER_SLIDE_U), int(YcdAnimationTrack.SHADER_SLIDE_V)}):
            return MetaHash(YCD_UV_UNKNOWN1C)
        skeletal_tracks = {
            int(YcdAnimationTrack.BONE_TRANSLATION),
            int(YcdAnimationTrack.BONE_ROTATION),
            int(YcdAnimationTrack.MOVER_TRANSLATION),
            int(YcdAnimationTrack.MOVER_ROTATION),
            int(YcdAnimationTrack.FACIAL_CONTROL),
            int(YcdAnimationTrack.FACIAL_TRANSLATION),
            int(YcdAnimationTrack.FACIAL_ROTATION),
        }
        if tracks & {int(YcdAnimationTrack.BONE_TRANSLATION), int(YcdAnimationTrack.BONE_ROTATION)} and tracks.issubset(skeletal_tracks):
            return MetaHash((int(self.hash.uint) + 1) & 0xFFFFFFFF)
        return current

    @property
    def uv_sequences(self) -> list[YcdAnimSequence]:
        return [sequence for sequence in self.find_sequences() if sequence.is_uv_animation]

    @property
    def object_sequences(self) -> list[YcdAnimSequence]:
        return [sequence for sequence in self.find_sequences() if sequence.is_object_animation]

    @property
    def camera_sequences(self) -> list[YcdAnimSequence]:
        return [sequence for sequence in self.find_sequences() if getattr(sequence, "is_camera_animation", False)]

    @property
    def root_motion_sequences(self) -> list[YcdAnimSequence]:
        return [sequence for sequence in self.find_sequences() if getattr(sequence, "is_root_motion", False)]

    @property
    def facial_sequences(self) -> list[YcdAnimSequence]:
        return [sequence for sequence in self.find_sequences() if getattr(sequence, "is_facial_animation", False)]

    @property
    def has_uv_animation(self) -> bool:
        return bool(self.uv_sequences)

    @property
    def has_object_animation(self) -> bool:
        return bool(self.object_sequences)

    @property
    def has_camera_animation(self) -> bool:
        return bool(self.camera_sequences)

    @property
    def has_root_motion(self) -> bool:
        return bool(self.root_motion_sequences)

    @property
    def has_facial_animation(self) -> bool:
        return bool(self.facial_sequences)

    def get_sequence_block(self, frame: int) -> YcdSequence | None:
        if not self.sequences:
            return None
        frame_value = max(int(frame), 0)
        limit = max(int(self.sequence_frame_limit), 1)
        block_index = min(frame_value // limit, len(self.sequences) - 1)
        return self.sequences[block_index]

    def get_local_frame(self, frame: int) -> int:
        frame_value = max(int(frame), 0)
        limit = max(int(self.sequence_frame_limit), 1)
        return frame_value % limit

    def get_frame_position(self, frame: int | float) -> YcdFramePosition:
        frame_value = max(float(frame), 0.0)
        frame0 = int(math.floor(frame_value))
        if self.frames > 0:
            frame0 = min(frame0, max(self.frames - 1, 0))
        frame1 = frame0 + 1
        if self.frames > 0:
            frame1 = min(frame1, max(self.frames - 1, 0))
        alpha1 = float(frame_value - frame0)
        alpha0 = 1.0 - alpha1
        return YcdFramePosition(frame0=frame0, frame1=frame1, alpha0=alpha0, alpha1=alpha1)

    def evaluate_tracks(self, frame: int | float, *, track: int | YcdAnimationTrack | None = None, interpolate: bool = True) -> dict[tuple[int, int], tuple[float, float, float, float]]:
        if not interpolate or isinstance(frame, int):
            return self._evaluate_integer_tracks(int(frame), track=track)
        pos = self.get_frame_position(frame)
        values0 = self._evaluate_integer_tracks(pos.frame0, track=track)
        if pos.frame1 == pos.frame0 or pos.alpha1 <= 0.0:
            return values0
        values1 = self._evaluate_integer_tracks(pos.frame1, track=track)
        keys = set(values0) | set(values1)
        result: dict[tuple[int, int], tuple[float, float, float, float]] = {}
        for key in keys:
            v0 = values0.get(key, values1.get(key))
            v1 = values1.get(key, values0.get(key))
            if v0 is None or v1 is None:
                continue
            if is_ycd_rotation_track(key[1]):
                result[key] = _nlerp_vector4(v0, v1, pos.alpha1)
            else:
                result[key] = _lerp_vector4(v0, v1, pos.alpha1)
        return result

    def _evaluate_integer_tracks(self, frame: int, *, track: int | YcdAnimationTrack | None = None) -> dict[tuple[int, int], tuple[float, float, float, float]]:
        result: dict[tuple[int, int], tuple[float, float, float, float]] = {}
        sequence_block = self.get_sequence_block(frame)
        if sequence_block is None:
            return result
        local_frame = self.get_local_frame(frame)
        track_value = None if track is None else int(track)
        for sequence in sequence_block.anim_sequences:
            bone = sequence.bone_id
            if bone is None:
                continue
            if track_value is not None and int(bone.track) != track_value:
                continue
            result[(int(bone.bone_id), int(bone.track))] = sequence.evaluate_vector4(local_frame)
        return result

    def evaluate_uv_animation(self, frame: int) -> dict[tuple[int, int], tuple[float, float, float, float]]:
        return {
            key: value
            for key, value in self.evaluate_tracks(frame).items()
            if is_ycd_uv_track(key[1])
        }

    def evaluate_object_animation(self, frame: int | float) -> dict[tuple[int, int], tuple[float, float, float, float]]:
        return {
            key: value
            for key, value in self.evaluate_tracks(frame).items()
            if is_ycd_object_track(key[1])
        }

    def evaluate_root_motion(self, frame: int | float) -> YcdTransformSample:
        tracks = {
            key: value
            for key, value in self.evaluate_tracks(frame).items()
            if is_ycd_root_motion_track(key[1])
        }
        position = next((value[:3] for (_, track), value in tracks.items() if int(track) == int(YcdAnimationTrack.MOVER_TRANSLATION)), None)
        rotation = next((value for (_, track), value in tracks.items() if int(track) == int(YcdAnimationTrack.MOVER_ROTATION)), None)
        return YcdTransformSample(position=position, rotation=rotation)

    def evaluate_camera_animation(self, frame: int | float) -> YcdCameraAnimationSample:
        tracks = {
            key: value
            for key, value in self.evaluate_tracks(frame).items()
            if is_ycd_camera_track(key[1])
        }
        position = next((value[:3] for (_, track), value in tracks.items() if int(track) == int(YcdAnimationTrack.CAMERA_TRANSLATION)), None)
        rotation = next((value for (_, track), value in tracks.items() if int(track) == int(YcdAnimationTrack.CAMERA_ROTATION)), None)
        return YcdCameraAnimationSample(
            position=position,
            rotation=rotation,
            field_of_view=_track_scalar(tracks, YcdAnimationTrack.CAMERA_FIELD_OF_VIEW),
            depth_of_field=_track_vector3(tracks, YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD),
            depth_of_field_strength=_track_scalar(tracks, YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH),
            motion_blur=_track_scalar(tracks, YcdAnimationTrack.CAMERA_MOTION_BLUR),
            coc=_track_scalar(tracks, YcdAnimationTrack.CAMERA_COC),
            focus=_track_scalar(tracks, YcdAnimationTrack.CAMERA_FOCUS),
            night_coc=_track_scalar(tracks, YcdAnimationTrack.CAMERA_NIGHT_COC),
            near_out_of_focus_plane=_track_scalar(tracks, YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE),
            near_in_focus_plane=_track_scalar(tracks, YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE),
            far_out_of_focus_plane=_track_scalar(tracks, YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE),
            far_in_focus_plane=_track_scalar(tracks, YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE),
            tracks={int(track): value for (_, track), value in tracks.items()},
        )

    def evaluate_facial_animation(self, frame: int | float) -> dict[int, YcdFacialAnimationSample]:
        result: dict[int, YcdFacialAnimationSample] = {}
        tracks = {
            key: value
            for key, value in self.evaluate_tracks(frame).items()
            if is_ycd_facial_track(key[1])
        }
        for (bone_id, track), value in tracks.items():
            sample = result.setdefault(int(bone_id), YcdFacialAnimationSample())
            if int(track) == int(YcdAnimationTrack.FACIAL_CONTROL):
                sample.control = float(value[0])
            elif int(track) == int(YcdAnimationTrack.FACIAL_TRANSLATION):
                sample.translation = value[:3]
            elif int(track) == int(YcdAnimationTrack.FACIAL_ROTATION):
                sample.rotation = value
        return result

    def evaluate_uv_transform(self, frame: int | float) -> YcdUvTransformSample:
        tracks = self.evaluate_uv_animation(frame)
        uv0 = next((value[:3] for (_, track), value in tracks.items() if int(track) == int(YcdAnimationTrack.SHADER_SLIDE_U)), None)
        uv1 = next((value[:3] for (_, track), value in tracks.items() if int(track) == int(YcdAnimationTrack.SHADER_SLIDE_V)), None)
        return YcdUvTransformSample(uv0=uv0, uv1=uv1)


YcdClipPropertyValue = float | int | bool | str | tuple[float, ...] | MetaHash


@dataclass(slots=True)
class YcdClipPropertyAttribute:
    name_hash: MetaHash
    attribute_type: YcdClipPropertyAttributeType
    value: YcdClipPropertyValue
    vft: int = 0
    unknown_04h: int = 0
    unknown_09h: int = 0
    unknown_0ah: int = 0
    unknown_0ch: int = 0
    unknown_10h: int = 0
    unknown_14h: int = 0
    unknown_1ch: int = 0
    extra: float | int | None = None

    @property
    def name(self) -> str | None:
        return self.name_hash.text


@dataclass(slots=True)
class YcdClipProperty:
    name_hash: MetaHash
    attributes: list[YcdClipPropertyAttribute] = field(default_factory=list)
    vft: int = 0
    unknown_04h: int = 0
    unknown_08h: int = 0
    unknown_0ch: int = 0
    unknown_10h: int = 0
    unknown_14h: int = 0
    unknown_1ch: int = 0
    unknown_2ch: int = 0
    unknown_30h: int = 0
    unknown_34h: int = 0
    unknown_hash: MetaHash = field(default_factory=MetaHash)
    unknown_3ch: int = 0

    @property
    def name(self) -> str | None:
        return self.name_hash.text

    def get_attribute(self, value: int | str | MetaHash) -> YcdClipPropertyAttribute | None:
        key = MetaHash(value).uint
        for attribute in self.attributes:
            if attribute.name_hash.uint == key:
                return attribute
        return None


@dataclass(slots=True)
class YcdClipTag(YcdClipProperty):
    start_phase: float = 0.0
    end_phase: float = 0.0
    tags: list[YcdClipTag] = field(default_factory=list)
    has_block_tag: bool = False
    tag_list_reserved_0ch: int = 0
    tag_list_reserved_14h: int = 0
    tag_list_reserved_18h: int = 0
    tag_list_reserved_1ch: int = 0

    def get_tag(self, value: int | str | MetaHash) -> YcdClipTag | None:
        key = MetaHash(value).uint
        for tag in self.tags:
            if tag.name_hash.uint == key:
                return tag
        return None


@dataclass(slots=True)
class YcdClipAnimationEntry:
    start_time: float
    end_time: float
    rate: float
    animation_hash: MetaHash
    animation: YcdAnimation | None = None
    alignment_padding_0ch: int = 0

    @property
    def duration(self) -> float:
        return max(0.0, float(self.end_time) - float(self.start_time))


@dataclass(slots=True)
class YcdClip:
    hash: MetaHash
    name: str
    short_name: str
    clip_type: YcdClipType
    property_count: int = 0
    tag_count: int = 0
    flags: int = 0
    vft: int = 0
    tags: list[YcdClipTag] = field(default_factory=list)
    properties: list[YcdClipProperty] = field(default_factory=list)
    unknown_04h: int = 0
    unknown_08h: int = 0
    unknown_0ch: int = 0
    unknown_14h: int = 0
    unknown_24h: int = 0
    reserved_34h: int = 0
    unknown_48h: int = 0
    unknown_4ch: int = 0
    has_block_tag: bool = False
    tag_list_reserved_0ch: int = 0
    tag_list_reserved_14h: int = 0
    tag_list_reserved_18h: int = 0
    tag_list_reserved_1ch: int = 0
    property_map_reserved_0ch: int = 0x01000000

    @property
    def is_looped(self) -> bool:
        return bool(int(self.flags) & 0x1)

    @property
    def resolved_name(self) -> str | int:
        return self.name or self.hash.resolved

    @property
    def uv_binding(self) -> YcdUvClipBinding | None:
        return parse_ycd_uv_clip_binding(self.short_name or self.name)

    @property
    def is_uv_clip(self) -> bool:
        return self.uv_binding is not None

    @property
    def uv_object_name(self) -> str | None:
        binding = self.uv_binding
        return binding.object_name if binding is not None else None

    @property
    def uv_slot_index(self) -> int | None:
        binding = self.uv_binding
        return binding.slot_index if binding is not None else None

    def get_property(self, value: int | str | MetaHash) -> YcdClipProperty | None:
        for key in _ycd_hash_candidates(value):
            for prop in self.properties:
                if prop.name_hash.uint == key:
                    return prop
        return None

    def get_tag(self, value: int | str | MetaHash) -> YcdClipTag | None:
        for key in _ycd_hash_candidates(value):
            for tag in self.tags:
                if tag.name_hash.uint == key:
                    return tag
        return None


@dataclass(slots=True)
class YcdClipAnimation(YcdClip):
    animation_hash: MetaHash = field(default_factory=MetaHash)
    start_time: float = 0.0
    end_time: float = 0.0
    rate: float = 1.0
    animation: YcdAnimation | None = None
    reserved_64h: int = 0
    reserved_68h: int = 0
    reserved_6ch: int = 0

    @property
    def duration(self) -> float:
        return max(0.0, float(self.end_time) - float(self.start_time))

    @property
    def has_uv_animation(self) -> bool:
        return bool(self.animation and self.animation.has_uv_animation)

    @property
    def has_object_animation(self) -> bool:
        return bool(self.animation and self.animation.has_object_animation)

    @property
    def has_camera_animation(self) -> bool:
        return bool(self.animation and self.animation.has_camera_animation)

    @property
    def has_root_motion(self) -> bool:
        return bool(self.animation and self.animation.has_root_motion)

    @property
    def has_facial_animation(self) -> bool:
        return bool(self.animation and self.animation.has_facial_animation)

    def get_animation_frame(self, phase: float) -> float:
        if self.animation is None or self.animation.frames <= 1:
            return 0.0
        phase_value = min(max(float(phase), 0.0), 1.0)
        return phase_value * float(self.animation.frames - 1)

    def get_animation_frame_at_time(self, seconds: float) -> float:
        clip_duration = max(float(self.duration), 0.0)
        if clip_duration <= 0.0:
            return 0.0
        phase = min(max(float(seconds) / clip_duration, 0.0), 1.0)
        return self.get_animation_frame(phase)

    def evaluate_tracks_at_phase(self, phase: float, *, track: int | YcdAnimationTrack | None = None, interpolate: bool = True) -> dict[tuple[int, int], tuple[float, float, float, float]]:
        if self.animation is None:
            return {}
        return self.animation.evaluate_tracks(self.get_animation_frame(phase), track=track, interpolate=interpolate)

    def evaluate_tracks_at_time(self, seconds: float, *, track: int | YcdAnimationTrack | None = None, interpolate: bool = True) -> dict[tuple[int, int], tuple[float, float, float, float]]:
        if self.animation is None:
            return {}
        return self.animation.evaluate_tracks(self.get_animation_frame_at_time(seconds), track=track, interpolate=interpolate)

    def evaluate_uv_animation_at_time(self, seconds: float) -> YcdUvTransformSample:
        if self.animation is None:
            return YcdUvTransformSample()
        return self.animation.evaluate_uv_transform(self.get_animation_frame_at_time(seconds))

    def evaluate_object_animation_at_time(self, seconds: float) -> YcdTransformSample:
        if self.animation is None:
            return YcdTransformSample()
        tracks = self.animation.evaluate_object_animation(self.get_animation_frame_at_time(seconds))
        position = next((value[:3] for (_, track), value in tracks.items() if int(track) == int(YcdAnimationTrack.BONE_TRANSLATION)), None)
        rotation = next((value for (_, track), value in tracks.items() if int(track) == int(YcdAnimationTrack.BONE_ROTATION)), None)
        return YcdTransformSample(position=position, rotation=rotation)

    def evaluate_root_motion_at_time(self, seconds: float) -> YcdTransformSample:
        if self.animation is None:
            return YcdTransformSample()
        return self.animation.evaluate_root_motion(self.get_animation_frame_at_time(seconds))

    def evaluate_camera_animation_at_time(self, seconds: float) -> YcdCameraAnimationSample:
        if self.animation is None:
            return YcdCameraAnimationSample()
        return self.animation.evaluate_camera_animation(self.get_animation_frame_at_time(seconds))

    def evaluate_facial_animation_at_time(self, seconds: float) -> dict[int, YcdFacialAnimationSample]:
        if self.animation is None:
            return {}
        return self.animation.evaluate_facial_animation(self.get_animation_frame_at_time(seconds))


@dataclass(slots=True)
class YcdClipAnimationList(YcdClip):
    total_duration: float = 0.0
    animations: list[YcdClipAnimationEntry] = field(default_factory=list)
    unknown_5ch: int = 0
    parallel: bool = False
    parallel_padding: bytes = b"\x00\x00\x00"
    reserved_68h: int = 0
    reserved_6ch: int = 0


@dataclass(slots=True)
class Ycd:
    header: ResourceHeader
    clips: list[YcdClip]
    animations: list[YcdAnimation]
    path: str | None = None
    clip_map: dict[int, YcdClip] = field(default_factory=dict)
    animation_map: dict[int, YcdAnimation] = field(default_factory=dict)
    clip_bucket_capacity: int = 0
    clip_entry_count: int = 0
    animation_bucket_capacity: int = 0
    animation_entry_count: int = 0

    @property
    def name(self) -> str | None:
        if not self.path:
            return None
        return Path(self.path).name

    @property
    def stem(self) -> str | None:
        if not self.path:
            return None
        return Path(self.path).stem

    def get_clip(self, value: int | str | MetaHash) -> YcdClip | None:
        for key in _ycd_hash_candidates(value):
            clip = self.clip_map.get(key)
            if clip is not None:
                return clip
        return None

    def get_animation(self, value: int | str | MetaHash) -> YcdAnimation | None:
        for key in _ycd_hash_candidates(value):
            animation = self.animation_map.get(key)
            if animation is not None:
                return animation
        return None

    def build_cutscene_map(self, cut_index: int) -> dict[int, YcdClip]:
        suffix = f"-{int(cut_index)}"
        result: dict[int, YcdClip] = {}
        for clip in self.clips:
            short_name = clip.short_name
            if short_name.endswith(suffix):
                short_name = short_name[: -len(suffix)]
            if short_name.endswith("_dual"):
                short_name = short_name[:-5]
            result[MetaHash(short_name).uint] = clip
        return result

    def validate(self) -> Ycd:
        for clip in self.clips:
            if not isinstance(clip, YcdClipAnimation):
                continue
            binding = clip.uv_binding
            has_uv_animation = bool(clip.animation and clip.animation.has_uv_animation)
            if binding is None and not has_uv_animation:
                continue
            if binding is None:
                raise ValueError(f"YCD UV clip '{clip.short_name or clip.name}' is missing a '<object>_uv_<slot_index>' name")
            expected_short_name = binding.clip_name
            if clip.short_name and clip.short_name != expected_short_name:
                raise ValueError(
                    f"YCD UV clip short_name '{clip.short_name}' does not match expected '{expected_short_name}' for slot_index={binding.slot_index}"
                )
            expected_hash = binding.clip_hash.uint
            if clip.hash.uint and clip.hash.uint != expected_hash:
                raise ValueError(
                    f"YCD UV clip '{expected_short_name}' has hash 0x{clip.hash.uint:08X}, expected 0x{expected_hash:08X}"
                )
            if clip.animation is None:
                raise ValueError(f"YCD UV clip '{expected_short_name}' is missing its animation payload")
            if not clip.animation.uv_sequences:
                raise ValueError(f"YCD UV clip '{expected_short_name}' does not contain shader UV tracks")
            for sequence in clip.animation.uv_sequences:
                bone = sequence.bone_id
                if bone is None:
                    raise ValueError(f"YCD UV clip '{expected_short_name}' contains a UV sequence without bone metadata")
                if int(bone.bone_id) != 0:
                    raise ValueError(
                        f"YCD UV clip '{expected_short_name}' uses bone_id={bone.bone_id}, but the runtime expects UV tracks on bone_id 0"
                    )
                if int(bone.track) not in (
                    int(YcdAnimationTrack.SHADER_SLIDE_U),
                    int(YcdAnimationTrack.SHADER_SLIDE_V),
                ):
                    raise ValueError(
                        f"YCD UV clip '{expected_short_name}' contains unexpected UV track id {bone.track}"
                    )
        return self

    def build(self) -> Ycd:
        self.animation_map = {}
        for animation in self.animations:
            if animation.hash.uint == 0 and animation.name:
                animation.hash = MetaHash(animation.name)
            animation.prepare_for_export()
            self.animation_map[animation.hash.uint] = animation

        for clip in self.clips:
            if not clip.short_name and clip.name:
                clip.short_name = _normalize_ycd_clip_name(clip.name)
            if clip.hash.uint == 0:
                clip.hash = _resolve_ycd_clip_hash(clip)
            if isinstance(clip, YcdClipAnimation):
                if clip.animation is None and clip.animation_hash.uint:
                    clip.animation = self.animation_map.get(clip.animation_hash.uint)
                if clip.animation is not None:
                    if clip.animation.hash.uint == 0 and clip.animation.name:
                        clip.animation.hash = MetaHash(clip.animation.name)
                    clip.animation_hash = clip.animation.hash
            elif isinstance(clip, YcdClipAnimationList):
                for entry in clip.animations:
                    if entry.animation is None and entry.animation_hash.uint:
                        entry.animation = self.animation_map.get(entry.animation_hash.uint)
                    if entry.animation is not None:
                        if entry.animation.hash.uint == 0 and entry.animation.name:
                            entry.animation.hash = MetaHash(entry.animation.name)
                        entry.animation_hash = entry.animation.hash

        self.clip_map = {clip.hash.uint: clip for clip in self.clips}
        self.clip_entry_count = len(self.clips)
        self.animation_entry_count = len(self.animations)
        self.clip_bucket_capacity = max(int(self.clip_bucket_capacity), _get_ycd_bucket_capacity(self.clip_entry_count))
        self.animation_bucket_capacity = max(int(self.animation_bucket_capacity), _get_ycd_bucket_capacity(self.animation_entry_count))
        self.validate()
        return self

    def to_bytes(self) -> bytes:
        from .write import build_ycd_bytes

        return build_ycd_bytes(self)

    def save(self, path: str | Path) -> Path:
        from .write import save_ycd

        return save_ycd(self, path)


__all__ = [
    "Ycd",
    "YcdAnimation",
    "YcdAnimationBoneId",
    "YcdAnimationTrack",
    "YcdAnimSequence",
    "YcdCameraAnimationSample",
    "YcdChannelType",
    "YcdClip",
    "YcdClipAnimation",
    "YcdClipAnimationEntry",
    "YcdClipAnimationList",
    "YcdClipProperty",
    "YcdClipPropertyAttribute",
    "YcdClipPropertyAttributeType",
    "YcdClipTag",
    "YcdClipType",
    "YcdFacialAnimationSample",
    "YcdFramePosition",
    "YcdSequence",
    "YcdSequenceRootChannelRef",
    "YcdTransformSample",
    "YcdUvClipBinding",
    "YcdUvAnimationSample",
    "YcdUvTransformSample",
    "build_ycd_uv_clip_hash",
    "build_ycd_uv_clip_name",
    "create_ycd_uv_clip",
    "parse_ycd_uv_clip_binding",
]


def _resolve_ycd_clip_hash(clip: YcdClip) -> MetaHash:
    if clip.hash.uint:
        return clip.hash
    binding = clip.uv_binding
    if binding is not None:
        return binding.clip_hash
    short_name = clip.short_name or ""
    if short_name:
        return MetaHash(short_name)
    if clip.name:
        return MetaHash(clip.name)
    return MetaHash(0)


def _get_ycd_bucket_capacity(count: int) -> int:
    if count < 11:
        return 11
    if count < 29:
        return 29
    if count < 59:
        return 59
    if count < 107:
        return 107
    if count < 191:
        return 191
    if count < 331:
        return 331
    if count < 563:
        return 563
    if count < 953:
        return 953
    if count < 1609:
        return 1609
    if count < 2729:
        return 2729
    if count < 4621:
        return 4621
    if count < 7841:
        return 7841
    if count < 13297:
        return 13297
    if count < 22571:
        return 22571
    if count < 38351:
        return 38351
    if count < 65167:
        return 65167
    return 65521


def create_ycd_uv_clip(
    *,
    object_name: str,
    slot_index: int,
    animation: YcdAnimation | None = None,
    start_time: float = 0.0,
    end_time: float = 0.0,
    rate: float = 1.0,
    name: str | None = None,
    flags: int = 0,
) -> YcdClipAnimation:
    binding = YcdUvClipBinding(object_name=object_name, slot_index=int(slot_index))
    clip_name = name or binding.clip_name
    return YcdClipAnimation(
        hash=binding.clip_hash,
        name=clip_name,
        short_name=binding.clip_name,
        clip_type=YcdClipType.ANIMATION,
        flags=int(flags),
        animation_hash=animation.hash if animation is not None else MetaHash(0),
        start_time=float(start_time),
        end_time=float(end_time),
        rate=float(rate),
        animation=animation,
    )


def _lerp_vector4(
    value0: tuple[float, float, float, float],
    value1: tuple[float, float, float, float],
    alpha1: float,
) -> tuple[float, float, float, float]:
    alpha0 = 1.0 - float(alpha1)
    return (
        float((value0[0] * alpha0) + (value1[0] * alpha1)),
        float((value0[1] * alpha0) + (value1[1] * alpha1)),
        float((value0[2] * alpha0) + (value1[2] * alpha1)),
        float((value0[3] * alpha0) + (value1[3] * alpha1)),
    )


def _nlerp_vector4(
    value0: tuple[float, float, float, float],
    value1: tuple[float, float, float, float],
    alpha1: float,
) -> tuple[float, float, float, float]:
    x, y, z, w = _lerp_vector4(value0, value1, alpha1)
    length = math.sqrt((x * x) + (y * y) + (z * z) + (w * w))
    if length <= 0.0:
        return (x, y, z, w)
    inv = 1.0 / length
    return (x * inv, y * inv, z * inv, w * inv)


def _track_scalar(
    tracks: dict[tuple[int, int], tuple[float, float, float, float]],
    track: int | YcdAnimationTrack,
) -> float | None:
    for (_, current_track), value in tracks.items():
        if int(current_track) == int(track):
            return float(value[0])
    return None


def _track_vector3(
    tracks: dict[tuple[int, int], tuple[float, float, float, float]],
    track: int | YcdAnimationTrack,
) -> tuple[float, float, float] | None:
    for (_, current_track), value in tracks.items():
        if int(current_track) == int(track):
            return value[:3]
    return None
