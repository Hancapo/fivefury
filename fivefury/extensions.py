from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any, ClassVar

from .meta import MetaFieldInfo, MetaStructInfo, RawStruct
from .meta_defs import META_TYPE_NAME_ARRAYINFO, MetaDataType, meta_name


def _entry(
    name: str | int,
    offset: int,
    data_type: MetaDataType,
    unknown_9h: int = 0,
    ref_index: int = 0,
    ref_key: str | int = 0,
) -> MetaFieldInfo:
    name_hash = name if isinstance(name, int) else meta_name(name)
    ref_hash = meta_name(ref_key) if isinstance(ref_key, str) else ref_key
    return MetaFieldInfo(name_hash, offset, data_type, unknown_9h, ref_index, ref_hash)


def _arrayinfo(data_type: MetaDataType, *, ref_key: str | int = 0, unknown_9h: int = 0) -> MetaFieldInfo:
    ref_hash = meta_name(ref_key) if isinstance(ref_key, str) else ref_key
    return MetaFieldInfo(META_TYPE_NAME_ARRAYINFO, 0, data_type, unknown_9h, 0, ref_hash)


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


@dataclasses.dataclass(slots=True)
class MetaBackedStruct:
    META_NAME: ClassVar[str] = ""
    META_FIELD_MAP: ClassVar[dict[str, str]] = {}
    META_LIST_TYPES: ClassVar[dict[str, type["MetaBackedStruct"]]] = {}

    def to_meta(self) -> dict[str, Any]:
        data: dict[str, Any] = {"_meta_name_hash": meta_name(self.META_NAME)}
        for field in dataclasses.fields(self):
            attr = field.name
            meta_field = self.META_FIELD_MAP.get(attr, _snake_to_camel(attr))
            data[meta_field] = self._serialize_field(attr, getattr(self, attr))
        return data

    def _serialize_field(self, attr: str, value: Any) -> Any:
        if isinstance(value, list):
            return [item.to_meta() if hasattr(item, "to_meta") else item for item in value]
        if hasattr(value, "to_meta") and not isinstance(value, (str, bytes, bytearray)):
            return value.to_meta()
        return value

    @classmethod
    def from_meta(cls, value: Any) -> "MetaBackedStruct":
        if not isinstance(value, Mapping):
            return cls()
        kwargs: dict[str, Any] = {}
        for field in dataclasses.fields(cls):
            attr = field.name
            meta_field = cls.META_FIELD_MAP.get(attr, _snake_to_camel(attr))
            if meta_field not in value:
                continue
            kwargs[attr] = cls._deserialize_field(attr, value.get(meta_field))
        return cls(**kwargs)

    @classmethod
    def _deserialize_field(cls, attr: str, value: Any) -> Any:
        item_type = cls.META_LIST_TYPES.get(attr)
        if item_type is not None:
            return [item_type.from_meta(item) if isinstance(item, Mapping) else item for item in (value or [])]
        return value


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


