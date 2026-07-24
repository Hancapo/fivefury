from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any, ClassVar

from ..metahash import MetaHash
from .common import (
    field,
    fields,
    items,
    meta_hash,
    node_type_name,
    number,
    vector,
)


@dataclasses.dataclass(slots=True, frozen=True)
class HandlingSubData:
    TYPE_NAME: ClassVar[str] = "CBaseSubHandlingData"
    values: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> HandlingSubData:
        return cls(values=dict(fields(value)), raw=value)


@dataclasses.dataclass(slots=True, frozen=True)
class BoatHandlingData(HandlingSubData):
    TYPE_NAME: ClassVar[str] = "CBoatHandlingData"


@dataclasses.dataclass(slots=True, frozen=True)
class SeaPlaneHandlingData(HandlingSubData):
    TYPE_NAME: ClassVar[str] = "CSeaPlaneHandlingData"


@dataclasses.dataclass(slots=True, frozen=True)
class FlyingHandlingData(HandlingSubData):
    TYPE_NAME: ClassVar[str] = "CFlyingHandlingData"


@dataclasses.dataclass(slots=True, frozen=True)
class VehicleWeaponHandlingData(HandlingSubData):
    TYPE_NAME: ClassVar[str] = "CVehicleWeaponHandlingData"


@dataclasses.dataclass(slots=True, frozen=True)
class BikeHandlingData(HandlingSubData):
    TYPE_NAME: ClassVar[str] = "CBikeHandlingData"


@dataclasses.dataclass(slots=True, frozen=True)
class SubmarineHandlingData(HandlingSubData):
    TYPE_NAME: ClassVar[str] = "CSubmarineHandlingData"


@dataclasses.dataclass(slots=True, frozen=True)
class TrailerHandlingData(HandlingSubData):
    TYPE_NAME: ClassVar[str] = "CTrailerHandlingData"


@dataclasses.dataclass(slots=True, frozen=True)
class CarHandlingData(HandlingSubData):
    TYPE_NAME: ClassVar[str] = "CCarHandlingData"


@dataclasses.dataclass(slots=True, frozen=True)
class SpecialFlightHandlingData(HandlingSubData):
    TYPE_NAME: ClassVar[str] = "CSpecialFlightHandlingData"


_SUB_HANDLING_TYPES: dict[str, type[HandlingSubData]] = {
    item.TYPE_NAME: item
    for item in (
        BoatHandlingData,
        SeaPlaneHandlingData,
        FlyingHandlingData,
        VehicleWeaponHandlingData,
        BikeHandlingData,
        SubmarineHandlingData,
        TrailerHandlingData,
        CarHandlingData,
        SpecialFlightHandlingData,
    )
}


def map_sub_handling(value: Any) -> HandlingSubData:
    model_type = _SUB_HANDLING_TYPES.get(node_type_name(value), HandlingSubData)
    return model_type.from_value(value)


