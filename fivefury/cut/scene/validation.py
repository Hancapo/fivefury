from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Any, Literal

from ...hashing import jenk_finalize_hash, jenk_partial_hash
from ...metahash import MetaHash
from ..events import get_cut_event_name, get_cut_event_spec
from ..flags import CutSceneFlags, unpack_cutscene_flags
from .bindings import CutBinding
from .shared import _coerce_name, _is_scene_entity

if TYPE_CHECKING:  # pragma: no cover
    from .base import CutScene
    from .timeline import CutTimelineEvent


CutSceneValidationSeverity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class CutSceneValidationIssue:
    severity: CutSceneValidationSeverity
    code: str
    message: str
    hint: str | None = None

    def format(self) -> str:
        text = f"[{self.severity.upper()}:{self.code}] {self.message}"
        if self.hint:
            text += f" Hint: {self.hint}"
        return text


class CutSceneValidationError(ValueError):
    def __init__(self, issues: list[CutSceneValidationIssue]) -> None:
        self.issues = [issue for issue in issues if issue.severity == "error"]
        super().__init__("\n".join(issue.format() for issue in self.issues))


def _issue(
    issues: list[CutSceneValidationIssue],
    severity: CutSceneValidationSeverity,
    code: str,
    message: str,
    *,
    hint: str | None = None,
) -> None:
    issues.append(CutSceneValidationIssue(severity=severity, code=code, message=message, hint=hint))


def _name(value: Any) -> str | None:
    return _coerce_name(value)


def _binding_name(binding: CutBinding) -> str:
    return binding.name or f"{binding.role}:{binding.object_id}"


def _is_streamed_model(binding: CutBinding) -> bool:
    return binding.role in {"ped", "prop", "vehicle"}


def _is_animation_capable(binding: CutBinding) -> bool:
    return binding.role in {"ped", "prop", "vehicle", "camera"}


def _event_id(event: "CutTimelineEvent") -> int | None:
    if event.event_id is None:
        return None
    return int(event.event_id)


def _event_name(event: "CutTimelineEvent") -> str:
    if event.event_name:
        return event.event_name
    event_id = _event_id(event)
    return get_cut_event_name(event_id) if event_id is not None else event.kind


def _event_target_id(event: "CutTimelineEvent") -> int | None:
    if event.target_id is not None:
        return int(event.target_id)
    raw_id = event.event_payload.get("iObjectId")
    return int(raw_id) if isinstance(raw_id, int) else None


def _event_object_payload_id(event: "CutTimelineEvent") -> int | None:
    value = event.payload.get("iObjectId")
    return int(value) if isinstance(value, int) else None


def _event_object_id_list(event: "CutTimelineEvent") -> list[int]:
    value = event.payload.get("iObjectIdList")
    if not isinstance(value, list):
        return []
    return [int(item) for item in value]


def _events_by_name(scene: "CutScene", name: str) -> list["CutTimelineEvent"]:
    return [event for event in scene.timeline if _event_name(event) == name]


def _has_event_at_or_before(events: list["CutTimelineEvent"], name: str, time: float) -> bool:
    return any(_event_name(event) == name and float(event.start) <= time for event in events)


def _has_loaded_model(scene: "CutScene", object_id: int, time: float) -> bool:
    for event in _events_by_name(scene, "load_models"):
        if float(event.start) <= time and object_id in _event_object_id_list(event):
            return True
    return False


def _binding_text_field(binding: CutBinding, field_name: str) -> str | None:
    value = binding.fields.get(field_name)
    return _name(value)


def _binding_int_field(binding: CutBinding, field_name: str) -> int:
    value = binding.fields.get(field_name)
    return int(value) if value not in (None, "") else 0


