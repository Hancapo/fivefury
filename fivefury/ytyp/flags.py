from __future__ import annotations

from enum import IntFlag


class ArchetypeFlags(IntFlag):
    """Flags for ``CBaseArchetypeDef.flags`` / ``CBaseArchetypeDefLoadFlags``."""

    WET_ROAD_REFLECTION = 1 << 0
    DONT_FADE = 1 << 1
    DRAW_LAST = 1 << 2
    PROP_CLIMBABLE_BY_AI = 1 << 3
    SUPPRESS_HD_TXDS = 1 << 4
    IS_FIXED = 1 << 5
    DONT_WRITE_ZBUFFER = 1 << 6
    TOUGH_FOR_BULLETS = 1 << 7
    IS_GENERIC = 1 << 8
    HAS_ANIM = 1 << 9
    HAS_UVANIM = 1 << 10
    SHADOW_ONLY = 1 << 11
    DAMAGE_MODEL = 1 << 12
    DONT_CAST_SHADOWS = 1 << 13
    CAST_TEXTURE_SHADOWS = 1 << 14
    DONT_COLLIDE_WITH_FLYER = 1 << 15
    IS_TREE = 1 << 16
    IS_TYPE_OBJECT = 1 << 17
    OVERRIDE_PHYSICS_BOUNDS = 1 << 18
    AUTOSTART_ANIM = 1 << 19
    HAS_PRE_REFLECTED_WATER_PROXY = 1 << 20
    HAS_DRAWABLE_PROXY_FOR_WATER_REFLECTIONS = 1 << 21
    DOES_NOT_PROVIDE_AI_COVER = 1 << 22
    DOES_NOT_PROVIDE_PLAYER_COVER = 1 << 23
    IS_LADDER_DEPRECATED = 1 << 24
    HAS_CLOTH = 1 << 25
    DOOR_PHYSICS = 1 << 26
    IS_FIXED_FOR_NAVIGATION = 1 << 27
    DONT_AVOID_BY_PEDS = 1 << 28
    USE_AMBIENT_SCALE = 1 << 29
    IS_DEBUG = 1 << 30
    HAS_ALPHA_SHADOW = 1 << 31


class TimeArchetypeFlags(IntFlag):
    """Flags for ``CTimeArchetypeDef.m_timeFlags`` / ``CTimeInfo.m_hoursOnOff``."""

    NONE = 0
    HOUR_00 = 1 << 0
    HOUR_01 = 1 << 1
    HOUR_02 = 1 << 2
    HOUR_03 = 1 << 3
    HOUR_04 = 1 << 4
    HOUR_05 = 1 << 5
    HOUR_06 = 1 << 6
    HOUR_07 = 1 << 7
    HOUR_08 = 1 << 8
    HOUR_09 = 1 << 9
    HOUR_10 = 1 << 10
    HOUR_11 = 1 << 11
    HOUR_12 = 1 << 12
    HOUR_13 = 1 << 13
    HOUR_14 = 1 << 14
    HOUR_15 = 1 << 15
    HOUR_16 = 1 << 16
    HOUR_17 = 1 << 17
    HOUR_18 = 1 << 18
    HOUR_19 = 1 << 19
    HOUR_20 = 1 << 20
    HOUR_21 = 1 << 21
    HOUR_22 = 1 << 22
    HOUR_23 = 1 << 23
    ALL_HOURS = (1 << 24) - 1
    HOUR_BITMASK = ALL_HOURS
    FLIP_WHILE_VISIBLE = 1 << 24


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
    "ArchetypeFlags",
    "MloInstanceFlags",
    "MloInteriorFlags",
    "PortalFlags",
    "RoomFlags",
    "TimeArchetypeFlags",
]
