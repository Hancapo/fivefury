from __future__ import annotations

import itertools
from copy import deepcopy
from math import isfinite
from typing import TYPE_CHECKING, Any, Literal

from ...authoring.diagnostics import DiagnosticSeverity, ValidationReport
from ...hashing import jenk_hash, jenk_partial_hash
from ...vector import is_finite_vector
from ...ycd.sequence_tracks import is_ycd_camera_track
from ..events import get_cut_event_name, get_cut_event_spec
from ..flags import (
    DEFAULT_PLAYABLE_CUTSCENE_FLAGS,
    CutSceneFlags,
    unpack_cutscene_flags,
)
from ..limits import (
    CUT_FPS,
    CUT_MAX_CONCATENATED_SCENES,
    CUT_MAX_PSO_ARRAY_ITEMS,
    CUT_MINIMUM_DURATION,
    CUT_MINIMUM_SECTION_DURATION,
)
from .bindings import (
    CutAnimatedLight,
    CutAnimatedParticleEffect,
    CutBinding,
    CutCamera,
    CutPed,
)
from .shared import (
    _coerce_name,
    _is_scene_entity,
    _parse_hex_hash,
    _runtime_animation_section_index,
)

if TYPE_CHECKING:  # pragma: no cover
    from ...authoring.context import BuildContext
    from .base import CutScene
    from .timeline import CutTimelineEvent


CutSceneValidationSeverity = Literal["error", "warning"]


def _issue(
    issues: ValidationReport,
    severity: CutSceneValidationSeverity,
    code: str,
    message: str,
    *,
    hint: str | None = None,
) -> None:
    issues.issue(
        code,
        f"{message} {hint}" if hint else message,
        severity=(
            DiagnosticSeverity.ERROR
            if severity == "error"
            else DiagnosticSeverity.WARNING
        ),
        path=code,
    )


def _name(value: Any) -> str | None:
    return _coerce_name(value)


def _binding_name(binding: CutBinding) -> str:
    return binding.name or f"{binding.role}:{binding.object_id}"


def _is_streamed_model(binding: CutBinding) -> bool:
    return binding.role in {"ped", "prop", "vehicle", "weapon"}


def _is_animation_capable(binding: CutBinding) -> bool:
    return binding.role in {"ped", "prop", "vehicle", "weapon", "camera"} or isinstance(
        binding, (CutAnimatedLight, CutAnimatedParticleEffect)
    )


def _event_id(event: CutTimelineEvent) -> int | None:
    if event.event_id is None:
        return None
    return int(event.event_id)


def _event_name(event: CutTimelineEvent) -> str:
    if event.event_name:
        return event.event_name
    event_id = _event_id(event)
    return get_cut_event_name(event_id) if event_id is not None else event.kind


def _event_target_id(event: CutTimelineEvent) -> int | None:
    if event.target_id is not None:
        return int(event.target_id)
    raw_id = event.event_payload.get("iObjectId")
    return int(raw_id) if isinstance(raw_id, int) else None


def _event_object_payload_id(event: CutTimelineEvent) -> int | None:
    value = event.payload.get("iObjectId")
    return int(value) if isinstance(value, int) else None


def _event_object_id_list(event: CutTimelineEvent) -> list[int]:
    value = event.payload.get("iObjectIdList")
    if not isinstance(value, list):
        return []
    return [int(item) for item in value]


def _find_non_finite(value: Any, path: str) -> list[str]:
    if isinstance(value, float):
        return [] if isfinite(value) else [path]
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_find_non_finite(item, f"{path}.{key}"))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for index, item in enumerate(value):
            result.extend(_find_non_finite(item, f"{path}[{index}]"))
        return result
    fields = getattr(value, "fields", None)
    return _find_non_finite(fields, path) if isinstance(fields, dict) else []


def _events_by_name(scene: CutScene, name: str) -> list[CutTimelineEvent]:
    return [event for event in scene.timeline if _event_name(event) == name]


def _has_loaded_model(scene: CutScene, object_id: int, time: float) -> bool:
    loaded = False
    events = sorted(
        (
            event
            for event in scene.timeline
            if event.event_name in {"load_models", "unload_models"}
            and float(event.start) <= time
        ),
        key=lambda event: float(event.start),
    )
    for event in events:
        if object_id in _event_object_id_list(event):
            loaded = event.event_name == "load_models"
    return loaded


def _active_animation_dicts(scene: CutScene, time: float) -> set[str]:
    active: set[str] = set()
    events = sorted(
        (
            event
            for event in scene.timeline
            if event.event_name in {"load_anim_dict", "unload_anim_dict"}
            and float(event.start) <= time
        ),
        key=lambda event: float(event.start),
    )
    for event in events:
        name = (event.label or _name(event.payload.get("cName")) or "").lower()
        if not name:
            continue
        if event.event_name == "load_anim_dict":
            active.add(name)
        else:
            active.discard(name)
    return active


