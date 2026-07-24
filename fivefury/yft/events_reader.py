from __future__ import annotations

from ..binary import i32 as _i32
from ..binary import u16 as _u16
from ..binary import u32 as _u32
from ..binary import u64 as _u64
from .events import YftEventSet
from .io_helpers import read_pointer_array, try_virtual_offset

_EVENT_SET_SIZE = 0x38


def read_event_set(
    system_data: bytes,
    pointer: int,
    *,
    cache: dict[int, YftEventSet] | None = None,
) -> YftEventSet | None:
    if not pointer:
        return None
    if cache is not None and pointer in cache:
        return cache[pointer]
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or offset + _EVENT_SET_SIZE > len(system_data):
        return None
    count = _u16(system_data, offset + 0x18)
    capacity = _u16(system_data, offset + 0x1A)
    instance_pointer = _u64(system_data, offset + 0x10)
    event_set = YftEventSet(
        pointer=pointer,
        resource_tag=_u32(system_data, offset),
        resource_state=_u32(system_data, offset + 4),
        reserved_08=_u64(system_data, offset + 8),
        instance_pointers=tuple(
            read_pointer_array(system_data, instance_pointer, count)
        ),
        capacity=capacity,
        new_instance_type=_i32(system_data, offset + 0x20),
        bank_pointer=_u64(system_data, offset + 0x28),
        group_pointer=_u64(system_data, offset + 0x30),
    )
    if cache is not None:
        cache[pointer] = event_set
    return event_set


__all__ = ["read_event_set"]
