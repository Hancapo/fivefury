from __future__ import annotations

import dataclasses
from typing import Any

from ..colors import CssColor
from ..hashing import jenk_hash
from ..meta.defs import meta_name
from .enums import (
    YmapLodLightCategory,
    YmapLodLightType,
    coerce_ymap_lod_light_category,
    coerce_ymap_lod_light_type,
)
from .packing import clamp_byte, pack_lod_light_u8, pack_rgbi, unpack_lod_light_u8, unpack_rgbi


MAX_LOD_LIGHT_CONE_ANGLE = 180.0
MAX_LOD_LIGHT_CORONA_INTENSITY = 32.0
MAX_LOD_LIGHT_CAPSULE_EXTENT = 140.0


@dataclasses.dataclass(slots=True)
class LodLight:
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    direction: tuple[float, float, float] = (0.0, 0.0, -1.0)
    falloff: float = 1.0
    falloff_exponent: float = 1.0
    time_and_state_flags: int = 0
    hash: int | str = 0
    cone_inner_angle: int = 0
    cone_outer_angle_or_cap_ext: int = 0
    corona_intensity: int = 0
    rgbi: int = 0

    @property
    def light_type(self) -> YmapLodLightType:
        return coerce_ymap_lod_light_type((self.time_and_state_flags >> 26) & 0x1F)

    @light_type.setter
    def light_type(self, value: int | YmapLodLightType) -> None:
        light_type = coerce_ymap_lod_light_type(value)
        self.time_and_state_flags = (self.time_and_state_flags & 0x83FFFFFF) | ((int(light_type) & 0x1F) << 26)

    @property
    def time_flags(self) -> int:
        return self.time_and_state_flags & 0xFFFFFF

    @time_flags.setter
    def time_flags(self, value: int) -> None:
        self.time_and_state_flags = (self.time_and_state_flags & 0xFF000000) | (int(value) & 0xFFFFFF)

    @property
    def state_flags_1(self) -> int:
        return (self.time_and_state_flags >> 24) & 3

    @state_flags_1.setter
    def state_flags_1(self, value: int) -> None:
        self.time_and_state_flags = (self.time_and_state_flags & 0xFCFFFFFF) | ((int(value) & 3) << 24)

    @property
    def state_flags_2(self) -> int:
        return (self.time_and_state_flags >> 31) & 1

    @state_flags_2.setter
    def state_flags_2(self, value: int) -> None:
        self.time_and_state_flags = (self.time_and_state_flags & 0x7FFFFFFF) | ((int(value) & 1) << 31)

    @property
    def is_street_light(self) -> bool:
        return bool((self.time_and_state_flags >> 24) & 1)

    @is_street_light.setter
    def is_street_light(self, value: bool) -> None:
        self.state_flags_1 = (self.state_flags_1 & ~0x1) | (1 if value else 0)

    @property
    def is_corona_only(self) -> bool:
        return bool((self.time_and_state_flags >> 25) & 1)

    @is_corona_only.setter
    def is_corona_only(self, value: bool) -> None:
        self.state_flags_1 = (self.state_flags_1 & ~0x2) | (0x2 if value else 0)

    @property
    def dont_use_in_cutscene(self) -> bool:
        return bool(self.state_flags_2)

    @dont_use_in_cutscene.setter
    def dont_use_in_cutscene(self, value: bool) -> None:
        self.state_flags_2 = 1 if value else 0

    @property
    def colour(self) -> tuple[int, int, int]:
        return unpack_rgbi(self.rgbi)[0]

    @colour.setter
    def colour(self, value: tuple[int, int, int] | CssColor) -> None:
        self.rgbi = pack_rgbi(value, self.intensity)

    @property
    def intensity(self) -> int:
        return unpack_rgbi(self.rgbi)[1]

    @intensity.setter
    def intensity(self, value: int) -> None:
        self.rgbi = pack_rgbi(self.colour, value)

    @property
    def cone_inner_angle_degrees(self) -> float:
        return unpack_lod_light_u8(self.cone_inner_angle, MAX_LOD_LIGHT_CONE_ANGLE)

    @cone_inner_angle_degrees.setter
    def cone_inner_angle_degrees(self, value: float) -> None:
        self.cone_inner_angle = pack_lod_light_u8(value, MAX_LOD_LIGHT_CONE_ANGLE)

    @property
    def cone_outer_angle_degrees(self) -> float:
        return unpack_lod_light_u8(self.cone_outer_angle_or_cap_ext, MAX_LOD_LIGHT_CONE_ANGLE)

    @cone_outer_angle_degrees.setter
    def cone_outer_angle_degrees(self, value: float) -> None:
        self.cone_outer_angle_or_cap_ext = pack_lod_light_u8(value, MAX_LOD_LIGHT_CONE_ANGLE)

    @property
    def capsule_extent(self) -> float:
        return unpack_lod_light_u8(self.cone_outer_angle_or_cap_ext, MAX_LOD_LIGHT_CAPSULE_EXTENT)

    @capsule_extent.setter
    def capsule_extent(self, value: float) -> None:
        self.cone_outer_angle_or_cap_ext = pack_lod_light_u8(value, MAX_LOD_LIGHT_CAPSULE_EXTENT)

    @property
    def corona_intensity_value(self) -> float:
        return unpack_lod_light_u8(self.corona_intensity, MAX_LOD_LIGHT_CORONA_INTENSITY)

    @corona_intensity_value.setter
    def corona_intensity_value(self, value: float) -> None:
        self.corona_intensity = pack_lod_light_u8(value, MAX_LOD_LIGHT_CORONA_INTENSITY)


