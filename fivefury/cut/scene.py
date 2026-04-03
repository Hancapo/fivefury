from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .model import CutFile, CutHashedString, CutNode, CutResolvedEvent
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


def _coerce_name(value: Any) -> str | None:
    if isinstance(value, CutHashedString):
        return value.text or f"0x{value.hash:08X}"
    if isinstance(value, str):
        return value or None
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

    def to_node(self) -> CutNode:
        node = _clone_value(self.raw) if self.raw is not None else CutNode(type_name=self.type_name)
        node.type_name = self.type_name
        node.fields["iObjectId"] = self.object_id
        for key, value in self.fields.items():
            node.fields[key] = _clone_value(value)
        if self.name is not None and "cName" in node.fields:
            current = node.fields["cName"]
            node.fields["cName"] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) else 0, text=self.name)
        return node


@dataclass(slots=True)
class CutTimelineEvent:
    start: float
    kind: str
    track: str
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
        return self.kind

    def to_resolved_event(self) -> CutResolvedEvent:
        if self.raw is None:
            raise ValueError("scene event cannot be compiled without a backing raw CUT event yet")
        event = _clone_value(self.raw.event)
        event.fields["fTime"] = float(self.start)
        if self.target_id is not None:
            event.fields["iObjectId"] = self.target_id
        for key, value in self.event_payload.items():
            event.fields[key] = _clone_value(value)
        args = _clone_value(self.raw.event_args) if self.raw.event_args is not None else None
        if args is not None:
            if self.label is not None:
                if "cName" in args.fields:
                    current = args.fields["cName"]
                    args.fields["cName"] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) else 0, text=self.label)
                elif "cameraCutHashName" in args.fields:
                    current = args.fields["cameraCutHashName"]
                    args.fields["cameraCutHashName"] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) else 0, text=self.label)
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
    raw: CutFile | None = None

    @property
    def cameras(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "camera"]

    @property
    def actors(self) -> list[CutBinding]:
        return self.peds

    @property
    def entities(self) -> list[CutBinding]:
        return [item for item in self.bindings if _is_scene_entity(item.role)]

    @property
    def peds(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "ped"]

    @property
    def props(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "prop"]

    @property
    def vehicles(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "vehicle"]

    @property
    def lights(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "light"]

    @property
    def audio(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "audio"]

    @property
    def subtitles(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "subtitle"]

    @property
    def fades(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "fade"]

    @property
    def overlays(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "overlay"]

    @property
    def particle_effects(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "particle_fx"]

    @property
    def blocking_bounds(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "blocking_bounds"]

    @property
    def animation_managers(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "animation_manager"]

    @property
    def asset_managers(self) -> list[CutBinding]:
        return [item for item in self.bindings if item.role == "asset_manager"]

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
    def bindings_by_id(self) -> dict[int, CutBinding]:
        return {item.object_id: item for item in self.bindings}

    def to_cut(self) -> CutFile:
        return scene_to_cut(self)

    def to_bytes(self, *, template: CutFile | bytes | str | Path | None = None) -> bytes:
        return self.to_cut().to_bytes(template=template)

    def save(self, destination: str | Path, *, template: CutFile | bytes | str | Path | None = None) -> None:
        self.to_cut().save(str(destination), template=template)


def _binding_from_node(node: CutNode) -> CutBinding:
    fields = {key: _clone_value(value) for key, value in node.fields.items() if key != "iObjectId"}
    return CutBinding(
        object_id=int(node.fields.get("iObjectId", -1)),
        type_name=node.type_name,
        role=_object_role(node.type_name),
        name=_coerce_name(node.fields.get("cName")) or _coerce_name(node.fields.get("StreamingName")),
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
