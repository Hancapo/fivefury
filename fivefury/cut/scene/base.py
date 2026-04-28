from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...ycd.model import Ycd, YcdAnimation, YcdClip

from ...metahash import MetaHash
from ...hashing import jenk_finalize_hash, jenk_partial_hash
from ..events import CutEventType, get_cut_event_spec
from ..flags import CutSceneFlags
from ..model import CutFile
from ..payloads import CutEventPayload
from .bindings import (
    _BINDING_ADDERS,
    _BINDING_CLASS_BY_TYPE,
    _ROLE_PROPERTY_NAMES,
    _TypedCutBinding,
    CutBinding,
    CutProp,
    CutPropAnimationPreset,
    CutTypeFileStrategy,
)
from .shared import _ROLE_DEFAULT_OBJECT_TYPE, _is_scene_entity, _object_role
from .timeline import CutTimelineEvent, CutTrack


@dataclass(slots=True)
class CutScene:
    scene_name: str | None = None
    duration: float | None = None
    playback_rate: float = 1.0
    face_dir: str | None = None
    cutscene_flags: CutSceneFlags | int | list[int] | None = None
    offset: tuple[float, float, float] | None = None
    rotation: float | None = None
    trigger_offset: tuple[float, float, float] | None = None
    range_start: int | None = None
    range_end: int | None = None
    alt_range_end: int | None = None
    section_by_time_slice_duration: float | None = None
    camera_cut_list: list[float] | None = None
    section_split_list: list[float] | None = None
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
        from ...ycd.model import Ycd

        if not isinstance(ycd, Ycd):
            raise TypeError(f"expected Ycd, got {type(ycd).__name__}")
        self.clip_dicts.append(ycd)

    def add_clip_dict(self, ycd: object) -> None:
        self.attach_clip_dict(ycd)

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
        from .io import scene_to_cut

        self.build()
        return scene_to_cut(self)

    def to_bytes(self, *, template: CutFile | bytes | str | Path | None = None) -> bytes:
        return self.to_cut().to_bytes(template=template)

    def save(self, destination: str | Path, *, template: CutFile | bytes | str | Path | None = None) -> None:
        self.to_cut().save(str(destination), template=template)

    @classmethod
    def create(
        cls,
        *,
        scene_name: str | None = None,
        duration: float = 0.0,
        face_dir: str | None = None,
        cutscene_flags: CutSceneFlags | int | list[int] | None = None,
        offset: tuple[float, float, float] | None = None,
        rotation: float = 0.0,
        trigger_offset: tuple[float, float, float] | None = None,
        range_start: int | None = None,
        range_end: int | None = None,
        alt_range_end: int | None = None,
        section_by_time_slice_duration: float = 4.0,
        camera_cut_list: list[float] | None = None,
        section_split_list: list[float] | None = None,
    ) -> "CutScene":
        resolved_offset = offset or (0.0, 0.0, 0.0)
        return cls(
            scene_name=scene_name,
            duration=float(duration),
            face_dir=face_dir,
            cutscene_flags=cutscene_flags,
            offset=resolved_offset,
            rotation=float(rotation),
            trigger_offset=trigger_offset if trigger_offset is not None else (0.0, 0.0, 0.0),
            range_start=range_start,
            range_end=range_end,
            alt_range_end=alt_range_end,
            section_by_time_slice_duration=section_by_time_slice_duration,
            camera_cut_list=list(camera_cut_list) if camera_cut_list is not None else None,
            section_split_list=list(section_split_list) if section_split_list is not None else None,
            bindings=[],
            tracks=[],
            raw=None,
        )

    def next_object_id(self) -> int:
        if not self.bindings:
            return 0
        return max(binding.object_id for binding in self.bindings) + 1

    def build(self) -> "CutScene":
        next_id = 0
        normalized: list[CutBinding] = []
        for binding in sorted(self.bindings, key=lambda item: (item.object_id if item.object_id >= 0 else 10**9, item.display_name)):
            if binding.object_id < 0:
                binding.object_id = next_id
            next_id = max(next_id, binding.object_id + 1)
            normalized = [item for item in normalized if item.object_id != binding.object_id] + [binding]
        self.bindings = sorted(normalized, key=lambda item: item.object_id)
        self.tracks = sorted(self.tracks, key=lambda item: item.key)
        for track in self.tracks:
            track.events.sort(key=lambda item: (item.start, item.event_id or -1, item.display_name))
        return self

    def validate(self) -> list[str]:
        issues: list[str] = []
        ids = [binding.object_id for binding in self.bindings]
        if len(ids) != len(set(ids)):
            issues.append("CutScene has duplicate binding object ids")
        if self.duration is not None and self.duration < 0:
            issues.append("CutScene duration is negative")
        issues.extend(self.validate_animations())
        return issues

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
                    if bound is None:
                        continue
                    candidate_hashes: list[int] = []
                    candidate_labels: list[str] = []
                    animation_clip_base = getattr(bound, "animation_clip_base", None)
                    if animation_clip_base:
                        expected_clip_name = f"{animation_clip_base}-{int(cut_index)}"
                        candidate_hashes.append(MetaHash(animation_clip_base).uint)
                        candidate_hashes.append(MetaHash(expected_clip_name).uint)
                        candidate_labels.append(expected_clip_name)
                    if not animation_clip_base and bound.name:
                        candidate_hashes.append(MetaHash(bound.name).uint)
                        candidate_labels.append(bound.name)
                    cutscene_name = getattr(bound, "cutscene_name", None)
                    if not animation_clip_base and cutscene_name:
                        candidate_hashes.append(MetaHash(cutscene_name).uint)
                        candidate_hashes.append(MetaHash(f"{cutscene_name}-{int(cut_index)}").uint)
                        candidate_labels.append(cutscene_name)
                    anim_streaming_base = getattr(bound, "animation_streaming_base", None)
                    if anim_streaming_base not in (None, "", 0):
                        candidate_hashes.append(jenk_finalize_hash(int(anim_streaming_base)))
                        candidate_labels.append(f"AnimStreamingBase=0x{int(anim_streaming_base):08X}")
                    if animation_clip_base and anim_streaming_base not in (None, "", 0):
                        expected_base = jenk_partial_hash(animation_clip_base)
                        if int(anim_streaming_base) != expected_base:
                            warnings.append(
                                f"set_anim target '{animation_clip_base}' (id={oid}) has AnimStreamingBase=0x{int(anim_streaming_base):08X}, "
                                f"expected 0x{expected_base:08X}"
                            )
                    if candidate_hashes and not any(key in clip_map for key in candidate_hashes):
                        label = " / ".join(dict.fromkeys(candidate_labels)) or f"id={oid}"
                        warnings.append(f"set_anim target '{label}' (id={oid}) has no matching clip in attached YCDs")
        return warnings

    def ensure_ydr_embedded_lights(
        self,
        source: Any,
        *,
        name_prefix: str | None = None,
        start: float = 0.0,
    ) -> list[CutBinding]:
        from ..lights import ensure_ydr_embedded_lights

        return ensure_ydr_embedded_lights(self, source, name_prefix=name_prefix, start=start)


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


