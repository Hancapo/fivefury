from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


_CUT_EVENT_ENUMS = [
    "CUTSCENE_LOAD_SCENE_EVENT",
    "CUTSCENE_UNLOAD_SCENE_EVENT",
    "CUTSCENE_LOAD_ANIM_DICT_EVENT",
    "CUTSCENE_UNLOAD_ANIM_DICT_EVENT",
    "CUTSCENE_LOAD_AUDIO_EVENT",
    "CUTSCENE_UNLOAD_AUDIO_EVENT",
    "CUTSCENE_LOAD_MODELS_EVENT",
    "CUTSCENE_UNLOAD_MODELS_EVENT",
    "CUTSCENE_LOAD_PARTICLE_EFFECTS_EVENT",
    "CUTSCENE_UNLOAD_PARTICLE_EFFECTS_EVENT",
    "CUTSCENE_LOAD_OVERLAYS_EVENT",
    "CUTSCENE_UNLOAD_OVERLAYS_EVENT",
    "CUTSCENE_LOAD_SUBTITLES_EVENT",
    "CUTSCENE_UNLOAD_SUBTITLES_EVENT",
    "CUTSCENE_HIDE_OBJECTS_EVENT",
    "CUTSCENE_SHOW_OBJECTS_EVENT",
    "CUTSCENE_FIXUP_OBJECTS_EVENT",
    "CUTSCENE_REVERT_FIXUP_OBJECTS_EVENT",
    "CUTSCENE_ADD_BLOCKING_BOUNDS_EVENT",
    "CUTSCENE_REMOVE_BLOCKING_BOUNDS_EVENT",
    "CUTSCENE_FADE_OUT_EVENT",
    "CUTSCENE_FADE_IN_EVENT",
    "CUTSCENE_SET_ANIM_EVENT",
    "CUTSCENE_CLEAR_ANIM_EVENT",
    "CUTSCENE_PLAY_PARTICLE_EFFECT_EVENT",
    "CUTSCENE_STOP_PARTICLE_EFFECT_EVENT",
    "CUTSCENE_SHOW_OVERLAY_EVENT",
    "CUTSCENE_HIDE_OVERLAY_EVENT",
    "CUTSCENE_PLAY_AUDIO_EVENT",
    "CUTSCENE_STOP_AUDIO_EVENT",
    "CUTSCENE_SHOW_SUBTITLE_EVENT",
    "CUTSCENE_HIDE_SUBTITLE_EVENT",
    "CUTSCENE_SET_DRAW_DISTANCE_EVENT",
    "CUTSCENE_SET_ATTACHMENT_EVENT",
    "CUTSCENE_SET_VARIATION_EVENT",
    "CUTSCENE_ACTIVATE_BLOCKING_BOUNDS_EVENT",
    "CUTSCENE_DEACTIVATE_BLOCKING_BOUNDS_EVENT",
    "CUTSCENE_HIDE_HIDDEN_OBJECT_EVENT",
    "CUTSCENE_SHOW_HIDDEN_OBJECT_EVENT",
    "CUTSCENE_FIX_FIXUP_OBJECT_EVENT",
    "CUTSCENE_REVERT_FIXUP_OBJECT_EVENT",
    "CUTSCENE_ADD_REMOVAL_BOUNDS_EVENT",
    "CUTSCENE_REMOVE_REMOVAL_BOUNDS_EVENT",
    "CUTSCENE_CAMERA_CUT_EVENT",
    "CUTSCENE_ACTIVATE_REMOVAL_BOUNDS_EVENT",
    "CUTSCENE_DEACTIVATE_REMOVAL_BOUNDS_EVENT",
    "CUTSCENE_LOAD_RAYFIRE_EVENT",
    "CUTSCENE_UNLOAD_RAYFIRE_EVENT",
    "CUTSCENE_ENABLE_DOF_EVENT",
    "CUTSCENE_DISABLE_DOF_EVENT",
    "CUTSCENE_CATCHUP_CAMERA_EVENT",
    "CUTSCENE_BLENDOUT_CAMERA_EVENT",
    "CUTSCENE_TRIGGER_DECAL_EVENT",
    "CUTSCENE_REMOVE_DECAL_EVENT",
    "CUTSCENE_ENABLE_CASCADE_SHADOW_BOUNDS_EVENT",
    "CUTSCENE_CASCADE_SHADOWS_ENABLE_ENTITY_TRACKER",
    "CUTSCENE_CASCADE_SHADOWS_SET_WORLD_HEIGHT_UPDATE",
    "CUTSCENE_CASCADE_SHADOWS_SET_RECEIVER_HEIGHT_UPDATE",
    "CUTSCENE_CASCADE_SHADOWS_SET_AIRCRAFT_MODE",
    "CUTSCENE_CASCADE_SHADOWS_SET_DYNAMIC_DEPTH_MODE",
    "CUTSCENE_CASCADE_SHADOWS_SET_FLY_CAMERA_MODE",
    "CUTSCENE_CASCADE_SHADOWS_SET_CASCADE_BOUNDS_HFOV",
    "CUTSCENE_CASCADE_SHADOWS_SET_CASCADE_BOUNDS_VFOV",
    "CUTSCENE_CASCADE_SHADOWS_SET_CASCADE_BOUNDS_SCALE",
    "CUTSCENE_CASCADE_SHADOWS_SET_ENTITY_TRACKER_SCALE",
    "CUTSCENE_CASCADE_SHADOWS_SET_SPLIT_Z_EXP_WEIGHT",
    "CUTSCENE_CASCADE_SHADOWS_SET_DITHER_RADIUS_SCALE",
    "CUTSCENE_CASCADE_SHADOWS_SET_WORLD_HEIGHT_MINMAX",
    "CUTSCENE_CASCADE_SHADOWS_SET_RECEIVER_HEIGHT_MINMAX",
    "CUTSCENE_CASCADE_SHADOWS_SET_DEPTH_BIAS",
    "CUTSCENE_CASCADE_SHADOWS_SET_SLOPE_BIAS",
    "CUTSCENE_CASCADE_SHADOWS_SET_SHADOW_SAMPLE_TYPE",
    "CUTSCENE_RESET_ADAPTION_EVENT",
    "CUTSCENE_CASCADE_SHADOWS_SET_DYNAMIC_DEPTH_VALUE",
    "CUTSCENE_SET_LIGHT_EVENT",
    "CUTSCENE_CLEAR_LIGHT_EVENT",
    "CUTSCENE_CASCADE_SHADOWS_RESET_CASCADE_SHADOWS",
    "CUTSCENE_START_REPLAY_RECORD",
    "CUTSCENE_STOP_REPLAY_RECORD",
    "CUTSCENE_FIRST_PERSON_BLENDOUT_CAMERA_EVENT",
    "CUTSCENE_FIRST_PERSON_CATCHUP_CAMERA_EVENT",
]


