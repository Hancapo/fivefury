from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from ...common import hash_value
from ..model import CutHashedString, CutNode, CutResolvedEvent
from ..names import CUT_NAME_VALUES
from ..payloads import CutEventPayload

if TYPE_CHECKING:  # pragma: no cover
    from .bindings import CutBinding


_OBJECT_ROLE_MAP = {
    "rage__cutfCameraObject": "camera",
    "rage__cutfPedModelObject": "ped",
    "rage__cutfPropModelObject": "prop",
    "rage__cutfVehicleModelObject": "vehicle",
    "rage__cutfHiddenModelObject": "hidden_object",
    "rage__cutfFixupModelObject": "fixup_object",
    "rage__cutfOverlayObject": "overlay",
    "rage__cutfDecalObject": "decal",
    "rage__cutfBlockingBoundsObject": "blocking_bounds",
    "rage__cutfLightObject": "light",
    "rage__cutfAnimatedLightObject": "light",
    "rage__cutfParticleEffectObject": "particle_fx",
    "rage__cutfAudioObject": "audio",
    "rage__cutfSubtitleObject": "subtitle",
    "rage__cutfScreenFadeObject": "fade",
    "rage__cutfAnimationManagerObject": "animation_manager",
    "rage__cutfAssetManagerObject": "asset_manager",
}

_ARGS_CATEGORY_MAP = {
    "rage__cutfCameraCutEventArgs": "camera_cut",
    "rage__cutfSubtitleEventArgs": "subtitle",
    "rage__cutfLoadSceneEventArgs": "load_scene",
    "rage__cutfObjectIdListEventArgs": "object_group",
    "rage__cutfObjectIdEventArgs": "object_ref",
    "rage__cutfObjectVariationEventArgs": "object_variation",
    "rage__cutfObjectIdNameEventArgs": "object_named",
    "rage__cutfNameEventArgs": "named",
    "rage__cutfFinalNameEventArgs": "named",
    "rage__cutfCascadeShadowEventArgs": "camera_fx",
    "hash_5FF00EA5": "camera_fx",
    "hash_94061376": "camera_fx",
}

_EVENT_BASE_FIELDS = {"fTime", "iEventId", "iEventArgsIndex", "pChildEvents", "StickyId", "IsChild", "iObjectId"}
_ARGS_BASE_FIELDS = {"attributeList", "cutfAttributes"}

_ROLE_DEFAULT_OBJECT_TYPE = {
    "camera": "rage__cutfCameraObject",
    "ped": "rage__cutfPedModelObject",
    "prop": "rage__cutfPropModelObject",
    "vehicle": "rage__cutfVehicleModelObject",
    "light": "rage__cutfLightObject",
    "audio": "rage__cutfAudioObject",
    "subtitle": "rage__cutfSubtitleObject",
    "fade": "rage__cutfScreenFadeObject",
    "overlay": "rage__cutfOverlayObject",
    "decal": "rage__cutfDecalObject",
    "hidden_object": "rage__cutfHiddenModelObject",
    "fixup_object": "rage__cutfFixupModelObject",
    "blocking_bounds": "rage__cutfBlockingBoundsObject",
    "animation_manager": "rage__cutfAnimationManagerObject",
    "asset_manager": "rage__cutfAssetManagerObject",
}


def _coerce_name(value: Any) -> str | None:
    if isinstance(value, CutHashedString):
        return value.text or f"0x{value.hash:08X}"
    if isinstance(value, str):
        return value or None
    return None


def _parse_hex_hash(text: str | None) -> int | None:
    if not isinstance(text, str):
        return None
    value = text.strip()
    if len(value) <= 2 or not value.lower().startswith("0x"):
        return None
    try:
        return int(value, 16) & 0xFFFFFFFF
    except ValueError:
        return None


def _hashed_string(text: str | None) -> CutHashedString:
    parsed_hash = _parse_hex_hash(text)
    if parsed_hash is not None:
        return CutHashedString(hash=parsed_hash, text=None)
    value = text or ""
    return CutHashedString(hash=hash_value(value) if value else 0, text=value or None)


def _node_type_hash(type_name: str, type_hash: int | None = None) -> int:
    return int(type_hash if type_hash is not None else CUT_NAME_VALUES.get(type_name, hash_value(type_name)))


def _object_name_field(type_name: str) -> str:
    if type_name == "rage__cutfAudioObject":
        return "cName"
    if type_name in {
        "rage__cutfPedModelObject",
        "rage__cutfPropModelObject",
        "rage__cutfVehicleModelObject",
        "rage__cutfParticleEffectObject",
    }:
        return "StreamingName"
    return "cName"


def _event_label_field(args_type_name: str) -> str | None:
    if args_type_name == "rage__cutfCameraCutEventArgs":
        return "cName"
    if args_type_name == "rage__cutfCascadeShadowEventArgs":
        return "cameraCutHashTag"
    if args_type_name in {"rage__cutfSubtitleEventArgs", "rage__cutfNameEventArgs", "rage__cutfFinalNameEventArgs"}:
        return "cName"
    return None


