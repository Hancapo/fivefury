from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import Self


class VehicleMetaEnum(IntEnum):
    @classmethod
    def from_token(cls, token: str) -> Self | None:
        value = _TOKEN_MEMBERS.get(cls, {}).get(str(token).strip())
        return cls(value) if value is not None else None

    @property
    def token(self) -> str:
        return _ENUM_TOKENS[type(self)][int(self)]


class VehicleType(VehicleMetaEnum):
    NONE = -1
    CAR = 0
    PLANE = 1
    TRAILER = 2
    QUADBIKE = 3
    DRAFT = 4
    SUBMARINE_CAR = 5
    AMPHIBIOUS_AUTOMOBILE = 6
    AMPHIBIOUS_QUADBIKE = 7
    HELICOPTER = 8
    BLIMP = 9
    AUTOGYRO = 10
    BIKE = 11
    BICYCLE = 12
    BOAT = 13
    TRAIN = 14
    SUBMARINE = 15


class VehicleDoor(VehicleMetaEnum):
    INVALID = -1
    DRIVER_FRONT = 0
    DRIVER_REAR = 1
    PASSENGER_FRONT = 2
    PASSENGER_REAR = 3
    BONNET = 4
    BOOT = 5


class VehicleWindow(VehicleMetaEnum):
    INVALID = -1
    WINDSCREEN = 0
    REAR_WINDSCREEN = 1
    LEFT_FRONT = 2
    RIGHT_FRONT = 3
    LEFT_REAR = 4
    RIGHT_REAR = 5
    LEFT_MIDDLE = 6
    RIGHT_MIDDLE = 7


class VehicleSwankness(VehicleMetaEnum):
    ZERO = 0
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5


class VehicleWheelType(VehicleMetaEnum):
    INVALID = -1
    SPORT = 0
    MUSCLE = 1
    LOWRIDER = 2
    SUV = 3
    OFFROAD = 4
    TUNER = 5
    BIKE = 6
    HIGH_END = 7
    SUPER_MOD_1 = 8
    SUPER_MOD_2 = 9
    SUPER_MOD_3 = 10
    SUPER_MOD_4 = 11
    SUPER_MOD_5 = 12


class VehiclePlateType(VehicleMetaEnum):
    FRONT_AND_BACK = 0
    FRONT = 1
    BACK = 2
    NONE = 3


class VehicleClass(VehicleMetaEnum):
    COMPACT = 0
    SEDAN = 1
    SUV = 2
    COUPE = 3
    MUSCLE = 4
    SPORT_CLASSIC = 5
    SPORT = 6
    SUPER = 7
    MOTORCYCLE = 8
    OFF_ROAD = 9
    INDUSTRIAL = 10
    UTILITY = 11
    VAN = 12
    CYCLE = 13
    BOAT = 14
    HELICOPTER = 15
    PLANE = 16
    SERVICE = 17
    EMERGENCY = 18
    MILITARY = 19
    COMMERCIAL = 20
    RAIL = 21
    OPEN_WHEEL = 22


class VehicleDashboardType(VehicleMetaEnum):
    BANSHEE = 0
    BOBCAT = 1
    CAVALCADE = 2
    COMET = 3
    DUKES = 4
    FACTION = 5
    FELTZER = 6
    FEROCI = 7
    FUTO = 8
    GENERIC_TAXI = 9
    MAVERICK = 10
    PEYOTE = 11
    RUINER = 12
    SPEEDO = 13
    SULTAN = 14
    SUPER_GT = 15
    TAILGATER = 16
    TRUCK = 17
    DIGITAL_TRUCK = 18
    INFERNUS = 19
    ZTYPE = 20
    LAZER = 21
    SPORT_BIKE = 22
    RACE = 23
    VINTAGE_LAZER = 24
    PBUS2 = 25


class HandlingType(VehicleMetaEnum):
    INVALID = -1
    BIKE = 0
    FLYING = 1
    VERTICAL_FLYING = 2
    BOAT = 3
    SEAPLANE = 4
    SUBMARINE = 5
    TRAIN = 6
    TRAILER = 7
    CAR = 8
    WEAPON = 9
    SPECIAL_FLIGHT = 10


