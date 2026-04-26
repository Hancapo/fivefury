from __future__ import annotations

import enum

from ..common import FlexibleIntEnum


class YmapFlags(enum.IntFlag):
    NONE = 0
    SCRIPTED = 1 << 0
    HAS_LODS = 1 << 1


class YmapContentFlags(enum.IntFlag):
    NONE = 0
    ENTITIES_HD = 1 << 0
    ENTITIES_LOD = 1 << 1
    ENTITIES_CONTAINER_LOD = 1 << 2
    MLO = 1 << 3
    BLOCKINFO = 1 << 4
    OCCLUDER = 1 << 5
    ENTITIES_USING_PHYSICS = 1 << 6
    LOD_LIGHTS = 1 << 7
    DISTANT_LOD_LIGHTS = 1 << 8
    ENTITIES_CRITICAL = 1 << 9
    INSTANCE_LIST = 1 << 10

    MASK_LODS = ENTITIES_LOD | ENTITIES_CONTAINER_LOD
    MASK_ENTITIES = ENTITIES_HD | ENTITIES_LOD | ENTITIES_CONTAINER_LOD | MLO | ENTITIES_CRITICAL
    MASK_LOD_LIGHTS = LOD_LIGHTS | DISTANT_LOD_LIGHTS
    MASK_RETAINED = INSTANCE_LIST | OCCLUDER | LOD_LIGHTS | DISTANT_LOD_LIGHTS


class YmapLodLevel(FlexibleIntEnum):
    DEPTH_HD = 0
    DEPTH_LOD = 1
    DEPTH_SLOD1 = 2
    DEPTH_SLOD2 = 3
    DEPTH_SLOD3 = 4
    DEPTH_ORPHANHD = 5
    DEPTH_SLOD4 = 6


class YmapPriorityLevel(FlexibleIntEnum):
    REQUIRED = 0
    OPTIONAL_HIGH = 1
    OPTIONAL_MEDIUM = 2
    OPTIONAL_LOW = 3


class YmapEntityFlags(enum.IntFlag):
    NONE = 0
    FULLMATRIX = 1 << 0
    STREAM_LOWPRIORITY = 1 << 1
    DONT_INSTANCE_COLLISION = 1 << 2
    LOD_IS_IN_PARENT_MAPDATA = 1 << 3
    LOD_ADOPTME = 1 << 4
    IS_FIXED = 1 << 5
    IS_INTERIOR_LOD = 1 << 6
    DRAWABLELODUSEALTFADE = 1 << 7
    UNUSED = 1 << 8
    DOESNOTTOUCHWATER = 1 << 9
    DOESNOTSPAWNPEDS = 1 << 10
    LIGHTS_CAST_STATIC_SHADOWS = 1 << 11
    LIGHTS_CAST_DYNAMIC_SHADOWS = 1 << 12
    LIGHTS_IGNORE_DAY_NIGHT_SETTINGS = 1 << 13
    DONT_RENDER_IN_SHADOWS = 1 << 14
    ONLY_RENDER_IN_SHADOWS = 1 << 15
    DONT_RENDER_IN_REFLECTIONS = 1 << 16
    ONLY_RENDER_IN_REFLECTIONS = 1 << 17
    DONT_RENDER_IN_WATER_REFLECTIONS = 1 << 18
    ONLY_RENDER_IN_WATER_REFLECTIONS = 1 << 19
    DONT_RENDER_IN_MIRROR_REFLECTIONS = 1 << 20
    ONLY_RENDER_IN_MIRROR_REFLECTIONS = 1 << 21

    EMBEDDED_COLLISIONS_DISABLED = DONT_INSTANCE_COLLISION


class YmapMloInstanceFlags(enum.IntFlag):
    NONE = 0
    GPS_ON = 1 << 0
    CAP_CONTENTS_ALPHA = 1 << 1
    SHORT_FADE = 1 << 2
    SPECIAL_BEHAVIOUR_1 = 1 << 3
    SPECIAL_BEHAVIOUR_2 = 1 << 4
    SPECIAL_BEHAVIOUR_3 = 1 << 5


class YmapCarGenFlags(enum.IntFlag):
    NONE = 0
    FORCESPAWN = 1 << 0
    IGNORE_DENSITY = 1 << 1
    POLICE = 1 << 2
    FIRETRUCK = 1 << 3
    AMBULANCE = 1 << 4
    DURING_DAY = 1 << 5
    AT_NIGHT = 1 << 6
    ALIGN_LEFT = 1 << 7
    ALIGN_RIGHT = 1 << 8
    SINGLE_PLAYER = 1 << 9
    NETWORK_PLAYER = 1 << 10
    LOWPRIORITY = 1 << 11
    PREVENT_ENTRY = 1 << 12


class YmapLodLightType(FlexibleIntEnum):
    POINT = 1
    SPOT = 2
    CAPSULE = 4


class YmapLodLightCategory(FlexibleIntEnum):
    SMALL = 0
    MEDIUM = 1
    LARGE = 2


def coerce_ymap_lod_level(value: int | YmapLodLevel) -> YmapLodLevel:
    return value if isinstance(value, YmapLodLevel) else YmapLodLevel(int(value))


def coerce_ymap_priority_level(value: int | YmapPriorityLevel) -> YmapPriorityLevel:
    return value if isinstance(value, YmapPriorityLevel) else YmapPriorityLevel(int(value))


def coerce_ymap_flags(value: int | YmapFlags) -> YmapFlags:
    return value if isinstance(value, YmapFlags) else YmapFlags(int(value))


def coerce_ymap_content_flags(value: int | YmapContentFlags) -> YmapContentFlags:
    return value if isinstance(value, YmapContentFlags) else YmapContentFlags(int(value))


def coerce_ymap_entity_flags(value: int | YmapEntityFlags) -> YmapEntityFlags:
    return value if isinstance(value, YmapEntityFlags) else YmapEntityFlags(int(value))


def coerce_ymap_cargen_flags(value: int | YmapCarGenFlags) -> YmapCarGenFlags:
    return value if isinstance(value, YmapCarGenFlags) else YmapCarGenFlags(int(value))


def coerce_ymap_mlo_instance_flags(value: int | YmapMloInstanceFlags) -> YmapMloInstanceFlags:
    return value if isinstance(value, YmapMloInstanceFlags) else YmapMloInstanceFlags(int(value))


def coerce_ymap_lod_light_type(value: int | YmapLodLightType) -> YmapLodLightType:
    return value if isinstance(value, YmapLodLightType) else YmapLodLightType(int(value))


def coerce_ymap_lod_light_category(value: int | YmapLodLightCategory) -> YmapLodLightCategory:
    return value if isinstance(value, YmapLodLightCategory) else YmapLodLightCategory(int(value))


__all__ = [
    "YmapCarGenFlags",
    "YmapContentFlags",
    "YmapEntityFlags",
    "YmapFlags",
    "YmapLodLevel",
    "YmapLodLightCategory",
    "YmapLodLightType",
    "YmapMloInstanceFlags",
    "YmapPriorityLevel",
    "coerce_ymap_cargen_flags",
    "coerce_ymap_content_flags",
    "coerce_ymap_entity_flags",
    "coerce_ymap_flags",
    "coerce_ymap_lod_level",
    "coerce_ymap_lod_light_category",
    "coerce_ymap_lod_light_type",
    "coerce_ymap_mlo_instance_flags",
    "coerce_ymap_priority_level",
]