@dataclasses.dataclass(slots=True, frozen=True)
class HandlingData:
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    mass: float = 0.0
    initial_drag_coefficient: float = 0.0
    percent_submerged: float = 0.0
    center_of_mass_offset: tuple[float, ...] = (0.0, 0.0, 0.0)
    inertia_multiplier: tuple[float, ...] = (0.0, 0.0, 0.0)
    drive_bias_front: float = 0.0
    initial_drive_gears: int = 0
    initial_drive_force: float = 0.0
    drive_inertia: float = 0.0
    clutch_change_rate_up: float = 0.0
    clutch_change_rate_down: float = 0.0
    initial_drive_max_flat_velocity: float = 0.0
    brake_force: float = 0.0
    brake_bias_front: float = 0.0
    handbrake_force: float = 0.0
    steering_lock: float = 0.0
    traction_curve_max: float = 0.0
    traction_curve_min: float = 0.0
    traction_curve_lateral: float = 0.0
    traction_spring_delta_max: float = 0.0
    low_speed_traction_loss_multiplier: float = 0.0
    camber_stiffness: float = 0.0
    traction_bias_front: float = 0.0
    traction_loss_multiplier: float = 0.0
    suspension_force: float = 0.0
    suspension_compression_damping: float = 0.0
    suspension_rebound_damping: float = 0.0
    suspension_upper_limit: float = 0.0
    suspension_lower_limit: float = 0.0
    suspension_raise: float = 0.0
    suspension_bias_front: float = 0.0
    anti_roll_bar_force: float = 0.0
    anti_roll_bar_bias_front: float = 0.0
    roll_center_height_front: float = 0.0
    roll_center_height_rear: float = 0.0
    collision_damage_multiplier: float = 0.0
    weapon_damage_multiplier: float = 0.0
    deformation_damage_multiplier: float = 0.0
    engine_damage_multiplier: float = 0.0
    petrol_tank_volume: float = 0.0
    oil_volume: float = 0.0
    petrol_consumption_rate: float = 0.5
    seat_offset_x: float = 0.0
    seat_offset_y: float = 0.0
    seat_offset_z: float = 0.0
    monetary_value: int = 0
    model_flags: MetaHash = dataclasses.field(default_factory=MetaHash)
    handling_flags: MetaHash = dataclasses.field(default_factory=MetaHash)
    damage_flags: MetaHash = dataclasses.field(default_factory=MetaHash)
    ai_handling: MetaHash = dataclasses.field(default_factory=MetaHash)
    sub_handling: list[HandlingSubData] = dataclasses.field(default_factory=list)
    weapon_damage_to_health_multiplier: float = 0.5
    downforce_modifier: float = 0.0
    popup_light_rotation: float = 0.0
    rocket_boost_capacity: float = 1.25
    boost_max_speed: float = 70.0
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> HandlingData:
        return cls(
            name=meta_hash(field(value, "m_handlingName", "handlingName")),
            mass=number(field(value, "m_fMass", "fMass"), 0.0),
            initial_drag_coefficient=number(
                field(value, "m_fInitialDragCoeff", "fInitialDragCoeff"), 0.0
            ),
            percent_submerged=number(
                field(value, "m_fPercentSubmerged", "fPercentSubmerged"), 0.0
            ),
            center_of_mass_offset=vector(
                field(value, "m_vecCentreOfMassOffset", "vecCentreOfMassOffset")
            ),
            inertia_multiplier=vector(
                field(value, "m_vecInertiaMultiplier", "vecInertiaMultiplier")
            ),
            drive_bias_front=number(
                field(value, "m_fDriveBiasFront", "fDriveBiasFront"), 0.0
            ),
            initial_drive_gears=number(
                field(value, "m_nInitialDriveGears", "nInitialDriveGears"), 0
            ),
            initial_drive_force=number(
                field(value, "m_fInitialDriveForce", "fInitialDriveForce"), 0.0
            ),
            drive_inertia=number(field(value, "m_fDriveInertia", "fDriveInertia"), 0.0),
            clutch_change_rate_up=number(
                field(
                    value,
                    "m_fClutchChangeRateScaleUpShift",
                    "fClutchChangeRateScaleUpShift",
                ),
                0.0,
            ),
            clutch_change_rate_down=number(
                field(
                    value,
                    "m_fClutchChangeRateScaleDownShift",
                    "fClutchChangeRateScaleDownShift",
                ),
                0.0,
            ),
            initial_drive_max_flat_velocity=number(
                field(value, "m_fInitialDriveMaxFlatVel", "fInitialDriveMaxFlatVel"),
                0.0,
            ),
            brake_force=number(field(value, "m_fBrakeForce", "fBrakeForce"), 0.0),
            brake_bias_front=number(
                field(value, "m_fBrakeBiasFront", "fBrakeBiasFront"), 0.0
            ),
            handbrake_force=number(
                field(value, "m_fHandBrakeForce", "fHandBrakeForce"), 0.0
            ),
            steering_lock=number(field(value, "m_fSteeringLock", "fSteeringLock"), 0.0),
            traction_curve_max=number(
                field(value, "m_fTractionCurveMax", "fTractionCurveMax"), 0.0
            ),
            traction_curve_min=number(
                field(value, "m_fTractionCurveMin", "fTractionCurveMin"), 0.0
            ),
            traction_curve_lateral=number(
                field(value, "m_fTractionCurveLateral", "fTractionCurveLateral"), 0.0
            ),
            traction_spring_delta_max=number(
                field(value, "m_fTractionSpringDeltaMax", "fTractionSpringDeltaMax"),
                0.0,
            ),
            low_speed_traction_loss_multiplier=number(
                field(
                    value, "m_fLowSpeedTractionLossMult", "fLowSpeedTractionLossMult"
                ),
                0.0,
            ),
            camber_stiffness=number(
                field(value, "m_fCamberStiffnesss", "fCamberStiffnesss"), 0.0
            ),
            traction_bias_front=number(
                field(value, "m_fTractionBiasFront", "fTractionBiasFront"), 0.0
            ),
            traction_loss_multiplier=number(
                field(value, "m_fTractionLossMult", "fTractionLossMult"), 0.0
            ),
            suspension_force=number(
                field(value, "m_fSuspensionForce", "fSuspensionForce"), 0.0
            ),
            suspension_compression_damping=number(
                field(value, "m_fSuspensionCompDamp", "fSuspensionCompDamp"), 0.0
            ),
            suspension_rebound_damping=number(
                field(value, "m_fSuspensionReboundDamp", "fSuspensionReboundDamp"), 0.0
            ),
            suspension_upper_limit=number(
                field(value, "m_fSuspensionUpperLimit", "fSuspensionUpperLimit"), 0.0
            ),
            suspension_lower_limit=number(
                field(value, "m_fSuspensionLowerLimit", "fSuspensionLowerLimit"), 0.0
            ),
            suspension_raise=number(
                field(value, "m_fSuspensionRaise", "fSuspensionRaise"), 0.0
            ),
            suspension_bias_front=number(
                field(value, "m_fSuspensionBiasFront", "fSuspensionBiasFront"), 0.0
            ),
            anti_roll_bar_force=number(
                field(value, "m_fAntiRollBarForce", "fAntiRollBarForce"), 0.0
            ),
            anti_roll_bar_bias_front=number(
                field(value, "m_fAntiRollBarBiasFront", "fAntiRollBarBiasFront"), 0.0
            ),
            roll_center_height_front=number(
                field(value, "m_fRollCentreHeightFront", "fRollCentreHeightFront"), 0.0
            ),
            roll_center_height_rear=number(
                field(value, "m_fRollCentreHeightRear", "fRollCentreHeightRear"), 0.0
            ),
            collision_damage_multiplier=number(
                field(value, "m_fCollisionDamageMult", "fCollisionDamageMult"), 0.0
            ),
            weapon_damage_multiplier=number(
                field(value, "m_fWeaponDamageMult", "fWeaponDamageMult"), 0.0
            ),
            deformation_damage_multiplier=number(
                field(value, "m_fDeformationDamageMult", "fDeformationDamageMult"), 0.0
            ),
            engine_damage_multiplier=number(
                field(value, "m_fEngineDamageMult", "fEngineDamageMult"), 0.0
            ),
            petrol_tank_volume=number(
                field(value, "m_fPetrolTankVolume", "fPetrolTankVolume"), 0.0
            ),
            oil_volume=number(field(value, "m_fOilVolume", "fOilVolume"), 0.0),
            petrol_consumption_rate=number(
                field(value, "m_fPetrolConsumptionRate", "fPetrolConsumptionRate"), 0.5
            ),
            seat_offset_x=number(
                field(value, "m_fSeatOffsetDistX", "fSeatOffsetDistX"), 0.0
            ),
            seat_offset_y=number(
                field(value, "m_fSeatOffsetDistY", "fSeatOffsetDistY"), 0.0
            ),
            seat_offset_z=number(
                field(value, "m_fSeatOffsetDistZ", "fSeatOffsetDistZ"), 0.0
            ),
            monetary_value=number(
                field(value, "m_nMonetaryValue", "nMonetaryValue"), 0
            ),
            model_flags=meta_hash(field(value, "m_strModelFlags", "strModelFlags")),
            handling_flags=meta_hash(
                field(value, "m_strHandlingFlags", "strHandlingFlags")
            ),
            damage_flags=meta_hash(field(value, "m_strDamageFlags", "strDamageFlags")),
            ai_handling=meta_hash(field(value, "m_AIHandling", "AIHandling")),
            sub_handling=[
                map_sub_handling(item)
                for item in items(value, "m_SubHandlingData", "SubHandlingData")
            ],
            weapon_damage_to_health_multiplier=number(
                field(
                    value,
                    "m_fWeaponDamageScaledToVehHealthMult",
                    "fWeaponDamageScaledToVehHealthMult",
                ),
                0.5,
            ),
            downforce_modifier=number(
                field(value, "m_fDownforceModifier", "fDownforceModifier"), 0.0
            ),
            popup_light_rotation=number(
                field(value, "m_fPopUpLightRotation", "fPopUpLightRotation"), 0.0
            ),
            rocket_boost_capacity=number(
                field(value, "m_fRocketBoostCapacity", "fRocketBoostCapacity"), 1.25
            ),
            boost_max_speed=number(
                field(value, "m_fBoostMaxSpeed", "fBoostMaxSpeed"), 70.0
            ),
            raw=value,
        )


@dataclasses.dataclass(slots=True, frozen=True)
class HandlingDataManager:
    entries: list[HandlingData] = dataclasses.field(default_factory=list)
    raw: Any = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_value(cls, value: Any) -> HandlingDataManager:
        return cls(
            entries=[
                HandlingData.from_value(item)
                for item in items(value, "m_HandlingData", "HandlingData")
            ],
            raw=value,
        )

    def get(self, name: str | int | MetaHash) -> HandlingData | None:
        target = MetaHash(name)
        return next((entry for entry in self.entries if entry.name == target), None)


__all__ = [
    "BikeHandlingData",
    "BoatHandlingData",
    "CarHandlingData",
    "FlyingHandlingData",
    "HandlingData",
    "HandlingDataManager",
    "HandlingSubData",
    "SeaPlaneHandlingData",
    "SpecialFlightHandlingData",
    "SubmarineHandlingData",
    "TrailerHandlingData",
    "VehicleWeaponHandlingData",
    "map_sub_handling",
]