class VehicleModType(VehicleMetaEnum):
    INVALID = -1
    SPOILER = 0
    FRONT_BUMPER = 1
    REAR_BUMPER = 2
    SKIRT = 3
    EXHAUST = 4
    CHASSIS = 5
    GRILL = 6
    BONNET = 7
    LEFT_WING = 8
    RIGHT_WING = 9
    ROOF = 10
    PLATE_HOLDER = 11
    VANITY_PLATE = 12
    INTERIOR_1 = 13
    INTERIOR_2 = 14
    INTERIOR_3 = 15
    INTERIOR_4 = 16
    INTERIOR_5 = 17
    SEATS = 18
    STEERING = 19
    KNOB = 20
    PLAQUE = 21
    ICE = 22
    TRUNK = 23
    HYDRAULICS_BODY = 24
    ENGINE_BAY_1 = 25
    ENGINE_BAY_2 = 26
    ENGINE_BAY_3 = 27
    CHASSIS_2 = 28
    CHASSIS_3 = 29
    CHASSIS_4 = 30
    CHASSIS_5 = 31
    LEFT_DOOR = 32
    RIGHT_DOOR = 33
    LIVERY = 34
    LIGHTBAR = 35
    ENGINE = 36
    BRAKES = 37
    GEARBOX = 38
    HORN = 39
    SUSPENSION = 40
    ARMOUR = 41
    NITROUS = 42
    TURBO = 43
    SUBWOOFER = 44
    TYRE_SMOKE = 45
    HYDRAULICS = 46
    XENON_LIGHTS = 47
    WHEELS = 48
    REAR_WHEELS_OR_HYDRAULICS = 49


class VehicleModKitType(VehicleMetaEnum):
    STANDARD = 0
    SPORT = 1
    SUV = 2
    SPECIAL = 3


class VehicleModCameraPosition(VehicleMetaEnum):
    DEFAULT = 0
    FRONT = 1
    FRONT_LEFT = 2
    FRONT_RIGHT = 3
    REAR = 4
    REAR_LEFT = 5
    REAR_RIGHT = 6
    LEFT = 7
    RIGHT = 8
    TOP = 9
    BOTTOM = 10


