from __future__ import annotations

import dataclasses
import struct
from pathlib import Path

from ..binary import read_c_string
from ..bounds import Bound, read_bound_from_pointer
from ..resource import virtual_to_offset
from ..vector import Vector3
from ..ydr import Ydr
from ..ydr.model import YdrMaterial
from ..ydr.reader import _read_ydr_from_sections
from ..ydr.shaders import ShaderLibrary
from .constants import (
    DAT_VIRTUAL_BASE,
    FRAGMENT_DRAWABLE_BASE_OFFSET,
    FRAGMENT_DRAWABLE_SIZE,
    GEN9_YFT_VERSIONS,
)
from .fragment_drawable import (
    YftFragmentDrawable,
    YftFragmentDrawableName,
    YftFragmentMatrix,
)


def drawable_root_offset(system_data: bytes, pointer: int) -> int:
    offset = virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE)
    if offset < 0 or offset + FRAGMENT_DRAWABLE_SIZE > len(system_data):
        raise ValueError("YFT drawable pointer is out of range")
    return offset


def internal_drawable_path(container_path: str, label: str) -> str:
    if not container_path:
        return f"{label}.ydr"
    return f"{Path(container_path).stem}/{label}.ydr"


def _read_fragment_matrix(system_data: bytes, offset: int) -> YftFragmentMatrix:
    columns = []
    flags = []
    for index in range(4):
        column_offset = offset + (index * 16)
        columns.append(
            Vector3.from_iterable(
                struct.unpack_from("<3f", system_data, column_offset)
            )
        )
        flags.append(struct.unpack_from("<I", system_data, column_offset + 12)[0])
    return YftFragmentMatrix(
        columns=tuple(columns),  # type: ignore[arg-type]
        flags=tuple(flags),  # type: ignore[arg-type]
    )


def _read_extra_bounds(
    system_data: bytes,
    pointer: int,
    array_count: int,
    active_count: int,
) -> tuple[Bound | None, ...]:
    if active_count > array_count:
        raise ValueError("YFT fragment drawable extra-bound count exceeds array count")
    if array_count <= 0:
        return ()
    if not pointer:
        raise ValueError("YFT fragment drawable extra-bound array is null")
    offset = virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE)
    end = offset + (array_count * 8)
    if offset < 0 or end > len(system_data):
        raise ValueError("YFT fragment drawable extra-bound array is truncated")
    pointers = struct.unpack_from(f"<{array_count}Q", system_data, offset)
    bounds = tuple(
        read_bound_from_pointer(bound_pointer, system_data)
        if bound_pointer
        else None
        for bound_pointer in pointers
    )
    return bounds[:active_count]


def _read_fragment_matrices(
    system_data: bytes, pointer: int, count: int
) -> tuple[YftFragmentMatrix, ...]:
    if not pointer or count <= 0:
        return ()
    offset = virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE)
    end = offset + (count * 64)
    if offset < 0 or end > len(system_data):
        raise ValueError("YFT fragment drawable matrix array is truncated")
    return tuple(
        _read_fragment_matrix(system_data, offset + (index * 64))
        for index in range(count)
    )


def _read_skeleton_type_name(
    system_data: bytes, pointer: int
) -> str | YftFragmentDrawableName:
    if not pointer:
        return YftFragmentDrawableName.NULL
    offset = virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE)
    if offset < 0 or offset >= len(system_data):
        raise ValueError("YFT fragment drawable string pointer is out of range")
    return read_c_string(system_data, offset)


def read_fragment_drawable(
    header,
    system_data: bytes,
    graphics_data: bytes,
    pointer: int,
    *,
    label: str,
    path: str,
    shader_library: ShaderLibrary | None,
    inherited_materials: list[YdrMaterial] | None = None,
):
    root_offset = drawable_root_offset(system_data, pointer)
    drawable_base = _read_ydr_from_sections(
        header,
        system_data,
        graphics_data,
        root_offset=root_offset + FRAGMENT_DRAWABLE_BASE_OFFSET,
        path=internal_drawable_path(path, label),
        shader_library=shader_library,
        read_extensions=False,
        inherited_materials=inherited_materials,
        enhanced=int(header.version) in GEN9_YFT_VERSIONS,
    )
    bound_pointer = struct.unpack_from("<Q", system_data, root_offset + 0xF0)[0]
    bound = (
        read_bound_from_pointer(bound_pointer, system_data) if bound_pointer else None
    )
    bounds_pointer = struct.unpack_from("<Q", system_data, root_offset + 0xF8)[0]
    bounds_count = struct.unpack_from("<H", system_data, root_offset + 0x100)[0]
    bounds_capacity = struct.unpack_from("<H", system_data, root_offset + 0x102)[0]
    matrices_pointer = struct.unpack_from("<Q", system_data, root_offset + 0x108)[0]
    active_bound_count = struct.unpack_from("<H", system_data, root_offset + 0x110)[0]
    if bounds_count > bounds_capacity:
        raise ValueError("YFT fragment drawable extra-bound array exceeds capacity")
    if active_bound_count > bounds_count:
        raise ValueError("YFT fragment drawable extra-bound count exceeds array count")
    name_pointer = struct.unpack_from("<Q", system_data, root_offset + 0x130)[0]
    base_values = {
        field.name: getattr(drawable_base, field.name)
        for field in dataclasses.fields(Ydr)
        if field.init
    }
    base_values["bound"] = bound
    return YftFragmentDrawable(
        **base_values,
        fragment_matrix=_read_fragment_matrix(system_data, root_offset + 0xB0),
        extra_bounds=_read_extra_bounds(
            system_data,
            bounds_pointer,
            bounds_count,
            active_bound_count,
        ),
        extra_bound_matrices=_read_fragment_matrices(
            system_data,
            matrices_pointer,
            active_bound_count,
        ),
        skeleton_type_name=_read_skeleton_type_name(system_data, name_pointer),
        load_skeleton=bool(
            struct.unpack_from("<H", system_data, root_offset + 0x112)[0]
        ),
        locators_pointer=struct.unpack_from("<Q", system_data, root_offset + 0x118)[0],
        animations_pointer=struct.unpack_from("<Q", system_data, root_offset + 0x120)[
            0
        ],
        cloned_shader_group_pointer=struct.unpack_from(
            "<Q", system_data, root_offset + 0x128
        )[0],
    )


__all__ = [
    "drawable_root_offset",
    "internal_drawable_path",
    "read_fragment_drawable",
]
