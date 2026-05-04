from .blocks import BlockDesc, CarGen, ContainerLodDef, PhysicsDictionary, TimeCycleModifier
from .defs import YMAP_ENUM_INFOS, YMAP_STRUCT_INFOS
from .enums import (
    YmapCarGenFlags,
    YmapContentFlags,
    YmapEntityFlags,
    YmapFlags,
    YmapLodLevel,
    YmapLodLightCategory,
    YmapLodLightType,
    YmapMloInstanceFlags,
    YmapPriorityLevel,
)
from .entities import EntityDef, MloInstanceDef
from .model import Ymap, read_ymap, save_ymap
from .surfaces import (
    Aabb,
    AngleMode,
    BoxOccluder,
    DistantLodLightsSoa,
    GrassInstance,
    GrassInstanceBatch,
    InstancedMapData,
    LodLight,
    LodLightsSoa,
    MAX_LOD_LIGHT_CAPSULE_EXTENT,
    MAX_LOD_LIGHT_CONE_ANGLE,
    MAX_LOD_LIGHT_CORONA_INTENSITY,
    OccludeModel,
)

Entity = EntityDef
MloInstance = MloInstanceDef
CarGenerator = CarGen
Block = BlockDesc

__all__ = [
    "Aabb",
    "AngleMode",
    "Block",
    "BlockDesc",
    "BoxOccluder",
    "CarGen",
    "CarGenerator",
    "ContainerLodDef",
    "DistantLodLightsSoa",
    "Entity",
    "EntityDef",
    "GrassInstance",
    "GrassInstanceBatch",
    "InstancedMapData",
    "LodLight",
    "LodLightsSoa",
    "MAX_LOD_LIGHT_CAPSULE_EXTENT",
    "MAX_LOD_LIGHT_CONE_ANGLE",
    "MAX_LOD_LIGHT_CORONA_INTENSITY",
    "MloInstance",
    "MloInstanceDef",
    "OccludeModel",
    "PhysicsDictionary",
    "TimeCycleModifier",
    "YmapCarGenFlags",
    "YmapContentFlags",
    "YmapEntityFlags",
    "YmapFlags",
    "YmapLodLevel",
    "YmapLodLightCategory",
    "YmapLodLightType",
    "YmapMloInstanceFlags",
    "YmapPriorityLevel",
    "YMAP_ENUM_INFOS",
    "YMAP_STRUCT_INFOS",
    "Ymap",
    "read_ymap",
    "save_ymap",
]
