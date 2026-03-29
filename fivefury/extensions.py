from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any, ClassVar

from .extensions_defs import EXTENSION_STRUCT_INFOS, MetaBackedStruct
from .meta import RawStruct

@dataclasses.dataclass(slots=True)
class LightAttrDef(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CLightAttrDef"

    posn: tuple[float, float, float] = (0.0, 0.0, 0.0)
    colour: tuple[int, int, int] = (255, 255, 255)
    flashiness: int = 0
    intensity: float = 1.0
    flags: int = 0
    bone_tag: int = 0
    light_type: int = 0
    group_id: int = 0
    time_flags: int = 0
    falloff: float = 0.0
    falloff_exponent: float = 0.0
    culling_plane: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    shadow_blur: int = 0
    padding1: int = 0
    padding2: int = 0
    padding3: int = 0
    vol_intensity: float = 0.0
    vol_size_scale: float = 0.0
    vol_outer_colour: tuple[int, int, int] = (255, 255, 255)
    light_hash: int = 0
    vol_outer_intensity: float = 0.0
    corona_size: float = 0.0
    vol_outer_exponent: float = 0.0
    light_fade_distance: int = 0
    shadow_fade_distance: int = 0
    specular_fade_distance: int = 0
    volumetric_fade_distance: int = 0
    shadow_near_clip: float = 0.0
    corona_intensity: float = 0.0
    corona_z_bias: float = 0.0
    direction: tuple[float, float, float] = (0.0, 0.0, -1.0)
    tangent: tuple[float, float, float] = (1.0, 0.0, 0.0)
    cone_inner_angle: float = 0.0
    cone_outer_angle: float = 0.0
    extents: tuple[float, float, float] = (0.0, 0.0, 0.0)
    projected_texture_key: int = 0


@dataclasses.dataclass(slots=True)
class CapsuleBoundDef(MetaBackedStruct):
    META_NAME: ClassVar[str] = "rage__phCapsuleBoundDef"
    META_FIELD_MAP: ClassVar[dict[str, str]] = {
        "owner_name": "OwnerName",
        "rotation": "Rotation",
        "position": "Position",
        "normal": "Normal",
        "capsule_radius": "CapsuleRadius",
        "capsule_len": "CapsuleLen",
        "capsule_half_height": "CapsuleHalfHeight",
        "capsule_half_width": "CapsuleHalfWidth",
        "flags": "Flags",
    }

    owner_name: str = ""
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    capsule_radius: float = 0.0
    capsule_len: float = 0.0
    capsule_half_height: float = 0.0
    capsule_half_width: float = 0.0
    flags: int = 0


@dataclasses.dataclass(slots=True)
class LightEffectExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefLightEffect"
    META_LIST_TYPES: ClassVar[dict[str, type[MetaBackedStruct]]] = {"instances": LightAttrDef}

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    instances: list[LightAttrDef] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(slots=True)
class ParticleEffectExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefParticleEffect"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    offset_rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    fx_name: str = ""
    fx_type: int = 0
    bone_tag: int = 0
    scale: float = 1.0
    probability: int = 100
    flags: int = 0
    color: int = 0


@dataclasses.dataclass(slots=True)
class AudioCollisionSettingsExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefAudioCollisionSettings"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    settings: int | str = 0


@dataclasses.dataclass(slots=True)
class AudioEmitterExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefAudioEmitter"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    offset_rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    effect_hash: int | str = 0


@dataclasses.dataclass(slots=True)
class ExplosionEffectExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefExplosionEffect"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    offset_rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    explosion_name: str = ""
    bone_tag: int = 0
    explosion_tag: int = 0
    explosion_type: int = 0
    flags: int = 0


@dataclasses.dataclass(slots=True)
class SpawnPointExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefSpawnPoint"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    offset_rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    spawn_type: int | str = 0
    ped_type: int | str = 0
    group: int | str = 0
    interior: int | str = 0
    required_imap: int | str = 0
    available_in_mp_sp: int = 0
    probability: float = 0.0
    time_till_ped_leaves: float = 0.0
    radius: float = 0.0
    start: int = 0
    end: int = 0
    flags: int = 0
    high_pri: bool = False
    extended_range: bool = False
    short_range: bool = False


@dataclasses.dataclass(slots=True)
class DoorExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefDoor"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    enable_limit_angle: bool = False
    starts_locked: bool = False
    can_break: bool = False
    limit_angle: float = 0.0
    door_target_ratio: float = 0.0
    audio_hash: int | str = 0


@dataclasses.dataclass(slots=True)
class SpawnPointOverrideExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefSpawnPointOverride"
    META_FIELD_MAP: ClassVar[dict[str, str]] = {
        "scenario_type": "ScenarioType",
        "time_start_override": "iTimeStartOverride",
        "time_end_override": "iTimeEndOverride",
        "group": "Group",
        "model_set": "ModelSet",
        "availability_in_mp_sp": "AvailabilityInMpSp",
        "flags": "Flags",
        "radius": "Radius",
        "time_till_ped_leaves": "TimeTillPedLeaves",
    }

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scenario_type: int | str = 0
    time_start_override: int = 0
    time_end_override: int = 0
    group: int | str = 0
    model_set: int | str = 0
    availability_in_mp_sp: int = 0
    flags: int = 0
    radius: float = 0.0
    time_till_ped_leaves: float = 0.0


@dataclasses.dataclass(slots=True)
class LadderExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefLadder"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bottom: tuple[float, float, float] = (0.0, 0.0, 0.0)
    top: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    material_type: int = 0
    template: int | str = 0
    can_get_off_at_top: bool = True
    can_get_off_at_bottom: bool = True


@dataclasses.dataclass(slots=True)
class BuoyancyExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefBuoyancy"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclasses.dataclass(slots=True)
class ExpressionExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefExpression"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    expression_dictionary_name: int | str = 0
    expression_name: int | str = 0
    creature_metadata_name: int | str = 0
    initialise_on_collision: bool = False


@dataclasses.dataclass(slots=True)
class LightShaftExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefLightShaft"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    corner_a: tuple[float, float, float] = (0.0, 0.0, 0.0)
    corner_b: tuple[float, float, float] = (0.0, 0.0, 0.0)
    corner_c: tuple[float, float, float] = (0.0, 0.0, 0.0)
    corner_d: tuple[float, float, float] = (0.0, 0.0, 0.0)
    direction: tuple[float, float, float] = (0.0, 0.0, -1.0)
    direction_amount: float = 0.0
    length: float = 0.0
    fade_in_time_start: float = 0.0
    fade_in_time_end: float = 0.0
    fade_out_time_start: float = 0.0
    fade_out_time_end: float = 0.0
    fade_distance_start: float = 0.0
    fade_distance_end: float = 0.0
    color: int = 0
    intensity: float = 0.0
    flashiness: int = 0
    flags: int = 0
    density_type: int = 0
    volume_type: int = 0
    softness: float = 0.0
    scale_by_sun_intensity: bool = False


@dataclasses.dataclass(slots=True)
class WindDisturbanceExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefWindDisturbance"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    offset_rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    disturbance_type: int = 0
    bone_tag: int = 0
    size: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    strength: float = 0.0
    flags: int = 0


@dataclasses.dataclass(slots=True)
class ProcObjectExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "CExtensionDefProcObject"

    name: int | str = 0
    offset_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius_inner: float = 0.0
    radius_outer: float = 0.0
    spacing: float = 0.0
    min_scale: float = 0.0
    max_scale: float = 0.0
    min_scale_z: float = 0.0
    max_scale_z: float = 0.0
    min_z_offset: float = 0.0
    max_z_offset: float = 0.0
    object_hash: int | str = 0
    flags: int = 0


@dataclasses.dataclass(slots=True)
class VerletClothCustomBoundsExtension(MetaBackedStruct):
    META_NAME: ClassVar[str] = "rage__phVerletClothCustomBounds"
    META_FIELD_MAP: ClassVar[dict[str, str]] = {"collision_data": "CollisionData"}
    META_LIST_TYPES: ClassVar[dict[str, type[MetaBackedStruct]]] = {"collision_data": CapsuleBoundDef}

    name: int | str = 0
    collision_data: list[CapsuleBoundDef] = dataclasses.field(default_factory=list)


KNOWN_EXTENSION_TYPES: tuple[type[MetaBackedStruct], ...] = (
    LightEffectExtension,
    ParticleEffectExtension,
    AudioCollisionSettingsExtension,
    AudioEmitterExtension,
    ExplosionEffectExtension,
    SpawnPointExtension,
    DoorExtension,
    SpawnPointOverrideExtension,
    LadderExtension,
    BuoyancyExtension,
    ExpressionExtension,
    LightShaftExtension,
    WindDisturbanceExtension,
    ProcObjectExtension,
    VerletClothCustomBoundsExtension,
)


EXTENSION_TYPES_BY_META_NAME = {extension_type.META_NAME: extension_type for extension_type in KNOWN_EXTENSION_TYPES}


def extension_from_meta(value: Any) -> Any:
    if isinstance(value, RawStruct):
        return value
    if not isinstance(value, Mapping):
        return value
    meta_name_value = value.get("_meta_name")
    extension_type = EXTENSION_TYPES_BY_META_NAME.get(str(meta_name_value))
    if extension_type is None:
        return value
    return extension_type.from_meta(value)


def extensions_from_meta(values: Any) -> list[Any]:
    return [extension_from_meta(value) for value in (values or [])]


def extension_to_meta(value: Any) -> Any:
    return value.to_meta() if hasattr(value, "to_meta") else value


def extensions_to_meta(values: Any) -> list[Any]:
    return [extension_to_meta(value) for value in (values or [])]


__all__ = [
    "AudioCollisionSettingsExtension",
    "AudioEmitterExtension",
    "BuoyancyExtension",
    "CapsuleBoundDef",
    "DoorExtension",
    "EXTENSION_STRUCT_INFOS",
    "EXTENSION_TYPES_BY_META_NAME",
    "ExpressionExtension",
    "ExplosionEffectExtension",
    "KNOWN_EXTENSION_TYPES",
    "LadderExtension",
    "LightAttrDef",
    "LightEffectExtension",
    "LightShaftExtension",
    "ParticleEffectExtension",
    "ProcObjectExtension",
    "SpawnPointExtension",
    "SpawnPointOverrideExtension",
    "VerletClothCustomBoundsExtension",
    "WindDisturbanceExtension",
    "extension_from_meta",
    "extension_to_meta",
    "extensions_from_meta",
    "extensions_to_meta",
]
