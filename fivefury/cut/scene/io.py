from __future__ import annotations

from pathlib import Path

from ..model import CutFile, CutHashedString, CutNode
from ..flags import CutSceneFlags, DEFAULT_PLAYABLE_CUTSCENE_FLAGS, pack_cutscene_flags, unpack_cutscene_flags
from ..pso import read_cut
from ..xml import read_cutxml
from .base import CutScene
from .bindings import _binding_from_node
from .shared import _clone_value, _coerce_name, _freeze_value, _hashed_string
from .timeline import CutTrack, _timeline_event_from_resolved


_CUTSCENE_FPS = 30.0
_CONCAT_DATA_TYPE_HASH = 1737539928


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
        scene_name=None,
        duration=root.get("fTotalDuration"),
        playback_rate=1.0,
        face_dir=_coerce_name(root.get("cFaceDir")),
        cutscene_flags=unpack_cutscene_flags(root.get("iCutsceneFlags")),
        offset=_clone_value(root.get("vOffset")),
        rotation=root.get("fRotation"),
        trigger_offset=_clone_value(root.get("vTriggerOffset")),
        range_start=root.get("iRangeStart"),
        range_end=root.get("iRangeEnd"),
        alt_range_end=root.get("iAltRangeEnd"),
        section_by_time_slice_duration=root.get("fSectionByTimeSliceDuration"),
        camera_cut_list=list(root.get("cameraCutList") or []),
        section_split_list=list(root.get("sectionSplitList") or []),
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
            "iCutsceneFlags": pack_cutscene_flags(None),
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


def _infer_scene_name(scene: CutScene) -> str:
    if scene.scene_name:
        return str(scene.scene_name)
    for event in scene.timeline:
        if event.event_name == "load_scene":
            raw = event.payload.get("cName") if event.payload else None
            if isinstance(raw, CutHashedString) and raw.hash == 0 and not raw.text:
                continue
            name = _coerce_name(raw)
            if name:
                return name
            if event.label:
                return event.label
    return "cutscene"


def _infer_face_dir(scene: CutScene, scene_name: str) -> str:
    if scene.face_dir:
        return scene.face_dir
    return f"x:/gta5/assets_ng/cuts/{scene_name.upper()}/faces"


def _timeline_camera_cut_list(scene: CutScene) -> list[float]:
    values = scene.camera_cut_list
    if values is None:
        # Camera cut events describe runtime camera state. They do not imply
        # cutscene streaming sections by themselves; real one-section cuts can
        # have camera events while leaving cameraCutList empty.
        values = []
    duration = float(scene.duration or 0.0)
    result = sorted({round(float(value), 6) for value in values if 0.0 < float(value) < duration})
    return result


def _load_event_sort_key(event: CutNode) -> tuple[float, int, int]:
    event_id = int(event.fields.get("iEventId", -1))
    # Keep loads in the same dependency order used by retail cutscene tables:
    # scene first, animation dictionaries before the models that bind them.
    priority = {
        0: 0,   # load_scene
        2: 10,  # load_anim_dict
        6: 20,  # load_models
        8: 20,  # load_particle_effects
        10: 20, # load_overlays
        4: 30,  # load_audio
        12: 40, # load_subtitles
        7: 90,  # unload_models
        9: 90,  # unload_particle_effects
        11: 90, # unload_overlays
        3: 91,  # unload_anim_dict
        5: 92,  # unload_audio
        13: 93, # unload_subtitles
    }.get(event_id, 50)
    return (float(event.fields.get("fTime", 0.0) or 0.0), priority, event_id)


def _normalize_initial_set_anim_events(events: list[CutNode]) -> None:
    if not events:
        return
    first_camera_time = min(
        (
            float(event.fields.get("fTime", 0.0) or 0.0)
            for event in events
            if int(event.fields.get("iEventId", -1)) == 43
        ),
        default=None,
    )
    if first_camera_time is None or abs(first_camera_time) > (1.0 / _CUTSCENE_FPS):
        return
    first_frame = 1.0 / _CUTSCENE_FPS
    for event in events:
        if int(event.fields.get("iEventId", -1)) != 22:
            continue
        event_time = float(event.fields.get("fTime", 0.0) or 0.0)
        if 0.0 <= event_time <= first_frame:
            event.fields["fTime"] = first_frame