def _validate_root(scene: "CutScene", issues: list[CutSceneValidationIssue]) -> None:
    if scene.duration is None:
        _issue(issues, "error", "cut.duration.missing", "CutScene duration is missing")
    else:
        duration = float(scene.duration)
        if not isfinite(duration):
            _issue(issues, "error", "cut.duration.invalid", "CutScene duration must be finite")
        elif duration <= 0.0:
            _issue(issues, "error", "cut.duration.non_positive", "CutScene duration must be greater than zero")
    if scene.playback_rate <= 0.0 or not isfinite(float(scene.playback_rate)):
        _issue(issues, "error", "cut.playback_rate.invalid", "CutScene playback_rate must be finite and greater than zero")
    if scene.section_by_time_slice_duration is not None and float(scene.section_by_time_slice_duration) <= 0.0:
        _issue(issues, "error", "cut.section_duration.invalid", "section_by_time_slice_duration must be greater than zero")
    if scene.range_start is not None and scene.range_end is not None and int(scene.range_end) < int(scene.range_start):
        _issue(issues, "error", "cut.range.invalid", "range_end cannot be lower than range_start")


def _validate_bindings(scene: "CutScene", issues: list[CutSceneValidationIssue]) -> None:
    ids = [binding.object_id for binding in scene.bindings]
    if len(ids) != len(set(ids)):
        _issue(issues, "error", "object.id.duplicate", "CutScene has duplicate object ids")
    for binding in scene.bindings:
        if binding.object_id < 0:
            _issue(issues, "error", "object.id.invalid", f"{_binding_name(binding)} has a negative object id")
        if not binding.type_name:
            _issue(issues, "error", "object.type.missing", f"{_binding_name(binding)} has no cutscene object type")
        if _is_streamed_model(binding):
            streaming_name = _binding_text_field(binding, "StreamingName")
            type_file = _binding_text_field(binding, "typeFile")
            if not streaming_name:
                _issue(issues, "error", "object.streaming_name.missing", f"{_binding_name(binding)} has no StreamingName")
            if not type_file:
                _issue(
                    issues,
                    "error",
                    "object.type_file.missing",
                    f"{_binding_name(binding)} has no typeFile/YTYP reference",
                    hint="Pass ytyp_name=... or type_file=... when creating the prop/ped/vehicle.",
                )


def _validate_events(scene: "CutScene", issues: list[CutSceneValidationIssue]) -> None:
    duration = float(scene.duration or 0.0)
    bindings_by_id = scene.bindings_by_id
    for event in scene.timeline:
        name = _event_name(event)
        event_id = _event_id(event)
        if event_id is None or get_cut_event_name(event_id) is None:
            _issue(issues, "error", "event.id.unknown", f"Unknown cutscene event id/name for event '{name}'")
            continue
        spec = get_cut_event_spec(event_id)
        if not isfinite(float(event.start)):
            _issue(issues, "error", "event.time.invalid", f"{name} has a non-finite start time")
        elif float(event.start) < 0.0:
            _issue(issues, "error", "event.time.negative", f"{name} starts before 0.0")
        elif duration > 0.0 and float(event.start) > duration + (1.0 / 30.0):
            _issue(issues, "warning", "event.time.after_duration", f"{name} starts after the cutscene duration")
        target_id = _event_target_id(event)
        if target_id is not None and target_id not in bindings_by_id:
            _issue(issues, "error", "event.target.missing", f"{name} targets missing object id {target_id}")
        if spec is not None and spec.default_target_role is not None and target_id is None:
            _issue(
                issues,
                "error",
                "event.target.required",
                f"{name} requires a target {spec.default_target_role} object",
                hint=f"Create scene.add_{spec.default_target_role}() or pass target=...",
            )
        payload_id = _event_object_payload_id(event)
        if payload_id is not None and payload_id not in bindings_by_id:
            _issue(issues, "error", "event.payload_object.missing", f"{name} references missing object id {payload_id}")
        for object_id in _event_object_id_list(event):
            if object_id not in bindings_by_id:
                _issue(issues, "error", "event.payload_list_object.missing", f"{name} references missing object id {object_id}")


