from __future__ import annotations

import dataclasses
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from enum import IntEnum
from typing import Any

from ..metahash import MetaHash
from .carcols import (
    VehicleCarCols,
    VehicleCorona,
    VehicleLight,
    VehicleMetallicSetting,
    VehicleModelColor,
    VehicleModKit,
    VehiclePlates,
    VehiclePlateTexture,
    VehicleSirenLight,
    VehicleVariationGlobalData,
    VehicleWheel,
    VehicleWindowColor,
    VehicleXenonLightColor,
)
from .enums import (
    VehicleExtraFlag,
    VehicleMetaEnum,
    vehicle_extra_flag_text,
    vehicle_model_flag_text,
)
from .handling import HandlingData, HandlingDataManager, HandlingSubData
from .handling_flags import HandlingFlagValue
from .variations import (
    LicensePlateProbability,
    VehicleColorIndices,
    VehicleModelInfoVariation,
    VehicleVariation,
)
from .vehicles import (
    VehicleDoorStiffness,
    VehicleInitData,
    VehicleInitDataList,
    VehicleMobilePhoneSeatOffset,
    VehicleRagdollThreshold,
    VehicleVfxExtra,
)

_VEHICLE_TAGS = {
    "model_name": "modelName",
    "txd_name": "txdName",
    "handling_id": "handlingId",
    "game_name": "gameName",
    "make_name": "vehicleMakeName",
    "expression_dictionary": "expressionDictName",
    "expression_name": "expressionName",
    "convertible_roof_dictionary": "animConvRoofDictName",
    "convertible_roof_animation": "animConvRoofName",
    "convertible_roof_windows": "animConvRoofWindowsAffected",
    "particle_asset_name": "ptfxAssetName",
    "audio_name": "audioNameHash",
    "pov_tuning": "POVTuningInfo",
    "first_person_driveby_data": "firstPersonDrivebyData",
    "mobile_phone_seat_offsets": "FirstPersonMobilePhoneSeatIKOffset",
    "pov_camera_offset": "PovCameraOffset",
    "pov_passenger_camera_offset": "PovPassengerCameraOffset",
    "pov_rear_passenger_camera_offset": "PovRearPassengerCameraOffset",
    "pov_camera_roll_cage_adjustment": "PovCameraVerticalAdjustmentForRollCage",
    "cinematic_view": "shouldUseCinematicViewMode",
    "camera_transition_on_climb": "shouldCameraTransitionOnClimbUpDown",
    "camera_ignore_exiting": "shouldCameraIgnoreExiting",
    "allow_pretend_occupants": "AllowPretendOccupants",
    "allow_joyriding": "AllowJoyriding",
    "allow_sunday_driving": "AllowSundayDriving",
    "allow_body_color_mapping": "AllowBodyColorMapping",
    "rear_wheel_scale": "wheelScaleRear",
    "environment_effect_scale_min": "envEffScaleMin",
    "environment_effect_scale_max": "envEffScaleMax",
    "secondary_environment_effect_scale_min": "envEffScaleMin2",
    "secondary_environment_effect_scale_max": "envEffScaleMax2",
    "steering_wheel_multiplier": "steerWheelMult",
    "first_person_steering_wheel_multiplier": "firstPersonSteerWheelMult",
    "hd_texture_distance": "HDTextureDist",
    "max_same_color": "maxNumOfSameColor",
    "max_number": "maxNum",
    "visible_spawn_distance_scale": "visibleSpawnDistScale",
    "weapon_force_multiplier": "weaponForceMult",
    "vehicle_type": "type",
    "additional_trailers": "additionalTrailers",
    "extra_includes": "extraIncludes",
    "vfx_extras": "vfxExtraInfos",
    "closed_collision_doors": "doorsWithCollisionWhenClosed",
    "driveable_doors": "driveableDoors",
    "door_stiffness": "doorStiffnessMultipliers",
    "bumpers_collide_with_map": "bumpersNeedToCollideWithMap",
    "cinematic_part_cameras": "cinematicPartCamera",
    "brace_override_set": "NmBraceOverrideSet",
    "buoyancy_sphere_scale": "buoyancySphereSizeScale",
    "water_samples": "additionalVfxWaterSamples",
    "ragdoll_threshold": "pOverrideRagdollThreshold",
    "max_steering_wheel_animation_angle": "maxSteeringWheelAnimAngle",
    "lowrider_arm_window_height": "LowriderArmWindowHeight",
    "lowrider_lean_acceleration_multiplier": "LowriderLeanAccelModifier",
    "seat_count_override": "numSeatsOverride",
}