def _dictionary_matches_ycd(name: str, ycd_stem: str) -> bool:
    if name == ycd_stem or ycd_stem.startswith(f"{name}-"):
        return True
    name_hash = _parse_hex_hash(name)
    if name_hash is None:
        return False
    candidates = {ycd_stem}
    base, separator, suffix = ycd_stem.rpartition("-")
    if separator and suffix.isdigit():
        candidates.add(base)
    return any(jenk_hash(candidate) == name_hash for candidate in candidates)


def _binding_text_field(binding: CutBinding, field_name: str) -> str | None:
    value = binding.fields.get(field_name)
    return _name(value)


def _binding_int_field(binding: CutBinding, field_name: str) -> int:
    value = binding.fields.get(field_name)
    return int(value) if value not in (None, "") else 0


def _has_segmented_clip(scene: CutScene, clip_base: str, cut_index: int) -> bool:
    expected_name = f"{clip_base}-{cut_index}"
    return scene.get_clip(expected_name) is not None


def _camera_clip_bases_by_section(scene: CutScene) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for ycd in scene.clip_dicts:
        for clip in ycd.clips:
            animations = [getattr(clip, "animation", None)]
            animations.extend(
                getattr(entry, "animation", None)
                for entry in getattr(clip, "animations", ())
            )
            if not any(
                animation is not None
                and any(is_ycd_camera_track(bone.track) for bone in animation.bone_ids)
                for animation in animations
            ):
                continue
            name = str(clip.short_name or clip.name or "")
            base, separator, suffix = name.rpartition("-")
            if separator and base and suffix.isdigit():
                result.setdefault(int(suffix), set()).add(base)
    return result


def _scene_flags(scene: CutScene) -> CutSceneFlags:
    if scene.cutscene_flags is not None:
        return unpack_cutscene_flags(scene.cutscene_flags)
    if scene.raw is not None:
        stored = scene.raw.root.fields.get("iCutsceneFlags")
        if stored is not None:
            return unpack_cutscene_flags(stored)
    flags = CutSceneFlags(DEFAULT_PLAYABLE_CUTSCENE_FLAGS)
    if scene.camera_cut_list:
        flags |= CutSceneFlags.SECTION_BY_CAMERA_CUTS
    return flags


def _validate_root(scene: CutScene, issues: ValidationReport, *, strict: bool) -> None:
    if scene.duration is None:
        _issue(issues, "error", "cut.duration.missing", "CutScene duration is missing")
    else:
        duration = float(scene.duration)
        if not isfinite(duration):
            _issue(
                issues,
                "error",
                "cut.duration.invalid",
                "CutScene duration must be finite",
            )
        elif duration <= 0.0:
            _issue(
                issues,
                "error",
                "cut.duration.non_positive",
                "CutScene duration must be greater than zero",
            )
        elif duration < CUT_MINIMUM_DURATION:
            _issue(
                issues,
                "error",
                "cut.duration.too_short",
                f"CutScene duration must be at least {CUT_MINIMUM_DURATION:g} second",
            )
    if scene.playback_rate <= 0.0 or not isfinite(float(scene.playback_rate)):
        _issue(
            issues,
            "error",
            "cut.playback_rate.invalid",
            "CutScene playback_rate must be finite and greater than zero",
        )
    for path in _find_non_finite(
        {
            "offset": scene.offset,
            "rotation": scene.rotation,
            "trigger_offset": scene.trigger_offset,
        },
        "cut",
    ):
        _issue(issues, "error", "cut.value.non_finite", f"{path} must be finite")
    if scene.section_by_time_slice_duration is not None:
        section_duration = float(scene.section_by_time_slice_duration)
        if not isfinite(section_duration) or section_duration <= 0.0:
            _issue(
                issues,
                "error",
                "cut.section_duration.invalid",
                "section_by_time_slice_duration must be finite and greater than zero",
            )
    range_start = int(scene.range_start or 0)
    range_end = (
        int(scene.range_end)
        if scene.range_end is not None
        else round(float(scene.duration or 0.0) * CUT_FPS)
    )
    if range_start < 0:
        _issue(
            issues,
            "error",
            "cut.range.start_negative",
            "range_start cannot be negative",
        )
    if range_end < range_start:
        _issue(
            issues,
            "error",
            "cut.range.invalid",
            "range_end cannot be lower than range_start",
        )
    elif scene.duration is not None and isfinite(float(scene.duration)):
        expected_frames = round(float(scene.duration) * CUT_FPS)
        if abs((range_end - range_start) - expected_frames) > 1:
            _issue(
                issues,
                "error",
                "cut.range.duration_mismatch",
                "range_start/range_end do not describe the authored cutscene duration",
            )
    if strict and not _events_by_name(scene, "load_scene"):
        _issue(
            issues,
            "error",
            "load_scene.missing",
            "CutScene has no LOAD_SCENE event",
            hint="A playable authored cutscene must load its scene before playback.",
        )


