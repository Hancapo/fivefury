from __future__ import annotations

import dataclasses
import enum
from typing import Any

from ..extensions import extensions_from_meta, extensions_to_meta
from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta.defs import meta_name
from .flags import TimeArchetypeFlags


class ArchetypeAssetType(enum.IntEnum):
    UNINITIALIZED = 0
    FRAGMENT = 1
    DRAWABLE = 2
    DRAWABLE_DICTIONARY = 3
    ASSETLESS = 4

    DRAWABLEDICTIONARY = DRAWABLE_DICTIONARY


def coerce_archetype_asset_type(value: int | ArchetypeAssetType) -> ArchetypeAssetType:
    return value if isinstance(value, ArchetypeAssetType) else ArchetypeAssetType(int(value))


def coerce_time_archetype_flags(value: int | TimeArchetypeFlags) -> TimeArchetypeFlags:
    return value if isinstance(value, TimeArchetypeFlags) else TimeArchetypeFlags(int(value))


@dataclasses.dataclass(slots=True)
class BaseArchetypeDef(MetaHashFieldsMixin):
    _hash_fields = ("name", "texture_dictionary", "clip_dictionary", "drawable_dictionary", "physics_dictionary", "asset_name")

    lod_dist: float = 0.0
    flags: int = 0
    special_attribute: int = 0
    bb_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bb_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bs_centre: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bs_radius: float = 0.0
    hd_texture_dist: float = 0.0
    name: MetaHash | HashLike = 0
    texture_dictionary: MetaHash | HashLike = 0
    clip_dictionary: MetaHash | HashLike = 0
    drawable_dictionary: MetaHash | HashLike = 0
    physics_dictionary: MetaHash | HashLike = 0
    asset_type: ArchetypeAssetType = ArchetypeAssetType.UNINITIALIZED
    asset_name: MetaHash | HashLike = 0
    extensions: list[Any] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        self.asset_type = coerce_archetype_asset_type(self.asset_type)
        if self.asset_name in (0, "") and self.name not in (0, ""):
            self.asset_name = self.name

    def add_extension(self, extension: Any) -> Any:
        self.extensions.append(extension)
        return extension

    def to_meta(self) -> dict[str, Any]:
        return {
            "lodDist": self.lod_dist,
            "flags": self.flags,
            "specialAttribute": self.special_attribute,
            "bbMin": self.bb_min,
            "bbMax": self.bb_max,
            "bsCentre": self.bs_centre,
            "bsRadius": self.bs_radius,
            "hdTextureDist": self.hd_texture_dist,
            "name": self.name,
            "textureDictionary": self.texture_dictionary,
            "clipDictionary": self.clip_dictionary,
            "drawableDictionary": self.drawable_dictionary,
            "physicsDictionary": self.physics_dictionary,
            "assetType": int(self.asset_type),
            "assetName": self.asset_name,
            "extensions": extensions_to_meta(self.extensions),
            "_meta_name_hash": meta_name("CBaseArchetypeDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "BaseArchetypeDef":
        return cls(
            lod_dist=float(value.get("lodDist", 0.0)),
            flags=int(value.get("flags", 0)),
            special_attribute=int(value.get("specialAttribute", 0)),
            bb_min=tuple(value.get("bbMin", (0.0, 0.0, 0.0))),
            bb_max=tuple(value.get("bbMax", (0.0, 0.0, 0.0))),
            bs_centre=tuple(value.get("bsCentre", (0.0, 0.0, 0.0))),
            bs_radius=float(value.get("bsRadius", 0.0)),
            hd_texture_dist=float(value.get("hdTextureDist", 0.0)),
            name=value.get("name", 0),
            texture_dictionary=value.get("textureDictionary", 0),
            clip_dictionary=value.get("clipDictionary", 0),
            drawable_dictionary=value.get("drawableDictionary", 0),
            physics_dictionary=value.get("physicsDictionary", 0),
            asset_type=coerce_archetype_asset_type(value.get("assetType", ArchetypeAssetType.UNINITIALIZED)),
            asset_name=value.get("assetName", 0),
            extensions=extensions_from_meta(value.get("extensions", []) or []),
        )


@dataclasses.dataclass(slots=True)
class TimeArchetypeDef(BaseArchetypeDef):
    time_flags: TimeArchetypeFlags | int = TimeArchetypeFlags.NONE

    def __post_init__(self) -> None:
        super().__post_init__()
        self.time_flags = coerce_time_archetype_flags(self.time_flags)

    @property
    def flip_while_visible(self) -> bool:
        return bool(self.time_flags & TimeArchetypeFlags.FLIP_WHILE_VISIBLE)

    @flip_while_visible.setter
    def flip_while_visible(self, value: bool) -> None:
        if value:
            self.time_flags |= TimeArchetypeFlags.FLIP_WHILE_VISIBLE
        else:
            self.time_flags &= ~TimeArchetypeFlags.FLIP_WHILE_VISIBLE

    @property
    def hour_flags(self) -> TimeArchetypeFlags:
        return self.time_flags & TimeArchetypeFlags.ALL_HOURS

    def to_meta(self) -> dict[str, Any]:
        data = super().to_meta()
        data.update({"timeFlags": int(self.time_flags), "_meta_name_hash": meta_name("CTimeArchetypeDef")})
        return data

    @classmethod
    def from_meta(cls, value: Any) -> "TimeArchetypeDef":
        base = BaseArchetypeDef.from_meta(value)
        return cls(**dataclasses.asdict(base), time_flags=coerce_time_archetype_flags(int(value.get("timeFlags", 0))))


Archetype = BaseArchetypeDef
TimeArchetype = TimeArchetypeDef
