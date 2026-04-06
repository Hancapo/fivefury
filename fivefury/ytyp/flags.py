from __future__ import annotations

from enum import IntFlag


class EntityFlags(IntFlag):
    """Flags for CEntityDef / CBaseArchetypeDef ``flags`` field."""

    FULL_MATRIX = 1
    STREAM_LOW_PRIORITY = 2
    DONT_INSTANCE_COLLISION = 4
    LOD_IS_IN_PARENT_MAPDATA = 8
    LOD_ADOPT_ME = 16
    IS_FIXED = 32
    IS_INTERIOR_LOD = 64
    DRAWABLE_LOD_USE_ALT_FADE = 1 << 15
    UNUSED = 1 << 16
    DOES_NOT_TOUCH_WATER = 1 << 17
    DOES_NOT_SPAWN_PEDS = 1 << 18
    LIGHTS_CAST_STATIC_SHADOWS = 1 << 19
    LIGHTS_CAST_DYNAMIC_SHADOWS = 1 << 20
    LIGHTS_IGNORE_DAY_NIGHT_SETTINGS = 1 << 21
    DONT_RENDER_IN_SHADOWS = 1 << 22
    ONLY_RENDER_IN_SHADOWS = 1 << 23
    DONT_RENDER_IN_REFLECTIONS = 1 << 24
    ONLY_RENDER_IN_REFLECTIONS = 1 << 25
    DONT_RENDER_IN_WATER_REFLECTIONS = 1 << 26
    ONLY_RENDER_IN_WATER_REFLECTIONS = 1 << 27
    DONT_RENDER_IN_MIRROR_REFLECTIONS = 1 << 28
    ONLY_RENDER_IN_MIRROR_REFLECTIONS = 1 << 29


class MloInteriorFlags(IntFlag):
    """Flags for CMloArchetypeDef ``mlo_flags`` field."""

    SUBWAY = 256
    OFFICE = 512
    ALLOW_RUN = 1024
    CUTSCENE_ONLY = 2048
    LOD_WHEN_LOCKED = 4096
    NO_WATER_REFLECTION = 8192
    HAS_LOW_LOD_PORTALS = 32768


class MloInstanceFlags(IntFlag):
    """Flags for MLO entity instance ``flags`` field."""

    GPS_ON = 1
    CAP_CONTENTS_ALPHA = 2
    SHORT_FADE = 4
    SPECIAL_BEHAVIOUR_1 = 8
    SPECIAL_BEHAVIOUR_2 = 16
    SPECIAL_BEHAVIOUR_3 = 32


class RoomFlags(IntFlag):
    """Flags for CMloRoomDef ``flags`` field."""

    FREEZE_VEHICLES = 1
    FREEZE_PEDS = 2
    NO_DIR_LIGHT = 4
    NO_EXTERIOR_LIGHTS = 8
    FORCE_FREEZE = 16
    REDUCE_CARS = 32
    REDUCE_PEDS = 64
    FORCE_DIR_LIGHT_ON = 128
    DONT_RENDER_EXTERIOR = 256
    MIRROR_POTENTIALLY_VISIBLE = 512


class PortalFlags(IntFlag):
    """Flags for CMloPortalDef ``flags`` field."""

    ONE_WAY = 1
    LINK = 2
    MIRROR = 4
    IGNORE_MODIFIER = 8
    MIRROR_USING_EXPENSIVE_SHADERS = 16
    LOW_LOD_ONLY = 32
    ALLOW_CLOSING = 64
    MIRROR_CAN_SEE_DIRECTIONAL_LIGHT = 128
    MIRROR_USING_PORTAL_TRAVERSAL = 256
    MIRROR_FLOOR = 512
    MIRROR_CAN_SEE_EXTERIOR_VIEW = 1024
    WATER_SURFACE = 2048
    WATER_SURFACE_EXTEND_TO_HORIZON = 4096
    USE_LIGHT_BLEED = 8192


__all__ = [
    "EntityFlags",
    "MloInstanceFlags",
    "MloInteriorFlags",
    "PortalFlags",
    "RoomFlags",
]
