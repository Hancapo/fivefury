from __future__ import annotations

from pathlib import Path

from ..resource import virtual_to_offset
from ..ydr.reader import _read_ydr_from_sections
from ..ydr.shaders import ShaderLibrary
from .constants import DAT_VIRTUAL_BASE, DRAWABLE_FIELDS_OFFSET


def drawable_root_offset(system_data: bytes, pointer: int) -> int:
    offset = virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE) + DRAWABLE_FIELDS_OFFSET
    if offset < 0 or offset >= len(system_data):
        raise ValueError("YFT drawable pointer is out of range")
    return offset


def internal_drawable_path(container_path: str, label: str) -> str:
    if not container_path:
        return f"{label}.ydr"
    return f"{Path(container_path).stem}/{label}.ydr"


def read_fragment_drawable(
    header,
    system_data: bytes,
    graphics_data: bytes,
    pointer: int,
    *,
    label: str,
    path: str,
    shader_library: ShaderLibrary | None,
):
    return _read_ydr_from_sections(
        header,
        system_data,
        graphics_data,
        root_offset=drawable_root_offset(system_data, pointer),
        path=internal_drawable_path(path, label),
        shader_library=shader_library,
    )


__all__ = [
    "drawable_root_offset",
    "internal_drawable_path",
    "read_fragment_drawable",
]
