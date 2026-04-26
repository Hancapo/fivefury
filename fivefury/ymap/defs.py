from __future__ import annotations

from ..extensions import EXTENSION_STRUCT_INFOS
from ..metahash import HashLike, MetaHash
from ..meta import MetaEnumEntry, MetaEnumInfo, MetaStructInfo
from ..meta.defs import KNOWN_ENUMS, MetaDataType, meta_name
from ..meta.utils import meta_array_info as _arrayinfo, meta_field_entry as _entry
from .surfaces import YMAP_SURFACE_STRUCT_INFOS


def _enum_info(name: str) -> MetaEnumInfo:
    info = KNOWN_ENUMS[name]
    return MetaEnumInfo(
        name_hash=info.name_hash,
        key=info.key,
        entries=[MetaEnumEntry(meta_name(entry_name), entry_value) for entry_name, entry_value in info.items],
    )


def _resource_text(value: HashLike | None) -> str:
    if isinstance(value, MetaHash):
        return value.text or ""
    if isinstance(value, str):
        return value
    return ""


def _ensure_base_name(value: HashLike | None, extension: str) -> HashLike:
    if isinstance(value, MetaHash):
        raw = value.raw
        if isinstance(raw, str):
            text = raw
            if text.lower().endswith(extension):
                text = text[: -len(extension)]
            return MetaHash.from_value(text or raw)
        return value
    if isinstance(value, str):
        text = value
        if text.lower().endswith(extension):
            text = text[: -len(extension)]
        return MetaHash.from_value(text or value)
    return MetaHash.from_value(value or 0)


