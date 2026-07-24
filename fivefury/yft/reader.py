from __future__ import annotations

import struct
from pathlib import Path

from ..binary import f32 as _f32
from ..binary import u16 as _u16
from ..binary import u32 as _u32
from ..binary import u64 as _u64
from ..binary import vec3 as _vec3
from ..common import ByteSource, read_source_bytes
from ..resource import RSC7_MAGIC, split_rsc7_sections, virtual_to_offset
from ..ydr.read_lights import parse_light_array
from ..ydr.shaders import ShaderLibrary
from .cloth_reader import read_environment_cloths
from .constants import (
    DAT_VIRTUAL_BASE,
    DRAWABLE_ARRAY_COUNT_OFFSET,
    LIGHT_ATTRIBUTES_ARRAY_OFFSET,
)
from .drawable_reader import read_fragment_drawable
from .drawables import YftDrawable
from .events import YftEventSet
from .events_reader import read_event_set
from .fields_reader import read_fragment_pointers, read_fragment_state, read_raw_fields
from .fragment import Yft
from .glass_reader import read_glass_panes, read_vehicle_glass_windows
from .io_helpers import (
    read_bounding_sphere,
    read_pointer_array,
    read_string_pointer_array,
    try_read_c_string,
)
from .matrices_reader import read_shared_matrix_set
from .physics_reader import (
    read_physics_child,
    read_physics_lod_pointers,
    read_physics_lods,
)


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
    event_set_cache: dict[int, YftEventSet] = {}
    physics_lod_pointers = read_physics_lod_pointers(
        system_data, pointers.physics_lod_group
    )

    physics_lod_details = read_physics_lods(
        header,
        system_data,
        graphics_data,
        physics_lod_pointers,
        path=resource_path,
        shader_library=shader_library,
        resolve_entities=resolve_physics_entities,
        event_set_cache=event_set_cache,
    )
    root_child = next(
        (
            child
            for lod in physics_lod_details
            for child in lod.children
            if child.pointer == pointers.root_child
        ),
        None,
    )
    if root_child is None:
        root_child = read_physics_child(
            system_data,
            pointers.root_child,
            event_set_cache=event_set_cache,
        )

    main_drawable = _read_optional_drawable(
        header,
        system_data,
        graphics_data,
        pointers.common_drawable,
        label="drawable",
        path=resource_path,
        shader_library=shader_library,
    )
    drawables = _read_drawable_array(
        header,
        system_data,
        graphics_data,
        pointers=pointers,
        path=resource_path,
        shader_library=shader_library,
    )
    cloth_drawable = _read_optional_drawable(
        header,
        system_data,
        graphics_data,
        pointers.cloth_drawable,
        label="drawable_cloth",
        path=resource_path,
        shader_library=shader_library,
    )
    drawable_labels = {pointers.common_drawable: "drawable"}
    drawable_labels.update({entry.pointer: entry.label for entry in drawables})
    if pointers.cloth_drawable:
        drawable_labels[pointers.cloth_drawable] = "drawable_cloth"
    environment_cloths, character_cloth_count = read_environment_cloths(
        system_data,
        drawable_labels=drawable_labels,
    )
    glass_pane_count = system_data[0xD9] if len(system_data) > 0xD9 else 0

    return Yft(
        version=int(header.version),
        path=resource_path,
        bounding_sphere=read_bounding_sphere(system_data),
        pointers=pointers,
        state=read_fragment_state(system_data),
        physics_lods=physics_lod_pointers,
        physics_lod_details=physics_lod_details,
        root_child=root_child,
        collision_event_set=read_event_set(
            system_data,
            pointers.collision_event_set,
            cache=event_set_cache,
        ),
        user_data=pointers.user_data,
        tune_name=try_read_c_string(system_data, pointers.tune_name),
        raw_fields=read_raw_fields(system_data),
        main_drawable=main_drawable,
        drawables=drawables,
        cloth_drawable=cloth_drawable,
        environment_cloths=environment_cloths,
        character_cloth_count=character_cloth_count,
        glass_panes=read_glass_panes(
            system_data,
            pointers.glass_pane_model_infos,
            glass_pane_count,
        ),
        vehicle_glass_windows=read_vehicle_glass_windows(
            system_data,
            pointers.vehicle_glass_windows,
        ),
        shared_matrix_set=read_shared_matrix_set(
            system_data,
            pointers.shared_matrix_set,
        ),
        lights=parse_light_array(
            system_data,
            header_offset=LIGHT_ATTRIBUTES_ARRAY_OFFSET,
            virtual_offset=lambda pointer, _data: virtual_to_offset(
                pointer,
                base=DAT_VIRTUAL_BASE,
            ),
            u16=_u16,
            u32=_u32,
            u64=_u64,
            f32=_f32,
            vec3=_vec3,
        ),
        raw_bytes=bytes(data),
    )


__all__ = [
    "read_yft",
]