def _normalize_event_name(enum_name: str) -> str:
    name = enum_name
    if name.startswith("CUTSCENE_"):
        name = name[len("CUTSCENE_") :]
    if name.endswith("_EVENT"):
        name = name[: -len("_EVENT")]
    return name.lower()


CUT_EVENT_ID_TO_ENUM_NAME: dict[int, str] = {index: enum_name for index, enum_name in enumerate(_CUT_EVENT_ENUMS)}
CUT_EVENT_ENUM_NAME_TO_ID: dict[str, int] = {enum_name: index for index, enum_name in CUT_EVENT_ID_TO_ENUM_NAME.items()}
CUT_EVENT_ID_TO_NAME: dict[int, str] = {index: _normalize_event_name(enum_name) for index, enum_name in CUT_EVENT_ID_TO_ENUM_NAME.items()}
CUT_EVENT_NAME_TO_ID: dict[str, int] = {name: index for index, name in CUT_EVENT_ID_TO_NAME.items()}
CutEventType = IntEnum("CutEventType", {name.upper(): index for index, name in CUT_EVENT_ID_TO_NAME.items()})


class CutEventBehavior(str, Enum):
    INSTANT = "instant"
    DURATION = "duration"
    STATE = "state"


@dataclass(slots=True)
class CutEventSpec:
    name: str
    event_id: int
    enum_name: str
    event_type_name: str = "rage__cutfObjectIdEvent"
    args_type_name: str | None = None
    default_target_role: str | None = None
    default_args: dict[str, Any] = field(default_factory=dict)
    default_event_fields: dict[str, Any] = field(default_factory=dict)
    is_load_event: bool = False
    behavior: CutEventBehavior = CutEventBehavior.INSTANT