def _validate_binary_capacities(scene: CutScene, issues: ValidationReport) -> None:
    counts = {
        "objects": len(scene.bindings),
        "load events": sum(event.is_load_event for event in scene.timeline),
        "events": sum(not event.is_load_event for event in scene.timeline),
        "event arguments": len(scene.timeline),
        "camera cuts": len(scene.camera_cut_list or ()),
        "section splits": len(scene.section_split_list or ()),
    }
    for label, count in counts.items():
        if count > CUT_MAX_PSO_ARRAY_ITEMS:
            _issue(
                issues,
                "error",
                "cut.array.capacity",
                f"CutScene has {count} {label}; PSO arrays support at most {CUT_MAX_PSO_ARRAY_ITEMS}",
            )
    concat_count = 1
    if scene.raw is not None:
        concat_count = len(scene.raw.root.fields.get("concatDataList") or ()) or 1
    if concat_count > CUT_MAX_CONCATENATED_SCENES:
        _issue(
            issues,
            "error",
            "cut.concat.capacity",
            f"CutScene has {concat_count} concatenated scenes; maximum is {CUT_MAX_CONCATENATED_SCENES}",
        )


def _validate_section_list(
    values: list[float] | None,
    *,
    label: str,
    range_start: float,
    range_end: float,
    issues: ValidationReport,
) -> list[float]:
    result: list[float] = []
    previous: float | None = None
    for index, raw_value in enumerate(values or ()):
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            _issue(
                issues,
                "error",
                f"cut.section.{label}.invalid",
                f"{label} entry {index} must be numeric",
            )
            continue
        if not isfinite(value):
            _issue(
                issues,
                "error",
                f"cut.section.{label}.invalid",
                f"{label} entry {index} must be finite",
            )
            continue
        if value <= range_start or value >= range_end:
            _issue(
                issues,
                "error",
                f"cut.section.{label}.range",
                f"{label} entry {index} must be inside the active cutscene range",
            )
        if previous is not None and value <= previous:
            _issue(
                issues,
                "error",
                f"cut.section.{label}.order",
                f"{label} entries must be strictly increasing",
            )
        result.append(value)
        previous = value
    return result


def _validate_sections(scene: CutScene, issues: ValidationReport) -> None:
    flags = _scene_flags(scene)
    modes = flags & (
        CutSceneFlags.SECTION_BY_CAMERA_CUTS
        | CutSceneFlags.SECTION_BY_DURATION
        | CutSceneFlags.SECTION_BY_SPLIT
    )
    if int(modes).bit_count() > 1:
        _issue(
            issues,
            "error",
            "cut.section.mode.multiple",
            "CutScene can use only one sectioning mode",
        )
    if modes and not flags & CutSceneFlags.IS_SECTIONED:
        _issue(
            issues,
            "error",
            "cut.section.mode.unsectioned",
            "A sectioning mode requires IS_SECTIONED",
        )

    range_start = int(scene.range_start or 0) / CUT_FPS
    range_end_frames = (
        int(scene.range_end)
        if scene.range_end is not None
        else round(float(scene.duration or 0.0) * CUT_FPS)
    )
    range_end = range_end_frames / CUT_FPS
    if range_end <= range_start:
        return
    boundaries = [range_start]
    if modes == CutSceneFlags.SECTION_BY_CAMERA_CUTS:
        boundaries.extend(
            _validate_section_list(
                scene.camera_cut_list,
                label="camera_cut",
                range_start=range_start,
                range_end=range_end,
                issues=issues,
            )
        )
    elif modes == CutSceneFlags.SECTION_BY_SPLIT:
        boundaries.extend(
            _validate_section_list(
                scene.section_split_list,
                label="split",
                range_start=range_start,
                range_end=range_end,
                issues=issues,
            )
        )
    elif modes == CutSceneFlags.SECTION_BY_DURATION:
        section_duration = float(scene.section_by_time_slice_duration or 0.0)
        if section_duration < CUT_MINIMUM_SECTION_DURATION:
            _issue(
                issues,
                "error",
                "cut.section.duration.too_short",
                f"Duration-based sections must be at least {CUT_MINIMUM_SECTION_DURATION:g} second",
            )
        elif isfinite(section_duration):
            next_boundary = range_start + section_duration
            while next_boundary < range_end:
                boundaries.append(next_boundary)
                next_boundary += section_duration
    boundaries.append(range_end)
    for index, (start, end) in enumerate(itertools.pairwise(boundaries)):
        if end - start < CUT_MINIMUM_SECTION_DURATION - 1e-4:
            _issue(
                issues,
                "error",
                "cut.section.interval.too_short",
                f"CutScene section {index} is shorter than {CUT_MINIMUM_SECTION_DURATION:g} second",
            )


