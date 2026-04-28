from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...common import hash_value
from ..events import CutEventBehavior, CutEventType, get_cut_event_enum_name, get_cut_event_id, get_cut_event_name, get_cut_event_spec
from ..model import CutHashedString, CutNode, CutResolvedEvent
from ..payloads import CutEventPayload
from .bindings import CutBinding
from .shared import (
    _ARGS_BASE_FIELDS,
    _EVENT_BASE_FIELDS,
    _clone_value,
    _coerce_event_label_value,
    _coerce_payload,
    _event_category,
    _event_duration,
    _event_label,
    _event_label_field,
    _node_type_hash,
    _object_role,
    _track_identity,
    _uses_plain_cname,
)


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
                    args_fields[label_field] = _coerce_event_label_value(spec.args_type_name, label_field, self.label)
                if self.duration is not None:
                    if "fSubtitleDuration" in args_fields:
                        args_fields["fSubtitleDuration"] = float(self.duration)
                    elif "interpTime" in args_fields:
                        args_fields["interpTime"] = float(self.duration)
                    elif "interpTimeTag" in args_fields:
                        args_fields["interpTimeTag"] = float(self.duration)
                for key, value in self.payload.items():
                    if key == label_field and isinstance(value, str):
                        args_fields[key] = _coerce_event_label_value(spec.args_type_name, key, value)
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
                    if _uses_plain_cname(args.type_name):
                        args.fields["cName"] = self.label
                    else:
                        args.fields["cName"] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) and current.hash else hash_value(self.label), text=self.label)
                elif "cameraCutHashName" in args.fields:
                    current = args.fields["cameraCutHashName"]
                    args.fields["cameraCutHashName"] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) and current.hash else hash_value(self.label), text=self.label)
                elif "cameraCutHashTag" in args.fields:
                    current = args.fields["cameraCutHashTag"]
                    args.fields["cameraCutHashTag"] = CutHashedString(hash=current.hash if isinstance(current, CutHashedString) and current.hash else hash_value(self.label), text=self.label)
            if self.duration is not None:
                if "fSubtitleDuration" in args.fields:
                    args.fields["fSubtitleDuration"] = float(self.duration)
                elif "interpTime" in args.fields:
                    args.fields["interpTime"] = float(self.duration)
                elif "interpTimeTag" in args.fields:
                    args.fields["interpTimeTag"] = float(self.duration)
            for key, value in self.payload.items():
                args.fields[key] = _clone_value(value)
        return CutResolvedEvent(event=event, object=_clone_value(self.raw.object) if self.raw.object is not None else None, event_args=args, is_load_event=self.is_load_event)


@dataclass(slots=True)
class CutTrack:
    key: str
    name: str
    kind: str
    events: list[CutTimelineEvent] = field(default_factory=list)


def _timeline_event_from_resolved(resolved: CutResolvedEvent, bindings_by_id: dict[int, CutBinding]) -> CutTimelineEvent:
    event = resolved.event
    object_id = event.fields.get("iObjectId")
    binding = bindings_by_id.get(object_id) if isinstance(object_id, int) else None
    object_name = binding.name if binding is not None else None
    object_role = binding.role if binding is not None else (_object_role(resolved.object.type_name) if resolved.object is not None else None)
    kind = _event_category(resolved)
    track_key, _ = _track_identity(kind, object_role, object_name, object_id if isinstance(object_id, int) else None, is_load_event=resolved.is_load_event)
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
