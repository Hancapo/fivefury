from __future__ import annotations

from collections.abc import Iterable

from ..resource import ResourceWriter
from .events import YftEventSet, YftPhysicsChildEvents

_EVENT_SET_SIZE = 0x40


def write_event_sets(
    writer: ResourceWriter,
    event_sets: Iterable[YftEventSet],
) -> dict[int, int]:
    offsets: dict[int, int] = {}
    for event_set in event_sets:
        identity = id(event_set)
        if identity in offsets:
            continue
        if not event_set.can_rebuild:
            raise ValueError("only empty runtime YFT event sets can be rebuilt")
        offset = writer.alloc(_EVENT_SET_SIZE, 16)
        writer.pack_into("I", offset, int(event_set.resource_tag))
        writer.pack_into("I", offset + 4, int(event_set.resource_state))
        writer.pack_into("Q", offset + 8, int(event_set.reserved_08))
        writer.pack_into("HH", offset + 0x18, 0, 0)
        writer.pack_into("i", offset + 0x20, int(event_set.new_instance_type))
        offsets[identity] = offset
    return offsets


def event_set_pointer(
    event_set: YftEventSet | None,
    offsets: dict[int, int],
    *,
    virtual_base: int,
) -> int:
    if event_set is None:
        return 0
    return virtual_base + offsets[id(event_set)]


def write_child_event_pointers(
    writer: ResourceWriter,
    offset: int,
    events: YftPhysicsChildEvents,
    event_set_offsets: dict[int, int],
    *,
    virtual_base: int,
) -> None:
    for field_offset, event_set in (
        (0xB0, events.continuous),
        (0xB8, events.collision),
        (0xC0, events.break_event),
        (0xC8, events.break_from_root),
    ):
        writer.pack_into(
            "Q",
            offset + field_offset,
            event_set_pointer(
                event_set,
                event_set_offsets,
                virtual_base=virtual_base,
            ),
        )
    writer.pack_into(
        "Q",
        offset + 0xD0,
        int(events.collision_player_pointer),
    )
    writer.pack_into(
        "Q",
        offset + 0xD8,
        int(events.break_player_pointer),
    )
    writer.pack_into(
        "Q",
        offset + 0xE0,
        int(events.break_from_root_player_pointer),
    )


__all__ = [
    "event_set_pointer",
    "write_child_event_pointers",
    "write_event_sets",
]
