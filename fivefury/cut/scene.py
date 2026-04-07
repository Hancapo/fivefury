from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from ..ycd.model import Ycd, YcdAnimation, YcdClip

from ..hashing import jenk_hash
from ..metahash import MetaHash
from .events import CutEventBehavior, CutEventSpec, CutEventType, get_cut_event_enum_name, get_cut_event_id, get_cut_event_name, get_cut_event_spec
from .model import CutFile, CutHashedString, CutNode, CutResolvedEvent
from .names import CUT_NAME_VALUES
from .payloads import (
    CutAnimationDictPayload,
    CutAnimationTargetPayload,
    CutCameraCutPayload,
    CutEventPayload,
    CutLoadScenePayload,
    CutNamePayload,
    CutObjectIdListPayload,
    CutSubtitlePayload,
)
from .pso import read_cut
from .xml import read_cutxml


_OBJECT_ROLE_MAP = {
    "rage__cutfCameraObject": "camera",
    "rage__cutfPedModelObject": "ped",
    "rage__cutfPropModelObject": "prop",
    "rage__cutfVehicleModelObject": "vehicle",
    "rage__cutfHiddenModelObject": "hidden_object",
    "rage__cutfOverlayObject": "overlay",
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
    "hidden_object": "rage__cutfHiddenModelObject",
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


def _hashed_string(text: str | None) -> CutHashedString:
    value = text or ""
    return CutHashedString(hash=jenk_hash(value) if value else 0, text=value or None)


def _node_type_hash(type_name: str, type_hash: int | None = None) -> int:
    return int(type_hash if type_hash is not None else CUT_NAME_VALUES.get(type_name, jenk_hash(type_name)))


def _object_name_field(type_name: str) -> str:
    if type_name == "rage__cutfAudioObject":
        return "cName"
    if type_name in {"rage__cutfPedModelObject", "rage__cutfPropModelObject", "rage__cutfVehicleModelObject"}:
        return "StreamingName"
    return "cName"


def _event_label_field(args_type_name: str) -> str | None:
    if args_type_name == "rage__cutfCameraCutEventArgs":
        return "cName"
    if args_type_name == "rage__cutfCascadeShadowEventArgs":
        return "cameraCutHashName"
    if args_type_name in {"rage__cutfSubtitleEventArgs", "rage__cutfNameEventArgs", "rage__cutfFinalNameEventArgs"}:
        return "cName"
    return None


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
    if "fTransitionInDuration" in args_node.fields or "fTransitionOutDuration" in args_node.fields:
        return max(
            float(args_node.fields.get("fTransitionInDuration", 0.0) or 0.0),
            float(args_node.fields.get("fTransitionOutDuration", 0.0) or 0.0),
        )
    return None


def _event_label(args_node: CutNode | None, object_name: str | None) -> str | None:
    if args_node is not None:
        for field_name in ("cName", "cameraCutHashName", "StreamingName"):
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


@dataclass(slots=True)
class CutBinding:
    object_id: int
    type_name: str
    role: str
    name: str | None
    fields: dict[str, Any] = field(default_factory=dict)
    raw: CutNode | None = None

    @property
    def display_name(self) -> str:
        return self.name or f"{self.role}:{self.object_id}"

    @classmethod
    def new(
        cls,
        *,
        object_id: int,
        type_name: str,
        name: str | None = None,
        role: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> "CutBinding":
        role_name = role or _object_role(type_name)
        field_values = dict(fields or {})
        name_field = _object_name_field(type_name)
        if name is not None and name_field not in field_values:
            if type_name == "rage__cutfAudioObject":
                field_values[name_field] = name
            else:
                field_values[name_field] = _hashed_string(name)
        raw = CutNode(type_name=type_name, type_hash=_node_type_hash(type_name), fields={})
        return cls(object_id=object_id, type_name=type_name, role=role_name, name=name, fields=field_values, raw=raw)

    def to_node(self) -> CutNode:
        node = _clone_value(self.raw) if self.raw is not None else CutNode(type_name=self.type_name)
        node.type_name = self.type_name
        node.type_hash = _node_type_hash(self.type_name, node.type_hash)
        node.fields["iObjectId"] = self.object_id
        for key, value in self.fields.items():
            node.fields[key] = _clone_value(value)
        if self.name is not None:
            field_name = _object_name_field(self.type_name)
            if field_name in node.fields:
                if self.type_name == "rage__cutfAudioObject":
                    node.fields[field_name] = self.name
                else:
                    current = node.fields[field_name]
                    node.fields[field_name] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) and current.hash else jenk_hash(self.name), text=self.name)
        return node