YMAP_STRUCT_INFOS = [
    MetaStructInfo(
        name_hash=meta_name("CEntityDef"),
        key=1825799514,
        unknown=1024,
        structure_size=128,
        entries=[
            _entry("archetypeName", 8, MetaDataType.HASH),
            _entry("flags", 12, MetaDataType.UNSIGNED_INT),
            _entry("guid", 16, MetaDataType.UNSIGNED_INT),
            _entry("position", 32, MetaDataType.FLOAT_XYZ),
            _entry("rotation", 48, MetaDataType.FLOAT_XYZW),
            _entry("scaleXY", 64, MetaDataType.FLOAT),
            _entry("scaleZ", 68, MetaDataType.FLOAT),
            _entry("parentIndex", 72, MetaDataType.SIGNED_INT),
            _entry("lodDist", 76, MetaDataType.FLOAT),
            _entry("childLodDist", 80, MetaDataType.FLOAT),
            _entry("lodLevel", 84, MetaDataType.INT_ENUM, ref_key="rage__eLodType"),
            _entry("numChildren", 88, MetaDataType.UNSIGNED_INT),
            _entry("priorityLevel", 92, MetaDataType.INT_ENUM, ref_key="rage__ePriorityLevel"),
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("extensions", 96, MetaDataType.ARRAY, ref_index=13),
            _entry("ambientOcclusionMultiplier", 112, MetaDataType.SIGNED_INT),
            _entry("artificialAmbientOcclusion", 116, MetaDataType.SIGNED_INT),
            _entry("tintValue", 120, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CMloInstanceDef"),
        key=2151576752,
        unknown=1024,
        structure_size=160,
        entries=[
            _entry("archetypeName", 8, MetaDataType.HASH),
            _entry("flags", 12, MetaDataType.UNSIGNED_INT),
            _entry("guid", 16, MetaDataType.UNSIGNED_INT),
            _entry("position", 32, MetaDataType.FLOAT_XYZ),
            _entry("rotation", 48, MetaDataType.FLOAT_XYZW),
            _entry("scaleXY", 64, MetaDataType.FLOAT),
            _entry("scaleZ", 68, MetaDataType.FLOAT),
            _entry("parentIndex", 72, MetaDataType.SIGNED_INT),
            _entry("lodDist", 76, MetaDataType.FLOAT),
            _entry("childLodDist", 80, MetaDataType.FLOAT),
            _entry("lodLevel", 84, MetaDataType.INT_ENUM, ref_key="rage__eLodType"),
            _entry("numChildren", 88, MetaDataType.UNSIGNED_INT),
            _entry("priorityLevel", 92, MetaDataType.INT_ENUM, ref_key="rage__ePriorityLevel"),
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("extensions", 96, MetaDataType.ARRAY, ref_index=13),
            _entry("ambientOcclusionMultiplier", 112, MetaDataType.SIGNED_INT),
            _entry("artificialAmbientOcclusion", 116, MetaDataType.SIGNED_INT),
            _entry("tintValue", 120, MetaDataType.UNSIGNED_INT),
            _entry("groupId", 128, MetaDataType.UNSIGNED_INT),
            _entry("floorId", 132, MetaDataType.UNSIGNED_INT),
            _arrayinfo(MetaDataType.HASH),
            _entry("defaultEntitySets", 136, MetaDataType.ARRAY, ref_index=20),
            _entry("numExitPortals", 152, MetaDataType.UNSIGNED_INT),
            _entry("MLOInstflags", 156, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CTimeCycleModifier"),
        key=2683420777,
        unknown=1024,
        structure_size=64,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("minExtents", 16, MetaDataType.FLOAT_XYZ),
            _entry("maxExtents", 32, MetaDataType.FLOAT_XYZ),
            _entry("percentage", 48, MetaDataType.FLOAT),
            _entry("range", 52, MetaDataType.FLOAT),
            _entry("startHour", 56, MetaDataType.UNSIGNED_INT),
            _entry("endHour", 60, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CCarGen"),
        key=2345238261,
        unknown=1024,
        structure_size=80,
        entries=[
            _entry("position", 16, MetaDataType.FLOAT_XYZ),
            _entry("orientX", 32, MetaDataType.FLOAT),
            _entry("orientY", 36, MetaDataType.FLOAT),
            _entry("perpendicularLength", 40, MetaDataType.FLOAT),
            _entry("carModel", 44, MetaDataType.HASH),
            _entry("flags", 48, MetaDataType.UNSIGNED_INT),
            _entry("bodyColorRemap1", 52, MetaDataType.SIGNED_INT),
            _entry("bodyColorRemap2", 56, MetaDataType.SIGNED_INT),
            _entry("bodyColorRemap3", 60, MetaDataType.SIGNED_INT),
            _entry("bodyColorRemap4", 64, MetaDataType.SIGNED_INT),
            _entry("popGroup", 68, MetaDataType.HASH),
            _entry("livery", 72, MetaDataType.SIGNED_BYTE),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CBlockDesc"),
        key=2015795449,
        unknown=768,
        structure_size=72,
        entries=[
            _entry("version", 0, MetaDataType.UNSIGNED_INT),
            _entry("flags", 4, MetaDataType.UNSIGNED_INT),
            _entry("name", 8, MetaDataType.CHAR_POINTER),
            _entry("exportedBy", 24, MetaDataType.CHAR_POINTER),
            _entry("owner", 40, MetaDataType.CHAR_POINTER),
            _entry("time", 56, MetaDataType.CHAR_POINTER),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("FloatXYZ"),
        key=0,
        unknown=256,
        structure_size=16,
        entries=[
            _entry("x", 0, MetaDataType.FLOAT),
            _entry("y", 4, MetaDataType.FLOAT),
            _entry("z", 8, MetaDataType.FLOAT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("BoxOccluder"),
        key=1831736438,
        unknown=256,
        structure_size=16,
        entries=[
            _entry("iCenterX", 0, MetaDataType.SIGNED_SHORT),
            _entry("iCenterY", 2, MetaDataType.SIGNED_SHORT),
            _entry("iCenterZ", 4, MetaDataType.SIGNED_SHORT),
            _entry("iCosZ", 6, MetaDataType.SIGNED_SHORT),
            _entry("iLength", 8, MetaDataType.SIGNED_SHORT),
            _entry("iWidth", 10, MetaDataType.SIGNED_SHORT),
            _entry("iHeight", 12, MetaDataType.SIGNED_SHORT),
            _entry("iSinZ", 14, MetaDataType.SIGNED_SHORT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("OccludeModel"),
        key=1172796107,
        unknown=1024,
        structure_size=64,
        entries=[
            _entry("bmin", 0, MetaDataType.FLOAT_XYZ),
            _entry("bmax", 16, MetaDataType.FLOAT_XYZ),
            _entry("dataSize", 32, MetaDataType.UNSIGNED_INT),
            _arrayinfo(MetaDataType.UNSIGNED_BYTE),
            _entry("verts", 40, MetaDataType.DATA_BLOCK_POINTER, unknown_9h=4, ref_index=3, ref_key=2),
            _entry("numVertsInBytes", 48, MetaDataType.UNSIGNED_SHORT),
            _entry("numTris", 50, MetaDataType.UNSIGNED_SHORT),
            _entry("flags", 52, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CLODLight"),
        key=2325189228,
        unknown=768,
        structure_size=136,
        entries=[
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="FloatXYZ"),
            _entry("direction", 8, MetaDataType.ARRAY, ref_index=0),
            _arrayinfo(MetaDataType.FLOAT),
            _entry("falloff", 24, MetaDataType.ARRAY, ref_index=2),
            _arrayinfo(MetaDataType.FLOAT),
            _entry("falloffExponent", 40, MetaDataType.ARRAY, ref_index=4),
            _arrayinfo(MetaDataType.UNSIGNED_INT),
            _entry("timeAndStateFlags", 56, MetaDataType.ARRAY, ref_index=6),
            _arrayinfo(MetaDataType.UNSIGNED_INT),
            _entry("hash", 72, MetaDataType.ARRAY, ref_index=8),
            _arrayinfo(MetaDataType.UNSIGNED_BYTE),
            _entry("coneInnerAngle", 88, MetaDataType.ARRAY, ref_index=10),
            _arrayinfo(MetaDataType.UNSIGNED_BYTE),
            _entry("coneOuterAngleOrCapExt", 104, MetaDataType.ARRAY, ref_index=12),
            _arrayinfo(MetaDataType.UNSIGNED_BYTE),
            _entry("coronaIntensity", 120, MetaDataType.ARRAY, ref_index=14),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CDistantLODLight"),
        key=2820908419,
        unknown=768,
        structure_size=48,
        entries=[
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="FloatXYZ"),
            _entry("position", 8, MetaDataType.ARRAY, ref_index=0),
            _arrayinfo(MetaDataType.UNSIGNED_INT),
            _entry("RGBI", 24, MetaDataType.ARRAY, ref_index=2),
            _entry("numStreetLights", 40, MetaDataType.UNSIGNED_SHORT),
            _entry("category", 42, MetaDataType.UNSIGNED_SHORT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("rage__fwContainerLodDef"),
        key=372253349,
        unknown=256,
        structure_size=8,
        entries=[
            _entry("name", 0, MetaDataType.HASH),
            _entry("parentIndex", 4, MetaDataType.UNSIGNED_INT),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("CMapData"),
        key=3448101671,
        unknown=1024,
        structure_size=512,
        entries=[
            _entry("name", 8, MetaDataType.HASH),
            _entry("parent", 12, MetaDataType.HASH),
            _entry("flags", 16, MetaDataType.UNSIGNED_INT),
            _entry("contentFlags", 20, MetaDataType.UNSIGNED_INT),
            _entry("streamingExtentsMin", 32, MetaDataType.FLOAT_XYZ),
            _entry("streamingExtentsMax", 48, MetaDataType.FLOAT_XYZ),
            _entry("entitiesExtentsMin", 64, MetaDataType.FLOAT_XYZ),
            _entry("entitiesExtentsMax", 80, MetaDataType.FLOAT_XYZ),
            _arrayinfo(MetaDataType.STRUCTURE_POINTER),
            _entry("entities", 96, MetaDataType.ARRAY, ref_index=8),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="rage__fwContainerLodDef"),
            _entry("containerLods", 112, MetaDataType.ARRAY, ref_index=10),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="BoxOccluder"),
            _entry("boxOccluders", 128, MetaDataType.ARRAY, unknown_9h=4, ref_index=12),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="OccludeModel"),
            _entry("occludeModels", 144, MetaDataType.ARRAY, unknown_9h=4, ref_index=14),
            _arrayinfo(MetaDataType.HASH),
            _entry("physicsDictionaries", 160, MetaDataType.ARRAY, ref_index=16),
            _entry("instancedData", 176, MetaDataType.STRUCTURE, ref_key="rage__fwInstancedMapData"),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CTimeCycleModifier"),
            _entry("timeCycleModifiers", 224, MetaDataType.ARRAY, ref_index=19),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="CCarGen"),
            _entry("carGenerators", 240, MetaDataType.ARRAY, ref_index=21),
            _entry("LODLightsSOA", 256, MetaDataType.STRUCTURE, ref_key="CLODLight"),
            _entry("DistantLODLightsSOA", 392, MetaDataType.STRUCTURE, ref_key="CDistantLODLight"),
            _entry("block", 440, MetaDataType.STRUCTURE, ref_key="CBlockDesc"),
        ],
    ),
]

YMAP_STRUCT_INFOS.extend(YMAP_SURFACE_STRUCT_INFOS)
YMAP_STRUCT_INFOS.extend(EXTENSION_STRUCT_INFOS)

YMAP_ENUM_INFOS = [
    _enum_info("rage__fwArchetypeDef__eAssetType"),
    _enum_info("rage__eLodType"),
    _enum_info("rage__ePriorityLevel"),
]