_HANDLING_TAGS = {
    "name": "handlingName",
    "mass": "fMass",
    "initial_drag_coefficient": "fInitialDragCoeff",
    "percent_submerged": "fPercentSubmerged",
    "center_of_mass_offset": "vecCentreOfMassOffset",
    "inertia_multiplier": "vecInertiaMultiplier",
    "drive_bias_front": "fDriveBiasFront",
    "initial_drive_gears": "nInitialDriveGears",
    "initial_drive_force": "fInitialDriveForce",
    "drive_inertia": "fDriveInertia",
    "clutch_change_rate_up": "fClutchChangeRateScaleUpShift",
    "clutch_change_rate_down": "fClutchChangeRateScaleDownShift",
    "initial_drive_max_flat_velocity": "fInitialDriveMaxFlatVel",
    "brake_force": "fBrakeForce",
    "brake_bias_front": "fBrakeBiasFront",
    "handbrake_force": "fHandBrakeForce",
    "steering_lock": "fSteeringLock",
    "traction_curve_max": "fTractionCurveMax",
    "traction_curve_min": "fTractionCurveMin",
    "traction_curve_lateral": "fTractionCurveLateral",
    "traction_spring_delta_max": "fTractionSpringDeltaMax",
    "low_speed_traction_loss_multiplier": "fLowSpeedTractionLossMult",
    "camber_stiffness": "fCamberStiffnesss",
    "traction_bias_front": "fTractionBiasFront",
    "traction_loss_multiplier": "fTractionLossMult",
    "suspension_force": "fSuspensionForce",
    "suspension_compression_damping": "fSuspensionCompDamp",
    "suspension_rebound_damping": "fSuspensionReboundDamp",
    "suspension_upper_limit": "fSuspensionUpperLimit",
    "suspension_lower_limit": "fSuspensionLowerLimit",
    "suspension_raise": "fSuspensionRaise",
    "suspension_bias_front": "fSuspensionBiasFront",
    "anti_roll_bar_force": "fAntiRollBarForce",
    "anti_roll_bar_bias_front": "fAntiRollBarBiasFront",
    "roll_center_height_front": "fRollCentreHeightFront",
    "roll_center_height_rear": "fRollCentreHeightRear",
    "collision_damage_multiplier": "fCollisionDamageMult",
    "weapon_damage_multiplier": "fWeaponDamageMult",
    "deformation_damage_multiplier": "fDeformationDamageMult",
    "engine_damage_multiplier": "fEngineDamageMult",
    "petrol_tank_volume": "fPetrolTankVolume",
    "oil_volume": "fOilVolume",
    "petrol_consumption_rate": "fPetrolConsumptionRate",
    "seat_offset_x": "fSeatOffsetDistX",
    "seat_offset_y": "fSeatOffsetDistY",
    "seat_offset_z": "fSeatOffsetDistZ",
    "monetary_value": "nMonetaryValue",
    "model_flags": "strModelFlags",
    "handling_flags": "strHandlingFlags",
    "damage_flags": "strDamageFlags",
    "ai_handling": "AIHandling",
    "sub_handling": "SubHandlingData",
    "weapon_damage_to_health_multiplier": "fWeaponDamageScaledToVehHealthMult",
    "downforce_modifier": "fDownforceModifier",
    "popup_light_rotation": "fPopUpLightRotation",
    "rocket_boost_capacity": "fRocketBoostCapacity",
    "boost_max_speed": "fBoostMaxSpeed",
}

_SPECIAL_TAGS = {
    "default_texture_index": "DefaultTexureIndex",
    "numeric_offset": "NumericOffset",
    "alphabetic_offset": "AlphabeticOffset",
    "space_offset": "SpaceOffset",
    "random_character_offset": "RandomCharOffset",
    "random_character_count": "NumRandomChar",
    "diffuse_map": "DiffuseMapName",
    "normal_map": "NormalMapName",
    "font_extents": "FontExtents",
    "max_letters": "MaxLettersOnPlate",
    "font_color": "FontColor",
    "outline_color": "FontOutlineColor",
    "outline_enabled": "IsFontOutlineEnabled",
    "outline_depth": "FontOutlineMinMaxDepth",
    "model_name": "modelName",
    "linked_models": "linkedModels",
    "mod_type": "type",
    "camera_position": "cameraPos",
    "label": "modShopLabel",
    "secondary_weapon_slot": "weaponSlotSecondary",
    "secondary_disable_driveby_seat": "disableDrivebySeatSecondary",
    "identifier": "identifier",
    "modifier": "modifier",
    "slot": "slot",
    "variation": "wheelVariation",
    "rim_radius": "rimRadius",
    "kit_type": "kitType",
    "visible_mods": "visibleMods",
    "linked_mods": "linkMods",
    "stat_mods": "statMods",
    "slot_names": "slotNames",
    "livery_names": "liveryNames",
    "secondary_livery_names": "livery2Names",
    "metallic_id": "metallicID",
    "audio_color": "audioColor",
    "audio_prefix": "audioPrefix",
    "audio_color_hash": "audioColorHash",
    "audio_prefix_hash": "audioPrefixHash",
    "xenon_light_color": "xenonLightColor",
    "xenon_corona_color": "xenonCoronaColor",
    "light_intensity_multiplier": "lightIntensityModifier",
    "corona_intensity_multiplier": "coronaIntensityModifier",
    "light_color": "lightColor",
    "corona_color": "coronaColor",
    "texture_name": "textureName",
    "sequencer_bpm": "sequencerBpm",
    "use_real_lights": "useRealLights",
    "light_group": "lightGroup",
    "scale_factor": "scaleFactor",
    "spotlight": "spotLight",
    "cast_shadows": "castShadows",
}