def _validate_bindings(scene: CutScene, issues: ValidationReport) -> None:
    ids = [binding.object_id for binding in scene.bindings]
    if len(ids) != len(set(ids)):
        _issue(
            issues, "error", "object.id.duplicate", "CutScene has duplicate object ids"
        )
    for binding in scene.bindings:
        if binding.object_id < 0:
            _issue(
                issues,
                "error",
                "object.id.invalid",
                f"{_binding_name(binding)} has a negative object id",
            )
        if not binding.type_name:
            _issue(
                issues,
                "error",
                "object.type.missing",
                f"{_binding_name(binding)} has no cutscene object type",
            )
        for path in _find_non_finite(binding.fields, f"object[{binding.object_id}]"):
            _issue(issues, "error", "object.value.non_finite", f"{path} must be finite")
        if _is_streamed_model(binding):
            streaming_name = _binding_text_field(binding, "StreamingName")
            type_file = _binding_text_field(binding, "typeFile")
            if not streaming_name:
                _issue(
                    issues,
                    "error",
                    "object.streaming_name.missing",
                    f"{_binding_name(binding)} has no StreamingName",
                )
            # Retail cutscene peds commonly leave typeFile at zero and resolve
            # their model through StreamingName plus the mounted PEDSTREAM_FILE.
            # Props and vehicles still require a YTYP/container reference.
            if not type_file and binding.role in {"prop", "vehicle"}:
                _issue(
                    issues,
                    "error",
                    "object.type_file.missing",
                    f"{_binding_name(binding)} has no typeFile/YTYP reference",
                    hint="Pass ytyp_name=... or type_file=... when creating the prop/ped/vehicle.",
                )


def _validate_events(scene: CutScene, issues: ValidationReport) -> None:
    duration = float(scene.duration or 0.0)
    bindings_by_id = scene.bindings_by_id
    for event in scene.timeline:
        name = _event_name(event)
        event_id = _event_id(event)
        if event_id is None or get_cut_event_name(event_id) is None:
            _issue(
                issues,
                "error",
                "event.id.unknown",
                f"Unknown cutscene event id/name for event '{name}'",
            )
            continue
        spec = get_cut_event_spec(event_id)
        for path in _find_non_finite(
            {"payload": event.payload, "event_payload": event.event_payload},
            f"event[{name}]",
        ):
            _issue(issues, "error", "event.value.non_finite", f"{path} must be finite")
        if not isfinite(float(event.start)):
            _issue(
                issues,
                "error",
                "event.time.invalid",
                f"{name} has a non-finite start time",
            )
        elif float(event.start) < 0.0:
            _issue(issues, "error", "event.time.negative", f"{name} starts before 0.0")
        elif duration > 0.0 and float(event.start) > duration + (1.0 / 30.0):
            _issue(
                issues,
                "warning",
                "event.time.after_duration",
                f"{name} starts after the cutscene duration",
            )
        target_id = _event_target_id(event)
        if target_id is not None and target_id not in bindings_by_id:
            _issue(
                issues,
                "error",
                "event.target.missing",
                f"{name} targets missing object id {target_id}",
            )
        if (
            spec is not None
            and spec.default_target_role is not None
            and target_id is None
        ):
            _issue(
                issues,
                "error",
                "event.target.required",
                f"{name} requires a target {spec.default_target_role} object",
                hint=f"Create scene.{spec.default_target_role}() or pass target=...",
            )
        elif (
            spec is not None
            and spec.default_target_role is not None
            and target_id is not None
        ):
            target = bindings_by_id.get(target_id)
            if target is not None and target.role != spec.default_target_role:
                _issue(
                    issues,
                    "error",
                    "event.target.role",
                    f"{name} targets {_binding_name(target)}, but requires role '{spec.default_target_role}'",
                )
        if event.duration is not None:
            event_duration = float(event.duration)
            if not isfinite(event_duration) or event_duration < 0.0:
                _issue(
                    issues,
                    "error",
                    "event.duration.invalid",
                    f"{name} has an invalid duration",
                )
        payload_id = _event_object_payload_id(event)
        if payload_id is not None and payload_id not in bindings_by_id:
            _issue(
                issues,
                "error",
                "event.payload_object.missing",
                f"{name} references missing object id {payload_id}",
            )
        for object_id in _event_object_id_list(event):
            if object_id not in bindings_by_id:
                _issue(
                    issues,
                    "error",
                    "event.payload_list_object.missing",
                    f"{name} references missing object id {object_id}",
                )


def _validate_attachments(scene: CutScene, issues: ValidationReport) -> None:
    parents: dict[int, int] = {}
    events = sorted(
        _events_by_name(scene, "set_attachment"),
        key=lambda event: (float(event.start), int(event.event_id or -1)),
    )
    for event in events:
        child_id = _event_target_id(event)
        parent_id = _event_object_payload_id(event)
        bone_name = _name(event.payload.get("cBoneName"))
        if child_id is None or parent_id is None:
            continue
        if child_id == parent_id:
            _issue(
                issues,
                "error",
                "attachment.self",
                f"Object id {child_id} cannot attach to itself",
            )
            continue
        if not bone_name:
            _issue(
                issues,
                "error",
                "attachment.bone.missing",
                f"Attachment for object id {child_id} has no bone name",
            )
        parents[child_id] = parent_id
        visited = {child_id}
        current = parent_id
        while current in parents:
            if current in visited:
                _issue(
                    issues,
                    "error",
                    "attachment.cycle",
                    f"Attachment at {event.start:g}s creates an object cycle",
                )
                break
            visited.add(current)
            current = parents[current]


