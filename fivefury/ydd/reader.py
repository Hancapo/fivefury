from __future__ import annotations

import struct
from pathlib import Path

from ..binary import u16 as _u16, u32 as _u32, u64 as _u64
from ..resolver import resolve_hash
from ..resource import RSC7_MAGIC, checked_virtual_offset, read_virtual_pointer_array, split_rsc7_sections, virtual_to_offset
from ..ydr.shaders import ShaderLibrary
from ..ydr.reader import _read_ydr_from_sections
from .model import Ydd, YddDrawable

_DAT_VIRTUAL_BASE = 0x50000000
_DRAWABLE_FIELDS_OFFSET = 0x10
_HASHES_POINTER_OFFSET = 0x20
_HASHES_COUNT_OFFSET = 0x28
_DRAWABLES_POINTER_OFFSET = 0x30
_DRAWABLES_COUNT_OFFSET = 0x38


def _read_source_bytes(source: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    return bytes(source)


def _read_uint_array(system_data: bytes, pointer: int, count: int) -> list[int]:
    if not pointer or count <= 0:
        return []
    start = checked_virtual_offset(pointer, system_data, base=_DAT_VIRTUAL_BASE)
    end = start + (count * 4)
    if end > len(system_data):
        raise ValueError("uint array is truncated")
    return [int(_u32(system_data, start + index * 4)) for index in range(count)]


def _read_pointer_array(system_data: bytes, pointer: int, count: int) -> list[int]:
    return read_virtual_pointer_array(system_data, pointer, count, base=_DAT_VIRTUAL_BASE)


def _name_from_hash(name_hash: int) -> str:
    resolved = resolve_hash(name_hash)
    if resolved:
        return resolved
    return f"hash_{int(name_hash) & 0xFFFFFFFF:08X}"


def _internal_drawable_path(container_path: str, name: str, index: int) -> str:
    clean_name = str(name or f"drawable_{index}")
    if not container_path:
        return f"{clean_name}.ydr"
    return f"{Path(container_path).stem}/{clean_name}.ydr"


def read_ydd(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    path: str | Path = "",
    shader_library: ShaderLibrary | None = None,
) -> Ydd:
    data = _read_source_bytes(source)
    if len(data) < 16:
        raise ValueError("YDD data is too short")
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != RSC7_MAGIC:
        raise ValueError("YDD data must be a standalone RSC7 resource")

    header, system_data, graphics_data = split_rsc7_sections(data)
    hashes_pointer = _u64(system_data, _HASHES_POINTER_OFFSET)
    hashes_count = _u16(system_data, _HASHES_COUNT_OFFSET)
    drawables_pointer = _u64(system_data, _DRAWABLES_POINTER_OFFSET)
    drawables_count = _u16(system_data, _DRAWABLES_COUNT_OFFSET)

    hashes = _read_uint_array(system_data, hashes_pointer, hashes_count)
    drawable_pointers = _read_pointer_array(system_data, drawables_pointer, drawables_count)
    resource_path = str(path or source) if isinstance(source, (str, Path)) or path else ""

    entries: list[YddDrawable] = []
    for index, drawable_pointer in enumerate(drawable_pointers):
        if not drawable_pointer:
            continue
        name_hash = hashes[index] if index < len(hashes) else 0
        name = _name_from_hash(name_hash)
        root_offset = virtual_to_offset(drawable_pointer, base=_DAT_VIRTUAL_BASE) + _DRAWABLE_FIELDS_OFFSET
        if root_offset < 0 or root_offset >= len(system_data):
            raise ValueError("YDD drawable pointer is out of range")
        drawable = _read_ydr_from_sections(
            header,
            system_data,
            graphics_data,
            root_offset=root_offset,
            path=_internal_drawable_path(resource_path, name, index),
            shader_library=shader_library,
        )
        entries.append(YddDrawable(name_hash=name_hash, name=name, drawable=drawable))

    return Ydd(
        version=int(header.version),
        path=resource_path,
        drawables=entries,
    )


__all__ = [
    "read_ydd",
]
