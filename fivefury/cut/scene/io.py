from __future__ import annotations

from pathlib import Path

from ..model import CutFile, CutNode
from ..pso import read_cut
from ..xml import read_cutxml
from .base import CutScene
from .bindings import _binding_from_node
from .shared import _clone_value, _coerce_name, _freeze_value
from .timeline import CutTrack, _timeline_event_from_resolved


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
    return CutFile(root=root, source="cutscene", metadata=dict(base_cut.metadata) if base_cut is not None else {})
