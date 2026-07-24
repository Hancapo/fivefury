from __future__ import annotations

import dataclasses
from typing import Any

from ..gtxd import TxdRelationship
from ..metahash import MetaHash
from .common import boolean, enum_value, field, items, meta_hash, number, text, vector
from .enums import (
    VehicleClass,
    VehicleDashboardType,
    VehicleDoor,
    VehiclePlateType,
    VehicleSwankness,
    VehicleType,
    VehicleWheelType,
    VehicleWindow,
)


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleDriver:
    driver_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    npc_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleDriver:
        return cls(
            driver_name=meta_hash(field(value, "m_driverName", "driverName")),
            npc_name=meta_hash(field(value, "m_npcName", "npcName")),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleDoorStiffness:
    door: VehicleDoor | int = VehicleDoor.INVALID
    multiplier: float = 1.0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleDoorStiffness:
        return cls(
            door=enum_value(
                VehicleDoor, field(value, "m_doorId", "doorId"), VehicleDoor.INVALID
            ),
            multiplier=number(field(value, "m_stiffnessMult", "stiffnessMult"), 1.0),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleVfxExtra:
    extras: int = 0
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    offset: tuple[float, ...] = (0.0, 0.0, 0.0)
    range: float = 40.0
    speed_evolution_min: float = 5.0
    speed_evolution_max: float = 20.0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleVfxExtra:
        return cls(
            extras=number(field(value, "m_ptFxExtras", "ptFxExtras"), 0),
            name=meta_hash(field(value, "m_ptFxName", "ptFxName")),
            offset=vector(field(value, "m_ptFxOffset", "ptFxOffset")),
            range=number(field(value, "m_ptFxRange", "ptFxRange"), 40.0),
            speed_evolution_min=number(
                field(value, "m_ptFxSpeedEvoMin", "ptFxSpeedEvoMin"), 5.0
            ),
            speed_evolution_max=number(
                field(value, "m_ptFxSpeedEvoMax", "ptFxSpeedEvoMax"), 20.0
            ),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleMobilePhoneSeatOffset:
    offset: tuple[float, ...] = (0.0, 0.0, 0.0)
    seat_index: int = 0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleMobilePhoneSeatOffset:
        return cls(
            offset=vector(field(value, "m_Offset", "Offset", "offset")),
            seat_index=number(field(value, "m_SeatIndex", "SeatIndex", "seatIndex"), 0),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleRagdollThreshold:
    min_component: int = -1
    max_component: int = -1
    multiplier: float = 1.0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleRagdollThreshold:
        return cls(
            min_component=number(field(value, "m_MinComponent", "MinComponent"), -1),
            max_component=number(field(value, "m_MaxComponent", "MaxComponent"), -1),
            multiplier=number(field(value, "m_ThresholdMult", "ThresholdMult"), 1.0),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleWaterSample:
    position: tuple[float, ...] = (0.0, 0.0, 0.0)
    size: float = 0.0
    component: int = 0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleWaterSample:
        return cls(
            position=vector(field(value, "m_position", "position")),
            size=number(field(value, "m_size", "size"), 0.0),
            component=number(field(value, "m_component", "component"), 0),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleInitData:
    model_name: str = ""
    txd_name: str = ""
    handling_id: str = ""
    game_name: str = ""
    make_name: str = ""
    expression_dictionary: str = ""
    expression_name: str = ""
    convertible_roof_dictionary: str = ""
    convertible_roof_animation: str = ""
    convertible_roof_windows: list[VehicleWindow | int] = dataclasses.field(
        default_factory=list
    )
    particle_asset_name: str = ""
    audio_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    layout: MetaHash = dataclasses.field(default_factory=MetaHash)
    pov_tuning: MetaHash = dataclasses.field(default_factory=MetaHash)
    cover_bound_offsets: MetaHash = dataclasses.field(default_factory=MetaHash)
    explosion_info: MetaHash = dataclasses.field(default_factory=MetaHash)
    scenario_layout: MetaHash = dataclasses.field(default_factory=MetaHash)
    camera_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    aim_camera_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    bonnet_camera_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    pov_camera_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    pov_turret_camera_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    first_person_driveby_data: list[MetaHash] = dataclasses.field(default_factory=list)
    first_person_ik_offsets: dict[str, tuple[float, ...]] = dataclasses.field(
        default_factory=dict
    )
    mobile_phone_seat_offsets: list[VehicleMobilePhoneSeatOffset] = dataclasses.field(
        default_factory=list
    )
    pov_camera_offset: tuple[float, ...] = (0.0, 0.0, 0.0)
    pov_passenger_camera_offset: tuple[float, ...] = (0.0, 0.0, 0.0)
    pov_rear_passenger_camera_offset: tuple[float, ...] = (0.0, 0.0, 0.0)
    pov_camera_roll_cage_adjustment: float = 0.0
    vfx_info_name: MetaHash = dataclasses.field(default_factory=MetaHash)
    cinematic_view: bool = True
    camera_transition_on_climb: bool = False
    camera_ignore_exiting: bool = False
    allow_pretend_occupants: bool = True
    allow_joyriding: bool = True
    allow_sunday_driving: bool = True
    allow_body_color_mapping: bool = True
    wheel_scale: float = 0.0
    rear_wheel_scale: float = 0.0
    dirt_level_min: float = 0.0
    dirt_level_max: float = 0.0
    environment_effect_scale_min: float = 0.0
    environment_effect_scale_max: float = 0.0
    secondary_environment_effect_scale_min: float = 0.0
    secondary_environment_effect_scale_max: float = 0.0
    damage_map_scale: float = 0.0
    damage_offset_scale: float = 1.0
    diffuse_tint: int = 0x00FFFFFF
    steering_wheel_multiplier: float = 1.2
    first_person_steering_wheel_multiplier: float = -1.0
    hd_texture_distance: float = 5.0
    lod_distances: list[float] = dataclasses.field(default_factory=list)
    identical_model_spawn_distance: int = 0
    max_same_color: int = 10
    default_body_health: float = 1000.0
    pretend_occupants_scale: float = 1.0
    visible_spawn_distance_scale: float = 1.0
    tracker_path_width: float = 2.0
    weapon_force_multiplier: float = 1.0
    frequency: int = 0
    max_number: int = 0
    flags: int = 0
    vehicle_type: VehicleType | int = VehicleType.CAR
    plate_type: VehiclePlateType | int = VehiclePlateType.FRONT_AND_BACK
    vehicle_class: VehicleClass | int = VehicleClass.COMPACT
    dashboard_type: VehicleDashboardType | int = VehicleDashboardType.TAILGATER
    wheel_type: VehicleWheelType | int = VehicleWheelType.SPORT
    swankness: VehicleSwankness | int = VehicleSwankness.ZERO
    trailers: list[MetaHash] = dataclasses.field(default_factory=list)
    additional_trailers: list[MetaHash] = dataclasses.field(default_factory=list)
    drivers: list[VehicleDriver] = dataclasses.field(default_factory=list)
    extra_includes: list[int] = dataclasses.field(default_factory=list)
    vfx_extras: list[VehicleVfxExtra] = dataclasses.field(default_factory=list)
    closed_collision_doors: list[VehicleDoor | int] = dataclasses.field(
        default_factory=list
    )
    driveable_doors: list[VehicleDoor | int] = dataclasses.field(default_factory=list)
    door_stiffness: list[VehicleDoorStiffness] = dataclasses.field(default_factory=list)
    bumpers_collide_with_map: bool = False
    needs_rope_texture: bool = False
    required_extras: int = 0
    rewards: list[MetaHash] = dataclasses.field(default_factory=list)
    cinematic_part_cameras: list[MetaHash] = dataclasses.field(default_factory=list)
    brace_override_set: MetaHash = dataclasses.field(default_factory=MetaHash)
    buoyancy_sphere_offset: tuple[float, ...] = (0.0, 0.0, 0.0)
    buoyancy_sphere_scale: float = 1.0
    water_samples: list[VehicleWaterSample] = dataclasses.field(default_factory=list)
    ragdoll_threshold: VehicleRagdollThreshold | None = None
    max_steering_wheel_angle: float = 109.0
    max_steering_wheel_animation_angle: float = 90.0
    min_seat_height: float = -1.0
    lock_on_position_offset: tuple[float, ...] = (0.0, 0.0, 0.0)
    lowrider_arm_window_height: float = 1.0
    lowrider_lean_acceleration_multiplier: float = 1.0
    seat_count_override: int = -1
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleInitData:
        ragdoll = field(
            value, "m_pOverrideRagdollThreshold", "pOverrideRagdollThreshold"
        )
        return cls(
            model_name=text(field(value, "m_modelName", "modelName")),
            txd_name=text(field(value, "m_txdName", "txdName")),
            handling_id=text(field(value, "m_handlingId", "handlingId")),
            game_name=text(field(value, "m_gameName", "gameName")),
            make_name=text(field(value, "m_vehicleMakeName", "vehicleMakeName")),
            expression_dictionary=text(
                field(value, "m_expressionDictName", "expressionDictName")
            ),
            expression_name=text(field(value, "m_expressionName", "expressionName")),
            convertible_roof_dictionary=text(
                field(value, "m_animConvRoofDictName", "animConvRoofDictName")
            ),
            convertible_roof_animation=text(
                field(value, "m_animConvRoofName", "animConvRoofName")
            ),
            convertible_roof_windows=[
                enum_value(VehicleWindow, item, VehicleWindow.INVALID)
                for item in items(
                    value,
                    "m_animConvRoofWindowsAffected",
                    "animConvRoofWindowsAffected",
                )
            ],
            particle_asset_name=text(field(value, "m_ptfxAssetName", "ptfxAssetName")),
            audio_name=meta_hash(field(value, "m_audioNameHash", "audioNameHash")),
            layout=meta_hash(field(value, "m_layout", "layout")),
            pov_tuning=meta_hash(field(value, "m_POVTuningInfo", "POVTuningInfo")),
            cover_bound_offsets=meta_hash(
                field(value, "m_coverBoundOffsets", "coverBoundOffsets")
            ),
            explosion_info=meta_hash(field(value, "m_explosionInfo", "explosionInfo")),
            scenario_layout=meta_hash(
                field(value, "m_scenarioLayout", "scenarioLayout")
            ),
            camera_name=meta_hash(field(value, "m_cameraName", "cameraName")),
            aim_camera_name=meta_hash(field(value, "m_aimCameraName", "aimCameraName")),
            bonnet_camera_name=meta_hash(
                field(value, "m_bonnetCameraName", "bonnetCameraName")
            ),
            pov_camera_name=meta_hash(field(value, "m_povCameraName", "povCameraName")),
            pov_turret_camera_name=meta_hash(
                field(value, "m_povTurretCameraName", "povTurretCameraName")
            ),
            first_person_driveby_data=[
                meta_hash(item)
                for item in items(
                    value, "m_firstPersonDrivebyData", "firstPersonDrivebyData"
                )
            ],
            first_person_ik_offsets={
                semantic_name: vector(
                    field(value, source_name, source_name.removeprefix("m_"))
                )
                for semantic_name, source_name in (
                    ("driver_armed", "m_FirstPersonDriveByIKOffset"),
                    ("driver_unarmed", "m_FirstPersonDriveByUnarmedIKOffset"),
                    (
                        "left_passenger_armed",
                        "m_FirstPersonDriveByLeftPassengerIKOffset",
                    ),
                    (
                        "right_passenger_armed",
                        "m_FirstPersonDriveByRightPassengerIKOffset",
                    ),
                    (
                        "right_rear_passenger_armed",
                        "m_FirstPersonDriveByRightRearPassengerIKOffset",
                    ),
                    (
                        "left_passenger_unarmed",
                        "m_FirstPersonDriveByLeftPassengerUnarmedIKOffset",
                    ),
                    (
                        "right_passenger_unarmed",
                        "m_FirstPersonDriveByRightPassengerUnarmedIKOffset",
                    ),
                    ("driver_projectile", "m_FirstPersonProjectileDriveByIKOffset"),
                    (
                        "passenger_projectile",
                        "m_FirstPersonProjectileDriveByPassengerIKOffset",
                    ),
                    (
                        "rear_left_projectile",
                        "m_FirstPersonProjectileDriveByRearLeftIKOffset",
                    ),
                    (
                        "rear_right_projectile",
                        "m_FirstPersonProjectileDriveByRearRightIKOffset",
                    ),
                    ("visor_switch", "m_FirstPersonVisorSwitchIKOffset"),
                    ("driver_mobile_phone", "m_FirstPersonMobilePhoneOffset"),
                    (
                        "passenger_mobile_phone",
                        "m_FirstPersonPassengerMobilePhoneOffset",
                    ),
                )
            },
            mobile_phone_seat_offsets=[
                VehicleMobilePhoneSeatOffset.from_value(item)
                for item in items(
                    value,
                    "m_FirstPersonMobilePhoneSeatIKOffset",
                    "FirstPersonMobilePhoneSeatIKOffset",
                )
            ],
            pov_camera_offset=vector(
                field(value, "m_PovCameraOffset", "PovCameraOffset")
            ),
            pov_passenger_camera_offset=vector(
                field(value, "m_PovPassengerCameraOffset", "PovPassengerCameraOffset")
            ),
            pov_rear_passenger_camera_offset=vector(
                field(
                    value,
                    "m_PovRearPassengerCameraOffset",
                    "PovRearPassengerCameraOffset",
                )
            ),
            pov_camera_roll_cage_adjustment=number(
                field(
                    value,
                    "m_PovCameraVerticalAdjustmentForRollCage",
                    "PovCameraVerticalAdjustmentForRollCage",
                ),
                0.0,
            ),
            vfx_info_name=meta_hash(field(value, "m_vfxInfoName", "vfxInfoName")),
            cinematic_view=boolean(
                field(
                    value, "m_shouldUseCinematicViewMode", "shouldUseCinematicViewMode"
                ),
                True,
            ),
            camera_transition_on_climb=boolean(
                field(
                    value,
                    "m_shouldCameraTransitionOnClimbUpDown",
                    "shouldCameraTransitionOnClimbUpDown",
                )
            ),
            camera_ignore_exiting=boolean(
                field(value, "m_shouldCameraIgnoreExiting", "shouldCameraIgnoreExiting")
            ),
            allow_pretend_occupants=boolean(
                field(value, "m_AllowPretendOccupants", "AllowPretendOccupants"), True
            ),
            allow_joyriding=boolean(
                field(value, "m_AllowJoyriding", "AllowJoyriding"), True
            ),
            allow_sunday_driving=boolean(
                field(value, "m_AllowSundayDriving", "AllowSundayDriving"), True
            ),
            allow_body_color_mapping=boolean(
                field(value, "m_AllowBodyColorMapping", "AllowBodyColorMapping"), True
            ),
            wheel_scale=number(field(value, "m_wheelScale", "wheelScale"), 0.0),
            rear_wheel_scale=number(
                field(value, "m_wheelScaleRear", "wheelScaleRear"), 0.0
            ),
            dirt_level_min=number(field(value, "m_dirtLevelMin", "dirtLevelMin"), 0.0),
            dirt_level_max=number(field(value, "m_dirtLevelMax", "dirtLevelMax"), 0.0),
            environment_effect_scale_min=number(
                field(value, "m_envEffScaleMin", "envEffScaleMin"), 0.0
            ),
            environment_effect_scale_max=number(
                field(value, "m_envEffScaleMax", "envEffScaleMax"), 0.0
            ),
            secondary_environment_effect_scale_min=number(
                field(value, "m_envEffScaleMin2", "envEffScaleMin2"), 0.0
            ),
            secondary_environment_effect_scale_max=number(
                field(value, "m_envEffScaleMax2", "envEffScaleMax2"), 0.0
            ),
            damage_map_scale=number(
                field(value, "m_damageMapScale", "damageMapScale"), 0.0
            ),
            damage_offset_scale=number(
                field(value, "m_damageOffsetScale", "damageOffsetScale"), 1.0
            ),
            diffuse_tint=number(
                field(value, "m_diffuseTint", "diffuseTint"), 0x00FFFFFF
            ),
            steering_wheel_multiplier=number(
                field(value, "m_steerWheelMult", "steerWheelMult"), 1.2
            ),
            first_person_steering_wheel_multiplier=number(
                field(
                    value, "m_firstPersonSteerWheelMult", "firstPersonSteerWheelMult"
                ),
                -1.0,
            ),
            hd_texture_distance=number(
                field(value, "m_HDTextureDist", "HDTextureDist"), 5.0
            ),
            lod_distances=[
                float(item) for item in items(value, "m_lodDistances", "lodDistances")
            ],
            identical_model_spawn_distance=number(
                field(
                    value,
                    "m_identicalModelSpawnDistance",
                    "identicalModelSpawnDistance",
                ),
                0,
            ),
            max_same_color=number(
                field(value, "m_maxNumOfSameColor", "maxNumOfSameColor"), 10
            ),
            default_body_health=number(
                field(value, "m_defaultBodyHealth", "defaultBodyHealth"), 1000.0
            ),
            pretend_occupants_scale=number(
                field(value, "m_pretendOccupantsScale", "pretendOccupantsScale"), 1.0
            ),
            visible_spawn_distance_scale=number(
                field(value, "m_visibleSpawnDistScale", "visibleSpawnDistScale"), 1.0
            ),
            tracker_path_width=number(
                field(value, "m_trackerPathWidth", "trackerPathWidth"), 2.0
            ),
            weapon_force_multiplier=number(
                field(value, "m_weaponForceMult", "weaponForceMult"), 1.0
            ),
            frequency=number(field(value, "m_frequency", "frequency"), 0),
            max_number=number(field(value, "m_maxNum", "maxNum"), 0),
            flags=number(field(value, "m_flags", "flags"), 0),
            vehicle_type=enum_value(
                VehicleType, field(value, "m_type", "type"), VehicleType.CAR
            ),
            plate_type=enum_value(
                VehiclePlateType,
                field(value, "m_plateType", "plateType"),
                VehiclePlateType.FRONT_AND_BACK,
            ),
            vehicle_class=enum_value(
                VehicleClass,
                field(value, "m_vehicleClass", "vehicleClass"),
                VehicleClass.COMPACT,
            ),
            dashboard_type=enum_value(
                VehicleDashboardType,
                field(value, "m_dashboardType", "dashboardType"),
                VehicleDashboardType.TAILGATER,
            ),
            wheel_type=enum_value(
                VehicleWheelType,
                field(value, "m_wheelType", "wheelType"),
                VehicleWheelType.SPORT,
            ),
            swankness=enum_value(
                VehicleSwankness,
                field(value, "m_swankness", "swankness"),
                VehicleSwankness.ZERO,
            ),
            trailers=[
                meta_hash(item) for item in items(value, "m_trailers", "trailers")
            ],
            additional_trailers=[
                meta_hash(item)
                for item in items(value, "m_additionalTrailers", "additionalTrailers")
            ],
            drivers=[
                VehicleDriver.from_value(item)
                for item in items(value, "m_drivers", "drivers")
            ],
            extra_includes=[
                int(item) for item in items(value, "m_extraIncludes", "extraIncludes")
            ],
            vfx_extras=[
                VehicleVfxExtra.from_value(item)
                for item in items(value, "m_vfxExtraInfos", "vfxExtraInfos")
            ],
            closed_collision_doors=[
                enum_value(VehicleDoor, item, VehicleDoor.INVALID)
                for item in items(
                    value,
                    "m_doorsWithCollisionWhenClosed",
                    "doorsWithCollisionWhenClosed",
                )
            ],
            driveable_doors=[
                enum_value(VehicleDoor, item, VehicleDoor.INVALID)
                for item in items(value, "m_driveableDoors", "driveableDoors")
            ],
            door_stiffness=[
                VehicleDoorStiffness.from_value(item)
                for item in items(
                    value, "m_doorStiffnessMultipliers", "doorStiffnessMultipliers"
                )
            ],
            bumpers_collide_with_map=boolean(
                field(
                    value,
                    "m_bumpersNeedToCollideWithMap",
                    "bumpersNeedToCollideWithMap",
                )
            ),
            needs_rope_texture=boolean(
                field(value, "m_needsRopeTexture", "needsRopeTexture")
            ),
            required_extras=number(
                field(value, "m_requiredExtras", "requiredExtras"), 0
            ),
            rewards=[meta_hash(item) for item in items(value, "m_rewards", "rewards")],
            cinematic_part_cameras=[
                meta_hash(item)
                for item in items(value, "m_cinematicPartCamera", "cinematicPartCamera")
            ],
            brace_override_set=meta_hash(
                field(value, "m_NmBraceOverrideSet", "NmBraceOverrideSet")
            ),
            buoyancy_sphere_offset=vector(
                field(value, "m_buoyancySphereOffset", "buoyancySphereOffset")
            ),
            buoyancy_sphere_scale=number(
                field(value, "m_buoyancySphereSizeScale", "buoyancySphereSizeScale"),
                1.0,
            ),
            water_samples=[
                VehicleWaterSample.from_value(item)
                for item in items(
                    value, "m_additionalVfxWaterSamples", "additionalVfxWaterSamples"
                )
            ],
            ragdoll_threshold=VehicleRagdollThreshold.from_value(ragdoll)
            if ragdoll is not None
            else None,
            max_steering_wheel_angle=number(
                field(value, "m_maxSteeringWheelAngle", "maxSteeringWheelAngle"), 109.0
            ),
            max_steering_wheel_animation_angle=number(
                field(
                    value, "m_maxSteeringWheelAnimAngle", "maxSteeringWheelAnimAngle"
                ),
                90.0,
            ),
            min_seat_height=number(
                field(value, "m_minSeatHeight", "minSeatHeight"), -1.0
            ),
            lock_on_position_offset=vector(
                field(value, "m_lockOnPositionOffset", "lockOnPositionOffset")
            ),
            lowrider_arm_window_height=number(
                field(value, "m_LowriderArmWindowHeight", "LowriderArmWindowHeight"),
                1.0,
            ),
            lowrider_lean_acceleration_multiplier=number(
                field(
                    value,
                    "m_LowriderLeanAccelModifier",
                    "LowriderLeanAccelModifier",
                ),
                1.0,
            ),
            seat_count_override=number(
                field(value, "m_numSeatsOverride", "numSeatsOverride"), -1
            ),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleInitDataList:
    resident_txd: str = ""
    resident_animations: list[str] = dataclasses.field(default_factory=list)
    vehicles: list[VehicleInitData] = dataclasses.field(default_factory=list)
    txd_relationships: list[TxdRelationship] = dataclasses.field(default_factory=list)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> VehicleInitDataList:
        relationships: list[TxdRelationship] = []
        for item in items(value, "m_txdRelationships", "txdRelationships"):
            parent = text(field(item, "parent", "m_parent"))
            child = text(field(item, "child", "m_child"))
            if parent and child:
                relationships.append(TxdRelationship(child=child, parent=parent))
        return cls(
            resident_txd=text(field(value, "m_residentTxd", "residentTxd")),
            resident_animations=[
                text(item) for item in items(value, "m_residentAnims", "residentAnims")
            ],
            vehicles=[
                VehicleInitData.from_value(item)
                for item in items(value, "m_InitDatas", "InitDatas")
            ],
            txd_relationships=relationships,
            raw=value,
        )

    def get(self, model_name: str) -> VehicleInitData | None:
        target = model_name.casefold()
        return next(
            (
                vehicle
                for vehicle in self.vehicles
                if vehicle.model_name.casefold() == target
            ),
            None,
        )


__all__ = [
    "VehicleDoorStiffness",
    "VehicleDriver",
    "VehicleInitData",
    "VehicleInitDataList",
    "VehicleMobilePhoneSeatOffset",
    "VehicleRagdollThreshold",
    "VehicleVfxExtra",
    "VehicleWaterSample",
]