def _validate_loading(scene: "CutScene", issues: list[CutSceneValidationIssue]) -> None:
    load_model_events = _events_by_name(scene, "load_models")
    loaded_ids = {object_id for event in load_model_events for object_id in _event_object_id_list(event)}
    for binding in scene.entities:
        if _is_scene_entity(binding.role) and binding.role in {"ped", "prop", "vehicle"} and binding.object_id not in loaded_ids:
            _issue(
                issues,
                "error",
                "object.not_loaded",
                f"{_binding_name(binding)} is never loaded by LOAD_MODELS",
                hint="Call scene.load_models(..., [object.object_id], target=asset_manager).",
            )
    for object_id in loaded_ids:
        binding = scene.get_binding(object_id)
        if binding is not None and binding.role not in {"ped", "prop", "vehicle", "hidden_object", "fixup_object", "overlay", "particle_fx"}:
            _issue(issues, "warning", "load_models.non_model", f"LOAD_MODELS includes non-model object {_binding_name(binding)}")


def _validate_cameras(scene: "CutScene", issues: list[CutSceneValidationIssue], *, strict: bool) -> None:
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
        name = _name(event.payload.get("cName")) or event.label
        if not name:
            _issue(issues, "error", "camera_cut.name.missing", "CAMERA_CUT has no cName")
        near_clip = float(event.payload.get("fNearDrawDistance") or 0.0)
        far_clip = float(event.payload.get("fFarDrawDistance") or 0.0)
        if near_clip < 0.0 or far_clip < 0.0:
            _issue(issues, "error", "camera_cut.clip.negative", f"CAMERA_CUT '{name or event.start}' has negative near/far draw distance")
        elif far_clip and near_clip and far_clip <= near_clip:
            _issue(issues, "error", "camera_cut.clip.order", f"CAMERA_CUT '{name or event.start}' far clip must be greater than near clip")
        elif strict and far_clip == 0.0:
            _issue(
                issues,
                "warning",
                "camera_cut.far_clip.zero",
                f"CAMERA_CUT '{name or event.start}' has far draw distance 0",
                hint="Use a sane far clip such as 1000.0 to avoid invisible scenes in-game.",
            )
        if far_clip > 100000.0:
            _issue(issues, "warning", "camera_cut.far_clip.huge", f"CAMERA_CUT '{name or event.start}' has a very large far clip")


def _validate_animations(scene: "CutScene", issues: list[CutSceneValidationIssue]) -> None:
    timeline = scene.timeline
    load_anim_events = _events_by_name(scene, "load_anim_dict")
    clip_map = scene.available_clips(cut_index=0) if scene.clip_dicts else {}
    for event in _events_by_name(scene, "set_anim"):
        payload_id = _event_object_payload_id(event)
        if payload_id is None:
            _issue(issues, "error", "set_anim.object.missing", "SET_ANIM has no target iObjectId in its payload")
            continue
        binding = scene.get_binding(payload_id)
        if binding is None:
            continue
        if not _is_animation_capable(binding):
            _issue(issues, "error", "set_anim.object.invalid", f"SET_ANIM references non-animatable object {_binding_name(binding)}")
            continue
        if not _has_event_at_or_before(timeline, "load_anim_dict", float(event.start)):
            _issue(issues, "error", "set_anim.dict.not_loaded", f"SET_ANIM for {_binding_name(binding)} has no previous LOAD_ANIM_DICT")
        if _is_streamed_model(binding) and not _has_loaded_model(scene, binding.object_id, float(event.start)):
            _issue(issues, "error", "set_anim.model.not_loaded", f"SET_ANIM for {_binding_name(binding)} happens before LOAD_MODELS")
        animation_clip_base = getattr(binding, "animation_clip_base", None)
        anim_streaming_base = _binding_int_field(binding, "AnimStreamingBase")
        if _is_streamed_model(binding) and not animation_clip_base and anim_streaming_base == 0:
            _issue(
                issues,
                "error",
                "set_anim.streaming_base.missing",
                f"{_binding_name(binding)} is animated but has no animation_clip_base/AnimStreamingBase",
            )
        if animation_clip_base:
            expected_base = jenk_partial_hash(animation_clip_base)
            if anim_streaming_base != expected_base:
                _issue(
                    issues,
                    "error",
                    "set_anim.streaming_base.mismatch",
                    f"{_binding_name(binding)} AnimStreamingBase=0x{anim_streaming_base:08X}, expected 0x{expected_base:08X}",
                )
            if clip_map:
                expected_clip_name = f"{animation_clip_base}-0"
                candidates = {
                    MetaHash(animation_clip_base).uint,
                    MetaHash(expected_clip_name).uint,
                    jenk_finalize_hash(expected_base),
                }
                if not any(key in clip_map for key in candidates):
                    _issue(
                        issues,
                        "error",
                        "set_anim.clip.missing",
                        f"{_binding_name(binding)} has no matching clip in attached YCDs",
                        hint=f"Expected a clip hash compatible with '{animation_clip_base}' or '{expected_clip_name}'.",
                    )
    for event in load_anim_events:
        label = event.label or _name(event.payload.get("cName"))
        if not label:
            _issue(issues, "error", "load_anim_dict.name.missing", "LOAD_ANIM_DICT has no dictionary name")