_VECTOR_NAMES = ("x", "y", "z", "w")
_MODEL_TAGS = {
    VehicleCorona: {
        "far_size": "size_far",
        "far_intensity": "intensity_far",
        "count": "numCoronas",
        "spacing": "distBetweenCoronas",
        "far_spacing": "distBetweenCoronas_far",
        "z_bias": "zBias",
        "pull_in": "pullCoronaIn",
    },
    VehicleLight: {
        "falloff_max": "falloffMax",
        "falloff_exponent": "falloffExponent",
        "inner_cone_angle": "innerConeAngle",
        "outer_cone_angle": "outerConeAngle",
        "emissive_boost": "emmissiveBoost",
        "mirror_texture": "mirrorTexture",
    },
    VehicleMetallicSetting: {
        "specular_intensity": "specInt",
        "specular_falloff": "specFalloff",
        "specular_fresnel": "specFresnel",
    },
    VehiclePlates: {"textures": "Textures"},
    VehicleVariationGlobalData: {
        "xenon_light_color": "xenonLightColor",
        "xenon_corona_color": "xenonCoronaColor",
        "light_intensity_multiplier": "xenonLightIntensityModifier",
        "corona_intensity_multiplier": "xenonCoronaIntensityModifier",
    },
    VehicleDoorStiffness: {
        "door": "doorId",
        "multiplier": "stiffnessMult",
    },
    VehicleMobilePhoneSeatOffset: {
        "offset": "Offset",
        "seat_index": "SeatIndex",
    },
    VehicleRagdollThreshold: {
        "min_component": "MinComponent",
        "max_component": "MaxComponent",
        "multiplier": "ThresholdMult",
    },
    VehicleVfxExtra: {
        "extras": "ptFxExtras",
        "name": "ptFxName",
        "offset": "ptFxOffset",
        "range": "ptFxRange",
        "speed_evolution_min": "ptFxSpeedEvoMin",
        "speed_evolution_max": "ptFxSpeedEvoMax",
    },
}
_COLOR_FIELDS = {
    VehicleCorona: {"color"},
    VehicleInitData: {"diffuse_tint"},
    VehicleLight: {"color"},
    VehicleModelColor: {"color"},
    VehiclePlateTexture: {"font_color", "outline_color"},
    VehicleSirenLight: {"color"},
    VehicleVariationGlobalData: {"xenon_light_color", "xenon_corona_color"},
    VehicleWindowColor: {"color"},
    VehicleXenonLightColor: {"light_color", "corona_color"},
}


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


def _field_tag(model: Any, name: str) -> str:
    if tag := _MODEL_TAGS.get(type(model), {}).get(name):
        return tag
    if isinstance(model, VehicleInitData):
        return _VEHICLE_TAGS.get(name, _camel(name))
    if isinstance(model, HandlingData):
        return _HANDLING_TAGS.get(name, _camel(name))
    if isinstance(model, VehicleModelColor) and name == "name":
        return "colorName"
    if isinstance(model, VehiclePlateTexture) and name == "name":
        return "TextureSetName"
    if isinstance(model, VehicleModKit) and name == "name":
        return "kitName"
    if isinstance(model, VehicleWheel) and name == "name":
        return "wheelName"
    return _SPECIAL_TAGS.get(name, _camel(name))


def _scalar_text(value: Any) -> str:
    if isinstance(value, HandlingFlagValue):
        return value.xml_token
    if isinstance(value, MetaHash):
        return str(value)
    if isinstance(value, VehicleMetaEnum):
        return value.token
    if isinstance(value, IntEnum):
        return str(int(value))
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        retail = f"{value:.6f}"
        return retail if float(retail) == value else format(value, ".9g")
    return str(value)


