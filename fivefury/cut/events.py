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
}


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