class VehicleModelFlag(IntFlag):
    FLAG_SMALL_WORKER = 1 << 0
    FLAG_BIG = 1 << 1
    FLAG_NO_BOOT = 1 << 2
    FLAG_ONLY_DURING_OFFICE_HOURS = 1 << 3
    FLAG_BOOT_IN_FRONT = 1 << 4
    FLAG_IS_VAN = 1 << 5
    FLAG_AVOID_TURNS = 1 << 6
    FLAG_HAS_LIVERY = 1 << 7
    FLAG_LIVERY_MATCH_EXTRA = 1 << 8
    FLAG_SPORTS = 1 << 9
    FLAG_DELIVERY = 1 << 10
    FLAG_NOAMBIENTOCCLUSION = 1 << 11
    FLAG_ONLY_ON_HIGHWAYS = 1 << 12
    FLAG_TALL_SHIP = 1 << 13
    FLAG_SPAWN_ON_TRAILER = 1 << 14
    FLAG_SPAWN_BOAT_ON_TRAILER = 1 << 15
    FLAG_EXTRAS_GANG = 1 << 16
    FLAG_EXTRAS_CONVERTIBLE = 1 << 17
    FLAG_EXTRAS_TAXI = 1 << 18
    FLAG_EXTRAS_RARE = 1 << 19
    FLAG_EXTRAS_REQUIRE = 1 << 20
    FLAG_EXTRAS_STRONG = 1 << 21
    FLAG_EXTRAS_ONLY_BREAK_WHEN_DESTROYED = 1 << 22
    FLAG_EXTRAS_SCRIPT = 1 << 23
    FLAG_EXTRAS_ALL = 1 << 24
    FLAG_EXTRAS_MATCH_LIVERY = 1 << 25
    FLAG_DONT_ROTATE_TAIL_ROTOR = 1 << 26
    FLAG_PARKING_SENSORS = 1 << 27
    FLAG_PEDS_CAN_STAND_ON_TOP = 1 << 28
    FLAG_TAILGATE_TYPE_BOOT = 1 << 29
    FLAG_GEN_NAVMESH = 1 << 30
    FLAG_LAW_ENFORCEMENT = 1 << 31
    FLAG_EMERGENCY_SERVICE = 1 << 32
    FLAG_DRIVER_NO_DRIVE_BY = 1 << 33
    FLAG_NO_RESPRAY = 1 << 34
    FLAG_IGNORE_ON_SIDE_CHECK = 1 << 35
    FLAG_RICH_CAR = 1 << 36
    FLAG_AVERAGE_CAR = 1 << 37
    FLAG_POOR_CAR = 1 << 38
    FLAG_ALLOWS_RAPPEL = 1 << 39
    FLAG_DONT_CLOSE_DOOR_UPON_EXIT = 1 << 40
    FLAG_USE_HIGHER_DOOR_TORQUE = 1 << 41
    FLAG_DISABLE_THROUGH_WINDSCREEN = 1 << 42
    FLAG_IS_ELECTRIC = 1 << 43
    FLAG_NO_BROKEN_DOWN_SCENARIO = 1 << 44
    FLAG_IS_JETSKI = 1 << 45
    FLAG_DAMPEN_STICKBOMB_DAMAGE = 1 << 46
    FLAG_DONT_SPAWN_IN_CARGEN = 1 << 47
    FLAG_IS_OFFROAD_VEHICLE = 1 << 48
    FLAG_INCREASE_PED_COMMENTS = 1 << 49
    FLAG_EXPLODE_ON_CONTACT = 1 << 50
    FLAG_USE_FAT_INTERIOR_LIGHT = 1 << 51
    FLAG_HEADLIGHTS_USE_ACTUAL_BONE_POS = 1 << 52
    FLAG_FAKE_EXTRALIGHTS = 1 << 53
    FLAG_CANNOT_BE_MODDED = 1 << 54
    FLAG_DONT_SPAWN_AS_AMBIENT = 1 << 55
    FLAG_IS_BULKY = 1 << 56
    FLAG_BLOCK_FROM_ATTRACTOR_SCENARIO = 1 << 57
    FLAG_IS_BUS = 1 << 58
    FLAG_USE_STEERING_PARAM_FOR_LEAN = 1 << 59
    FLAG_CANNOT_BE_DRIVEN_BY_PLAYER = 1 << 60
    FLAG_SPRAY_PETROL_BEFORE_EXPLOSION = 1 << 61
    FLAG_ATTACH_TRAILER_ON_HIGHWAY = 1 << 62
    FLAG_ATTACH_TRAILER_IN_CITY = 1 << 63
    FLAG_HAS_NO_ROOF = 1 << 64
    FLAG_ALLOW_TARGETING_OF_OCCUPANTS = 1 << 65
    FLAG_RECESSED_HEADLIGHT_CORONAS = 1 << 66
    FLAG_RECESSED_TAILLIGHT_CORONAS = 1 << 67
    FLAG_IS_TRACKED_FOR_TRAILS = 1 << 68
    FLAG_HEADLIGHTS_ON_LANDINGGEAR = 1 << 69
    FLAG_CONSIDERED_FOR_VEHICLE_ENTRY_WHEN_STOOD_ON = 1 << 70
    FLAG_GIVE_SCUBA_GEAR_ON_EXIT = 1 << 71
    FLAG_IS_DIGGER = 1 << 72
    FLAG_IS_TANK = 1 << 73
    FLAG_USE_COVERBOUND_INFO_FOR_COVERGEN = 1 << 74
    FLAG_CAN_BE_DRIVEN_ON = 1 << 75
    FLAG_HAS_BULLETPROOF_GLASS = 1 << 76
    FLAG_CANNOT_TAKE_COVER_WHEN_STOOD_ON = 1 << 77
    FLAG_INTERIOR_BLOCKED_BY_BOOT = 1 << 78
    FLAG_DONT_TIMESLICE_WHEELS = 1 << 79
    FLAG_FLEE_FROM_COMBAT = 1 << 80
    FLAG_DRIVER_SHOULD_BE_FEMALE = 1 << 81
    FLAG_DRIVER_SHOULD_BE_MALE = 1 << 82
    FLAG_COUNT_AS_FACEBOOK_DRIVEN = 1 << 83
    FLAG_BIKE_CLAMP_PICKUP_LEAN_RATE = 1 << 84
    FLAG_PLANE_WEAR_ALTERNATIVE_HELMET = 1 << 85
    FLAG_USE_STRICTER_EXIT_COLLISION_TESTS = 1 << 86
    FLAG_TWO_DOORS_ONE_SEAT = 1 << 87
    FLAG_USE_LIGHTING_INTERIOR_OVERRIDE = 1 << 88
    FLAG_USE_RESTRICTED_DRIVEBY_HEIGHT = 1 << 89
    FLAG_CAN_HONK_WHEN_FLEEING = 1 << 90
    FLAG_PEDS_INSIDE_CAN_BE_SET_ON_FIRE_MP = 1 << 91
    FLAG_REPORT_CRIME_IF_STANDING_ON = 1 << 92
    FLAG_HELI_USES_FIXUPS_ON_OPEN_DOOR = 1 << 93
    FLAG_FORCE_ENABLE_CHASSIS_COLLISION = 1 << 94
    FLAG_CANNOT_BE_PICKUP_BY_CARGOBOB = 1 << 95
    FLAG_CAN_HAVE_NEONS = 1 << 96
    FLAG_HAS_INTERIOR_EXTRAS = 1 << 97
    FLAG_HAS_TURRET_SEAT_ON_VEHICLE = 1 << 98
    FLAG_ALLOW_OBJECT_LOW_LOD_COLLISION = 1 << 99
    FLAG_DISABLE_AUTO_VAULT_ON_VEHICLE = 1 << 100
    FLAG_USE_TURRET_RELATIVE_AIM_CALCULATION = 1 << 101
    FLAG_USE_FULL_ANIMS_FOR_MP_WARP_ENTRY_POINTS = 1 << 102
    FLAG_HAS_DIRECTIONAL_SHUFFLES = 1 << 103
    FLAG_DISABLE_WEAPON_WHEEL_IN_FIRST_PERSON = 1 << 104
    FLAG_USE_PILOT_HELMET = 1 << 105
    FLAG_USE_WEAPON_WHEEL_WITHOUT_HELMET = 1 << 106
    FLAG_PREFER_ENTER_TURRET_AFTER_DRIVER = 1 << 107
    FLAG_USE_SMALLER_OPEN_DOOR_RATIO_TOLERANCE = 1 << 108
    FLAG_USE_HEADING_ONLY_IN_TURRET_MATRIX = 1 << 109
    FLAG_DONT_STOP_WHEN_GOING_TO_CLIMB_UP_POINT = 1 << 110
    FLAG_HAS_REAR_MOUNTED_TURRET = 1 << 111
    FLAG_DISABLE_BUSTING = 1 << 112
    FLAG_IGNORE_RWINDOW_COLLISION = 1 << 113
    FLAG_HAS_GULL_WING_DOORS = 1 << 114
    FLAG_CARGOBOB_HOOK_UP_CHASSIS = 1 << 115
    FLAG_USE_FIVE_ANIM_THROW_FP = 1 << 116
    FLAG_ALLOW_HATS_NO_ROOF = 1 << 117
    FLAG_HAS_REAR_SEAT_ACTIVITIES = 1 << 118
    FLAG_HAS_LOWRIDER_HYDRAULICS = 1 << 119
    FLAG_HAS_BULLET_RESISTANT_GLASS = 1 << 120
    FLAG_HAS_INCREASED_RAMMING_FORCE = 1 << 121
    FLAG_HAS_CAPPED_EXPLOSION_DAMAGE = 1 << 122
    FLAG_HAS_LOWRIDER_DONK_HYDRAULICS = 1 << 123
    FLAG_HELICOPTER_WITH_LANDING_GEAR = 1 << 124
    FLAG_JUMPING_CAR = 1 << 125
    FLAG_HAS_ROCKET_BOOST = 1 << 126
    FLAG_RAMMING_SCOOP = 1 << 127
    FLAG_HAS_PARACHUTE = 1 << 128
    FLAG_RAMP = 1 << 129
    FLAG_HAS_EXTRA_SHUFFLE_SEAT_ON_VEHICLE = 1 << 130
    FLAG_FRONT_BOOT = 1 << 131
    FLAG_HALF_TRACK = 1 << 132
    FLAG_RESET_TURRET_SEAT_HEADING = 1 << 133
    FLAG_TURRET_MODS_ON_ROOF = 1 << 134
    FLAG_UPDATE_WEAPON_BATTERY_BONES = 1 << 135
    FLAG_DONT_HOLD_LOW_GEARS_WHEN_ENGINE_UNDER_LOAD = 1 << 136
    FLAG_HAS_GLIDER = 1 << 137
    FLAG_INCREASE_LOW_SPEED_TORQUE = 1 << 138
    FLAG_USE_AIRCRAFT_STYLE_WEAPON_TARGETING = 1 << 139
    FLAG_KEEP_ALL_TURRETS_SYNCHRONISED = 1 << 140
    FLAG_SET_WANTED_FOR_ATTACHED_VEH = 1 << 141
    FLAG_TURRET_ENTRY_ATTACH_TO_DRIVER_SEAT = 1 << 142
    FLAG_USE_STANDARD_FLIGHT_HELMET = 1 << 143
    FLAG_SECOND_TURRET_MOD = 1 << 144
    FLAG_THIRD_TURRET_MOD = 1 << 145
    FLAG_HAS_EJECTOR_SEATS = 1 << 146
    FLAG_TURRET_MODS_ON_CHASSIS = 1 << 147
    FLAG_HAS_JATO_BOOST_MOD = 1 << 148
    FLAG_IGNORE_TRAPPED_HULL_CHECK = 1 << 149
    FLAG_HOLD_TO_SHUFFLE = 1 << 150
    FLAG_TURRET_MOD_WITH_NO_STOCK_TURRET = 1 << 151
    FLAG_EQUIP_UNARMED_ON_ENTER = 1 << 152
    FLAG_DISABLE_CAMERA_PUSH_BEYOND = 1 << 153
    FLAG_HAS_VERTICAL_FLIGHT_MODE = 1 << 154
    FLAG_HAS_OUTRIGGER_LEGS = 1 << 155
    FLAG_CAN_NAVIGATE_TO_ON_VEHICLE_ENTRY = 1 << 156
    FLAG_DROP_SUSPENSION_WHEN_STOPPED = 1 << 157
    FLAG_DONT_CRASH_ABANDONED_NEAR_GROUND = 1 << 158
    FLAG_USE_INTERIOR_RED_LIGHT = 1 << 159
    FLAG_HAS_HELI_STRAFE_MODE = 1 << 160
    FLAG_HAS_VERTICAL_ROCKET_BOOST = 1 << 161
    FLAG_CREATE_WEAPON_MANAGER_ON_SPAWN = 1 << 162
    FLAG_USE_ROOT_AS_BASE_LOCKON_POS = 1 << 163
    FLAG_HEADLIGHTS_ON_TAP_ONLY = 1 << 164
    FLAG_CHECK_WARP_TASK_FLAG_DURING_ENTER = 1 << 165
    FLAG_USE_RESTRICTED_DRIVEBY_HEIGHT_HIGH = 1 << 166
    FLAG_INCREASE_CAMBER_WITH_SUSPENSION_MOD = 1 << 167
    FLAG_NO_HEAVY_BRAKE_ANIMATION = 1 << 168
    FLAG_HAS_TWO_BONNET_BONES = 1 << 169
    FLAG_DONT_LINK_BOOT2 = 1 << 170
    FLAG_HAS_INCREASED_RAMMING_FORCE_WITH_CHASSIS_MOD = 1 << 171
    FLAG_HAS_INCREASED_RAMMING_FORCE_VS_ALL_VEHICLES = 1 << 172
    FLAG_HAS_EXTENDED_COLLISION_MODS = 1 << 173
    FLAG_HAS_NITROUS_MOD = 1 << 174
    FLAG_HAS_JUMP_MOD = 1 << 175
    FLAG_HAS_RAMMING_SCOOP_MOD = 1 << 176
    FLAG_HAS_SUPER_BRAKES_MOD = 1 << 177
    FLAG_CRUSHES_OTHER_VEHICLES = 1 << 178
    FLAG_HAS_WEAPON_BLADE_MODS = 1 << 179
    FLAG_HAS_WEAPON_SPIKE_MODS = 1 << 180
    FLAG_FORCE_BONNET_CAMERA_INSTEAD_OF_POV = 1 << 181
    FLAG_RAMP_MOD = 1 << 182
    FLAG_HAS_TOMBSTONE = 1 << 183
    FLAG_HAS_SIDE_SHUNT = 1 << 184
    FLAG_HAS_FRONT_SPIKE_MOD = 1 << 185
    FLAG_HAS_RAMMING_BAR_MOD = 1 << 186
    FLAG_TURRET_MODS_ON_CHASSIS5 = 1 << 187
    FLAG_HAS_SUPERCHARGER = 1 << 188
    FLAG_IS_TANK_WITH_FLAME_DAMAGE = 1 << 189
    FLAG_DISABLE_DEFORMATION = 1 << 190
    FLAG_ALLOW_RAPPEL_AI_ONLY = 1 << 191
    FLAG_USE_RESTRICTED_DRIVEBY_HEIGHT_MID_ONLY = 1 << 192
    FLAG_FORCE_AUTO_VAULT_ON_VEHICLE_WHEN_STUCK = 1 << 193
    FLAG_SPOILER_MOD_DOESNT_INCREASE_GRIP = 1 << 194
    FLAG_NO_REVERSING_ANIMATION = 1 << 195
    FLAG_IS_QUADBIKE_USING_BIKE_ANIMATIONS = 1 << 196
    FLAG_IS_FORMULA_VEHICLE = 1 << 197
    FLAG_LATCH_ALL_JOINTS = 1 << 198
    FLAG_REJECT_ENTRY_TO_VEHICLE_WHEN_STOOD_ON = 1 << 199
    FLAG_CHECK_IF_DRIVER_SEAT_IS_CLOSER_THAN_TURRETS_WITH_ON_BOARD_ENTER = 1 << 200
    FLAG_RENDER_WHEELS_WITH_ZERO_COMPRESSION = 1 << 201
    FLAG_USE_LENGTH_OF_VEHICLE_BOUNDS_FOR_PLAYER_LOCKON_POS = 1 << 202
    FLAG_PREFER_FRONT_SEAT = 1 << 203


