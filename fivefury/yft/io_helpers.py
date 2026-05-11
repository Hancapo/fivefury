from __future__ import annotations

from ..binary import f32 as _f32, read_c_string
from ..resource import read_virtual_pointer_array, virtual_to_offset
from .constants import BOUNDING_SPHERE_OFFSET, DAT_VIRTUAL_BASE


def read_pointer_array(system_data: bytes, pointer: int, count: int) -> list[int]:
    return read_virtual_pointer_array(
        system_data, pointer, count, base=DAT_VIRTUAL_BASE
    )


def try_virtual_offset(system_data: bytes, pointer: int) -> int | None:
    if not pointer:
        return None
    offset = virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE)
    if offset < 0 or offset >= len(system_data):
        return None
    return offset


def try_read_c_string(system_data: bytes, pointer: int) -> str:
    offset = try_virtual_offset(system_data, pointer)
    if offset is None:
        return ""
    try:
        text = read_c_string(system_data, offset)
    except Exception:
        return ""
    if not text or any(ord(char) < 32 or ord(char) > 126 for char in text):
        return ""
    return text


def read_string_pointer_array(
    system_data: bytes, pointer: int, count: int
) -> list[str]:
    return [
        try_read_c_string(system_data, item)
        for item in read_pointer_array(system_data, pointer, count)
    ]


def read_bounding_sphere(system_data: bytes) -> tuple[float, float, float, float]:
    return tuple(
        float(_f32(system_data, BOUNDING_SPHERE_OFFSET + (index * 4)))
        for index in range(4)
    )


def read_vec3(system_data: bytes, offset: int) -> tuple[float, float, float]:
    return (
        float(_f32(system_data, offset)),
        float(_f32(system_data, offset + 4)),
        float(_f32(system_data, offset + 8)),
    )


def read_fixed_ascii(data: bytes, offset: int, size: int) -> str:
    chunk = data[offset : offset + size]
    end = chunk.find(b"\x00")
    if end != -1:
        chunk = chunk[:end]
    return chunk.decode("ascii", errors="ignore")


def read_pointer_tuple(system_data: bytes, pointer: int, count: int) -> tuple[int, ...]:
    if count <= 0:
        return ()
    return tuple(read_pointer_array(system_data, pointer, count))


def read_u8_array(system_data: bytes, pointer: int, count: int) -> tuple[int, ...]:
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or count <= 0 or offset + count > len(system_data):
        return ()
    return tuple(system_data[offset : offset + count])


__all__ = [
    "read_bounding_sphere",
    "read_fixed_ascii",
    "read_pointer_array",
    "read_pointer_tuple",
    "read_string_pointer_array",
    "read_u8_array",
    "read_vec3",
    "try_read_c_string",
    "try_virtual_offset",
]
