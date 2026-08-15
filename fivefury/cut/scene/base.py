from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...authoring.context import BuildContext
from ...authoring.diagnostics import ValidationReport

if TYPE_CHECKING:
    from ...ycd.cutscene import YcdCutsceneBuilder
    from ...ycd.model import Ycd, YcdAnimation, YcdClip
    from .authoring import CutsceneAssets

from ...hashing import jenk_partial_hash
from ...metahash import MetaHash
from ..events import CutEventType, get_cut_event_spec
from ..flags import CutSceneFlags
from ..model import CutFile
from ..payloads import CutEventPayload
from .bindings import (
    _BINDING_ADDERS,
    _BINDING_CLASS_BY_TYPE,
    _ROLE_PROPERTY_NAMES,
    CutBinding,
    CutCamera,
    CutFacialAnimationMode,
    CutPed,
    CutProp,
    CutPropAnimationPreset,
    CutTypeFileStrategy,
    _TypedCutBinding,
)
from .shared import (
    _ROLE_DEFAULT_OBJECT_TYPE,
    _is_scene_entity,
    _object_role,
    _technical_cut_index,
)
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

    def clip_dictionary(self, ycd: object) -> object:
        from ...ycd.model import Ycd

        if not isinstance(ycd, Ycd):
            raise TypeError(f"expected Ycd, got {type(ycd).__name__}")
        self.clip_dicts.append(ycd)
        return ycd

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

    def clip_for_streaming_base(
        self,
        anim_streaming_base: int,
        *,
        cut_index: int = 0,
        combined_facial: bool = False,
    ) -> YcdClip | None:
        """Resolve an exact technical clip from a serialized partial hash."""
        for ycd in self.clip_dicts:
            clip = ycd.get_cutscene_clip(
                anim_streaming_base,
                cut_index,
                combined_facial=combined_facial,
            )
            if clip is not None:
                return clip
        return None

    def clip_for_binding(
        self, binding: CutBinding | int, *, cut_index: int = 0
    ) -> YcdClip | None:
        """Resolve the sectioned animation clip assigned to a CUT binding.

        ``AnimStreamingBase`` is a Jenkins partial hash in serialized CUT data,
        not a final clip hash and not the model's ``StreamingName``.  Multiple
        actors may intentionally share a model while using distinct animation
        streaming bases, so an authoritative but unresolved base must not fall
        back to the model name.
        """
        resolved = self.get_binding(binding) if isinstance(binding, int) else binding
        if resolved is None:
            return None
        clips = self.available_clips(cut_index=cut_index)
        animation_clip_base = getattr(
            resolved,
            "runtime_animation_clip_base",
            getattr(resolved, "animation_clip_base", None),
        )
        if animation_clip_base:
            clip = self.get_clip(f"{animation_clip_base}-{int(cut_index)}")
            if clip is None:
                clip = clips.get(MetaHash(animation_clip_base).uint)
            if clip is not None:
                return clip
        animation_streaming_base = getattr(resolved, "animation_streaming_base", None)
        if animation_streaming_base in (None, "", 0):
            animation_streaming_base = resolved.fields.get("AnimStreamingBase")
        if animation_streaming_base not in (None, "", 0):
            try:
                combined_facial = (
                    isinstance(resolved, CutPed)
                    and resolved.has_face_animation
                    and resolved.face_and_body_are_merged
                )
                return self.clip_for_streaming_base(
                    int(animation_streaming_base),
                    cut_index=cut_index,
                    combined_facial=combined_facial,
                )
            except (TypeError, ValueError):
                return None
        for candidate in (
            getattr(resolved, "cutscene_name", None),
            resolved.fields.get("cName"),
            resolved.name,
        ):
            if candidate:
                candidate_hash = getattr(candidate, "hash", None)
                if candidate_hash is None and isinstance(candidate, str):
                    try:
                        candidate_hash = (
                            int(candidate, 16)
                            if candidate.lower().startswith("0x")
                            else None
                        )
                    except ValueError:
                        candidate_hash = None
                clip = clips.get(
                    int(candidate_hash) & 0xFFFFFFFF
                    if candidate_hash is not None
                    else MetaHash(candidate).uint
                )
                if clip is not None:
                    return clip
        return None

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
        return sorted(values, key=lambda item: (item.start, item.order or 0))

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
        self.validate(strict=True).raise_for_errors()
        return scene_to_cut(self)

    def to_bytes(
        self, *, template: CutFile | bytes | str | Path | None = None
    ) -> bytes:
        from .io import read_cut_scene

        data = self.to_cut().to_bytes(template=template)
        rebuilt = read_cut_scene(data)
        rebuilt.clip_dicts = list(self.clip_dicts)
        rebuilt.validate(strict=True).raise_for_errors()
        return data

    def save(
        self,
        destination: str | Path,
        *,
        template: CutFile | bytes | str | Path | None = None,
    ) -> None:
        from ...common import atomic_write_bytes

        if self.clip_dicts:
            from .authoring import CutsceneAssets

            target = Path(destination)
            CutsceneAssets(
                scene=self,
                ycds=tuple(self.clip_dicts),
                cut_name=target.name,
            ).save(target.parent, template=template)
            return
        atomic_write_bytes(destination, self.to_bytes(template=template))

    def animation_builder(
        self, *, name: str | None = None, **kwargs: Any
    ) -> YcdCutsceneBuilder:
        from ...ycd.cutscene import YcdCutsceneBuilder

        return YcdCutsceneBuilder.from_cut(self, name=name or self.scene_name, **kwargs)

    def build_assets(
        self,
        animations: YcdCutsceneBuilder | None = None,
        *,
        cut_name: str | None = None,
    ) -> CutsceneAssets:
        from .authoring import CutsceneAssets

        if animations is None:
            ycds = tuple(self.clip_dicts)
        else:
            from ...ycd.cutscene import YcdCutsceneBuilder

            if not isinstance(animations, YcdCutsceneBuilder):
                raise TypeError(
                    f"expected YcdCutsceneBuilder, got {type(animations).__name__}"
                )
            ycds = tuple(animations.build_ycds())
        return CutsceneAssets(scene=self, ycds=ycds, cut_name=cut_name)

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
    ) -> CutScene:
        resolved_offset = offset or (0.0, 0.0, 0.0)
        return cls(
            scene_name=scene_name,
            duration=float(duration),
            face_dir=face_dir,
            cutscene_flags=cutscene_flags,
            offset=resolved_offset,
            rotation=float(rotation),
            trigger_offset=trigger_offset
            if trigger_offset is not None
            else (0.0, 0.0, 0.0),
            range_start=range_start,
            range_end=range_end,
            alt_range_end=alt_range_end,
            section_by_time_slice_duration=section_by_time_slice_duration,
            camera_cut_list=list(camera_cut_list)
            if camera_cut_list is not None
            else None,
            section_split_list=list(section_split_list)
            if section_split_list is not None
            else None,
            bindings=[],
            tracks=[],
            raw=None,
        )

    def next_object_id(self) -> int:
        if not self.bindings:
            return 0
        return max(binding.object_id for binding in self.bindings) + 1

    def build(self) -> CutScene:
        next_id = 0
        normalized: list[CutBinding] = []
        for binding in sorted(
            self.bindings,
            key=lambda item: (
                item.object_id if item.object_id >= 0 else 10**9,
                item.display_name,
            ),
        ):
            if binding.object_id < 0:
                binding.object_id = next_id
            next_id = max(next_id, binding.object_id + 1)
            normalized = [
                item for item in normalized if item.object_id != binding.object_id
            ] + [binding]
        self.bindings = sorted(normalized, key=lambda item: item.object_id)
        self.tracks = sorted(self.tracks, key=lambda item: item.key)
        for track in self.tracks:
            track.events.sort(
                key=lambda item: (item.start, item.event_id or -1, item.display_name)
            )
        return self

    def validate(
        self,
        *,
        context: BuildContext | None = None,
        strict: bool = False,
    ) -> ValidationReport:
        from .validation import validate_cut_scene

        return validate_cut_scene(self, strict=strict, context=context)

    def binding(self, binding: CutBinding) -> CutBinding:
        if binding.object_id < 0:
            binding.object_id = self.next_object_id()
        self.bindings = [
            item for item in self.bindings if item.object_id != binding.object_id
        ] + [binding]
        self.bindings.sort(key=lambda item: item.object_id)
        return binding

    def _typed_binding(
        self,
        binding_cls: type[CutBinding],
        name: str | None = None,
        *,
        object_id: int | None = None,
        fields: dict[str, Any] | None = None,
    ) -> CutBinding:
        resolved_object_id = (
            self.next_object_id() if object_id is None else int(object_id)
        )
        if issubclass(binding_cls, _TypedCutBinding):
            return self.binding(
                binding_cls(name=name, object_id=resolved_object_id, fields=fields)
            )
        return self.binding(
            binding_cls(
                object_id=resolved_object_id,
                type_name="",
                role="",
                name=name,
                fields=fields,
            )
        )

    def object(
        self,
        role_or_type: str,
        *,
        name: str | None = None,
        object_id: int | None = None,
        type_name: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> CutBinding:
        resolved_type = type_name or _ROLE_DEFAULT_OBJECT_TYPE.get(
            role_or_type, role_or_type
        )
        object_id = self.next_object_id() if object_id is None else int(object_id)
        binding_class = _BINDING_CLASS_BY_TYPE.get(resolved_type)
        if binding_class is not None:
            return self.binding(
                binding_class(name=name, object_id=object_id, fields=fields)
            )
        binding = CutBinding.new(
            object_id=object_id,
            type_name=resolved_type,
            name=name,
            role=_object_role(resolved_type),
            fields=fields,
        )
        return self.binding(binding)

    def track(
        self, key: str, *, name: str | None = None, kind: str | None = None
    ) -> CutTrack:
        existing = self.get_track(key)
        if existing is not None:
            return existing
        track = CutTrack(
            key=key, name=name or key.replace("_", " ").title(), kind=kind or key
        )
        self.tracks.append(track)
        self.tracks.sort(key=lambda item: item.key)
        return track

    def timeline_event(self, timeline_event: CutTimelineEvent) -> CutTimelineEvent:
        if timeline_event.order is None:
            timeline_event.order = (
                max(
                    (
                        int(event.order)
                        for track in self.tracks
                        for event in track.events
                        if event.order is not None
                    ),
                    default=-1,
                )
                + 1
            )
        track = self.get_track(timeline_event.track)
        if track is None:
            track = self.track(timeline_event.track, kind=timeline_event.kind)
        if (
            timeline_event.kind
            and track.kind != timeline_event.kind
            and track.kind == track.key
        ):
            track.kind = timeline_event.kind
        track.events.append(timeline_event)
        track.events.sort(key=lambda item: item.start)
        return timeline_event

    def event(
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
        args_type: str | None = None,
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
        if (
            target_binding is None
            and spec is not None
            and spec.default_target_role is not None
        ):
            target_binding = next(
                (
                    item
                    for item in self.bindings
                    if item.role == spec.default_target_role
                ),
                None,
            )
            if target_binding is not None:
                target_id = target_binding.object_id
        timeline_event = CutTimelineEvent.new(
            event=event,
            start=start,
            target_id=target_id,
            target_name=target_binding.name if target_binding is not None else None,
            target_role=target_binding.role
            if target_binding is not None
            else (spec.default_target_role if spec is not None else None),
            track=track,
            label=label,
            duration=duration,
            payload=payload,
            event_payload=event_payload,
            is_load_event=is_load_event,
            args_type=args_type,
        )
        return self.timeline_event(timeline_event)

    def validate_animations(self, *, cut_index: int = 0) -> list[str]:
        if not self.clip_dicts:
            return []
        warnings: list[str] = []
        known_stems = {ycd.stem.lower() for ycd in self.clip_dicts if ycd.stem}
        for event in self.timeline:
            if event.event_name == "load_anim_dict" and event.label:
                name = event.label.lower()
                if not any(name in stem or stem in name for stem in known_stems):
                    warnings.append(
                        f"load_anim_dict references unknown dict '{event.label}'"
                    )
            if event.event_name == "set_anim" and event.payload:
                oid = event.payload.get("iObjectId")
                if oid is not None:
                    bound = self.get_binding(int(oid))
                    if bound is None:
                        continue
                    candidate_hashes: list[int] = []
                    candidate_labels: list[str] = []
                    animation_clip_base = getattr(
                        bound,
                        "runtime_animation_clip_base",
                        getattr(bound, "animation_clip_base", None),
                    )
                    active_cut_index = _technical_cut_index(
                        self.camera_cut_list,
                        float(event.start),
                        default=cut_index,
                    )
                    if animation_clip_base:
                        expected_clip_name = f"{animation_clip_base}-{active_cut_index}"
                        candidate_labels.append(expected_clip_name)
                    if not animation_clip_base and bound.name:
                        candidate_hashes.append(MetaHash(bound.name).uint)
                        candidate_labels.append(bound.name)
                    cutscene_name = getattr(bound, "cutscene_name", None)
                    if not animation_clip_base and cutscene_name:
                        candidate_hashes.append(MetaHash(cutscene_name).uint)
                        candidate_hashes.append(
                            MetaHash(f"{cutscene_name}-{active_cut_index}").uint
                        )
                        candidate_labels.append(cutscene_name)
                    anim_streaming_base = getattr(
                        bound, "animation_streaming_base", None
                    )
                    if anim_streaming_base not in (None, "", 0):
                        candidate_labels.append(
                            f"AnimStreamingBase=0x{int(anim_streaming_base):08X}"
                        )
                    if animation_clip_base and anim_streaming_base not in (None, "", 0):
                        expected_base = jenk_partial_hash(animation_clip_base)
                        if int(anim_streaming_base) != expected_base:
                            warnings.append(
                                f"set_anim target '{animation_clip_base}' (id={oid}) has AnimStreamingBase=0x{int(anim_streaming_base):08X}, "
                                f"expected 0x{expected_base:08X}"
                            )
                    exact_clip_missing = animation_clip_base and not any(
                        ycd.get_clip(expected_clip_name) is not None
                        for ycd in self.clip_dicts
                    )
                    clip_map = self.available_clips(cut_index=active_cut_index)
                    has_streaming_base = anim_streaming_base not in (None, "", 0)
                    fallback_clip_missing = (
                        not has_streaming_base
                        and bool(candidate_hashes)
                        and not any(key in clip_map for key in candidate_hashes)
                    )
                    streaming_clip_missing = (
                        not animation_clip_base
                        and has_streaming_base
                        and self.clip_for_binding(
                            bound,
                            cut_index=active_cut_index,
                        )
                        is None
                    )
                    if exact_clip_missing or (
                        not animation_clip_base
                        and (streaming_clip_missing or fallback_clip_missing)
                    ):
                        label = (
                            " / ".join(dict.fromkeys(candidate_labels)) or f"id={oid}"
                        )
                        warnings.append(
                            f"set_anim target '{label}' (id={oid}) has no matching clip in attached YCDs"
                        )
        return warnings

    def ensure_ydr_embedded_lights(
        self,
        source: Any,
        *,
        name_prefix: str | None = None,
        start: float = 0.0,
    ) -> list[CutBinding]:
        from ..lights import ensure_ydr_embedded_lights

        return ensure_ydr_embedded_lights(
            self, source, name_prefix=name_prefix, start=start
        )


def _make_role_property(role: str):
    return property(lambda self: self.bindings_for_role(role))


def _make_binding_adder(binding_cls: type[CutBinding]):
    def _adder(
        self: CutScene,
        name: str | None = None,
        *,
        object_id: int | None = None,
        fields: dict[str, Any] | None = None,
    ):
        return self._typed_binding(
            binding_cls, name, object_id=object_id, fields=fields
        )

    return _adder


for _role, _property_name in _ROLE_PROPERTY_NAMES.items():
    setattr(CutScene, _property_name, _make_role_property(_role))

for _role, _binding_cls in _BINDING_ADDERS.items():
    setattr(CutScene, _role, _make_binding_adder(_binding_cls))


def camera(
    self: CutScene,
    name: str = "exportcamera",
    *,
    object_id: int | None = None,
    animation_streaming_base: int | None = None,
    near_draw_distance: float = 0.1,
    far_draw_distance: float = 1000.0,
    fields: dict[str, Any] | None = None,
) -> CutCamera:
    camera = self._typed_binding(
        CutCamera,
        name,
        object_id=object_id,
        fields=fields,
    )
    assert isinstance(camera, CutCamera)
    camera.animation_streaming_base = animation_streaming_base
    camera.near_draw_distance = near_draw_distance
    camera.far_draw_distance = far_draw_distance
    return camera


CutScene.camera = camera


def ped(
    self: CutScene,
    name: str | None = None,
    *,
    object_id: int | None = None,
    cutscene_name: str | None = None,
    streaming_name: str | None = None,
    model_name: str | None = None,
    animation_clip_base: str | None = None,
    anim_streaming_base: int | None = None,
    facial_animation: CutFacialAnimationMode | str | None = None,
    override_face_animation_filename: str | None = None,
    face_animation_node_name: str | None = None,
    face_attributes_filename: str | None = None,
    type_file: str | None = None,
    ytyp_name: str | None = None,
    fields: dict[str, Any] | None = None,
) -> CutPed:
    ped = self._typed_binding(CutPed, name, object_id=object_id, fields=fields)
    assert isinstance(ped, CutPed)
    ped.configure_model_asset(
        cutscene_name=cutscene_name,
        streaming_name=streaming_name if streaming_name is not None else model_name,
        animation_clip_base=animation_clip_base,
        anim_streaming_base=anim_streaming_base,
        type_file=type_file if type_file is not None else ytyp_name,
    )
    if facial_animation is not None:
        ped.configure_facial_animation(
            facial_animation,
            override_filename=override_face_animation_filename,
            node_name=face_animation_node_name,
            attributes_filename=face_attributes_filename,
        )
        if (
            ped.facial_animation_mode is not CutFacialAnimationMode.NONE
            and not ped.animation_clip_base
        ):
            raise ValueError(
                "animation_clip_base is required for merged facial animation"
            )
    return ped


CutScene.ped = ped


def prop(
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
    prop = self._typed_binding(CutProp, name, object_id=object_id, fields=fields)
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
        anim_streaming_base=anim_streaming_base
        if anim_streaming_base is not None
        else animation_streaming_base,
        anim_export_ctrl_spec_file=anim_export_ctrl_spec_file
        if anim_export_ctrl_spec_file is not None
        else animation_export_spec_file,
        face_export_ctrl_spec_file=face_export_ctrl_spec_file
        if face_export_ctrl_spec_file is not None
        else face_animation_export_spec_file,
        anim_compression_file=anim_compression_file
        if anim_compression_file is not None
        else animation_compression_filename,
        handle=handle if handle is not None else object_handle,
        type_file=type_file if type_file is not None else ytyp_name,
    )
    if (
        animation_clip_base is None
        and animation_preset is not None
        and (anim_streaming_base is None and animation_streaming_base is None)
    ):
        inferred_clip_base = prop.model_name
        if inferred_clip_base:
            prop.animation_clip_base = inferred_clip_base
    return prop


CutScene.prop = prop