_SUPPORTED_EVENT_SPECS = {
    "load_scene": CutEventSpec(
        name="load_scene",
        event_id=CUT_EVENT_NAME_TO_ID["load_scene"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["load_scene"]],
        args_type_name="rage__cutfLoadSceneEventArgs",
        default_target_role="asset_manager",
        default_args={"fStartTime": 0.0},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "load_models": CutEventSpec(
        name="load_models",
        event_id=CUT_EVENT_NAME_TO_ID["load_models"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["load_models"]],
        args_type_name="rage__cutfObjectIdListEventArgs",
        default_target_role="asset_manager",
        default_args={"iObjectIdList": []},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "unload_models": CutEventSpec(
        name="unload_models",
        event_id=CUT_EVENT_NAME_TO_ID["unload_models"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["unload_models"]],
        args_type_name="rage__cutfObjectIdListEventArgs",
        default_target_role="asset_manager",
        default_args={"iObjectIdList": []},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "load_anim_dict": CutEventSpec(
        name="load_anim_dict",
        event_id=CUT_EVENT_NAME_TO_ID["load_anim_dict"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["load_anim_dict"]],
        args_type_name="rage__cutfNameEventArgs",
        default_target_role="animation_manager",
        default_args={"cName": ""},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "unload_anim_dict": CutEventSpec(
        name="unload_anim_dict",
        event_id=CUT_EVENT_NAME_TO_ID["unload_anim_dict"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["unload_anim_dict"]],
        args_type_name="rage__cutfNameEventArgs",
        default_target_role="animation_manager",
        default_args={"cName": ""},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "set_anim": CutEventSpec(
        name="set_anim",
        event_id=CUT_EVENT_NAME_TO_ID["set_anim"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["set_anim"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_target_role="animation_manager",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "clear_anim": CutEventSpec(
        name="clear_anim",
        event_id=CUT_EVENT_NAME_TO_ID["clear_anim"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["clear_anim"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_target_role="animation_manager",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "load_audio": CutEventSpec(
        name="load_audio",
        event_id=CUT_EVENT_NAME_TO_ID["load_audio"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["load_audio"]],
        args_type_name="rage__cutfNameEventArgs",
        default_target_role="audio",
        default_args={"cName": ""},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "load_particle_effects": CutEventSpec(
        name="load_particle_effects",
        event_id=CUT_EVENT_NAME_TO_ID["load_particle_effects"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["load_particle_effects"]],
        args_type_name="rage__cutfObjectIdListEventArgs",
        default_target_role="asset_manager",
        default_args={"iObjectIdList": []},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "unload_particle_effects": CutEventSpec(
        name="unload_particle_effects",
        event_id=CUT_EVENT_NAME_TO_ID["unload_particle_effects"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["unload_particle_effects"]],
        args_type_name="rage__cutfObjectIdListEventArgs",
        default_target_role="asset_manager",
        default_args={"iObjectIdList": []},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "load_overlays": CutEventSpec(
        name="load_overlays",
        event_id=CUT_EVENT_NAME_TO_ID["load_overlays"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["load_overlays"]],
        args_type_name="rage__cutfObjectIdListEventArgs",
        default_target_role="asset_manager",
        default_args={"iObjectIdList": []},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "unload_overlays": CutEventSpec(
        name="unload_overlays",
        event_id=CUT_EVENT_NAME_TO_ID["unload_overlays"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["unload_overlays"]],
        args_type_name="rage__cutfObjectIdListEventArgs",
        default_target_role="asset_manager",
        default_args={"iObjectIdList": []},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "load_subtitles": CutEventSpec(
        name="load_subtitles",
        event_id=CUT_EVENT_NAME_TO_ID["load_subtitles"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["load_subtitles"]],
        args_type_name="rage__cutfFinalNameEventArgs",
        default_target_role="asset_manager",
        default_args={"cName": ""},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "unload_subtitles": CutEventSpec(
        name="unload_subtitles",
        event_id=CUT_EVENT_NAME_TO_ID["unload_subtitles"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["unload_subtitles"]],
        args_type_name="rage__cutfFinalNameEventArgs",
        default_target_role="asset_manager",
        default_args={"cName": ""},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "unload_audio": CutEventSpec(
        name="unload_audio",
        event_id=CUT_EVENT_NAME_TO_ID["unload_audio"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["unload_audio"]],
        args_type_name="rage__cutfNameEventArgs",
        default_target_role="audio",
        default_args={"cName": ""},
        is_load_event=True,
        behavior=CutEventBehavior.STATE,
    ),
    "play_audio": CutEventSpec(
        name="play_audio",
        event_id=CUT_EVENT_NAME_TO_ID["play_audio"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["play_audio"]],
        args_type_name="rage__cutfNameEventArgs",
        default_target_role="audio",
        default_args={"cName": ""},
        behavior=CutEventBehavior.STATE,
    ),
    "stop_audio": CutEventSpec(
        name="stop_audio",
        event_id=CUT_EVENT_NAME_TO_ID["stop_audio"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["stop_audio"]],
        args_type_name="rage__cutfNameEventArgs",
        default_target_role="audio",
        default_args={"cName": ""},
        behavior=CutEventBehavior.STATE,
    ),
    "show_subtitle": CutEventSpec(
        name="show_subtitle",
        event_id=CUT_EVENT_NAME_TO_ID["show_subtitle"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["show_subtitle"]],
        args_type_name="rage__cutfSubtitleEventArgs",
        default_target_role="subtitle",
        default_args={"cName": "", "fSubtitleDuration": 0.0, "iLanguageID": 0},
        behavior=CutEventBehavior.DURATION,
    ),
    "hide_subtitle": CutEventSpec(
        name="hide_subtitle",
        event_id=CUT_EVENT_NAME_TO_ID["hide_subtitle"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["hide_subtitle"]],
        args_type_name="rage__cutfSubtitleEventArgs",
        default_target_role="subtitle",
        default_args={"cName": "", "fSubtitleDuration": 0.0, "iLanguageID": 0},
        behavior=CutEventBehavior.INSTANT,
    ),
    "camera_cut": CutEventSpec(
        name="camera_cut",
        event_id=CUT_EVENT_NAME_TO_ID["camera_cut"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["camera_cut"]],
        args_type_name="rage__cutfCameraCutEventArgs",
        default_target_role="camera",
        default_args={"cName": ""},
        behavior=CutEventBehavior.STATE,
    ),
    "fade_out": CutEventSpec(
        name="fade_out",
        event_id=CUT_EVENT_NAME_TO_ID["fade_out"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["fade_out"]],
        args_type_name="rage__cutfScreenFadeEventArgs",
        default_target_role="fade",
        default_args={"fValue": 1.0, "color": 0xFF000000},
        behavior=CutEventBehavior.STATE,
    ),
    "fade_in": CutEventSpec(
        name="fade_in",
        event_id=CUT_EVENT_NAME_TO_ID["fade_in"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["fade_in"]],
        args_type_name="rage__cutfScreenFadeEventArgs",
        default_target_role="fade",
        default_args={"fValue": 0.0, "color": 0xFF000000},
        behavior=CutEventBehavior.STATE,
    ),
    "hide_objects": CutEventSpec(
        name="hide_objects",
        event_id=CUT_EVENT_NAME_TO_ID["hide_objects"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["hide_objects"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "show_objects": CutEventSpec(
        name="show_objects",
        event_id=CUT_EVENT_NAME_TO_ID["show_objects"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["show_objects"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "add_blocking_bounds": CutEventSpec(
        name="add_blocking_bounds",
        event_id=CUT_EVENT_NAME_TO_ID["add_blocking_bounds"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["add_blocking_bounds"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "remove_blocking_bounds": CutEventSpec(
        name="remove_blocking_bounds",
        event_id=CUT_EVENT_NAME_TO_ID["remove_blocking_bounds"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["remove_blocking_bounds"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "set_draw_distance": CutEventSpec(
        name="set_draw_distance",
        event_id=CUT_EVENT_NAME_TO_ID["set_draw_distance"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["set_draw_distance"]],
        args_type_name="rage__cutfFloatValueEventArgs",
        default_target_role="camera",
        default_args={"fValue": 0.0},
        behavior=CutEventBehavior.STATE,
    ),
    "set_variation": CutEventSpec(
        name="set_variation",
        event_id=CUT_EVENT_NAME_TO_ID["set_variation"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["set_variation"]],
        args_type_name="rage__cutfObjectVariationEventArgs",
        default_args={"iObjectId": -1, "iComponent": 0, "iDrawable": 0, "iTexture": 0},
        behavior=CutEventBehavior.STATE,
    ),
    "hide_hidden_object": CutEventSpec(
        name="hide_hidden_object",
        event_id=CUT_EVENT_NAME_TO_ID["hide_hidden_object"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["hide_hidden_object"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "show_hidden_object": CutEventSpec(
        name="show_hidden_object",
        event_id=CUT_EVENT_NAME_TO_ID["show_hidden_object"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["show_hidden_object"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "show_overlay": CutEventSpec(
        name="show_overlay",
        event_id=CUT_EVENT_NAME_TO_ID["show_overlay"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["show_overlay"]],
        args_type_name="rage__cutfEventArgs",
        default_target_role="overlay",
        behavior=CutEventBehavior.STATE,
    ),
    "hide_overlay": CutEventSpec(
        name="hide_overlay",
        event_id=CUT_EVENT_NAME_TO_ID["hide_overlay"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["hide_overlay"]],
        default_target_role="overlay",
        behavior=CutEventBehavior.STATE,
    ),
    "play_particle_effect": CutEventSpec(
        name="play_particle_effect",
        event_id=CUT_EVENT_NAME_TO_ID["play_particle_effect"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["play_particle_effect"]],
        args_type_name="hash_0D47CF77",
        default_target_role="particle_fx",
        default_args={
            "vParticleInitialBoneRotation": (0.0, 0.0, 0.0, 1.0),
            "vParticleInitialBoneOffset": (0.0, 0.0, 0.0),
            "hash_33B52A22": -1,
            "hash_EAA4CB67": 0,
        },
        behavior=CutEventBehavior.STATE,
    ),
    "stop_particle_effect": CutEventSpec(
        name="stop_particle_effect",
        event_id=CUT_EVENT_NAME_TO_ID["stop_particle_effect"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["stop_particle_effect"]],
        default_target_role="particle_fx",
        behavior=CutEventBehavior.STATE,
    ),
    "set_light": CutEventSpec(
        name="set_light",
        event_id=CUT_EVENT_NAME_TO_ID["set_light"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["set_light"]],
        default_target_role="light",
        behavior=CutEventBehavior.STATE,
    ),
    "clear_light": CutEventSpec(
        name="clear_light",
        event_id=CUT_EVENT_NAME_TO_ID["clear_light"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["clear_light"]],
        default_target_role="light",
        behavior=CutEventBehavior.STATE,
    ),
    "enable_dof": CutEventSpec(
        name="enable_dof",
        event_id=CUT_EVENT_NAME_TO_ID["enable_dof"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["enable_dof"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_target_role="camera",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "disable_dof": CutEventSpec(
        name="disable_dof",
        event_id=CUT_EVENT_NAME_TO_ID["disable_dof"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["disable_dof"]],
        args_type_name="rage__cutfObjectIdEventArgs",
        default_target_role="camera",
        default_args={"iObjectId": -1},
        behavior=CutEventBehavior.STATE,
    ),
    "blendout_camera": CutEventSpec(
        name="blendout_camera",
        event_id=CUT_EVENT_NAME_TO_ID["blendout_camera"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["blendout_camera"]],
        args_type_name="rage__cutfEventArgs",
        default_target_role="camera",
        behavior=CutEventBehavior.STATE,
    ),
    "trigger_decal": CutEventSpec(
        name="trigger_decal",
        event_id=CUT_EVENT_NAME_TO_ID["trigger_decal"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["trigger_decal"]],
        args_type_name="rage__cutfDecalEventArgs",
        default_target_role="decal",
        default_args={
            "vPosition": (0.0, 0.0, 0.0),
            "vRotation": (0.0, 0.0, 0.0, 1.0),
            "fWidth": 1.0,
            "fHeight": 1.0,
            "Colour": 0xFFFFFFFF,
            "fLifeTime": 0.0,
        },
        behavior=CutEventBehavior.STATE,
    ),
    "remove_decal": CutEventSpec(
        name="remove_decal",
        event_id=CUT_EVENT_NAME_TO_ID["remove_decal"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["remove_decal"]],
        default_target_role="decal",
        behavior=CutEventBehavior.STATE,
    ),
    "enable_cascade_shadow_bounds": CutEventSpec(
        name="enable_cascade_shadow_bounds",
        event_id=CUT_EVENT_NAME_TO_ID["enable_cascade_shadow_bounds"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["enable_cascade_shadow_bounds"]],
        args_type_name="rage__cutfCascadeShadowEventArgs",
        default_target_role="camera",
        default_args={
            "cameraCutHashTag": 0,
            "position": (0.0, 0.0, 0.0),
            "radius": 0.0,
            "interpTimeTag": 0.0,
            "cascadeIndexTag": 0,
            "enabled": True,
            "interpolateToDisabledTag": True,
        },
        behavior=CutEventBehavior.STATE,
    ),
    "cascade_shadows_set_dynamic_depth_value": CutEventSpec(
        name="cascade_shadows_set_dynamic_depth_value",
        event_id=CUT_EVENT_NAME_TO_ID["cascade_shadows_set_dynamic_depth_value"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["cascade_shadows_set_dynamic_depth_value"]],
        args_type_name="hash_5FF00EA5",
        default_target_role="camera",
        default_args={"hash_0BD8B46C": 0.0},
        behavior=CutEventBehavior.STATE,
    ),
    "cascade_shadows_reset_cascade_shadows": CutEventSpec(
        name="cascade_shadows_reset_cascade_shadows",
        event_id=CUT_EVENT_NAME_TO_ID["cascade_shadows_reset_cascade_shadows"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["cascade_shadows_reset_cascade_shadows"]],
        args_type_name="hash_94061376",
        default_target_role="camera",
        default_args={"hash_0C74B449": True},
        behavior=CutEventBehavior.STATE,
    ),
    "first_person_blendout_camera": CutEventSpec(
        name="first_person_blendout_camera",
        event_id=CUT_EVENT_NAME_TO_ID["first_person_blendout_camera"],
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[CUT_EVENT_NAME_TO_ID["first_person_blendout_camera"]],
        args_type_name="hash_5FF00EA5",
        default_target_role="camera",
        default_args={"hash_0BD8B46C": 1.0},
        behavior=CutEventBehavior.STATE,
    ),
}


def _event_spec(
    name: str,
    *,
    args_type_name: str | None = None,
    default_target_role: str | None = None,
    default_args: dict[str, Any] | None = None,
    is_load_event: bool = False,
    behavior: CutEventBehavior = CutEventBehavior.STATE,
) -> CutEventSpec:
    event_id = CUT_EVENT_NAME_TO_ID[name]
    return CutEventSpec(
        name=name,
        event_id=event_id,
        enum_name=CUT_EVENT_ID_TO_ENUM_NAME[event_id],
        args_type_name=args_type_name,
        default_target_role=default_target_role,
        default_args=dict(default_args or {}),
        is_load_event=is_load_event,
        behavior=behavior,
    )


_SUPPORTED_EVENT_SPECS.update(
    {
        "unload_scene": _event_spec(
            "unload_scene",
            args_type_name="rage__cutfLoadSceneEventArgs",
            default_target_role="asset_manager",
            default_args={"fStartTime": 0.0},
            is_load_event=True,
        ),
        "fixup_objects": _event_spec(
            "fixup_objects",
            args_type_name="rage__cutfObjectIdListEventArgs",
            default_target_role="asset_manager",
            default_args={"iObjectIdList": []},
        ),
        "revert_fixup_objects": _event_spec(
            "revert_fixup_objects",
            args_type_name="rage__cutfObjectIdListEventArgs",
            default_target_role="asset_manager",
            default_args={"iObjectIdList": []},
        ),
        "set_attachment": _event_spec(
            "set_attachment",
            args_type_name="rage__cutfObjectIdNameEventArgs",
            default_args={"iObjectId": -1, "cName": ""},
        ),
        "activate_blocking_bounds": _event_spec(
            "activate_blocking_bounds",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_args={"iObjectId": -1},
        ),
        "deactivate_blocking_bounds": _event_spec(
            "deactivate_blocking_bounds",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_args={"iObjectId": -1},
        ),
        "fix_fixup_object": _event_spec(
            "fix_fixup_object",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_args={"iObjectId": -1},
        ),
        "revert_fixup_object": _event_spec(
            "revert_fixup_object",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_args={"iObjectId": -1},
        ),
        "add_removal_bounds": _event_spec(
            "add_removal_bounds",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_args={"iObjectId": -1},
        ),
        "remove_removal_bounds": _event_spec(
            "remove_removal_bounds",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_args={"iObjectId": -1},
        ),
        "activate_removal_bounds": _event_spec(
            "activate_removal_bounds",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_args={"iObjectId": -1},
        ),
        "deactivate_removal_bounds": _event_spec(
            "deactivate_removal_bounds",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_args={"iObjectId": -1},
        ),
        "load_rayfire": _event_spec(
            "load_rayfire",
            args_type_name="rage__cutfObjectIdNameEventArgs",
            default_target_role="asset_manager",
            default_args={"iObjectId": -1, "cName": ""},
        ),
        "unload_rayfire": _event_spec(
            "unload_rayfire",
            args_type_name="rage__cutfObjectIdNameEventArgs",
            default_target_role="asset_manager",
            default_args={"iObjectId": -1, "cName": ""},
        ),
        "catchup_camera": _event_spec(
            "catchup_camera",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_target_role="camera",
            default_args={"iObjectId": -1},
        ),
        "cascade_shadows_enable_entity_tracker": _event_spec(
            "cascade_shadows_enable_entity_tracker",
            args_type_name="hash_94061376",
            default_target_role="camera",
            default_args={"hash_0C74B449": True},
        ),
        "cascade_shadows_set_world_height_update": _event_spec(
            "cascade_shadows_set_world_height_update",
            args_type_name="hash_94061376",
            default_target_role="camera",
            default_args={"hash_0C74B449": True},
        ),
        "cascade_shadows_set_receiver_height_update": _event_spec(
            "cascade_shadows_set_receiver_height_update",
            args_type_name="hash_94061376",
            default_target_role="camera",
            default_args={"hash_0C74B449": True},
        ),
        "cascade_shadows_set_aircraft_mode": _event_spec(
            "cascade_shadows_set_aircraft_mode",
            args_type_name="hash_94061376",
            default_target_role="camera",
            default_args={"hash_0C74B449": True},
        ),
        "cascade_shadows_set_dynamic_depth_mode": _event_spec(
            "cascade_shadows_set_dynamic_depth_mode",
            args_type_name="hash_94061376",
            default_target_role="camera",
            default_args={"hash_0C74B449": True},
        ),
        "cascade_shadows_set_fly_camera_mode": _event_spec(
            "cascade_shadows_set_fly_camera_mode",
            args_type_name="hash_94061376",
            default_target_role="camera",
            default_args={"hash_0C74B449": True},
        ),
        "cascade_shadows_set_cascade_bounds_hfov": _event_spec(
            "cascade_shadows_set_cascade_bounds_hfov",
            args_type_name="hash_5FF00EA5",
            default_target_role="camera",
            default_args={"hash_0BD8B46C": 0.0},
        ),
        "cascade_shadows_set_cascade_bounds_vfov": _event_spec(
            "cascade_shadows_set_cascade_bounds_vfov",
            args_type_name="hash_5FF00EA5",
            default_target_role="camera",
            default_args={"hash_0BD8B46C": 0.0},
        ),
        "cascade_shadows_set_cascade_bounds_scale": _event_spec(
            "cascade_shadows_set_cascade_bounds_scale",
            args_type_name="hash_5FF00EA5",
            default_target_role="camera",
            default_args={"hash_0BD8B46C": 0.0},
        ),
        "cascade_shadows_set_entity_tracker_scale": _event_spec(
            "cascade_shadows_set_entity_tracker_scale",
            args_type_name="hash_5FF00EA5",
            default_target_role="camera",
            default_args={"hash_0BD8B46C": 0.0},
        ),
        "cascade_shadows_set_split_z_exp_weight": _event_spec(
            "cascade_shadows_set_split_z_exp_weight",
            args_type_name="hash_5FF00EA5",
            default_target_role="camera",
            default_args={"hash_0BD8B46C": 0.0},
        ),
        "cascade_shadows_set_dither_radius_scale": _event_spec(
            "cascade_shadows_set_dither_radius_scale",
            args_type_name="hash_5FF00EA5",
            default_target_role="camera",
            default_args={"hash_0BD8B46C": 0.0},
        ),
        "cascade_shadows_set_world_height_minmax": _event_spec(
            "cascade_shadows_set_world_height_minmax",
            default_target_role="camera",
        ),
        "cascade_shadows_set_receiver_height_minmax": _event_spec(
            "cascade_shadows_set_receiver_height_minmax",
            default_target_role="camera",
        ),
        "cascade_shadows_set_depth_bias": _event_spec(
            "cascade_shadows_set_depth_bias",
            args_type_name="hash_5FF00EA5",
            default_target_role="camera",
            default_args={"hash_0BD8B46C": 0.0},
        ),
        "cascade_shadows_set_slope_bias": _event_spec(
            "cascade_shadows_set_slope_bias",
            args_type_name="hash_5FF00EA5",
            default_target_role="camera",
            default_args={"hash_0BD8B46C": 0.0},
        ),
        "cascade_shadows_set_shadow_sample_type": _event_spec(
            "cascade_shadows_set_shadow_sample_type",
            args_type_name="hash_5FF00EA5",
            default_target_role="camera",
            default_args={"hash_0BD8B46C": 0.0},
        ),
        "reset_adaption": _event_spec("reset_adaption"),
        "start_replay_record": _event_spec("start_replay_record", args_type_name=None),
        "stop_replay_record": _event_spec("stop_replay_record", args_type_name=None),
        "first_person_catchup_camera": _event_spec(
            "first_person_catchup_camera",
            args_type_name="rage__cutfObjectIdEventArgs",
            default_target_role="camera",
            default_args={"iObjectId": -1},
        ),
    }
)


def get_cut_event_name(event_id: int | None) -> str | None:
    if event_id is None:
        return None
    return CUT_EVENT_ID_TO_NAME.get(event_id)


def get_cut_event_enum_name(event_id: int | None) -> str | None:
    if event_id is None:
        return None
    return CUT_EVENT_ID_TO_ENUM_NAME.get(event_id)


def get_cut_event_id(name_or_id: str | int | CutEventType) -> int:
    if isinstance(name_or_id, CutEventType):
        return int(name_or_id)
    if isinstance(name_or_id, int):
        return name_or_id
    normalized = name_or_id.strip().lower()
    if normalized in CUT_EVENT_NAME_TO_ID:
        return CUT_EVENT_NAME_TO_ID[normalized]
    upper_name = name_or_id.strip().upper()
    if upper_name in CUT_EVENT_ENUM_NAME_TO_ID:
        return CUT_EVENT_ENUM_NAME_TO_ID[upper_name]
    raise KeyError(f"unknown cut event {name_or_id!r}")


def get_cut_event_spec(name_or_id: str | int | CutEventType) -> CutEventSpec | None:
    event_id = get_cut_event_id(name_or_id)
    return _SUPPORTED_EVENT_SPECS.get(CUT_EVENT_ID_TO_NAME[event_id])
