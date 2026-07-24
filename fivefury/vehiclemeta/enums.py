from __future__ import annotations

from enum import IntEnum


class VehicleType(IntEnum):
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


class VehicleDoor(IntEnum):
    INVALID = -1
    DRIVER_FRONT = 0
    DRIVER_REAR = 1
    PASSENGER_FRONT = 2
    PASSENGER_REAR = 3
    BONNET = 4
    BOOT = 5


class VehicleWindow(IntEnum):
    INVALID = -1
    WINDSCREEN = 0
    REAR_WINDSCREEN = 1
    LEFT_FRONT = 2
    RIGHT_FRONT = 3
    LEFT_REAR = 4
    RIGHT_REAR = 5
    LEFT_MIDDLE = 6
    RIGHT_MIDDLE = 7


class VehicleSwankness(IntEnum):
    ZERO = 0
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5


class VehicleWheelType(IntEnum):
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


class VehiclePlateType(IntEnum):
    FRONT_AND_BACK = 0
    FRONT = 1
    BACK = 2
    NONE = 3


class VehicleClass(IntEnum):
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


class VehicleDashboardType(IntEnum):
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


class HandlingType(IntEnum):
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


class VehicleModType(IntEnum):
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


class VehicleModKitType(IntEnum):
    STANDARD = 0
    SPORT = 1
    SUV = 2
    SPECIAL = 3


class VehicleModCameraPosition(IntEnum):
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


__all__ = [
    "HandlingType",
    "VehicleClass",
    "VehicleDashboardType",
    "VehicleDoor",
    "VehicleModCameraPosition",
    "VehicleModKitType",
    "VehicleModType",
    "VehiclePlateType",
    "VehicleSwankness",
    "VehicleType",
    "VehicleWheelType",
    "VehicleWindow",
]