def _validate_loading(scene: CutScene, issues: ValidationReport) -> None:
    load_model_events = _events_by_name(scene, "load_models")
    loaded_ids = {
        object_id
        for event in load_model_events
        for object_id in _event_object_id_list(event)
    }
    for binding in scene.entities:
        if (
            _is_scene_entity(binding.role)
            and binding.role in {"ped", "prop", "vehicle", "weapon"}
            and binding.object_id not in loaded_ids
        ):
            _issue(
                issues,
                "error",
                "object.not_loaded",
                f"{_binding_name(binding)} is never loaded by LOAD_MODELS",
                hint="Call scene.load_models(..., [object.object_id], target=asset_manager).",
            )
    for object_id in loaded_ids:
        binding = scene.get_binding(object_id)
        if binding is not None and binding.role not in {
            "ped",
            "prop",
            "vehicle",
            "weapon",
            "hidden_object",
            "fixup_object",
            "overlay",
            "particle_fx",
        }:
            _issue(
                issues,
                "warning",
                "load_models.non_model",
                f"LOAD_MODELS includes non-model object {_binding_name(binding)}",
            )


def _validate_cameras(
    scene: CutScene, issues: ValidationReport, *, strict: bool
) -> None:
    cameras = [binding for binding in scene.bindings if isinstance(binding, CutCamera)]
    if len(cameras) > 1:
        _issue(
            issues,
            "error",
            "camera.binding.multiple",
            f"CutScene has {len(cameras)} runtime camera bindings; exactly one is supported",
        )
    clip_bases_by_section = _camera_clip_bases_by_section(scene)
    inferred_clip_bases = (
        set().union(*clip_bases_by_section.values()) if clip_bases_by_section else set()
    )
    for camera in cameras:
        streaming_base = camera.animation_streaming_base
        readable_name = (
            camera.name
            if camera.name and _parse_hex_hash(camera.name) is None
            else None
        )
        clip_base = (
            next(iter(inferred_clip_bases))
            if len(inferred_clip_bases) == 1
            else readable_name
        )
        animated = bool(inferred_clip_bases) or streaming_base not in (None, 0)
        if animated and streaming_base in (None, 0):
            _issue(
                issues,
                "error",
                "camera.binding.streaming_base.missing",
                f"{_binding_name(camera)} has camera animation but no AnimStreamingBase",
            )
        if animated and streaming_base not in (None, 0) and clip_base:
            expected_base = jenk_partial_hash(clip_base)
            if streaming_base != expected_base:
                _issue(
                    issues,
                    "error",
                    "camera.binding.streaming_base.mismatch",
                    f"{_binding_name(camera)} AnimStreamingBase=0x{streaming_base:08X}, expected 0x{expected_base:08X} for '{clip_base}'",
                )

        near_clip = camera.near_draw_distance
        far_clip = camera.far_draw_distance
        if near_clip is None or near_clip <= 0.0:
            _issue(
                issues,
                "error",
                "camera.binding.near_draw_distance.invalid",
                f"{_binding_name(camera)} requires a positive near draw distance",
            )
        if far_clip is None or far_clip <= 0.0:
            _issue(
                issues,
                "error",
                "camera.binding.far_draw_distance.invalid",
                f"{_binding_name(camera)} requires a positive far draw distance",
            )
        elif near_clip is not None and near_clip > 0.0 and far_clip <= near_clip:
            _issue(
                issues,
                "error",
                "camera.binding.draw_distance.order",
                f"{_binding_name(camera)} far draw distance must exceed its near draw distance",
            )

        if animated and scene.clip_dicts:
            section_count = len(scene.camera_cut_list or ()) + 1
            for section_index in range(section_count):
                if clip_base not in clip_bases_by_section.get(section_index, set()):
                    _issue(
                        issues,
                        "error",
                        "camera.binding.clip.missing",
                        f"{_binding_name(camera)} has no matching camera clip in technical YCD section {section_index}",
                        hint=(
                            f"Expected '{clip_base}-{section_index}'."
                            if clip_base
                            else None
                        ),
                    )

            camera_cut_times = [
                float(event.start)
                for event in _events_by_name(scene, "camera_cut")
                if _event_target_id(event) == camera.object_id
            ]
            active_from = min(camera_cut_times, default=0.0)
            binding_times = [
                float(event.start)
                for event in _events_by_name(scene, "set_anim")
                if _event_object_payload_id(event) == camera.object_id
                and (
                    (target_id := _event_target_id(event)) is not None
                    and (target := scene.get_binding(target_id)) is not None
                    and target.role == "animation_manager"
                )
            ]
            concat_data = (
                scene.raw.root.fields.get("concatDataList") or ()
                if scene.raw is not None
                else ()
            )
            section_starts = [
                float(item.fields.get("fStartTime", 0.0))
                for item in concat_data
                if item.fields.get("bValidForPlayBack", True)
            ] or [0.0, *(float(value) for value in scene.camera_cut_list or ())]
            section_ends = [
                *section_starts[1:],
                float(scene.duration or 0.0),
            ]
            for section_index, (section_start, section_end) in enumerate(
                zip(section_starts, section_ends, strict=True)
            ):
                binding_time = max(active_from, section_start)
                if (
                    clip_base in clip_bases_by_section.get(section_index, set())
                    and active_from < section_end
                    and not any(
                        abs(event_time - binding_time) <= (1.0 / CUT_FPS)
                        for event_time in binding_times
                    )
                ):
                    _issue(
                        issues,
                        "error",
                        "camera.animation_binding.missing",
                        f"{_binding_name(camera)} has no SET_ANIM binding in technical YCD section {section_index}",
                    )

    camera_events = _events_by_name(scene, "camera_cut")
    if strict and not camera_events:
        _issue(
            issues,
            "error",
            "camera_cut.missing",
            "CutScene has no CAMERA_CUT event",
            hint="A playable cutscene needs at least one active camera.",
        )
    for event in camera_events:
        target_id = _event_target_id(event)
        target = scene.get_binding(target_id) if target_id is not None else None
        if target is None:
            _issue(
                issues,
                "error",
                "camera_cut.target.missing",
                f"CAMERA_CUT at {event.start:g} has no target camera",
            )
        elif target.role != "camera":
            _issue(
                issues,
                "error",
                "camera_cut.target.invalid",
                f"CAMERA_CUT at {event.start:g} targets {_binding_name(target)} instead of a camera",
            )

        name = _name(event.payload.get("cName")) or event.label
        if not name:
            _issue(
                issues, "error", "camera_cut.name.missing", "CAMERA_CUT has no cName"
            )
        position = event.payload.get("vPosition")
        rotation = event.payload.get("vRotationQuaternion")
        position_missing = not isinstance(position, (list, tuple)) or len(position) != 3
        rotation_missing = not isinstance(rotation, (list, tuple)) or len(rotation) != 4
        if position_missing or rotation_missing:
            _issue(
                issues,
                "error",
                "camera_cut.pose.missing",
                f"CAMERA_CUT '{name or event.start}' has no complete position and rotation pose",
            )
        elif not is_finite_vector(position, 3) or not is_finite_vector(rotation, 4):
            _issue(
                issues,
                "error",
                "camera_cut.pose.non_finite",
                f"CAMERA_CUT '{name or event.start}' has a non-finite pose",
            )
        near_clip = float(event.payload.get("fNearDrawDistance") or 0.0)
        far_clip = float(event.payload.get("fFarDrawDistance") or 0.0)
        invalid_negative = any(
            value < 0.0 and value != -1.0 for value in (near_clip, far_clip)
        )
        if invalid_negative:
            _issue(
                issues,
                "error",
                "camera_cut.clip.invalid",
                f"CAMERA_CUT '{name or event.start}' near/far draw distance "
                "must be non-negative or -1",
            )
        elif far_clip > 0.0 and near_clip > 0.0 and far_clip <= near_clip:
            _issue(
                issues,
                "error",
                "camera_cut.clip.order",
                f"CAMERA_CUT '{name or event.start}' far clip must be greater "
                "than near clip",
            )
        elif strict and far_clip == 0.0:
            _issue(
                issues,
                "warning",
                "camera_cut.far_clip.zero",
                f"CAMERA_CUT '{name or event.start}' has far draw distance 0",
                hint="Use a sane far clip such as 1000.0 to avoid invisible scenes in-game.",
            )
        if far_clip > 100000.0:
            _issue(
                issues,
                "warning",
                "camera_cut.far_clip.huge",
                f"CAMERA_CUT '{name or event.start}' has a very large far clip",
            )
        used_hours = 0
        modifiers = event.payload.get("TimeOfDayDofModifers") or []
        for index, modifier in enumerate(modifiers):
            fields = modifier.fields if hasattr(modifier, "fields") else modifier
            hour_flags = int(fields.get("TimeOfDayFlags", 0))
            strength = int(fields.get("DofStrengthModifier", 0))
            if hour_flags < 0 or hour_flags > 0xFFFFFF:
                _issue(
                    issues,
                    "error",
                    "camera_cut.dof.hours",
                    f"CAMERA_CUT '{name or event.start}' DOF modifier {index} "
                    "has invalid hour flags",
                )
            if used_hours & hour_flags:
                _issue(
                    issues,
                    "error",
                    "camera_cut.dof.overlap",
                    f"CAMERA_CUT '{name or event.start}' has overlapping DOF "
                    "modifier hours",
                )
            if strength < -15 or strength > 15:
                _issue(
                    issues,
                    "error",
                    "camera_cut.dof.strength",
                    f"CAMERA_CUT '{name or event.start}' DOF modifier {index} "
                    "strength is outside -15..15",
                )
            used_hours |= hour_flags