_NO_VEHICLE_MODEL_FLAGS = VehicleModelFlag(0)


@dataclass(frozen=True, slots=True)
class VehicleModelFlags:
    known: VehicleModelFlag = _NO_VEHICLE_MODEL_FLAGS
    unknown_tokens: tuple[str, ...] = ()

    def __int__(self) -> int:
        return int(self.known)


class VehicleExtraFlag(IntFlag):
    EXTRA_1 = 1 << 1
    EXTRA_2 = 1 << 2
    EXTRA_3 = 1 << 3
    EXTRA_4 = 1 << 4
    EXTRA_5 = 1 << 5
    EXTRA_6 = 1 << 6
    EXTRA_7 = 1 << 7
    EXTRA_8 = 1 << 8
    EXTRA_9 = 1 << 9
    EXTRA_10 = 1 << 10
    EXTRA_11 = 1 << 11
    EXTRA_12 = 1 << 12
    EXTRA_13 = 1 << 13


_ENUM_TOKENS: dict[type[VehicleMetaEnum], dict[int, str]] = {
    VehicleType: dict(
        enumerate(
            (
                "VEHICLE_TYPE_CAR",
                "VEHICLE_TYPE_PLANE",
                "VEHICLE_TYPE_TRAILER",
                "VEHICLE_TYPE_QUADBIKE",
                "VEHICLE_TYPE_DRAFT",
                "VEHICLE_TYPE_SUBMARINECAR",
                "VEHICLE_TYPE_AMPHIBIOUS_AUTOMOBILE",
                "VEHICLE_TYPE_AMPHIBIOUS_QUADBIKE",
                "VEHICLE_TYPE_HELI",
                "VEHICLE_TYPE_BLIMP",
                "VEHICLE_TYPE_AUTOGYRO",
                "VEHICLE_TYPE_BIKE",
                "VEHICLE_TYPE_BICYCLE",
                "VEHICLE_TYPE_BOAT",
                "VEHICLE_TYPE_TRAIN",
                "VEHICLE_TYPE_SUBMARINE",
            )
        )
    )
    | {-1: "VEHICLE_TYPE_NONE"},
    VehicleDoor: dict(
        enumerate(
            (
                "VEH_EXT_DOOR_DSIDE_F",
                "VEH_EXT_DOOR_DSIDE_R",
                "VEH_EXT_DOOR_PSIDE_F",
                "VEH_EXT_DOOR_PSIDE_R",
                "VEH_EXT_BONNET",
                "VEH_EXT_BOOT",
            )
        )
    )
    | {-1: "VEH_EXT_DOOR_INVALID_ID"},
    VehicleWindow: dict(
        enumerate(
            (
                "VEH_EXT_WINDSCREEN",
                "VEH_EXT_WINDSCREEN_R",
                "VEH_EXT_WINDOW_LF",
                "VEH_EXT_WINDOW_RF",
                "VEH_EXT_WINDOW_LR",
                "VEH_EXT_WINDOW_RR",
                "VEH_EXT_WINDOW_LM",
                "VEH_EXT_WINDOW_RM",
            )
        )
    )
    | {-1: "VEH_EXT_WINDOWS_INVALID_ID"},
    VehicleSwankness: {value: f"SWANKNESS_{value}" for value in range(6)},
    VehicleWheelType: dict(
        enumerate(
            (
                "VWT_SPORT",
                "VWT_MUSCLE",
                "VWT_LOWRIDER",
                "VWT_SUV",
                "VWT_OFFROAD",
                "VWT_TUNER",
                "VWT_BIKE",
                "VWT_HIEND",
                "VWT_SUPERMOD1",
                "VWT_SUPERMOD2",
                "VWT_SUPERMOD3",
                "VWT_SUPERMOD4",
                "VWT_SUPERMOD5",
            )
        )
    )
    | {-1: "VWT_INVALID"},
    VehiclePlateType: dict(
        enumerate(
            (
                "VPT_FRONT_AND_BACK_PLATES",
                "VPT_FRONT_PLATES",
                "VPT_BACK_PLATES",
                "VPT_NONE",
            )
        )
    ),
    VehicleClass: dict(
        enumerate(
            (
                "VC_COMPACT",
                "VC_SEDAN",
                "VC_SUV",
                "VC_COUPE",
                "VC_MUSCLE",
                "VC_SPORT_CLASSIC",
                "VC_SPORT",
                "VC_SUPER",
                "VC_MOTORCYCLE",
                "VC_OFF_ROAD",
                "VC_INDUSTRIAL",
                "VC_UTILITY",
                "VC_VAN",
                "VC_CYCLE",
                "VC_BOAT",
                "VC_HELICOPTER",
                "VC_PLANE",
                "VC_SERVICE",
                "VC_EMERGENCY",
                "VC_MILITARY",
                "VC_COMMERCIAL",
                "VC_RAIL",
                "VC_OPEN_WHEEL",
            )
        )
    ),
    VehicleDashboardType: dict(
        enumerate(
            (
                "VDT_BANSHEE",
                "VDT_BOBCAT",
                "VDT_CAVALCADE",
                "VDT_COMET",
                "VDT_DUKES",
                "VDT_FACTION",
                "VDT_FELTZER",
                "VDT_FEROCI",
                "VDT_FUTO",
                "VDT_GENTAXI",
                "VDT_MAVERICK",
                "VDT_PEYOTE",
                "VDT_RUINER",
                "VDT_SPEEDO",
                "VDT_SULTAN",
                "VDT_SUPERGT",
                "VDT_TAILGATER",
                "VDT_TRUCK",
                "VDT_TRUCKDIGI",
                "VDT_INFERNUS",
                "VDT_ZTYPE",
                "VDT_LAZER",
                "VDT_SPORTBK",
                "VDT_RACE",
                "VDT_LAZER_VINTAGE",
                "VDT_PBUS2",
            )
        )
    ),
    HandlingType: dict(
        enumerate(
            (
                "HANDLING_TYPE_BIKE",
                "HANDLING_TYPE_FLYING",
                "HANDLING_TYPE_VERTICAL_FLYING",
                "HANDLING_TYPE_BOAT",
                "HANDLING_TYPE_SEAPLANE",
                "HANDLING_TYPE_SUBMARINE",
                "HANDLING_TYPE_TRAIN",
                "HANDLING_TYPE_TRAILER",
                "HANDLING_TYPE_CAR",
                "HANDLING_TYPE_WEAPON",
                "HANDLING_TYPE_SPECIAL_FLIGHT",
            )
        )
    )
    | {-1: "HANDLING_TYPE_INVALID"},
    VehicleModType: dict(
        enumerate(
            (
                "VMT_SPOILER",
                "VMT_BUMPER_F",
                "VMT_BUMPER_R",
                "VMT_SKIRT",
                "VMT_EXHAUST",
                "VMT_CHASSIS",
                "VMT_GRILL",
                "VMT_BONNET",
                "VMT_WING_L",
                "VMT_WING_R",
                "VMT_ROOF",
                "VMT_PLTHOLDER",
                "VMT_PLTVANITY",
                "VMT_INTERIOR1",
                "VMT_INTERIOR2",
                "VMT_INTERIOR3",
                "VMT_INTERIOR4",
                "VMT_INTERIOR5",
                "VMT_SEATS",
                "VMT_STEERING",
                "VMT_KNOB",
                "VMT_PLAQUE",
                "VMT_ICE",
                "VMT_TRUNK",
                "VMT_HYDRO",
                "VMT_ENGINEBAY1",
                "VMT_ENGINEBAY2",
                "VMT_ENGINEBAY3",
                "VMT_CHASSIS2",
                "VMT_CHASSIS3",
                "VMT_CHASSIS4",
                "VMT_CHASSIS5",
                "VMT_DOOR_L",
                "VMT_DOOR_R",
                "VMT_LIVERY_MOD",
                "VMT_LIGHTBAR",
                "VMT_ENGINE",
                "VMT_BRAKES",
                "VMT_GEARBOX",
                "VMT_HORN",
                "VMT_SUSPENSION",
                "VMT_ARMOUR",
                "VMT_NITROUS",
                "VMT_TURBO",
                "VMT_SUBWOOFER",
                "VMT_TYRE_SMOKE",
                "VMT_HYDRAULICS",
                "VMT_XENON_LIGHTS",
                "VMT_WHEELS",
                "VMT_WHEELS_REAR_OR_HYDRAULICS",
            )
        )
    )
    | {-1: "VMT_INVALID"},
    VehicleModKitType: dict(
        enumerate(("MKT_STANDARD", "MKT_SPORT", "MKT_SUV", "MKT_SPECIAL"))
    ),
    VehicleModCameraPosition: dict(
        enumerate(
            (
                "VMCP_DEFAULT",
                "VMCP_FRONT",
                "VMCP_FRONT_LEFT",
                "VMCP_FRONT_RIGHT",
                "VMCP_REAR",
                "VMCP_REAR_LEFT",
                "VMCP_REAR_RIGHT",
                "VMCP_LEFT",
                "VMCP_RIGHT",
                "VMCP_TOP",
                "VMCP_BOTTOM",
            )
        )
    ),
}
_TOKEN_MEMBERS = {
    enum_type: {token: value for value, token in tokens.items()}
    for enum_type, tokens in _ENUM_TOKENS.items()
}


