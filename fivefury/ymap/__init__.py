from .blocks import BlockDesc, CarGen, ContainerLodDef, TimeCycleModifier
from .defs import YMAP_ENUM_INFOS, YMAP_STRUCT_INFOS
from .entities import EntityDef, MloInstanceDef
from .model import Ymap, _suggest_resource_path, read_ymap, save_ymap
from .surfaces import (
    Aabb,
    BoxOccluder,
    DistantLodLightsSoa,
    GrassInstance,
    GrassInstanceBatch,
    InstancedMapData,
    LodLight,
    LodLightsSoa,
    OccludeModel,
)

Entity = EntityDef
MloInstance = MloInstanceDef
CarGenerator = CarGen
Block = BlockDesc

__all__ = [
    "Aabb",
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
    "MloInstance",
    "MloInstanceDef",
    "OccludeModel",
    "TimeCycleModifier",
    "YMAP_ENUM_INFOS",
    "YMAP_STRUCT_INFOS",
    "Ymap",
    "read_ymap",
    "save_ymap",
]