def _validate_animations(
    scene: CutScene, issues: ValidationReport, *, strict: bool
) -> None:
    load_anim_events = _events_by_name(scene, "load_anim_dict")
    set_anim_events = _events_by_name(scene, "set_anim")
    if strict and set_anim_events and not scene.clip_dicts:
        _issue(
            issues,
            "error",
            "set_anim.ycd.missing",
            "CutScene contains SET_ANIM events but has no attached YCD dictionaries",
            hint="Attach the YCDs or build the scene through CutsceneProject.",
        )
    for event in set_anim_events:
        payload_id = _event_object_payload_id(event)
        if payload_id is None:
            _issue(
                issues,
                "error",
                "set_anim.object.missing",
                "SET_ANIM has no target iObjectId in its payload",
            )
            continue
        binding = scene.get_binding(payload_id)
        if binding is None:
            continue
        if not _is_animation_capable(binding):
            _issue(
                issues,
                "error",
                "set_anim.object.invalid",
                f"SET_ANIM references non-animatable object {_binding_name(binding)}",
            )
            continue
        active_dicts = _active_animation_dicts(scene, float(event.start))
        if not active_dicts:
            _issue(
                issues,
                "error",
                "set_anim.dict.not_loaded",
                f"SET_ANIM for {_binding_name(binding)} has no active LOAD_ANIM_DICT",
            )
        elif scene.clip_dicts:
            known_stems = {ycd.stem.lower() for ycd in scene.clip_dicts if ycd.stem}
            if (
                known_stems
                and all(_parse_hex_hash(name) is None for name in active_dicts)
                and not any(
                    _dictionary_matches_ycd(name, stem)
                    for name in active_dicts
                    for stem in known_stems
                )
            ):
                _issue(
                    issues,
                    "error",
                    "set_anim.dict.mismatch",
                    f"SET_ANIM for {_binding_name(binding)} has no active dictionary matching the attached YCDs",
                )
        if _is_streamed_model(binding) and not _has_loaded_model(
            scene, binding.object_id, float(event.start)
        ):
            _issue(
                issues,
                "error",
                "set_anim.model.not_loaded",
                f"SET_ANIM for {_binding_name(binding)} happens before LOAD_MODELS",
            )
        authored_clip_base = getattr(binding, "animation_clip_base", None)
        animation_clip_base = getattr(
            binding, "runtime_animation_clip_base", authored_clip_base
        )
        anim_streaming_base = _binding_int_field(binding, "AnimStreamingBase")
        if (
            _is_streamed_model(binding)
            and not animation_clip_base
            and anim_streaming_base == 0
        ):
            _issue(
                issues,
                "error",
                "set_anim.streaming_base.missing",
                f"{_binding_name(binding)} is animated but has no animation_clip_base/AnimStreamingBase",
            )
        if authored_clip_base:
            expected_base = jenk_partial_hash(authored_clip_base)
            if anim_streaming_base != expected_base:
                _issue(
                    issues,
                    "error",
                    "set_anim.streaming_base.mismatch",
                    f"{_binding_name(binding)} AnimStreamingBase=0x{anim_streaming_base:08X}, expected 0x{expected_base:08X}",
                )
            if scene.clip_dicts:
                cut_index = _runtime_animation_section_index(
                    scene, float(event.start)
                )
                expected_clip_name = f"{animation_clip_base}-{cut_index}"
                if not _has_segmented_clip(scene, animation_clip_base, cut_index):
                    _issue(
                        issues,
                        "error",
                        "set_anim.clip.missing",
                        f"{_binding_name(binding)} has no matching clip in technical YCD segment {cut_index}",
                        hint=f"Expected the exact segmented clip '{expected_clip_name}'.",
                    )
        elif anim_streaming_base and scene.clip_dicts:
            active_cut_index = _runtime_animation_section_index(
                scene, float(event.start)
            )
            if scene.clip_for_binding(binding, cut_index=active_cut_index) is None:
                _issue(
                    issues,
                    "error",
                    "set_anim.clip_hash.missing",
                    f"{_binding_name(binding)} has no clip matching AnimStreamingBase in technical YCD segment {active_cut_index}",
                )
        explicit_clip = _name(event.payload.get("cName"))
        explicit_clip_key = _parse_hex_hash(explicit_clip) or explicit_clip
        if (
            explicit_clip
            and scene.clip_dicts
            and scene.get_clip(explicit_clip_key) is None
        ):
            _issue(
                issues,
                "error",
                "set_anim.explicit_clip.missing",
                f"SET_ANIM references missing explicit clip '{explicit_clip}'",
            )
    for event in load_anim_events:
        label = event.label or _name(event.payload.get("cName"))
        if not label:
            _issue(
                issues,
                "error",
                "load_anim_dict.name.missing",
                "LOAD_ANIM_DICT has no dictionary name",
            )
        elif strict and scene.clip_dicts:
            known_stems = {ycd.stem.lower() for ycd in scene.clip_dicts if ycd.stem}
            if known_stems and not any(
                _dictionary_matches_ycd(label.lower(), stem) for stem in known_stems
            ):
                _issue(
                    issues,
                    "error",
                    "load_anim_dict.ycd.missing",
                    f"LOAD_ANIM_DICT '{label}' does not match any attached YCD",
                )