class _TypedCutBinding(CutBinding):
    TYPE_NAME = ""
    ROLE = ""

    def __init__(
        self,
        name: str | None = None,
        *,
        object_id: int = -1,
        fields: dict[str, Any] | None = None,
        raw: CutNode | None = None,
    ) -> None:
        type_name = self.TYPE_NAME
        role = self.ROLE or _object_role(type_name)
        field_values = dict(fields or {})
        if name is not None:
            name_field = _object_name_field(type_name)
            if name_field not in field_values:
                field_values[name_field] = name if type_name == "rage__cutfAudioObject" else _hashed_string(name)
        super().__init__(
            object_id=object_id,
            type_name=type_name,
            role=role,
            name=name,
            fields=field_values,
            raw=raw if raw is not None else CutNode(type_name=type_name, type_hash=_node_type_hash(type_name), fields={}),
        )


class CutAssetManager(_TypedCutBinding):
    TYPE_NAME = "rage__cutfAssetManagerObject"
    ROLE = "asset_manager"


class CutAnimationManager(_TypedCutBinding):
    TYPE_NAME = "rage__cutfAnimationManagerObject"
    ROLE = "animation_manager"


class CutCamera(_TypedCutBinding):
    TYPE_NAME = "rage__cutfCameraObject"
    ROLE = "camera"


class CutPed(_TypedCutBinding):
    TYPE_NAME = "rage__cutfPedModelObject"
    ROLE = "ped"


class CutProp(_TypedCutBinding):
    TYPE_NAME = "rage__cutfPropModelObject"
    ROLE = "prop"


class CutVehicle(_TypedCutBinding):
    TYPE_NAME = "rage__cutfVehicleModelObject"
    ROLE = "vehicle"


class CutLight(_TypedCutBinding):
    TYPE_NAME = "rage__cutfLightObject"
    ROLE = "light"


class CutAudio(_TypedCutBinding):
    TYPE_NAME = "rage__cutfAudioObject"
    ROLE = "audio"


class CutSubtitle(_TypedCutBinding):
    TYPE_NAME = "rage__cutfSubtitleObject"
    ROLE = "subtitle"


class CutFade(_TypedCutBinding):
    TYPE_NAME = "rage__cutfScreenFadeObject"
    ROLE = "fade"


class CutOverlay(_TypedCutBinding):
    TYPE_NAME = "rage__cutfOverlayObject"
    ROLE = "overlay"


class CutHiddenObject(_TypedCutBinding):
    TYPE_NAME = "rage__cutfHiddenModelObject"
    ROLE = "hidden_object"


class CutBlockingBounds(_TypedCutBinding):
    TYPE_NAME = "rage__cutfBlockingBoundsObject"
    ROLE = "blocking_bounds"


_BINDING_CLASS_BY_TYPE = {
    CutAssetManager.TYPE_NAME: CutAssetManager,
    CutAnimationManager.TYPE_NAME: CutAnimationManager,
    CutCamera.TYPE_NAME: CutCamera,
    CutPed.TYPE_NAME: CutPed,
    CutProp.TYPE_NAME: CutProp,
    CutVehicle.TYPE_NAME: CutVehicle,
    CutLight.TYPE_NAME: CutLight,
    CutAudio.TYPE_NAME: CutAudio,
    CutSubtitle.TYPE_NAME: CutSubtitle,
    CutFade.TYPE_NAME: CutFade,
    CutOverlay.TYPE_NAME: CutOverlay,
    CutHiddenObject.TYPE_NAME: CutHiddenObject,
    CutBlockingBounds.TYPE_NAME: CutBlockingBounds,
}

_ROLE_PROPERTY_NAMES = {
    "camera": "cameras",
    "ped": "peds",
    "prop": "props",
    "vehicle": "vehicles",
    "light": "lights",
    "audio": "audio",
    "subtitle": "subtitles",
    "fade": "fades",
    "overlay": "overlays",
    "particle_fx": "particle_effects",
    "blocking_bounds": "blocking_bounds",
    "animation_manager": "animation_managers",
    "asset_manager": "asset_managers",
}

_BINDING_ADDERS = {
    "asset_manager": CutAssetManager,
    "animation_manager": CutAnimationManager,
    "camera": CutCamera,
    "ped": CutPed,
    "prop": CutProp,
    "vehicle": CutVehicle,
    "light": CutLight,
    "audio": CutAudio,
    "subtitle": CutSubtitle,
    "fade": CutFade,
}


