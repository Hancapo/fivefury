from __future__ import annotations

from enum import IntEnum, IntFlag
from pathlib import Path
from typing import Any

from ..ydr.model import YdrLightType


class CutLightType(IntEnum):
    DIRECTIONAL = 0
    POINT = 1
    SPOT = 2


class CutLightProperty(IntEnum):
    NONE = 0
    CASTS_SHADOWS = 1
    ENVIRONMENT = 2


class CutLightFlag(IntFlag):
    NONE = 0
    DONT_LIGHT_ALPHA = 1 << 0
    CAST_STATIC_GEOM_SHADOWS = 1 << 7
    CAST_DYNAMIC_GEOM_SHADOWS = 1 << 8
    CALC_FROM_SUN = 1 << 9
    ENABLE_BUZZING = 1 << 10
    FORCE_BUZZING = 1 << 11
    DRAW_VOLUME = 1 << 12
    NO_SPECULAR = 1 << 13
    BOTH_INTERIOR_AND_EXTERIOR = 1 << 14
    CORONA_ONLY = 1 << 15
    NOT_IN_REFLECTION = 1 << 16
    ONLY_IN_REFLECTION = 1 << 17
    REFLECTOR = 1 << 18
    DIFFUSER = 1 << 19
    ADD_AMBIENT_LIGHT = 1 << 20
    USE_TIMECYCLE_VALUES = 1 << 21
    IS_CHARACTER_LIGHT = 1 << 22
    CHARACTER_LIGHT_INTENSITY_AS_MULTIPLIER = 1 << 23
    IS_PED_ONLY_LIGHT = 1 << 24


_YDR_LIGHTFLAG_CAST_SHADOWS = 1 << 6
_YDR_LIGHTFLAG_CAST_STATIC_GEOM_SHADOWS = 1 << 7
_YDR_LIGHTFLAG_CAST_DYNAMIC_GEOM_SHADOWS = 1 << 8
_YDR_LIGHTFLAG_CALC_FROM_SUN = 1 << 9
_YDR_LIGHTFLAG_DRAW_VOLUME = 1 << 12
_YDR_LIGHTFLAG_NO_SPECULAR = 1 << 13
_YDR_LIGHTFLAG_BOTH_INTERIOR_AND_EXTERIOR = 1 << 14
_YDR_LIGHTFLAG_CORONA_ONLY = 1 << 15
_YDR_LIGHTFLAG_NOT_IN_REFLECTION = 1 << 16
_YDR_LIGHTFLAG_ONLY_IN_REFLECTION = 1 << 17
_YDR_LIGHTFLAG_DONT_LIGHT_ALPHA = 1 << 23


def cut_light_type_from_ydr_light_type(light_type: YdrLightType | int) -> CutLightType:
    if int(light_type) == int(YdrLightType.SPOT):
        return CutLightType.SPOT
    return CutLightType.POINT


def cut_light_flags_from_ydr_flags(ydr_flags: int) -> CutLightFlag:
    flags = CutLightFlag.NONE
    if ydr_flags & _YDR_LIGHTFLAG_DONT_LIGHT_ALPHA:
        flags |= CutLightFlag.DONT_LIGHT_ALPHA
    if ydr_flags & _YDR_LIGHTFLAG_CAST_STATIC_GEOM_SHADOWS:
        flags |= CutLightFlag.CAST_STATIC_GEOM_SHADOWS
    if ydr_flags & _YDR_LIGHTFLAG_CAST_DYNAMIC_GEOM_SHADOWS:
        flags |= CutLightFlag.CAST_DYNAMIC_GEOM_SHADOWS
    if ydr_flags & _YDR_LIGHTFLAG_CALC_FROM_SUN:
        flags |= CutLightFlag.CALC_FROM_SUN
    if ydr_flags & _YDR_LIGHTFLAG_DRAW_VOLUME:
        flags |= CutLightFlag.DRAW_VOLUME
    if ydr_flags & _YDR_LIGHTFLAG_NO_SPECULAR:
        flags |= CutLightFlag.NO_SPECULAR
    if ydr_flags & _YDR_LIGHTFLAG_BOTH_INTERIOR_AND_EXTERIOR:
        flags |= CutLightFlag.BOTH_INTERIOR_AND_EXTERIOR
    if ydr_flags & _YDR_LIGHTFLAG_CORONA_ONLY:
        flags |= CutLightFlag.CORONA_ONLY
    if ydr_flags & _YDR_LIGHTFLAG_NOT_IN_REFLECTION:
        flags |= CutLightFlag.NOT_IN_REFLECTION
    if ydr_flags & _YDR_LIGHTFLAG_ONLY_IN_REFLECTION:
        flags |= CutLightFlag.ONLY_IN_REFLECTION
    return flags


