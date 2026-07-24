from __future__ import annotations

import struct
from pathlib import Path

from ..binary import u32 as _u32
from ..common import ByteSource, read_source_bytes
from ..resource import RSC7_MAGIC, split_rsc7_sections
from ..ydr.shaders import ShaderLibrary
from .constants import DRAWABLE_ARRAY_COUNT_OFFSET
from .drawable_reader import read_fragment_drawable
from .drawables import YftDrawable
from .fields_reader import read_fragment_pointers, read_fragment_state, read_raw_fields
from .fragment import Yft
from .io_helpers import (
    read_bounding_sphere,
    read_pointer_array,
    read_string_pointer_array,
    try_read_c_string,
)
from .physics_reader import read_physics_lod_pointers, read_physics_lods


def _read_drawable_array(
    header,
    system_data: bytes,
    graphics_data: bytes,
    *,
    pointers,
    path: str,
    shader_library: ShaderLibrary | None,
) -> list[YftDrawable]:
    drawable_count = _u32(system_data, DRAWABLE_ARRAY_COUNT_OFFSET)
    drawable_pointers = read_pointer_array(
        system_data, pointers.extra_drawables, drawable_count
    )
    drawable_names = read_string_pointer_array(
        system_data, pointers.extra_drawable_names, drawable_count
    )
    drawables: list[YftDrawable] = []
    for index, pointer in enumerate(drawable_pointers):
        if not pointer:
            continue
        name = (
            drawable_names[index]
            if index < len(drawable_names) and drawable_names[index]
            else ""
        )
        label = name or f"drawable_array_{index}"
        drawables.append(
            YftDrawable(
                label=label,
                pointer=pointer,
                name=name,
                drawable=read_fragment_drawable(
                    header,
                    system_data,
                    graphics_data,
                    pointer,
                    label=label,
                    path=path,
                    shader_library=shader_library,
                ),
            )
        )
    return drawables


def _read_optional_drawable(
    header,
    system_data: bytes,
    graphics_data: bytes,
    pointer: int,
    *,
    label: str,
    path: str,
    shader_library: ShaderLibrary | None,
):
    if not pointer:
        return None
    return read_fragment_drawable(
        header,
        system_data,
        graphics_data,
        pointer,
        label=label,
        path=path,
        shader_library=shader_library,
    )


def read_yft(
    source: ByteSource,
    *,
    path: str | Path = "",
    shader_library: ShaderLibrary | None = None,
    resolve_physics_entities: bool = True,
) -> Yft:
    data = read_source_bytes(source)
    if len(data) < 16:
        raise ValueError("YFT data is too short")
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != RSC7_MAGIC:
        raise ValueError("YFT data must be a standalone RSC7 resource")

    header, system_data, graphics_data = split_rsc7_sections(data)
    resource_path = (
        str(path or source) if isinstance(source, (str, Path)) or path else ""
    )
    pointers = read_fragment_pointers(system_data)
    physics_lod_pointers = read_physics_lod_pointers(
        system_data, pointers.physics_lod_group
    )

    return Yft(
        version=int(header.version),
        path=resource_path,
        bounding_sphere=read_bounding_sphere(system_data),
        pointers=pointers,
        state=read_fragment_state(system_data),
        physics_lods=physics_lod_pointers,
        physics_lod_details=read_physics_lods(
            header,
            system_data,
            graphics_data,
            physics_lod_pointers,
            path=resource_path,
            shader_library=shader_library,
            resolve_entities=resolve_physics_entities,
        ),
        tune_name=try_read_c_string(system_data, pointers.tune_name),
        raw_fields=read_raw_fields(system_data),
        main_drawable=_read_optional_drawable(
            header,
            system_data,
            graphics_data,
            pointers.common_drawable,
            label="drawable",
            path=resource_path,
            shader_library=shader_library,
        ),
        drawables=_read_drawable_array(
            header,
            system_data,
            graphics_data,
            pointers=pointers,
            path=resource_path,
            shader_library=shader_library,
        ),
        cloth_drawable=_read_optional_drawable(
            header,
            system_data,
            graphics_data,
            pointers.cloth_drawable,
            label="drawable_cloth",
            path=resource_path,
            shader_library=shader_library,
        ),
        raw_bytes=bytes(data),
    )


__all__ = [
    "read_yft",
]