@dataclass(slots=True)
class CutTimelineEvent:
    start: float
    kind: str
    track: str
    behavior: CutEventBehavior = CutEventBehavior.INSTANT
    event_name: str | None = None
    event_enum_name: str | None = None
    label: str | None = None
    duration: float | None = None
    event_id: int | None = None
    target_id: int | None = None
    target_name: str | None = None
    target_role: str | None = None
    args_type: str | None = None
    source_args_index: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_payload: dict[str, Any] = field(default_factory=dict)
    is_load_event: bool = False
    raw: CutResolvedEvent | None = None

    @property
    def display_name(self) -> str:
        if self.label:
            return self.label
        if self.target_name:
            return self.target_name
        if self.event_name:
            return self.event_name
        return self.kind

    @property
    def end(self) -> float | None:
        if self.behavior is CutEventBehavior.DURATION and self.duration is not None:
            return self.start + self.duration
        return None

    @property
    def is_state_event(self) -> bool:
        return self.behavior is CutEventBehavior.STATE

    @property
    def is_duration_event(self) -> bool:
        return self.behavior is CutEventBehavior.DURATION

    @property
    def is_instant_event(self) -> bool:
        return self.behavior is CutEventBehavior.INSTANT

    @classmethod
    def new(
        cls,
        *,
        event: str | int | CutEventType,
        start: float,
        target_id: int | None = None,
        target_name: str | None = None,
        target_role: str | None = None,
        track: str | None = None,
        kind: str | None = None,
        label: str | None = None,
        duration: float | None = None,
        payload: CutEventPayload | dict[str, Any] | None = None,
        event_payload: dict[str, Any] | None = None,
        is_load_event: bool | None = None,
    ) -> "CutTimelineEvent":
        spec = get_cut_event_spec(event)
        event_id = get_cut_event_id(event)
        event_name = get_cut_event_name(event_id)
        event_enum_name = get_cut_event_enum_name(event_id)
        event_kind = kind or (event_name or "event")
        payload_fields, payload_label, payload_duration = _coerce_payload(payload)
        if label is None:
            label = payload_label
        if duration is None:
            duration = payload_duration
        if track is None:
            role_or_kind = target_role
            if event_kind == "camera_cut":
                track = "camera"
            elif event_kind == "show_subtitle":
                track = "subtitle"
            elif is_load_event or (spec is not None and spec.is_load_event):
                track = "load"
            elif role_or_kind:
                track = f"{role_or_kind}:{target_name or target_id if target_id is not None else role_or_kind}"
            else:
                track = event_kind
        return cls(
            start=float(start),
            kind=event_kind,
            track=track,
            behavior=spec.behavior if spec is not None else CutEventBehavior.INSTANT,
            event_name=event_name,
            event_enum_name=event_enum_name,
            label=label,
            duration=duration,
            event_id=event_id,
            target_id=target_id,
            target_name=target_name,
            target_role=target_role,
            args_type=spec.args_type_name if spec is not None else None,
            payload=payload_fields,
            event_payload=dict(event_payload or {}),
            is_load_event=bool(spec.is_load_event if is_load_event is None and spec is not None else is_load_event),
            raw=None,
        )

    def to_resolved_event(self) -> CutResolvedEvent:
        if self.raw is None:
            spec = get_cut_event_spec(self.event_id if self.event_id is not None else self.event_name or self.kind)
            event_id = self.event_id if self.event_id is not None else get_cut_event_id(self.event_name or self.kind)
            event = CutNode(
                type_name=(spec.event_type_name if spec is not None else "rage__cutfObjectIdEvent"),
                type_hash=_node_type_hash(spec.event_type_name if spec is not None else "rage__cutfObjectIdEvent"),
                fields={
                    "fTime": float(self.start),
                    "iEventId": event_id,
                    "iEventArgsIndex": -1,
                    "pChildEvents": None,
                    "StickyId": 0,
                    "IsChild": False,
                },
            )
            if self.target_id is not None:
                event.fields["iObjectId"] = self.target_id
            for key, value in (spec.default_event_fields.items() if spec is not None else ()):
                event.fields[key] = _clone_value(value)
            for key, value in self.event_payload.items():
                event.fields[key] = _clone_value(value)
            args = None
            if spec is not None and spec.args_type_name is not None:
                args_fields = {key: _clone_value(value) for key, value in spec.default_args.items()}
                label_field = _event_label_field(spec.args_type_name)
                if self.label is not None and label_field is not None and label_field not in self.payload:
                    args_fields[label_field] = _hashed_string(self.label) if label_field != "cName" or spec.args_type_name != "rage__cutfNameEventArgs" else self.label
                if self.duration is not None:
                    if "fSubtitleDuration" in args_fields:
                        args_fields["fSubtitleDuration"] = float(self.duration)
                    elif "interpTime" in args_fields:
                        args_fields["interpTime"] = float(self.duration)
                for key, value in self.payload.items():
                    if key == label_field and isinstance(value, str):
                        args_fields[key] = _hashed_string(value) if key != "cName" or spec.args_type_name != "rage__cutfNameEventArgs" else value
                    else:
                        args_fields[key] = _clone_value(value)
                args = CutNode(type_name=spec.args_type_name, type_hash=_node_type_hash(spec.args_type_name), fields=args_fields)
            return CutResolvedEvent(event=event, object=None, event_args=args, is_load_event=self.is_load_event)

        event = _clone_value(self.raw.event)
        event.fields["fTime"] = float(self.start)
        if self.target_id is not None:
            event.fields["iObjectId"] = self.target_id
        if self.event_id is not None:
            event.fields["iEventId"] = self.event_id
        for key, value in self.event_payload.items():
            event.fields[key] = _clone_value(value)
        args = _clone_value(self.raw.event_args) if self.raw.event_args is not None else None
        if args is not None:
            if self.label is not None:
                if "cName" in args.fields:
                    current = args.fields["cName"]
                    args.fields["cName"] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) and current.hash else jenk_hash(self.label), text=self.label)
                elif "cameraCutHashName" in args.fields:
                    current = args.fields["cameraCutHashName"]
                    args.fields["cameraCutHashName"] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) and current.hash else jenk_hash(self.label), text=self.label)
            if self.duration is not None:
                if "fSubtitleDuration" in args.fields:
                    args.fields["fSubtitleDuration"] = float(self.duration)
                elif "interpTime" in args.fields:
                    args.fields["interpTime"] = float(self.duration)
            for key, value in self.payload.items():
                args.fields[key] = _clone_value(value)
        return CutResolvedEvent(event=event, object=_clone_value(self.raw.object) if self.raw.object is not None else None, event_args=args, is_load_event=self.is_load_event)