def _validate_assets(scene: "CutScene", issues: list[CutSceneValidationIssue]) -> None:
    for event_name in ("load_scene", "unload_scene", "load_audio", "unload_audio", "play_audio", "stop_audio", "load_subtitles", "unload_subtitles"):
        for event in _events_by_name(scene, event_name):
            label = event.label or _name(event.payload.get("cName"))
            if not label:
                _issue(issues, "error", f"{event_name}.name.missing", f"{event_name.upper()} has no name")
    for event in _events_by_name(scene, "show_subtitle"):
        if not (event.label or _name(event.payload.get("cName"))):
            _issue(issues, "error", "show_subtitle.name.missing", "SHOW_SUBTITLE has no text/key name")
        if float(event.payload.get("fSubtitleDuration") or event.duration or 0.0) <= 0.0:
            _issue(issues, "warning", "show_subtitle.duration.zero", "SHOW_SUBTITLE duration is zero or missing")


def _validate_flags(scene: "CutScene", issues: list[CutSceneValidationIssue]) -> None:
    flags = unpack_cutscene_flags(scene.cutscene_flags)
    if CutSceneFlags.IS_SECTIONED in flags:
        if scene.section_by_time_slice_duration is not None and float(scene.section_by_time_slice_duration) <= 0.0:
            _issue(issues, "error", "flags.sectioned.invalid_duration", "IS_SECTIONED requires a positive section duration")
    if CutSceneFlags.NO_AMBIENT_LIGHTS in flags and scene.lights:
        _issue(issues, "warning", "flags.lights.no_ambient", "NO_AMBIENT_LIGHTS is set while the cutscene contains light objects")


def validate_cut_scene(scene: "CutScene", *, strict: bool = False) -> list[CutSceneValidationIssue]:
    scene.build()
    issues: list[CutSceneValidationIssue] = []
    _validate_root(scene, issues)
    _validate_bindings(scene, issues)
    _validate_events(scene, issues)
    _validate_loading(scene, issues)
    _validate_cameras(scene, issues, strict=strict)
    _validate_animations(scene, issues)
    _validate_assets(scene, issues)
    _validate_flags(scene, issues)
    for warning in scene.validate_animations():
        if not any(warning in issue.message for issue in issues):
            _issue(issues, "warning", "animation.compat", warning)
    return issues


def assert_cut_scene_valid(scene: "CutScene", *, strict: bool = True) -> None:
    issues = validate_cut_scene(scene, strict=strict)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise CutSceneValidationError(errors)