@dataclasses.dataclass(slots=True)
class LodLightsSoa:
    direction: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    falloff: list[float] = dataclasses.field(default_factory=list)
    falloff_exponent: list[float] = dataclasses.field(default_factory=list)
    time_and_state_flags: list[int] = dataclasses.field(default_factory=list)
    hash: list[int | str] = dataclasses.field(default_factory=list)
    cone_inner_angle: list[int] = dataclasses.field(default_factory=list)
    cone_outer_angle_or_cap_ext: list[int] = dataclasses.field(default_factory=list)
    corona_intensity: list[int] = dataclasses.field(default_factory=list)

    def __len__(self) -> int:
        return len(self.direction)

    def to_meta(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "falloff": self.falloff,
            "falloffExponent": self.falloff_exponent,
            "timeAndStateFlags": [int(value) for value in self.time_and_state_flags],
            "hash": [jenk_hash(value) if isinstance(value, str) else int(value) for value in self.hash],
            "coneInnerAngle": [int(value) for value in self.cone_inner_angle],
            "coneOuterAngleOrCapExt": [int(value) for value in self.cone_outer_angle_or_cap_ext],
            "coronaIntensity": [int(value) for value in self.corona_intensity],
            "_meta_name_hash": meta_name("CLODLight"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "LodLightsSoa":
        if not isinstance(value, dict):
            return cls()
        return cls(
            direction=[tuple(item) for item in value.get("direction", []) or []],
            falloff=[float(item) for item in value.get("falloff", []) or []],
            falloff_exponent=[float(item) for item in value.get("falloffExponent", []) or []],
            time_and_state_flags=[int(item) for item in value.get("timeAndStateFlags", []) or []],
            hash=list(value.get("hash", []) or []),
            cone_inner_angle=[int(item) for item in value.get("coneInnerAngle", []) or []],
            cone_outer_angle_or_cap_ext=[int(item) for item in value.get("coneOuterAngleOrCapExt", []) or []],
            corona_intensity=[int(item) for item in value.get("coronaIntensity", []) or []],
        )

    def append(self, light: LodLight) -> LodLight:
        self.direction.append(tuple(light.direction))
        self.falloff.append(float(light.falloff))
        self.falloff_exponent.append(float(light.falloff_exponent))
        self.time_and_state_flags.append(int(light.time_and_state_flags))
        self.hash.append(light.hash)
        self.cone_inner_angle.append(clamp_byte(light.cone_inner_angle))
        self.cone_outer_angle_or_cap_ext.append(clamp_byte(light.cone_outer_angle_or_cap_ext))
        self.corona_intensity.append(clamp_byte(light.corona_intensity))
        return light


@dataclasses.dataclass(slots=True)
class DistantLodLightsSoa:
    position: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    RGBI: list[int] = dataclasses.field(default_factory=list)
    num_street_lights: int = 0
    category: YmapLodLightCategory | int = YmapLodLightCategory.SMALL

    def __post_init__(self) -> None:
        self.category = coerce_ymap_lod_light_category(self.category)

    def __len__(self) -> int:
        return len(self.position)

    def to_meta(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "RGBI": [int(value) for value in self.RGBI],
            "numStreetLights": int(self.num_street_lights),
            "category": int(self.category),
            "_meta_name_hash": meta_name("CDistantLODLight"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "DistantLodLightsSoa":
        if not isinstance(value, dict):
            return cls()
        return cls(
            position=[tuple(item) for item in value.get("position", []) or []],
            RGBI=[int(item) for item in value.get("RGBI", []) or []],
            num_street_lights=int(value.get("numStreetLights", 0)),
            category=coerce_ymap_lod_light_category(int(value.get("category", 0))),
        )

    def append(self, position: tuple[float, float, float], rgbi: int) -> None:
        self.position.append(tuple(position))
        self.RGBI.append(int(rgbi))

    def clamp_street_light_count(self) -> "DistantLodLightsSoa":
        self.num_street_lights = max(0, min(int(self.num_street_lights), len(self.position)))
        return self


def _coerce_lod_lights(**kwargs: Any) -> LodLightsSoa:
    if "falloffExponent" in kwargs:
        kwargs["falloff_exponent"] = kwargs.pop("falloffExponent")
    if "timeAndStateFlags" in kwargs:
        kwargs["time_and_state_flags"] = kwargs.pop("timeAndStateFlags")
    if "coneInnerAngle" in kwargs:
        kwargs["cone_inner_angle"] = kwargs.pop("coneInnerAngle")
    if "coneOuterAngleOrCapExt" in kwargs:
        kwargs["cone_outer_angle_or_cap_ext"] = kwargs.pop("coneOuterAngleOrCapExt")
    if "coronaIntensity" in kwargs:
        kwargs["corona_intensity"] = kwargs.pop("coronaIntensity")
    return LodLightsSoa(**kwargs)


def _coerce_lod_light(**kwargs: Any) -> LodLight | LodLightsSoa:
    if isinstance(kwargs.get("direction"), list) or isinstance(kwargs.get("falloff"), list):
        return _coerce_lod_lights(**kwargs)
    deferred: dict[str, Any] = {}
    if "timeAndStateFlags" in kwargs:
        kwargs["time_and_state_flags"] = kwargs.pop("timeAndStateFlags")
    if "coneInnerAngle" in kwargs:
        kwargs["cone_inner_angle"] = kwargs.pop("coneInnerAngle")
    if "coneOuterAngleOrCapExt" in kwargs:
        kwargs["cone_outer_angle_or_cap_ext"] = kwargs.pop("coneOuterAngleOrCapExt")
    if "coronaIntensity" in kwargs:
        kwargs["corona_intensity"] = kwargs.pop("coronaIntensity")
    if "color" in kwargs and "colour" not in kwargs:
        kwargs["colour"] = kwargs.pop("color")
    if "colour" in kwargs:
        colour = kwargs.pop("colour")
        intensity = int(kwargs.pop("intensity", kwargs.pop("alpha", 255)))
        kwargs["rgbi"] = pack_rgbi(colour, intensity)
    if "coneInnerAngleDegrees" in kwargs:
        deferred["cone_inner_angle_degrees"] = kwargs.pop("coneInnerAngleDegrees")
    if "cone_inner_angle_degrees" in kwargs:
        deferred["cone_inner_angle_degrees"] = kwargs.pop("cone_inner_angle_degrees")
    if "coneOuterAngleDegrees" in kwargs:
        deferred["cone_outer_angle_degrees"] = kwargs.pop("coneOuterAngleDegrees")
    if "cone_outer_angle_degrees" in kwargs:
        deferred["cone_outer_angle_degrees"] = kwargs.pop("cone_outer_angle_degrees")
    if "capsuleExtent" in kwargs:
        deferred["capsule_extent"] = kwargs.pop("capsuleExtent")
    if "capsule_extent" in kwargs:
        deferred["capsule_extent"] = kwargs.pop("capsule_extent")
    if "coronaIntensityValue" in kwargs:
        deferred["corona_intensity_value"] = kwargs.pop("coronaIntensityValue")
    if "corona_intensity_value" in kwargs:
        deferred["corona_intensity_value"] = kwargs.pop("corona_intensity_value")
    for name in (
        "time_flags",
        "state_flags_1",
        "state_flags_2",
        "light_type",
        "is_street_light",
        "is_corona_only",
        "dont_use_in_cutscene",
    ):
        if name in kwargs:
            deferred[name] = kwargs.pop(name)
    light = LodLight(**kwargs)
    for name, value in deferred.items():
        setattr(light, name, value)
    return light


LodLights = LodLightsSoa
DistantLodLights = DistantLodLightsSoa


__all__ = [
    "DistantLodLights",
    "DistantLodLightsSoa",
    "LodLight",
    "LodLights",
    "LodLightsSoa",
    "MAX_LOD_LIGHT_CAPSULE_EXTENT",
    "MAX_LOD_LIGHT_CONE_ANGLE",
    "MAX_LOD_LIGHT_CORONA_INTENSITY",
    "_coerce_lod_light",
    "_coerce_lod_lights",
]