@dataclass(slots=True)
class CutTrack:
    key: str
    name: str
    kind: str
    events: list[CutTimelineEvent] = field(default_factory=list)


@dataclass(slots=True)
class CutScene:
    duration: float | None = None
    playback_rate: float = 1.0
    face_dir: str | None = None
    offset: tuple[float, float, float] | None = None
    rotation: float | None = None
    trigger_offset: tuple[float, float, float] | None = None
    bindings: list[CutBinding] = field(default_factory=list)
    tracks: list[CutTrack] = field(default_factory=list)
    clip_dicts: list[Ycd] = field(default_factory=list)
    raw: CutFile | None = None

    @property
    def actors(self) -> list[CutBinding]:
        return self.peds

    @property
    def entities(self) -> list[CutBinding]:
        return [item for item in self.bindings if _is_scene_entity(item.role)]

    def bindings_for_role(self, role: str) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == role]

    def attach_clip_dict(self, ycd: object) -> None:
        from ..ycd.model import Ycd
        if not isinstance(ycd, Ycd):
            raise TypeError(f"expected Ycd, got {type(ycd).__name__}")
        self.clip_dicts.append(ycd)

    def get_clip(self, value: int | str) -> YcdClip | None:
        key = MetaHash(value).uint
        for ycd in self.clip_dicts:
            clip = ycd.clip_map.get(key)
            if clip is not None:
                return clip
        return None

    def get_animation(self, value: int | str) -> YcdAnimation | None:
        key = MetaHash(value).uint
        for ycd in self.clip_dicts:
            anim = ycd.animation_map.get(key)
            if anim is not None:
                return anim
        return None

    def available_clips(self, *, cut_index: int = 0) -> dict[int, YcdClip]:
        merged: dict[int, object] = {}
        for ycd in self.clip_dicts:
            merged.update(ycd.build_cutscene_map(cut_index))
        return merged

    @property
    def tracks_by_key(self) -> dict[str, CutTrack]:
        return {track.key: track for track in self.tracks}

    @property
    def camera_track(self) -> CutTrack | None:
        return self.tracks_by_key.get("camera")

    @property
    def subtitle_track(self) -> CutTrack | None:
        return self.tracks_by_key.get("subtitle")

    @property
    def load_track(self) -> CutTrack | None:
        return self.tracks_by_key.get("load")

    def get_track(self, key: str) -> CutTrack | None:
        return self.tracks_by_key.get(key)

    def get_binding(self, object_id: int) -> CutBinding | None:
        return self.bindings_by_id.get(object_id)

    @property
    def timeline(self) -> list[CutTimelineEvent]:
        values: list[CutTimelineEvent] = []
        for track in self.tracks:
            values.extend(track.events)
        return sorted(values, key=lambda item: (item.start, item.track, item.label or ""))

    @property
    def state_events(self) -> list[CutTimelineEvent]:
        return [event for event in self.timeline if event.is_state_event]

    @property
    def duration_events(self) -> list[CutTimelineEvent]:
        return [event for event in self.timeline if event.is_duration_event]

    @property
    def instant_events(self) -> list[CutTimelineEvent]:
        return [event for event in self.timeline if event.is_instant_event]

    @property
    def bindings_by_id(self) -> dict[int, CutBinding]:
        return {item.object_id: item for item in self.bindings}

    def to_cut(self) -> CutFile:
        return scene_to_cut(self)

    def to_bytes(self, *, template: CutFile | bytes | str | Path | None = None) -> bytes:
        return self.to_cut().to_bytes(template=template)

    def save(self, destination: str | Path, *, template: CutFile | bytes | str | Path | None = None) -> None:
        self.to_cut().save(str(destination), template=template)

    @classmethod
    def create(
        cls,
        *,
        duration: float = 0.0,
        face_dir: str | None = None,
        offset: tuple[float, float, float] | None = None,
        rotation: float = 0.0,
        trigger_offset: tuple[float, float, float] | None = None,
    ) -> "CutScene":
        return cls(
            duration=float(duration),
            face_dir=face_dir,
            offset=offset or (0.0, 0.0, 0.0),
            rotation=float(rotation),
            trigger_offset=trigger_offset or (0.0, 0.0, 0.0),
            bindings=[],
            tracks=[],
            raw=None,
        )

    def next_object_id(self) -> int:
        if not self.bindings:
            return 0
        return max(binding.object_id for binding in self.bindings) + 1

    def add(self, binding: CutBinding) -> CutBinding:
        if binding.object_id < 0:
            binding.object_id = self.next_object_id()
        self.bindings = [item for item in self.bindings if item.object_id != binding.object_id] + [binding]
        self.bindings.sort(key=lambda item: item.object_id)
        return binding

    def add_binding(self, binding: CutBinding) -> CutBinding:
        return self.add(binding)

    def add_typed_binding(
        self,
        binding_cls: type[CutBinding],
        name: str | None = None,
        *,
        object_id: int | None = None,
        fields: dict[str, Any] | None = None,
    ) -> CutBinding:
        resolved_object_id = self.next_object_id() if object_id is None else int(object_id)
        if issubclass(binding_cls, _TypedCutBinding):
            return self.add(binding_cls(name=name, object_id=resolved_object_id, fields=fields))
        return self.add(binding_cls(object_id=resolved_object_id, type_name="", role="", name=name, fields=fields))

    def add_object(
        self,
        role_or_type: str,
        *,
        name: str | None = None,
        object_id: int | None = None,
        type_name: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> CutBinding:
        resolved_type = type_name or _ROLE_DEFAULT_OBJECT_TYPE.get(role_or_type, role_or_type)
        object_id = self.next_object_id() if object_id is None else int(object_id)
        binding_class = _BINDING_CLASS_BY_TYPE.get(resolved_type)
        if binding_class is not None:
            return self.add(binding_class(name=name, object_id=object_id, fields=fields))
        binding = CutBinding.new(object_id=object_id, type_name=resolved_type, name=name, role=_object_role(resolved_type), fields=fields)
        return self.add(binding)

    def add_track(self, key: str, *, name: str | None = None, kind: str | None = None) -> CutTrack:
        existing = self.get_track(key)
        if existing is not None:
            return existing
        track = CutTrack(key=key, name=name or key.replace("_", " ").title(), kind=kind or key)
        self.tracks.append(track)
        self.tracks.sort(key=lambda item: item.key)
        return track

    def add_event(self, timeline_event: CutTimelineEvent) -> CutTimelineEvent:
        track = self.get_track(timeline_event.track)
        if track is None:
            track = self.add_track(timeline_event.track, kind=timeline_event.kind)
        if timeline_event.kind and track.kind != timeline_event.kind and track.kind == track.key:
            track.kind = timeline_event.kind
        track.events.append(timeline_event)
        track.events.sort(key=lambda item: (item.start, item.event_id or -1, item.display_name))
        return timeline_event

    def create_event(
        self,
        event: str | int | CutEventType,
        *,
        start: float,
        target: CutBinding | int | None = None,
        track: str | None = None,
        label: str | None = None,
        duration: float | None = None,
        payload: CutEventPayload | dict[str, Any] | None = None,
        event_payload: dict[str, Any] | None = None,
        is_load_event: bool | None = None,
    ) -> CutTimelineEvent:
        spec = get_cut_event_spec(event)
        target_binding: CutBinding | None = None
        target_id: int | None = None
        if isinstance(target, CutBinding):
            target_binding = target
            target_id = target.object_id
        elif isinstance(target, int):
            target_id = target
            target_binding = self.get_binding(target)
        if target_binding is None and spec is not None and spec.default_target_role is not None:
            target_binding = next((item for item in self.bindings if item.role == spec.default_target_role), None)
            if target_binding is not None:
                target_id = target_binding.object_id
        timeline_event = CutTimelineEvent.new(
            event=event,
            start=start,
            target_id=target_id,
            target_name=target_binding.name if target_binding is not None else None,
            target_role=target_binding.role if target_binding is not None else (spec.default_target_role if spec is not None else None),
            track=track,
            label=label,
            duration=duration,
            payload=payload,
            event_payload=event_payload,
            is_load_event=is_load_event,
        )
        return self.add_event(timeline_event)

    def load_scene(
        self,
        start: float,
        payload: CutLoadScenePayload,
        *,
        target: CutBinding | int | None = None,
    ) -> CutTimelineEvent:
        return self.create_event(CutEventType.LOAD_SCENE, start=start, target=target, payload=payload)

    def load_models(
        self,
        start: float,
        object_ids: list[int],
        *,
        target: CutBinding | int | None = None,
    ) -> CutTimelineEvent:
        return self.create_event(CutEventType.LOAD_MODELS, start=start, target=target, payload=CutObjectIdListPayload(object_ids))

    def unload_models(
        self,
        start: float,
        object_ids: list[int],
        *,
        target: CutBinding | int | None = None,
    ) -> CutTimelineEvent:
        return self.create_event(CutEventType.UNLOAD_MODELS, start=start, target=target, payload=CutObjectIdListPayload(object_ids))

    def load_anim_dict(
        self,
        start: float,
        name: str | CutAnimationDictPayload,
        *,
        target: CutBinding | int | None = None,
    ) -> CutTimelineEvent:
        payload = name if isinstance(name, CutAnimationDictPayload) else CutAnimationDictPayload(str(name))
        return self.create_event(CutEventType.LOAD_ANIM_DICT, start=start, target=target, track="animation_state", payload=payload)

    def unload_anim_dict(
        self,
        start: float,
        name: str | CutAnimationDictPayload,
        *,
        target: CutBinding | int | None = None,
    ) -> CutTimelineEvent:
        payload = name if isinstance(name, CutAnimationDictPayload) else CutAnimationDictPayload(str(name))
        return self.create_event(CutEventType.UNLOAD_ANIM_DICT, start=start, target=target, track="animation_state", payload=payload)

    def set_anim(
        self,
        start: float,
        animated: CutBinding | int,
        *,
        target: CutBinding | int | None = None,
    ) -> CutTimelineEvent:
        object_id = animated.object_id if isinstance(animated, CutBinding) else int(animated)
        return self.create_event(
            CutEventType.SET_ANIM,
            start=start,
            target=target,
            track="animation_binding",
            payload=CutAnimationTargetPayload(object_id),
        )

    def clear_anim(
        self,
        start: float,
        animated: CutBinding | int,
        *,
        target: CutBinding | int | None = None,
    ) -> CutTimelineEvent:
        object_id = animated.object_id if isinstance(animated, CutBinding) else int(animated)
        return self.create_event(
            CutEventType.CLEAR_ANIM,
            start=start,
            target=target,
            track="animation_binding",
            payload=CutAnimationTargetPayload(object_id),
        )

    def play_animation(
        self,
        start: float,
        animated: CutBinding | int,
        dict_name: str,
        *,
        end: float | None = None,
        target: CutBinding | int | None = None,
    ) -> list[CutTimelineEvent]:
        events: list[CutTimelineEvent] = []
        events.append(self.load_anim_dict(start, dict_name, target=target))
        events.append(self.set_anim(start, animated, target=target))
        if end is not None:
            events.append(self.clear_anim(end, animated, target=target))
            events.append(self.unload_anim_dict(end, dict_name, target=target))
        return events

    def validate_animations(self, *, cut_index: int = 0) -> list[str]:
        if not self.clip_dicts:
            return []
        warnings: list[str] = []
        known_stems = {ycd.stem.lower() for ycd in self.clip_dicts if ycd.stem}
        clip_map = self.available_clips(cut_index=cut_index)
        for event in self.timeline:
            if event.event_name == "load_anim_dict" and event.label:
                name = event.label.lower()
                if not any(name in stem or stem in name for stem in known_stems):
                    warnings.append(f"load_anim_dict references unknown dict '{event.label}'")
            if event.event_name == "set_anim" and event.payload:
                oid = event.payload.get("iObjectId")
                if oid is not None:
                    bound = self.get_binding(int(oid))
                    if bound is not None and bound.name:
                        key = MetaHash(bound.name).uint
                        if key not in clip_map:
                            warnings.append(f"set_anim target '{bound.name}' (id={oid}) has no matching clip in attached YCDs")
        return warnings

    def camera_cut(
        self,
        start: float,
        camera: CutBinding | int | None,
        payload: CutCameraCutPayload,
    ) -> CutTimelineEvent:
        return self.create_event(CutEventType.CAMERA_CUT, start=start, target=camera, payload=payload)

    def show_subtitle(
        self,
        start: float,
        subtitle: CutBinding | int | None,
        payload: CutSubtitlePayload,
    ) -> CutTimelineEvent:
        return self.create_event(CutEventType.SHOW_SUBTITLE, start=start, target=subtitle, payload=payload)

    def hide_subtitle(
        self,
        start: float,
        subtitle: CutBinding | int | None,
        text: str = "",
    ) -> CutTimelineEvent:
        return self.create_event(CutEventType.HIDE_SUBTITLE, start=start, target=subtitle, payload=CutSubtitlePayload(text, duration=0.0))

    def play_audio(
        self,
        start: float,
        audio: CutBinding | int | None,
        name: str,
    ) -> CutTimelineEvent:
        return self.create_event(CutEventType.PLAY_AUDIO, start=start, target=audio, payload=CutNamePayload(name))

    def stop_audio(
        self,
        start: float,
        audio: CutBinding | int | None,
        name: str,
    ) -> CutTimelineEvent:
        return self.create_event(CutEventType.STOP_AUDIO, start=start, target=audio, payload=CutNamePayload(name))


def _make_role_property(role: str):
    return property(lambda self: self.bindings_for_role(role))


def _make_binding_adder(binding_cls: type[CutBinding]):
    def _adder(self: CutScene, name: str | None = None, *, object_id: int | None = None, fields: dict[str, Any] | None = None):
        return self.add_typed_binding(binding_cls, name, object_id=object_id, fields=fields)

    return _adder


for _role, _property_name in _ROLE_PROPERTY_NAMES.items():
    setattr(CutScene, _property_name, _make_role_property(_role))

for _role, _binding_cls in _BINDING_ADDERS.items():
    setattr(CutScene, f"add_{_role}", _make_binding_adder(_binding_cls))


def _binding_from_node(node: CutNode) -> CutBinding:
    fields = {key: _clone_value(value) for key, value in node.fields.items() if key != "iObjectId"}
    name = _coerce_name(node.fields.get("cName")) or _coerce_name(node.fields.get("StreamingName"))
    binding_class = _BINDING_CLASS_BY_TYPE.get(node.type_name)
    if binding_class is not None:
        return binding_class(
            name=name,
            object_id=int(node.fields.get("iObjectId", -1)),
            fields=fields,
            raw=_clone_value(node),
        )
    return CutBinding(
        object_id=int(node.fields.get("iObjectId", -1)),
        type_name=node.type_name,
        role=_object_role(node.type_name),
        name=name,
        fields=fields,
        raw=_clone_value(node),
    )


def _timeline_event_from_resolved(resolved: CutResolvedEvent, bindings_by_id: dict[int, CutBinding]) -> CutTimelineEvent:
    event = resolved.event
    object_id = event.fields.get("iObjectId")
    binding = bindings_by_id.get(object_id) if isinstance(object_id, int) else None
    object_name = binding.name if binding is not None else None
    object_role = binding.role if binding is not None else (_object_role(resolved.object.type_name) if resolved.object is not None else None)
    kind = _event_category(resolved)
    track_key, track_name = _track_identity(kind, object_role, object_name, object_id if isinstance(object_id, int) else None, is_load_event=resolved.is_load_event)
    args_payload = {}
    if resolved.event_args is not None:
        args_payload = {key: _clone_value(value) for key, value in resolved.event_args.fields.items() if key not in _ARGS_BASE_FIELDS}
    event_payload = {key: _clone_value(value) for key, value in event.fields.items() if key not in _EVENT_BASE_FIELDS}
    return CutTimelineEvent(
        start=float(event.fields.get("fTime", 0.0) or 0.0),
        kind=kind,
        track=track_key,
        event_name=get_cut_event_name(event.fields.get("iEventId") if isinstance(event.fields.get("iEventId"), int) else None),
        event_enum_name=get_cut_event_enum_name(event.fields.get("iEventId") if isinstance(event.fields.get("iEventId"), int) else None),
        label=_event_label(resolved.event_args, object_name),
        duration=_event_duration(resolved.event_args),
        event_id=event.fields.get("iEventId"),
        target_id=object_id if isinstance(object_id, int) else None,
        target_name=object_name,
        target_role=object_role,
        args_type=resolved.event_args.type_name if resolved.event_args is not None else None,
        source_args_index=event.fields.get("iEventArgsIndex") if isinstance(event.fields.get("iEventArgsIndex"), int) and event.fields.get("iEventArgsIndex") >= 0 else None,
        payload=args_payload,
        event_payload=event_payload,
        is_load_event=resolved.is_load_event,
        raw=CutResolvedEvent(
            event=_clone_value(resolved.event),
            object=_clone_value(resolved.object) if resolved.object is not None else None,
            event_args=_clone_value(resolved.event_args) if resolved.event_args is not None else None,
            is_load_event=resolved.is_load_event,
        ),
    )


def cut_to_scene(data: CutFile | CutNode) -> CutScene:
    cut = data if isinstance(data, CutFile) else CutFile(root=data)
    bindings = [_binding_from_node(node) for node in cut.objects]
    bindings_by_id = {item.object_id: item for item in bindings}
    tracks_by_key: dict[str, CutTrack] = {}
    for resolved in cut.iter_resolved_events():
        timeline_event = _timeline_event_from_resolved(resolved, bindings_by_id)
        track = tracks_by_key.get(timeline_event.track)
        if track is None:
            name = timeline_event.track.split(":", 1)[-1].replace("_", " ").title()
            track = CutTrack(key=timeline_event.track, name=name, kind=timeline_event.kind)
            tracks_by_key[timeline_event.track] = track
        track.events.append(timeline_event)
    tracks = list(tracks_by_key.values())
    for track in tracks:
        track.events.sort(key=lambda item: (item.start, item.event_id or -1))
    root = cut.root.fields
    return CutScene(
        duration=root.get("fTotalDuration"),
        playback_rate=1.0,
        face_dir=_coerce_name(root.get("cFaceDir")),
        offset=_clone_value(root.get("vOffset")),
        rotation=root.get("fRotation"),
        trigger_offset=_clone_value(root.get("vTriggerOffset")),
        bindings=bindings,
        tracks=sorted(tracks, key=lambda item: item.key),
        raw=cut,
    )


def _scene_input_to_cut(data: CutScene | CutFile | bytes | str | Path) -> CutFile:
    if isinstance(data, CutScene):
        return scene_to_cut(data)
    if isinstance(data, CutFile):
        return data
    path = Path(data) if isinstance(data, (str, Path)) else None
    if path is not None and path.suffix.lower() == ".cutxml":
        return read_cutxml(path)
    return read_cut(data)


def read_cut_scene(data: CutScene | CutFile | bytes | str | Path) -> CutScene:
    if isinstance(data, CutScene):
        return data
    return cut_to_scene(_scene_input_to_cut(data))


def read_cutxml_scene(data: CutFile | bytes | str | Path) -> CutScene:
    if isinstance(data, CutFile):
        return cut_to_scene(data)
    return cut_to_scene(read_cutxml(data))


def _default_root(cut: CutFile | None) -> CutNode:
    if cut is not None:
        return _clone_value(cut.root)
    return CutNode(
        type_name="rage__cutfCutsceneFile2",
        fields={
            "fTotalDuration": 0.0,
            "cFaceDir": "",
            "iCutsceneFlags": [],
            "vOffset": (0.0, 0.0, 0.0),
            "fRotation": 0.0,
            "vTriggerOffset": (0.0, 0.0, 0.0),
            "pCutsceneObjects": [],
            "pCutsceneLoadEventList": [],
            "pCutsceneEventList": [],
            "pCutsceneEventArgsList": [],
            "concatDataList": [],
            "discardFrameList": [],
        },
    )


def scene_to_cut(scene: CutScene) -> CutFile:
    base_cut = scene.raw
    root = _default_root(base_cut)
    root.fields["fTotalDuration"] = float(scene.duration or 0.0)
    root.fields["cFaceDir"] = scene.face_dir or ""
    root.fields["vOffset"] = _clone_value(scene.offset) if scene.offset is not None else (0.0, 0.0, 0.0)
    root.fields["fRotation"] = float(scene.rotation or 0.0)
    root.fields["vTriggerOffset"] = _clone_value(scene.trigger_offset) if scene.trigger_offset is not None else (0.0, 0.0, 0.0)
    root.fields["pCutsceneObjects"] = [binding.to_node() for binding in scene.bindings]

    load_events: list[CutNode] = []
    events: list[CutNode] = []
    event_args: list[CutNode | None] = []
    for timeline_event in scene.timeline:
        resolved = timeline_event.to_resolved_event()
        event = resolved.event
        if resolved.event_args is not None:
            assigned_index: int | None = None
            source_index = timeline_event.source_args_index
            if source_index is not None and source_index >= 0:
                while len(event_args) <= source_index:
                    event_args.append(None)
                existing_args = event_args[source_index]
                if existing_args is None:
                    event_args[source_index] = resolved.event_args
                    assigned_index = source_index
                else:
                    same_type = existing_args.type_name == resolved.event_args.type_name and existing_args.type_hash == resolved.event_args.type_hash
                    same_fields = _freeze_value(existing_args.fields) == _freeze_value(resolved.event_args.fields)
                    if same_type and same_fields:
                        assigned_index = source_index
            if assigned_index is None:
                assigned_index = len(event_args)
                event_args.append(resolved.event_args)
            event.fields["iEventArgsIndex"] = assigned_index
        elif "iEventArgsIndex" in event.fields:
            event.fields["iEventArgsIndex"] = -1
        if timeline_event.is_load_event:
            load_events.append(event)
        else:
            events.append(event)
    root.fields["pCutsceneLoadEventList"] = load_events
    root.fields["pCutsceneEventList"] = events
    if any(item is None for item in event_args):
        remap: dict[int, int] = {}
        compact_args: list[CutNode] = []
        for old_index, item in enumerate(event_args):
            if item is None:
                continue
            remap[old_index] = len(compact_args)
            compact_args.append(item)
        for event in load_events + events:
            current_index = event.fields.get("iEventArgsIndex")
            if isinstance(current_index, int) and current_index >= 0:
                event.fields["iEventArgsIndex"] = remap[current_index]
        root.fields["pCutsceneEventArgsList"] = compact_args
    else:
        root.fields["pCutsceneEventArgsList"] = [item for item in event_args if item is not None]
    result = CutFile(root=root, source="cutscene", metadata=dict(base_cut.metadata) if base_cut is not None else {})
    return result