def _event_sort_key(event: CutNode) -> tuple[float, int, int]:
    event_id = int(event.fields.get("iEventId", -1))
    # Runtime cuts need an active camera before animation binding starts.
    # Starting every set_anim on the same tick as the first camera cut can
    # make streamed prop-heavy cuts fail to start in-game.
    priority = {
        43: 0,  # camera_cut
        22: 5,  # set_anim
        28: 5,  # play_audio
        34: 10, # set_variation
        18: 15, # add_blocking_bounds
        14: 16, # hide_objects
        48: 25, # enable_dof
        74: 30, # set_light
        30: 40, # show_subtitle
        23: 80, # clear_anim
        29: 85, # stop_audio
        75: 90, # clear_light
    }.get(event_id, 50)
    return (float(event.fields.get("fTime", 0.0) or 0.0), priority, event_id)


def _scene_offset(scene: CutScene) -> tuple[float, float, float]:
    return _clone_value(scene.offset) if scene.offset is not None else (0.0, 0.0, 0.0)


def _trigger_offset(scene: CutScene, scene_offset: tuple[float, float, float]) -> tuple[float, float, float]:
    return _clone_value(scene.trigger_offset) if scene.trigger_offset is not None else _clone_value(scene_offset)


def _normalize_load_scene_args(
    event: CutNode,
    args: CutNode | None,
    *,
    scene_offset: tuple[float, float, float],
    rotation: float,
) -> None:
    if int(event.fields.get("iEventId", -1)) != 0:
        return
    if args is None or args.type_name != "rage__cutfLoadSceneEventArgs":
        return
    # Retail cutfiles keep the load-scene name empty; the playable scene name
    # lives in concatDataList.cSceneName. Keeping both separate preserves
    # cutscene relocation semantics used by the game.
    args.fields["cName"] = _hashed_string(None)
    args.fields["vOffset"] = _clone_value(scene_offset)
    args.fields["fRotation"] = float(rotation)
    args.fields.setdefault("fPitch", 0.0)
    args.fields.setdefault("fRoll", 0.0)


def _has_streamed_prop_models(scene: CutScene) -> bool:
    return any(binding.type_name == "rage__cutfPropModelObject" for binding in scene.bindings)


def _hash_value(value: object) -> int:
    if isinstance(value, CutHashedString):
        return int(value.hash)
    if value in (None, "", 0):
        return 0
    try:
        return int(value)
    except Exception:
        return 0


def _is_animated_prop_node(node: CutNode) -> bool:
    if node.type_name != "rage__cutfPropModelObject":
        return False
    fields = node.fields
    return (
        _hash_value(fields.get("cAnimExportCtrlSpecFile")) != 0
        or _hash_value(fields.get("cAnimCompressionFile")) != 0
        or int(fields.get("AnimStreamingBase") or 0) != 0
    )


def _normalize_prop_model_node(node: CutNode) -> None:
    if not _is_animated_prop_node(node):
        return
    fields = node.fields
    handle_hash = _hash_value(fields.get("cHandle"))
    name_hash = _hash_value(fields.get("cName"))
    if handle_hash == 0:
        # Retail skinned props commonly leave cHandle empty. The runtime then
        # derives the scene handle from AnimStreamingBase; writing cHandle=cName
        # prevents that path and can make prop animation binding fail in game.
        fields["cHandle"] = _hashed_string(None)


def _resolved_cutscene_flags(scene: CutScene, camera_cut_list: list[float]) -> list[int]:
    if scene.cutscene_flags is not None:
        return pack_cutscene_flags(scene.cutscene_flags)
    if scene.raw is not None:
        existing = scene.raw.root.fields.get("iCutsceneFlags")
        if existing:
            return pack_cutscene_flags(existing)
    flags = CutSceneFlags(DEFAULT_PLAYABLE_CUTSCENE_FLAGS)
    if _has_streamed_prop_models(scene):
        flags &= ~CutSceneFlags.INTERNAL_CONCAT
        flags |= CutSceneFlags.EXTERNAL_CONCAT
    if camera_cut_list:
        flags |= CutSceneFlags.SECTION_BY_CAMERA_CUTS
    return pack_cutscene_flags(flags)