def _append_scalar(parent: ET.Element, tag: str, value: Any) -> ET.Element:
    element = ET.SubElement(parent, tag)
    if isinstance(value, VehicleMetaEnum):
        element.text = value.token
    elif isinstance(value, (bool, int, float, IntEnum)):
        element.set("value", _scalar_text(value))
    else:
        text = _scalar_text(value)
        if text:
            element.text = text
    return element


def _append_vector(parent: ET.Element, tag: str, value: Sequence[Any]) -> ET.Element:
    element = ET.SubElement(parent, tag)
    for name, component in zip(_VECTOR_NAMES, value, strict=False):
        element.set(name, _scalar_text(float(component)))
    return element


def _append_item(container: ET.Element, value: Any) -> None:
    item = ET.SubElement(container, "Item")
    if value is None:
        item.set("type", "NULL")
    elif isinstance(value, Mapping):
        if type_name := value.get("__type__", value.get("type", "")):
            item.set("type", str(type_name))
        _append_mapping(item, value)
    elif dataclasses.is_dataclass(value):
        if type_name := getattr(value, "TYPE_NAME", ""):
            item.set("type", type_name)
        _append_model_fields(item, value)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            _append_item(item, nested)
    elif isinstance(value, VehicleMetaEnum):
        item.text = value.token
    elif isinstance(value, VehicleExtraFlag):
        item.text = vehicle_extra_flag_text(value)
    elif isinstance(value, (bool, int, float, IntEnum)):
        item.set("value", _scalar_text(value))
    else:
        text = _scalar_text(value)
        if text:
            item.text = text


def _append_sequence(parent: ET.Element, tag: str, values: Sequence[Any]) -> ET.Element:
    container = ET.SubElement(parent, tag)
    for value in values:
        _append_item(container, value)
    return container


def _append_array(
    parent: ET.Element,
    tag: str,
    values: Sequence[Any],
    *,
    content: str,
) -> ET.Element:
    element = ET.SubElement(parent, tag, {"content": content})
    element.text = " ".join(_scalar_text(value) for value in values) or None
    return element


def _append_mapping(parent: ET.Element, values: Mapping[str, Any]) -> None:
    for source_name, value in values.items():
        if source_name in {"type", "__type__"}:
            continue
        tag = re.sub(r"^m_", "", str(source_name))
        _append_value(parent, tag, value)


def _append_value(parent: ET.Element, tag: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, Mapping):
        child = ET.SubElement(parent, tag)
        _append_mapping(child, value)
    elif dataclasses.is_dataclass(value):
        child = ET.SubElement(parent, tag)
        _append_model_fields(child, value)
    elif isinstance(value, tuple):
        _append_vector(parent, tag, value)
    elif isinstance(value, list):
        _append_sequence(parent, tag, value)
    else:
        _append_scalar(parent, tag, value)


def _append_color_indices(parent: ET.Element, value: VehicleColorIndices) -> None:
    _append_array(parent, "indices", value.indices, content="char_array")
    _append_sequence(parent, "liveries", value.liveries)


def _append_plate_probabilities(
    parent: ET.Element,
    values: Sequence[LicensePlateProbability],
) -> None:
    plate = ET.SubElement(parent, "plateProbabilities")
    probabilities = ET.SubElement(plate, "Probabilities")
    for value in values:
        _append_item(probabilities, value)