def add_prop(
    self: CutScene,
    name: str | None = None,
    *,
    object_id: int | None = None,
    animation_preset: CutPropAnimationPreset | str | None = None,
    cutscene_name: str | None = None,
    scene_name: str | None = None,
    streaming_name: str | None = None,
    model_name: str | None = None,
    animation_clip_base: str | None = None,
    anim_streaming_base: int | None = None,
    animation_streaming_base: int | None = None,
    anim_export_ctrl_spec_file: str | None = None,
    animation_export_spec_file: str | None = None,
    face_export_ctrl_spec_file: str | None = None,
    face_animation_export_spec_file: str | None = None,
    anim_compression_file: str | None = None,
    animation_compression_filename: str | None = None,
    handle: str | None = None,
    object_handle: str | None = None,
    type_file: str | None = None,
    ytyp_name: str | None = None,
    model: Any | None = None,
    archetype: Any | None = None,
    ytyp: Any | None = None,
    type_source: Any | None = None,
    type_file_strategy: CutTypeFileStrategy | str | None = None,
    fields: dict[str, Any] | None = None,
) -> CutProp:
    prop = self.add_typed_binding(CutProp, name, object_id=object_id, fields=fields)
    assert isinstance(prop, CutProp)
    if animation_preset is not None:
        prop.apply_animation_preset(animation_preset)
    prop.configure_runtime_source(
        model=model,
        archetype=archetype,
        ytyp=ytyp,
        type_source=type_source,
        type_file_strategy=type_file_strategy,
    )
    prop.configure_model_asset(
        cutscene_name=cutscene_name if cutscene_name is not None else scene_name,
        streaming_name=streaming_name if streaming_name is not None else model_name,
        animation_clip_base=animation_clip_base,
        anim_streaming_base=anim_streaming_base if anim_streaming_base is not None else animation_streaming_base,
        anim_export_ctrl_spec_file=anim_export_ctrl_spec_file if anim_export_ctrl_spec_file is not None else animation_export_spec_file,
        face_export_ctrl_spec_file=face_export_ctrl_spec_file if face_export_ctrl_spec_file is not None else face_animation_export_spec_file,
        anim_compression_file=anim_compression_file if anim_compression_file is not None else animation_compression_filename,
        handle=handle if handle is not None else object_handle,
        type_file=type_file if type_file is not None else ytyp_name,
    )
    if animation_clip_base is None and animation_preset is not None and (anim_streaming_base is None and animation_streaming_base is None):
        inferred_clip_base = prop.model_name
        if inferred_clip_base:
            prop.animation_clip_base = inferred_clip_base
    return prop