def _validate_facial_animation(scene: CutScene, issues: ValidationReport) -> None:
    for binding in scene.peds:
        if not isinstance(binding, CutPed):
            continue
        name = _binding_name(binding)
        if (
            binding.override_face_animation
            and not binding.override_face_animation_filename
        ):
            _issue(
                issues,
                "error",
                "ped.face.override_filename.missing",
                f"{name} enables facial animation override without a filename",
            )
        if binding.face_and_body_are_merged and not binding.has_face_animation:
            _issue(
                issues,
                "error",
                "ped.face.merged.inactive",
                f"{name} merges face and body but does not enable facial animation",
            )
        if binding.has_face_animation and not binding.face_and_body_are_merged:
            _issue(
                issues,
                "error",
                "ped.face.separate.unsupported",
                f"{name} requests a separate facial clip, which final runtime builds do not play",
                hint="Use merged facial animation and author the '<base>_dual-<section>' clip.",
            )
        if (
            binding.has_face_animation
            and not binding.animation_clip_base
            and _binding_int_field(binding, "AnimStreamingBase") == 0
        ):
            _issue(
                issues,
                "error",
                "ped.face.clip_base.missing",
                f"{name} has facial animation but no resolvable animation_clip_base",
            )


def _validate_assets(scene: CutScene, issues: ValidationReport) -> None:
    for event_name in (
        "load_scene",
        "unload_scene",
        "load_audio",
        "unload_audio",
        "play_audio",
        "stop_audio",
        "load_subtitles",
        "unload_subtitles",
    ):
        for event in _events_by_name(scene, event_name):
            label = event.label or _name(event.payload.get("cName"))
            if not label:
                _issue(
                    issues,
                    "error",
                    f"{event_name}.name.missing",
                    f"{event_name.upper()} has no name",
                )
    for event in _events_by_name(scene, "show_subtitle"):
        if not (event.label or _name(event.payload.get("cName"))):
            _issue(
                issues,
                "error",
                "show_subtitle.name.missing",
                "SHOW_SUBTITLE has no text/key name",
            )
        if (
            float(event.payload.get("fSubtitleDuration") or event.duration or 0.0)
            <= 0.0
        ):
            _issue(
                issues,
                "warning",
                "show_subtitle.duration.zero",
                "SHOW_SUBTITLE duration is zero or missing",
            )


