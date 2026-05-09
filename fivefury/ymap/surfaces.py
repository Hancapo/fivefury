from __future__ import annotations

from .grass import (
    Aabb,
    BATCH_VERT_MULTIPLIER,
    GrassBatch,
    GrassInstance,
    GrassInstanceBatch,
    InstancedData,
    InstancedMapData,
    YMAP_GRASS_STRUCT_INFOS,
)
from .lights import (
    MAX_LOD_LIGHT_CAPSULE_EXTENT,
    MAX_LOD_LIGHT_CONE_ANGLE,
    MAX_LOD_LIGHT_CORONA_INTENSITY,
    DistantLodLights,
    DistantLodLightsSoa,
    LodLight,
    LodLights,
    LodLightsSoa,
    _coerce_lod_light,
    _coerce_lod_lights,
)
from .occluders import AngleMode, BoxOccluder, OccludeModel, _coerce_occlude_model


YMAP_SURFACE_STRUCT_INFOS = YMAP_GRASS_STRUCT_INFOS


__all__ = [
    "Aabb",
    "AngleMode",
    "BATCH_VERT_MULTIPLIER",
    "BoxOccluder",
    "DistantLodLights",
    "DistantLodLightsSoa",
    "GrassBatch",
    "GrassInstance",
    "GrassInstanceBatch",
    "InstancedData",
    "InstancedMapData",
    "LodLight",
    "LodLights",
    "LodLightsSoa",
    "MAX_LOD_LIGHT_CAPSULE_EXTENT",
    "MAX_LOD_LIGHT_CONE_ANGLE",
    "MAX_LOD_LIGHT_CORONA_INTENSITY",
    "OccludeModel",
    "YMAP_SURFACE_STRUCT_INFOS",
    "_coerce_lod_light",
    "_coerce_lod_lights",
    "_coerce_occlude_model",
]