def _flag_text(flag_type: type[IntFlag], value: IntFlag | int) -> str:
    flags = flag_type(int(value))
    known = sum(int(flag) for flag in flag_type)
    unknown = int(flags) & ~known
    if unknown:
        raise ValueError(f"{flag_type.__name__} contains unknown bits 0x{unknown:X}")
    return " ".join(flag.name for flag in flag_type if flag in flags)


def _parse_flags(flag_type: type[IntFlag], value: object) -> IntFlag:
    if isinstance(value, str):
        flags = flag_type(0)
        for token in value.replace("|", " ").split():
            try:
                flags |= flag_type[token.upper()]
            except KeyError as exc:
                raise ValueError(
                    f"Unknown {flag_type.__name__} token {token!r}"
                ) from exc
        return flags
    return flag_type(int(value or 0))


def vehicle_model_flag_text(value: VehicleModelFlags | VehicleModelFlag | int) -> str:
    if isinstance(value, VehicleModelFlags):
        known = _flag_text(VehicleModelFlag, value.known)
        return " ".join(filter(None, (known, *value.unknown_tokens)))
    return _flag_text(VehicleModelFlag, value)


def parse_vehicle_model_flags(value: object) -> VehicleModelFlags:
    if isinstance(value, VehicleModelFlags):
        return value
    if not isinstance(value, str):
        return VehicleModelFlags(VehicleModelFlag(int(value or 0)))
    known = VehicleModelFlag(0)
    unknown: list[str] = []
    for token in value.replace("|", " ").split():
        try:
            known |= VehicleModelFlag[token.upper()]
        except KeyError:
            unknown.append(token)
    return VehicleModelFlags(known, tuple(unknown))


def vehicle_extra_flag_text(value: VehicleExtraFlag | int) -> str:
    return _flag_text(VehicleExtraFlag, value)


def parse_vehicle_extra_flags(value: object) -> VehicleExtraFlag:
    return VehicleExtraFlag(_parse_flags(VehicleExtraFlag, value))


__all__ = [
    "HandlingType",
    "VehicleClass",
    "VehicleDashboardType",
    "VehicleDoor",
    "VehicleExtraFlag",
    "VehicleMetaEnum",
    "VehicleModCameraPosition",
    "VehicleModKitType",
    "VehicleModType",
    "VehicleModelFlag",
    "VehicleModelFlags",
    "VehiclePlateType",
    "VehicleSwankness",
    "VehicleType",
    "VehicleWheelType",
    "VehicleWindow",
    "parse_vehicle_extra_flags",
    "parse_vehicle_model_flags",
    "vehicle_extra_flag_text",
    "vehicle_model_flag_text",
]