def _uses_plain_cname(args_type_name: str | None) -> bool:
    return args_type_name == "rage__cutfFinalNameEventArgs"


def _coerce_event_label_value(args_type_name: str | None, field_name: str, value: str) -> str | CutHashedString:
    if field_name == "cName" and _uses_plain_cname(args_type_name):
        return value
    return _hashed_string(value)


def _clone_value(value: Any) -> Any:
    if isinstance(value, CutNode):
        return CutNode(type_name=value.type_name, type_hash=value.type_hash, fields={key: _clone_value(item) for key, item in value.fields.items()})
    if isinstance(value, CutHashedString):
        return CutHashedString(hash=value.hash, text=value.text)
    if isinstance(value, list):
        return [_clone_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clone_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _clone_value(item) for key, item in value.items()}
    return value


def _coerce_payload(value: CutEventPayload | dict[str, Any] | None) -> tuple[dict[str, Any], str | None, float | None]:
    if value is None:
        return {}, None, None
    if isinstance(value, CutEventPayload):
        return value.to_fields(), value.event_label, value.event_duration
    return dict(value), None, None


def _freeze_value(value: Any) -> Any:
    if isinstance(value, CutNode):
        return ("CutNode", value.type_name, value.type_hash, tuple(sorted((key, _freeze_value(item)) for key, item in value.fields.items())))
    if isinstance(value, CutHashedString):
        return ("CutHashedString", value.hash, value.text)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze_value(item)) for key, item in value.items()))
    return value


def _coerce_object_id(value: CutBinding | int) -> int:
    from .bindings import CutBinding

    return value.object_id if isinstance(value, CutBinding) else int(value)


def _coerce_object_ids(values: Iterable[CutBinding | int]) -> list[int]:
    return [_coerce_object_id(value) for value in values]


def _object_role(type_name: str) -> str:
    return _OBJECT_ROLE_MAP.get(type_name, "object")


def _is_scene_entity(role: str | None) -> bool:
    return role in {"ped", "prop", "vehicle", "hidden_object", "overlay", "particle_fx"}


def _event_category(resolved: CutResolvedEvent) -> str:
    object_role = _object_role(resolved.object.type_name) if resolved.object is not None else None
    if resolved.event_args is not None:
        if resolved.event_args.type_name in {"rage__cutfNameEventArgs", "rage__cutfFinalNameEventArgs"}:
            if object_role == "audio":
                return "audio_cue"
            if object_role == "animation_manager":
                return "animation_state"
            if object_role == "asset_manager":
                return "asset_state"
        if resolved.event_args.type_name == "rage__cutfObjectIdEventArgs":
            if object_role == "animation_manager":
                return "animation_binding"
            if object_role == "camera":
                return "camera_binding"
        if resolved.event_args.type_name == "rage__cutfObjectIdListEventArgs" and object_role == "asset_manager":
            return "asset_group"
        category = _ARGS_CATEGORY_MAP.get(resolved.event_args.type_name)
        if category is not None:
            return category
    if resolved.object is not None:
        if object_role == "light":
            return "light_state"
        if object_role != "object":
            return object_role
    return "event"


def _event_duration(args_node: CutNode | None) -> float | None:
    if args_node is None:
        return None
    if "fSubtitleDuration" in args_node.fields:
        return float(args_node.fields["fSubtitleDuration"])
    if "interpTime" in args_node.fields:
        return float(args_node.fields["interpTime"])
    if "interpTimeTag" in args_node.fields:
        return float(args_node.fields["interpTimeTag"])
    if "fTransitionInDuration" in args_node.fields or "fTransitionOutDuration" in args_node.fields:
        return max(
            float(args_node.fields.get("fTransitionInDuration", 0.0) or 0.0),
            float(args_node.fields.get("fTransitionOutDuration", 0.0) or 0.0),
        )
    return None


def _event_label(args_node: CutNode | None, object_name: str | None) -> str | None:
    if args_node is not None:
        for field_name in ("cName", "cameraCutHashName", "cameraCutHashTag", "StreamingName"):
            if field_name in args_node.fields:
                value = _coerce_name(args_node.fields[field_name])
                if value:
                    return value
    return object_name


def _track_identity(category: str, object_role: str | None, object_name: str | None, object_id: int | None, *, is_load_event: bool) -> tuple[str, str]:
    if is_load_event:
        return "load", "Load"
    if category == "camera_cut":
        return "camera", "Camera"
    if category == "subtitle":
        return "subtitle", "Subtitles"
    if category == "load_scene":
        return "scene", "Scene"
    if object_role in {"camera", "light", "audio", "fade", "overlay", "particle_fx", "subtitle"}:
        key = object_name or (f"{object_role}:{object_id}" if object_id is not None else object_role)
        return f"{object_role}:{key}", key
    if _is_scene_entity(object_role):
        key = object_name or (f"{object_role}:{object_id}" if object_id is not None else object_role)
        return f"{object_role}:{key}", key
    key = object_name or category
    return category, key