EXTENSION_STRUCT_INFOS = [
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefLightEffect"),
        key=2436199897,
        unknown=1024,
        structure_size=48,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CLightAttrDef"),
            _entry("instances", 32, MetaDataType.ARRAY, ref_index=2),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CLightAttrDef"),
        key=2363260268,
        unknown=1024,
        structure_size=160,
        entries=[
            _arrayinfo(MetaDataType.FLOAT),
            _entry("posn", 8, MetaDataType.ARRAY_OF_BYTES, ref_index=0, ref_key=3),
            _arrayinfo(MetaDataType.UNSIGNED_BYTE),
            _entry("colour", 20, MetaDataType.ARRAY_OF_BYTES, ref_index=2, ref_key=3),
            _entry("flashiness", 23, MetaDataType.UNSIGNED_BYTE),
            _entry("intensity", 24, MetaDataType.FLOAT),
            _entry("flags", 28, MetaDataType.UNSIGNED_INT),
            _entry("boneTag", 32, MetaDataType.SIGNED_SHORT),
            _entry("lightType", 34, MetaDataType.UNSIGNED_BYTE),
            _entry("groupId", 35, MetaDataType.UNSIGNED_BYTE),
            _entry("timeFlags", 36, MetaDataType.UNSIGNED_INT),
            _entry("falloff", 40, MetaDataType.FLOAT),
            _entry("falloffExponent", 44, MetaDataType.FLOAT),
            _arrayinfo(MetaDataType.FLOAT),
            _entry("cullingPlane", 48, MetaDataType.ARRAY_OF_BYTES, ref_index=12, ref_key=4),
            _entry("shadowBlur", 64, MetaDataType.UNSIGNED_BYTE),
            _entry("padding1", 65, MetaDataType.UNSIGNED_BYTE),
            _entry("padding2", 66, MetaDataType.SIGNED_SHORT),
            _entry("padding3", 68, MetaDataType.UNSIGNED_INT),
            _entry("volIntensity", 72, MetaDataType.FLOAT),
            _entry("volSizeScale", 76, MetaDataType.FLOAT),
            _arrayinfo(MetaDataType.UNSIGNED_BYTE),
            _entry("volOuterColour", 80, MetaDataType.ARRAY_OF_BYTES, ref_index=20, ref_key=3),
            _entry("lightHash", 83, MetaDataType.UNSIGNED_BYTE),
            _entry("volOuterIntensity", 84, MetaDataType.FLOAT),
            _entry("coronaSize", 88, MetaDataType.FLOAT),
            _entry("volOuterExponent", 92, MetaDataType.FLOAT),
            _entry("lightFadeDistance", 96, MetaDataType.UNSIGNED_BYTE),
            _entry("shadowFadeDistance", 97, MetaDataType.UNSIGNED_BYTE),
            _entry("specularFadeDistance", 98, MetaDataType.UNSIGNED_BYTE),
            _entry("volumetricFadeDistance", 99, MetaDataType.UNSIGNED_BYTE),
            _entry("shadowNearClip", 100, MetaDataType.FLOAT),
            _entry("coronaIntensity", 104, MetaDataType.FLOAT),
            _entry("coronaZBias", 108, MetaDataType.FLOAT),
            _arrayinfo(MetaDataType.FLOAT),
            _entry("direction", 112, MetaDataType.ARRAY_OF_BYTES, ref_index=31, ref_key=3),
            _arrayinfo(MetaDataType.FLOAT),
            _entry("tangent", 124, MetaDataType.ARRAY_OF_BYTES, ref_index=33, ref_key=3),
            _entry("coneInnerAngle", 136, MetaDataType.FLOAT),
            _entry("coneOuterAngle", 140, MetaDataType.FLOAT),
            _arrayinfo(MetaDataType.FLOAT),
            _entry("extents", 144, MetaDataType.ARRAY_OF_BYTES, ref_index=37, ref_key=3),
            _entry("projectedTextureKey", 156, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefParticleEffect"),
        key=466596385,
        unknown=1024,
        structure_size=96,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("offsetRotation", 32, MetaDataType.FLOAT_XYZW),
            _entry("fxName", 48, MetaDataType.CHAR_POINTER),
            _entry("fxType", 64, MetaDataType.SIGNED_INT),
            _entry("boneTag", 68, MetaDataType.SIGNED_INT),
            _entry("scale", 72, MetaDataType.FLOAT),
            _entry("probability", 76, MetaDataType.SIGNED_INT),
            _entry("flags", 80, MetaDataType.SIGNED_INT),
            _entry("color", 84, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefAudioCollisionSettings"),
        key=2701897500,
        unknown=1024,
        structure_size=48,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("settings", 32, MetaDataType.HASH),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefAudioEmitter"),
        key=15929839,
        unknown=1024,
        structure_size=64,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("offsetRotation", 32, MetaDataType.FLOAT_XYZW),
            _entry("effectHash", 48, MetaDataType.HASH),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefExplosionEffect"),
        key=2840366784,
        unknown=1024,
        structure_size=80,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("offsetRotation", 32, MetaDataType.FLOAT_XYZW),
            _entry("explosionName", 48, MetaDataType.CHAR_POINTER),
            _entry("boneTag", 64, MetaDataType.SIGNED_INT),
            _entry("explosionTag", 68, MetaDataType.SIGNED_INT),
            _entry("explosionType", 72, MetaDataType.SIGNED_INT),
            _entry("flags", 76, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefSpawnPoint"),
        key=3077340721,
        unknown=1024,
        structure_size=96,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("offsetRotation", 32, MetaDataType.FLOAT_XYZW),
            _entry("spawnType", 48, MetaDataType.HASH),
            _entry("pedType", 52, MetaDataType.HASH),
            _entry("group", 56, MetaDataType.HASH),
            _entry("interior", 60, MetaDataType.HASH),
            _entry("requiredImap", 64, MetaDataType.HASH),
            _entry("availableInMpSp", 68, MetaDataType.INT_ENUM, ref_key="CSpawnPoint__AvailabilityMpSp"),
            _entry("probability", 72, MetaDataType.FLOAT),
            _entry("timeTillPedLeaves", 76, MetaDataType.FLOAT),
            _entry("radius", 80, MetaDataType.FLOAT),
            _entry("start", 84, MetaDataType.UNSIGNED_BYTE),
            _entry("end", 85, MetaDataType.UNSIGNED_BYTE),
            _entry("flags", 88, MetaDataType.INT_FLAGS_2, ref_key="CScenarioPointFlags__Flags"),
            _entry("highPri", 92, MetaDataType.BOOLEAN),
            _entry("extendedRange", 93, MetaDataType.BOOLEAN),
            _entry("shortRange", 94, MetaDataType.BOOLEAN),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefDoor"),
        key=2671601385,
        unknown=1024,
        structure_size=48,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("enableLimitAngle", 32, MetaDataType.BOOLEAN),
            _entry("startsLocked", 33, MetaDataType.BOOLEAN),
            _entry("canBreak", 34, MetaDataType.BOOLEAN),
            _entry("limitAngle", 36, MetaDataType.FLOAT),
            _entry("doorTargetRatio", 40, MetaDataType.FLOAT),
            _entry("audioHash", 44, MetaDataType.HASH),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefSpawnPointOverride"),
        key=2551875873,
        unknown=1024,
        structure_size=64,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("ScenarioType", 32, MetaDataType.HASH),
            _entry("iTimeStartOverride", 36, MetaDataType.UNSIGNED_BYTE),
            _entry("iTimeEndOverride", 37, MetaDataType.UNSIGNED_BYTE),
            _entry("Group", 40, MetaDataType.HASH),
            _entry("ModelSet", 44, MetaDataType.HASH),
            _entry("AvailabilityInMpSp", 48, MetaDataType.INT_ENUM, ref_key="CSpawnPoint__AvailabilityMpSp"),
            _entry("Flags", 52, MetaDataType.INT_FLAGS_2, ref_key="CScenarioPointFlags__Flags"),
            _entry("Radius", 56, MetaDataType.FLOAT),
            _entry("TimeTillPedLeaves", 60, MetaDataType.FLOAT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefLadder"),
        key=1978210597,
        unknown=1024,
        structure_size=96,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("bottom", 32, MetaDataType.FLOAT_XYZ),
            _entry("top", 48, MetaDataType.FLOAT_XYZ),
            _entry("normal", 64, MetaDataType.FLOAT_XYZ),
            _entry("materialType", 80, MetaDataType.INT_ENUM, ref_key="CExtensionDefLadderMaterialType"),
            _entry("template", 84, MetaDataType.HASH),
            _entry("canGetOffAtTop", 88, MetaDataType.BOOLEAN),
            _entry("canGetOffAtBottom", 89, MetaDataType.BOOLEAN),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefBuoyancy"),
        key=2383039928,
        unknown=1024,
        structure_size=32,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefExpression"),
        key=24441706,
        unknown=1024,
        structure_size=48,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("expressionDictionaryName", 32, MetaDataType.HASH),
            _entry("expressionName", 36, MetaDataType.HASH),
            _entry("creatureMetadataName", 40, MetaDataType.HASH),
            _entry("initialiseOnCollision", 44, MetaDataType.BOOLEAN),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefLightShaft"),
        key=2526429398,
        unknown=1024,
        structure_size=176,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("cornerA", 32, MetaDataType.FLOAT_XYZ),
            _entry("cornerB", 48, MetaDataType.FLOAT_XYZ),
            _entry("cornerC", 64, MetaDataType.FLOAT_XYZ),
            _entry("cornerD", 80, MetaDataType.FLOAT_XYZ),
            _entry("direction", 96, MetaDataType.FLOAT_XYZ),
            _entry("directionAmount", 112, MetaDataType.FLOAT),
            _entry("length", 116, MetaDataType.FLOAT),
            _entry("fadeInTimeStart", 120, MetaDataType.FLOAT),
            _entry("fadeInTimeEnd", 124, MetaDataType.FLOAT),
            _entry("fadeOutTimeStart", 128, MetaDataType.FLOAT),
            _entry("fadeOutTimeEnd", 132, MetaDataType.FLOAT),
            _entry("fadeDistanceStart", 136, MetaDataType.FLOAT),
            _entry("fadeDistanceEnd", 140, MetaDataType.FLOAT),
            _entry("color", 144, MetaDataType.UNSIGNED_INT),
            _entry("intensity", 148, MetaDataType.FLOAT),
            _entry("flashiness", 152, MetaDataType.UNSIGNED_BYTE),
            _entry("flags", 156, MetaDataType.UNSIGNED_INT),
            _entry("densityType", 160, MetaDataType.INT_ENUM, ref_key="CExtensionDefLightShaftDensityType"),
            _entry("volumeType", 164, MetaDataType.INT_ENUM, ref_key="CExtensionDefLightShaftVolumeType"),
            _entry("softness", 168, MetaDataType.FLOAT),
            _entry("scaleBySunIntensity", 172, MetaDataType.BOOLEAN),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefWindDisturbance"),
        key=3971538917,
        unknown=1024,
        structure_size=96,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("offsetRotation", 32, MetaDataType.FLOAT_XYZW),
            _entry("disturbanceType", 48, MetaDataType.SIGNED_INT),
            _entry("boneTag", 52, MetaDataType.SIGNED_INT),
            _entry("size", 64, MetaDataType.FLOAT_XYZW),
            _entry("strength", 80, MetaDataType.FLOAT),
            _entry("flags", 84, MetaDataType.SIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CExtensionDefProcObject"),
        key=3965391891,
        unknown=1024,
        structure_size=80,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("offsetPosition", 16, MetaDataType.FLOAT_XYZ),
            _entry("radiusInner", 32, MetaDataType.FLOAT),
            _entry("radiusOuter", 36, MetaDataType.FLOAT),
            _entry("spacing", 40, MetaDataType.FLOAT),
            _entry("minScale", 44, MetaDataType.FLOAT),
            _entry("maxScale", 48, MetaDataType.FLOAT),
            _entry("minScaleZ", 52, MetaDataType.FLOAT),
            _entry("maxScaleZ", 56, MetaDataType.FLOAT),
            _entry("minZOffset", 60, MetaDataType.FLOAT),
            _entry("maxZOffset", 64, MetaDataType.FLOAT),
            _entry("objectHash", 68, MetaDataType.HASH),
            _entry("flags", 72, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("rage__phCapsuleBoundDef"),
        key=2859775340,
        unknown=1024,
        structure_size=96,
        entries=[
            _entry("OwnerName", 0, MetaDataType.CHAR_POINTER),
            _entry("Rotation", 16, MetaDataType.FLOAT_XYZW),
            _entry("Position", 32, MetaDataType.FLOAT_XYZ),
            _entry("Normal", 48, MetaDataType.FLOAT_XYZ),
            _entry("CapsuleRadius", 64, MetaDataType.FLOAT),
            _entry("CapsuleLen", 68, MetaDataType.FLOAT),
            _entry("CapsuleHalfHeight", 72, MetaDataType.FLOAT),
            _entry("CapsuleHalfWidth", 76, MetaDataType.FLOAT),
            _entry("Flags", 80, MetaDataType.INT_FLAGS_2, ref_key="rage__phCapsuleBoundDef__enCollisionBoundDef"),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("rage__phVerletClothCustomBounds"),
        key=2075461750,
        unknown=1024,
        structure_size=32,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="rage__phCapsuleBoundDef"),
            _entry("CollisionData", 16, MetaDataType.ARRAY, ref_index=1),
        ],
    ),
]


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
