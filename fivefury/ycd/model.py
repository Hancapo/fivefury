from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

from ..metahash import MetaHash
from ..resource import ResourceHeader


class YcdClipType(IntEnum):
    ANIMATION = 1
    ANIMATION_LIST = 2


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
    raw_unknown_hash: MetaHash = field(default_factory=MetaHash)

    @property
    def name(self) -> str | None:
        return self.hash.text


@dataclass(slots=True)
class YcdClipAnimationEntry:
    start_time: float
    end_time: float
    rate: float
    animation_hash: MetaHash
    animation: YcdAnimation | None = None

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

    @property
    def resolved_name(self) -> str | int:
        return self.name or self.hash.resolved


@dataclass(slots=True)
class YcdClipAnimation(YcdClip):
    animation_hash: MetaHash = field(default_factory=MetaHash)
    start_time: float = 0.0
    end_time: float = 0.0
    rate: float = 1.0
    animation: YcdAnimation | None = None

    @property
    def duration(self) -> float:
        return max(0.0, float(self.end_time) - float(self.start_time))


@dataclass(slots=True)
class YcdClipAnimationList(YcdClip):
    duration: float = 0.0
    animations: list[YcdClipAnimationEntry] = field(default_factory=list)


@dataclass(slots=True)
class Ycd:
    header: ResourceHeader
    clips: list[YcdClip]
    animations: list[YcdAnimation]
    path: str | None = None
    clip_map: dict[int, YcdClip] = field(default_factory=dict)
    animation_map: dict[int, YcdAnimation] = field(default_factory=dict)

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
    "YcdClip",
    "YcdClipAnimation",
    "YcdClipAnimationEntry",
    "YcdClipAnimationList",
    "YcdClipType",
]