def _validate_audio_timeline(
    scene: CutScene,
    issues: ValidationReport,
    *,
    strict: bool,
) -> None:
    loaded: set[int] = set()
    playing: set[int] = set()
    events = sorted(
        (
            event
            for event in scene.timeline
            if _event_name(event)
            in {"load_audio", "unload_audio", "play_audio", "stop_audio"}
        ),
        key=lambda event: float(event.start),
    )
    for event in events:
        target_id = _event_target_id(event)
        if target_id is None:
            continue
        name = _event_name(event)
        if name == "load_audio":
            loaded.add(target_id)
        elif name == "play_audio":
            if strict and target_id not in loaded:
                _issue(
                    issues,
                    "error",
                    "play_audio.not_loaded",
                    f"PLAY_AUDIO for object {target_id} occurs before LOAD_AUDIO",
                    hint=(
                        "Author a LOAD_AUDIO event unless playback intentionally relies "
                        "on the external force-load runtime flag."
                    ),
                )
            playing.add(target_id)
        elif name == "stop_audio":
            if target_id not in playing:
                _issue(
                    issues,
                    "warning",
                    "stop_audio.not_playing",
                    f"STOP_AUDIO for object {target_id} has no preceding PLAY_AUDIO",
                )
            playing.discard(target_id)
        else:
            if target_id not in loaded:
                _issue(
                    issues,
                    "warning",
                    "unload_audio.not_loaded",
                    f"UNLOAD_AUDIO for object {target_id} has no preceding LOAD_AUDIO",
                )
            loaded.discard(target_id)
            playing.discard(target_id)


def _validate_flags(scene: CutScene, issues: ValidationReport) -> None:
    flags = _scene_flags(scene)
    if (
        CutSceneFlags.IS_SECTIONED in flags
        and scene.section_by_time_slice_duration is not None
        and float(scene.section_by_time_slice_duration) <= 0.0
    ):
        _issue(
            issues,
            "error",
            "flags.sectioned.invalid_duration",
            "IS_SECTIONED requires a positive section duration",
        )
    if CutSceneFlags.NO_AMBIENT_LIGHTS in flags and scene.lights:
        _issue(
            issues,
            "warning",
            "flags.lights.no_ambient",
            "NO_AMBIENT_LIGHTS is set while the cutscene contains light objects",
        )


def validate_cut_scene(
    scene: CutScene,
    *,
    strict: bool = False,
    context: BuildContext | None = None,
) -> ValidationReport:
    if context is not None:
        strict = context.strict
    source_asset = scene.scene_name or None
    scene = deepcopy(scene)
    scene.build()
    issues = ValidationReport()
    _validate_root(scene, issues, strict=strict)
    _validate_binary_capacities(scene, issues)
    _validate_sections(scene, issues)
    _validate_bindings(scene, issues)
    _validate_events(scene, issues)
    _validate_attachments(scene, issues)
    _validate_loading(scene, issues)
    _validate_cameras(scene, issues, strict=strict)
    _validate_facial_animation(scene, issues)
    _validate_animations(scene, issues, strict=strict)
    _validate_assets(scene, issues)
    _validate_audio_timeline(scene, issues, strict=strict)
    _validate_flags(scene, issues)
    if source_asset is not None:
        issues.issues = [issue.for_asset(source_asset) for issue in issues]
    return issues