def _append_model_fields(parent: ET.Element, model: Any) -> None:
    if isinstance(model, VehicleColorIndices):
        _append_color_indices(parent, model)
        return
    if isinstance(model, HandlingSubData):
        _append_mapping(parent, model.values)
        return
    for model_field in dataclasses.fields(model):
        name = model_field.name
        if name == "raw":
            continue
        value = getattr(model, name)
        if isinstance(model, LicensePlateProbability):
            _append_value(parent, "Name" if name == "name" else "Value", value)
            continue
        if isinstance(model, VehicleCorona) and name == "rotation":
            for tag, component in zip(
                ("xRotation", "yRotation", "zRotation"), value, strict=True
            ):
                _append_scalar(parent, tag, component)
            continue
        if name in _COLOR_FIELDS.get(type(model), ()):
            element = ET.SubElement(parent, _field_tag(model, name))
            element.set("value", f"0x{int(value) & 0xFFFFFFFF:08X}")
            continue
        if isinstance(model, VehicleVariation) and name == "plate_probabilities":
            _append_plate_probabilities(parent, value)
            continue
        if isinstance(model, VehicleInitData) and name == "first_person_ik_offsets":
            for semantic_name, offsets in value.items():
                for offset in offsets:
                    _append_vector(parent, _IK_TAGS[semantic_name], offset)
            continue
        if isinstance(model, VehicleInitData) and name == "lod_distances":
            _append_array(parent, "lodDistances", value, content="float_array")
            continue
        if isinstance(model, VehicleInitData) and name == "flags":
            flags = ET.SubElement(parent, "flags")
            flags.text = vehicle_model_flag_text(value) or None
            continue
        if isinstance(model, HandlingData) and name in {
            "model_flags",
            "handling_flags",
            "damage_flags",
        }:
            if value is not None:
                element = ET.SubElement(parent, _field_tag(model, name))
                element.text = value.xml_token
            continue
        if (isinstance(model, VehicleInitData) and name == "required_extras") or (
            isinstance(model, VehicleVfxExtra) and name == "extras"
        ):
            flags = ET.SubElement(parent, _field_tag(model, name))
            flags.text = vehicle_extra_flag_text(value) or None
            continue
        _append_value(parent, _field_tag(model, name), value)


_IK_TAGS = {
    "driver_armed": "FirstPersonDriveByIKOffset",
    "driver_unarmed": "FirstPersonDriveByUnarmedIKOffset",
    "left_passenger_armed": "FirstPersonDriveByLeftPassengerIKOffset",
    "right_passenger_armed": "FirstPersonDriveByRightPassengerIKOffset",
    "right_rear_passenger_armed": "FirstPersonDriveByRightRearPassengerIKOffset",
    "left_passenger_unarmed": "FirstPersonDriveByLeftPassengerUnarmedIKOffset",
    "right_passenger_unarmed": "FirstPersonDriveByRightPassengerUnarmedIKOffset",
    "driver_projectile": "FirstPersonProjectileDriveByIKOffset",
    "passenger_projectile": "FirstPersonProjectileDriveByPassengerIKOffset",
    "rear_left_projectile": "FirstPersonProjectileDriveByRearLeftIKOffset",
    "rear_right_projectile": "FirstPersonProjectileDriveByRearRightIKOffset",
    "visor_switch": "FirstPersonVisorSwitchIKOffset",
    "driver_mobile_phone": "FirstPersonMobilePhoneOffset",
    "passenger_mobile_phone": "FirstPersonPassengerMobilePhoneOffset",
}


def _vehicles_xml(document: VehicleInitDataList) -> ET.Element:
    root = ET.Element(document.ROOT_TAG)
    _append_scalar(root, "residentTxd", document.resident_txd)
    _append_sequence(root, "residentAnims", document.resident_animations)
    _append_sequence(root, "InitDatas", document.vehicles)
    relationships = ET.SubElement(root, "txdRelationships")
    for relationship in document.txd_relationships:
        item = ET.SubElement(relationships, "Item")
        _append_scalar(item, "parent", relationship.parent)
        _append_scalar(item, "child", relationship.child)
    return root


def _handling_xml(document: HandlingDataManager) -> ET.Element:
    root = ET.Element(document.ROOT_TAG)
    _append_sequence(root, "HandlingData", document.entries)
    return root


def _variations_xml(document: VehicleModelInfoVariation) -> ET.Element:
    root = ET.Element(document.ROOT_TAG)
    _append_sequence(root, "variationData", document.vehicles)
    return root


def _carcols_xml(document: VehicleCarCols) -> ET.Element:
    root = ET.Element(document.ROOT_TAG)
    fields = (
        ("VehiclePlates", document.plates),
        ("Colors", document.colors),
        ("MetallicSettings", document.metallic_settings),
        ("WindowColors", document.window_colors),
        ("Lights", document.lights),
        ("Sirens", document.sirens),
        ("Kits", document.kits),
        ("Wheels", document.wheels),
        ("GlobalVariationData", document.global_variation_data),
        ("XenonLightColors", document.xenon_light_colors),
    )
    for tag, value in fields:
        _append_value(root, tag, value)
    return root


def vehicle_meta_xml_element(document: Any) -> ET.Element:
    if isinstance(document, VehicleInitDataList):
        return _vehicles_xml(document)
    if isinstance(document, HandlingDataManager):
        return _handling_xml(document)
    if isinstance(document, VehicleModelInfoVariation):
        return _variations_xml(document)
    if isinstance(document, VehicleCarCols):
        return _carcols_xml(document)
    raise TypeError(f"Unsupported vehicle metadata document: {type(document).__name__}")


__all__ = ["vehicle_meta_xml_element"]