setattr(CutScene, "add_prop", add_prop)


def add_prop_from_runtime_asset(
    self: CutScene,
    *,
    model: Any | None = None,
    archetype: Any | None = None,
    ytyp: Any | None = None,
    type_source: Any | None = None,
    type_file_strategy: CutTypeFileStrategy | str | None = None,
    name: str | None = None,
    object_id: int | None = None,
    animation_preset: CutPropAnimationPreset | str | None = None,
    cutscene_name: str | None = None,
    scene_name: str | None = None,
    animation_clip_base: str | None = None,
    anim_streaming_base: int | None = None,
    animation_streaming_base: int | None = None,
    anim_export_ctrl_spec_file: str | None = None,
    animation_export_spec_file: str | None = None,
    face_export_ctrl_spec_file: str | None = None,
    face_animation_export_spec_file: str | None = None,
    anim_compression_file: str | None = None,
    animation_compression_filename: str | None = None,
    handle: str | None = None,
    object_handle: str | None = None,
    fields: dict[str, Any] | None = None,
) -> CutProp:
    return add_prop(
        self,
        name=name,
        object_id=object_id,
        animation_preset=animation_preset,
        cutscene_name=cutscene_name if cutscene_name is not None else scene_name,
        model=model,
        archetype=archetype,
        ytyp=ytyp,
        type_source=type_source,
        type_file_strategy=type_file_strategy,
        animation_clip_base=animation_clip_base,
        anim_streaming_base=anim_streaming_base if anim_streaming_base is not None else animation_streaming_base,
        anim_export_ctrl_spec_file=anim_export_ctrl_spec_file if anim_export_ctrl_spec_file is not None else animation_export_spec_file,
        face_export_ctrl_spec_file=face_export_ctrl_spec_file if face_export_ctrl_spec_file is not None else face_animation_export_spec_file,
        anim_compression_file=anim_compression_file if anim_compression_file is not None else animation_compression_filename,
        handle=handle if handle is not None else object_handle,
        fields=fields,
    )


setattr(CutScene, "add_prop_from_runtime_asset", add_prop_from_runtime_asset)