def cut_light_property_from_ydr_flags(ydr_flags: int) -> CutLightProperty:
    shadow_flags = (
        _YDR_LIGHTFLAG_CAST_SHADOWS
        | _YDR_LIGHTFLAG_CAST_STATIC_GEOM_SHADOWS
        | _YDR_LIGHTFLAG_CAST_DYNAMIC_GEOM_SHADOWS
    )
    if ydr_flags & shadow_flags:
        return CutLightProperty.CASTS_SHADOWS
    return CutLightProperty.NONE


def cut_light_fields_from_ydr_light(light: Any) -> dict[str, Any]:
    ydr_flags = int(light.flags)
    return {
        "vDirection": tuple(float(value) for value in light.direction),
        "vColour": tuple(float(value) / 255.0 for value in light.color),
        "vPosition": tuple(float(value) for value in light.position),
        "fIntensity": float(light.intensity),
        "fFallOff": float(light.falloff),
        "fConeAngle": float(light.cone_outer_angle),
        "fVolumeIntensity": float(light.volume_intensity),
        "fVolumeSizeScale": float(light.volume_size_scale),
        "fCoronaSize": float(light.corona_size),
        "fCoronaIntensity": float(light.corona_intensity),
        "fCoronaZBias": float(light.corona_z_bias),
        "fInnerConeAngle": float(light.cone_inner_angle),
        "fExponentialFallOff": float(light.falloff_exponent),
        "fShadowBlur": float(light.shadow_blur),
        "iLightType": int(cut_light_type_from_ydr_light_type(light.light_type)),
        "iLightProperty": int(cut_light_property_from_ydr_flags(ydr_flags)),
        "TextureDictID": 0,
        "TextureKey": int(light.projected_texture_hash),
        "uLightFlags": int(cut_light_flags_from_ydr_flags(ydr_flags)),
        "uHourFlags": int(light.time_flags) or 0xFFFFFF,
        "bStatic": False,
    }


def ensure_ydr_embedded_lights(
    scene: Any,
    source: Any,
    *,
    name_prefix: str | None = None,
    start: float = 0.0,
) -> list[Any]:
    from ..ydr.reader import read_ydr

    ydr = read_ydr(source) if isinstance(source, (bytes, bytearray, str, Path)) else source
    if name_prefix is None:
        source_path = Path(source) if isinstance(source, (str, Path)) else None
        name_prefix = source_path.stem if source_path is not None else "embedded"

    existing_names = {binding.name for binding in scene.bindings if getattr(binding, "role", None) == "light"}
    created: list[Any] = []
    for index, light in enumerate(getattr(ydr, "lights", []) or []):
        name = f"{name_prefix}_cut_light_{index}"
        if name in existing_names:
            continue
        binding = scene.add_light(name, fields=cut_light_fields_from_ydr_light(light))
        scene.set_light(float(start), binding)
        existing_names.add(name)
        created.append(binding)
    return created


__all__ = [
    "CutLightFlag",
    "CutLightProperty",
    "CutLightType",
    "cut_light_fields_from_ydr_light",
    "cut_light_flags_from_ydr_flags",
    "cut_light_property_from_ydr_flags",
    "cut_light_type_from_ydr_light_type",
    "ensure_ydr_embedded_lights",
]
