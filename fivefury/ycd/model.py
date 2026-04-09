from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

from ..metahash import MetaHash
from ..resource import ResourceHeader


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
    unknown: int = 0


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
    unknown_08h: int = 0
    unknown_14h: int = 0

    @property
    def root_position_ref_count(self) -> int:
        return (int(self.root_motion_ref_counts) >> 4) & 0xF

    @property
    def root_rotation_ref_count(self) -> int:
        return int(self.root_motion_ref_counts) & 0xF


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
    unknown_0ch: int = 0

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
    unknown_30h: int = 0
    vft: int = 0
    tags: list[YcdClipTag] = field(default_factory=list)
    properties: list[YcdClipProperty] = field(default_factory=list)
    unknown_04h: int = 0
    unknown_08h: int = 0
    unknown_0ch: int = 0
    unknown_14h: int = 0
    unknown_24h: int = 0
    unknown_48h: int = 0
    unknown_4ch: int = 0

    @property
    def resolved_name(self) -> str | int:
        return self.name or self.hash.resolved

    def get_property(self, value: int | str | MetaHash) -> YcdClipProperty | None:
        key = MetaHash(value).uint
        for prop in self.properties:
            if prop.name_hash.uint == key:
                return prop
        return None

    def get_tag(self, value: int | str | MetaHash) -> YcdClipTag | None:
        key = MetaHash(value).uint
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
    unknown_64h: int = 0
    unknown_68h: int = 0
    unknown_6ch: int = 0

    @property
    def duration(self) -> float:
        return max(0.0, float(self.end_time) - float(self.start_time))


@dataclass(slots=True)
class YcdClipAnimationList(YcdClip):
    duration: float = 0.0
    animations: list[YcdClipAnimationEntry] = field(default_factory=list)
    unknown_5ch: int = 0
    unknown_64h: int = 0
    unknown_68h: int = 0
    unknown_6ch: int = 0


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
        key = MetaHash(value).uint
        return self.clip_map.get(key)

    def get_animation(self, value: int | str | MetaHash) -> YcdAnimation | None:
        key = MetaHash(value).uint
        return self.animation_map.get(key)

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


__all__ = [
    "Ycd",
    "YcdAnimation",
    "YcdAnimationBoneId",
    "YcdClip",
    "YcdClipAnimation",
    "YcdClipAnimationEntry",
    "YcdClipAnimationList",
    "YcdClipProperty",
    "YcdClipPropertyAttribute",
    "YcdClipPropertyAttributeType",
    "YcdClipTag",
    "YcdClipType",
    "YcdSequence",
]
