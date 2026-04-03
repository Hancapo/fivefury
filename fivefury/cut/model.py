from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..metahash import MetaHash


@dataclass(slots=True)
class CutHashedString:
    hash: int
    text: str | None = None

    @property
    def meta_hash(self) -> MetaHash:
        return MetaHash(self.hash)

    def __str__(self) -> str:
        return self.text if self.text else f"0x{self.hash:08X}"


@dataclass(slots=True)
class CutNode:
    type_name: str
    type_hash: int | None = None
    fields: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: Any = None) -> Any:
        return self.fields.get(name, default)

    def __getitem__(self, key: str) -> Any:
        return self.fields[key]

    def __contains__(self, key: str) -> bool:
        return key in self.fields


@dataclass(slots=True)
class CutResolvedEvent:
    event: CutNode
    object: CutNode | None = None
    event_args: CutNode | None = None
    is_load_event: bool = False


@dataclass(slots=True)
class CutSummary:
    source: str
    root_type: str
    duration: float | None
    face_dir: str | CutHashedString | None
    object_count: int
    load_event_count: int
    event_count: int
    event_arg_count: int
    object_types: dict[str, int]
    load_event_types: dict[str, int]
    event_types: dict[str, int]
    event_arg_types: dict[str, int]


@dataclass(slots=True)
class CutFile:
    root: CutNode
    source: str = "cut"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def objects(self) -> list[CutNode]:
        return list(self.root.fields.get("pCutsceneObjects", []))

    @property
    def load_events(self) -> list[CutNode]:
        return list(self.root.fields.get("pCutsceneLoadEventList", []))

    @property
    def events(self) -> list[CutNode]:
        return list(self.root.fields.get("pCutsceneEventList", []))

    @property
    def event_args(self) -> list[CutNode]:
        return list(self.root.fields.get("pCutsceneEventArgsList", []))

    @property
    def objects_by_id(self) -> dict[int, CutNode]:
        result: dict[int, CutNode] = {}
        for node in self.objects:
            object_id = node.fields.get("iObjectId")
            if isinstance(object_id, int):
                result[object_id] = node
        return result

    def get_object(self, object_id: int) -> CutNode | None:
        return self.objects_by_id.get(object_id)

    def get_event_args(self, index: int) -> CutNode | None:
        if index < 0:
            return None
        values = self.event_args
        if index >= len(values):
            return None
        return values[index]

    def resolve_event(self, event: CutNode, *, is_load_event: bool = False) -> CutResolvedEvent:
        object_id = event.fields.get("iObjectId")
        event_args_index = event.fields.get("iEventArgsIndex")
        return CutResolvedEvent(
            event=event,
            object=self.get_object(object_id) if isinstance(object_id, int) else None,
            event_args=self.get_event_args(event_args_index) if isinstance(event_args_index, int) else None,
            is_load_event=is_load_event,
        )

    def iter_resolved_events(self, *, include_load_events: bool = True, include_events: bool = True):
        if include_load_events:
            for event in self.load_events:
                yield self.resolve_event(event, is_load_event=True)
        if include_events:
            for event in self.events:
                yield self.resolve_event(event, is_load_event=False)

    def summary(self) -> CutSummary:
        return CutSummary(
            source=self.source,
            root_type=self.root.type_name,
            duration=self.root.fields.get("fTotalDuration"),
            face_dir=self.root.fields.get("cFaceDir"),
            object_count=len(self.objects),
            load_event_count=len(self.load_events),
            event_count=len(self.events),
            event_arg_count=len(self.event_args),
            object_types=dict(Counter(node.type_name for node in self.objects)),
            load_event_types=dict(Counter(node.type_name for node in self.load_events)),
            event_types=dict(Counter(node.type_name for node in self.events)),
            event_arg_types=dict(Counter(node.type_name for node in self.event_args)),
        )

    def to_bytes(self, *, template: "CutFile | bytes | str | None" = None) -> bytes:
        from .write import build_cut_bytes

        return build_cut_bytes(self, template=template)

    def save(self, destination: str, *, template: "CutFile | bytes | str | None" = None) -> None:
        from pathlib import Path

        Path(destination).write_bytes(self.to_bytes(template=template))