def _range_end(scene: CutScene) -> int:
    if scene.range_end is not None:
        return int(scene.range_end)
    return max(0, int(round(float(scene.duration or 0.0) * _CUTSCENE_FPS)))


def _concat_data(scene: CutScene, scene_name: str, range_start: int, range_end: int) -> list[CutNode]:
    scene_offset = _scene_offset(scene)
    if scene.raw is not None:
        existing = scene.raw.root.fields.get("concatDataList")
        if existing:
            result = _clone_value(existing)
            for index, item in enumerate(result):
                item.fields["vOffset"] = _clone_value(scene_offset)
                item.fields["fRotation"] = float(scene.rotation or 0.0)
                if index == 0:
                    item.fields["cSceneName"] = _hashed_string(scene_name)
                    item.fields["iRangeStart"] = int(range_start)
                    item.fields["iRangeEnd"] = int(range_end)
                    item.fields["bValidForPlayBack"] = True
            return result
    return [
        CutNode(
            type_name="hash_6790C158",
            type_hash=_CONCAT_DATA_TYPE_HASH,
            fields={
                "cSceneName": _hashed_string(scene_name),
                "vOffset": _clone_value(scene_offset),
                "fStartTime": 0.0,
                "fRotation": float(scene.rotation or 0.0),
                "fPitch": 0.0,
                "fRoll": 0.0,
                "iRangeStart": int(range_start),
                "iRangeEnd": int(range_end),
                "bValidForPlayBack": True,
            },
        )
    ]


def scene_to_cut(scene: CutScene) -> CutFile:
    base_cut = scene.raw
    root = _default_root(base_cut)
    scene_name = _infer_scene_name(scene)
    camera_cut_list = _timeline_camera_cut_list(scene)
    range_start = int(scene.range_start or 0)
    range_end = _range_end(scene)
    scene_offset = _scene_offset(scene)
    scene_rotation = float(scene.rotation or 0.0)
    root.fields["fTotalDuration"] = float(scene.duration or 0.0)
    root.fields["cFaceDir"] = _infer_face_dir(scene, scene_name)
    root.fields["iCutsceneFlags"] = _resolved_cutscene_flags(scene, camera_cut_list)
    root.fields["vOffset"] = _clone_value(scene_offset)
    root.fields["fRotation"] = scene_rotation
    root.fields["vTriggerOffset"] = _trigger_offset(scene, scene_offset)
    root.fields["iRangeStart"] = range_start
    root.fields["iRangeEnd"] = range_end
    root.fields["iAltRangeEnd"] = int(scene.alt_range_end or 0)
    root.fields["fSectionByTimeSliceDuration"] = float(scene.section_by_time_slice_duration or 4.0)
    root.fields["cameraCutList"] = camera_cut_list
    root.fields["sectionSplitList"] = list(scene.section_split_list or [])
    root.fields["concatDataList"] = _concat_data(scene, scene_name, range_start, range_end)
    object_nodes = [binding.to_node() for binding in scene.bindings]
    for node in object_nodes:
        _normalize_prop_model_node(node)
    root.fields["pCutsceneObjects"] = object_nodes

    load_events: list[CutNode] = []
    events: list[CutNode] = []
    event_args: list[CutNode | None] = []
    for timeline_event in scene.timeline:
        resolved = timeline_event.to_resolved_event()
        event = resolved.event
        _normalize_load_scene_args(
            event,
            resolved.event_args,
            scene_offset=scene_offset,
            rotation=scene_rotation,
        )
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
    _normalize_initial_set_anim_events(events)
    root.fields["pCutsceneLoadEventList"] = sorted(load_events, key=_load_event_sort_key)
    root.fields["pCutsceneEventList"] = sorted(events, key=_event_sort_key)
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
