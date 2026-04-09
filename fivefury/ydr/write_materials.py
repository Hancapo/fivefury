from __future__ import annotations

import struct
from typing import Callable, Sequence

from ..binary import align
from ..hashing import jenk_hash


def normalize_parameter_key(value: str) -> str:
    return str(value).strip().lower()


def coerce_parameter_inline(value: float | tuple[float, ...] | int | str) -> bytes:
    if isinstance(value, str):
        raise ValueError("String shader parameters are not supported by the YDR builder yet")
    if isinstance(value, (int, float)):
        components = [float(value), 0.0, 0.0, 0.0]
    else:
        components = [float(component) for component in value]
        if not components or len(components) > 4:
            raise ValueError("Shader parameter tuples must have between 1 and 4 components")
        while len(components) < 4:
            components.append(0.0)
    return struct.pack("<4f", *components)


def merge_shader_parameter_defaults(
    parameters: dict[str, float | tuple[float, ...] | int | str],
    shader_definition,
) -> dict[str, float | tuple[float, ...] | int | str]:
    merged: dict[str, float | tuple[float, ...] | int | str] = {}
    for definition in shader_definition.parameters:
        if definition.is_texture or definition.default_value is None:
            continue
        merged[definition.name] = definition.default_value
    for name, value in parameters.items():
        merged[str(name)] = value
    return merged


def prepare_materials(
    materials,
    shader_library,
    *,
    prepared_material_cls,
    normalize_material_textures: Callable,
    resolve_shader: Callable,
) -> tuple[list[object], dict[str, int]]:
    prepared: list[object] = []
    index_by_name: dict[str, int] = {}
    for index, material in enumerate(materials):
        key = material.name.lower()
        if key in index_by_name:
            raise ValueError(f"Duplicate YDR material name '{material.name}'")
        shader_definition, shader_file_name = resolve_shader(material.shader, int(material.render_bucket), shader_library)
        normalized_textures = normalize_material_textures(material.textures)
        valid_texture_slots = {parameter.name.lower(): parameter for parameter in shader_definition.texture_parameters}
        for slot_name in normalized_textures:
            if slot_name.lower() not in valid_texture_slots:
                raise ValueError(
                    f"Material '{material.name}' uses texture slot '{slot_name}' which is not defined by shader '{shader_file_name}'"
                )
        prepared.append(
            prepared_material_cls(
                index=index,
                name=material.name,
                shader_definition=shader_definition,
                shader_file_name=shader_file_name,
                render_bucket=int(material.render_bucket),
                textures=normalized_textures,
                parameters=merge_shader_parameter_defaults(
                    {str(name): value for name, value in material.parameters.items()},
                    shader_definition,
                ),
            )
        )
        index_by_name[key] = index
    return prepared, index_by_name


def build_parameter_entries(
    material,
    system,
    *,
    shader_parameter_entry_cls,
    texture_base_vft: int,
    virtual: Callable[[int], int],
) -> list[object]:
    texture_slots = {slot.lower(): texture for slot, texture in material.textures.items()}
    numeric_params = {normalize_parameter_key(name): value for name, value in material.parameters.items()}
    entries: list[object] = []
    for definition in material.shader_definition.parameters:
        key = definition.name.lower()
        if definition.is_texture:
            texture_input = texture_slots.get(key)
            if texture_input is None:
                continue
            texture_name_off = system.c_string(texture_input.name)
            texture_base_off = system.alloc(0x50, 16)
            system.pack_into("I", texture_base_off + 0x00, texture_base_vft)
            system.pack_into("I", texture_base_off + 0x04, 1)
            system.pack_into("Q", texture_base_off + 0x28, virtual(texture_name_off))
            system.pack_into("H", texture_base_off + 0x30, 1)
            system.pack_into("H", texture_base_off + 0x32, 2)
            entries.append(shader_parameter_entry_cls(definition=definition, data_type=0, data_pointer=virtual(texture_base_off)))
            continue
        if key not in numeric_params:
            continue
        entries.append(
            shader_parameter_entry_cls(
                definition=definition,
                data_type=1,
                inline_data=coerce_parameter_inline(numeric_params[key]),
            )
        )
    return entries


def write_shader_parameters_block(
    system,
    material,
    *,
    shader_parameter_entry_cls,
    texture_base_vft: int,
    virtual: Callable[[int], int],
) -> tuple[int, int, int, int, int]:
    entries = build_parameter_entries(
        material,
        system,
        shader_parameter_entry_cls=shader_parameter_entry_cls,
        texture_base_vft=texture_base_vft,
        virtual=virtual,
    )
    if not entries:
        return 0, 0, 0, 0, 0

    inline_size = sum(len(entry.inline_data) for entry in entries)
    parameter_count = len(entries)
    parameter_size = (parameter_count * 16) + inline_size
    parameter_data_size = align(32 + parameter_size + (parameter_count * 4), 16)
    params_off = system.alloc(parameter_data_size, 16)

    inline_off = params_off + (parameter_count * 16)
    for index, entry in enumerate(entries):
        entry_off = params_off + (index * 16)
        system.data[entry_off] = entry.data_type & 0xFF
        if entry.data_type == 0:
            system.pack_into("Q", entry_off + 0x08, entry.data_pointer)
        else:
            system.write(inline_off, entry.inline_data)
            system.pack_into("Q", entry_off + 0x08, virtual(inline_off))
            inline_off += len(entry.inline_data)

    hashes_off = params_off + parameter_size
    for index, entry in enumerate(entries):
        system.pack_into("I", hashes_off + (index * 4), entry.definition.name_hash)

    texture_count = sum(1 for entry in entries if entry.data_type == 0)
    return virtual(params_off), parameter_count, parameter_size, parameter_data_size, texture_count


def write_shader_blocks(
    system,
    materials: Sequence[object],
    *,
    shader_parameter_entry_cls,
    texture_base_vft: int,
    shader_group_vft: int,
    virtual: Callable[[int], int],
) -> tuple[int, int]:
    shader_group_off = system.alloc(0x40, 16)
    shader_ptrs_off = system.alloc(len(materials) * 8, 8) if materials else 0
    if materials:
        system.pack_into("Q", shader_group_off + 0x10, virtual(shader_ptrs_off))
        system.pack_into("H", shader_group_off + 0x18, len(materials))
        system.pack_into("H", shader_group_off + 0x1A, len(materials))
    system.pack_into("I", shader_group_off + 0x00, shader_group_vft)
    system.pack_into("I", shader_group_off + 0x04, 1)
    system.pack_into("I", shader_group_off + 0x30, 4)

    for material in materials:
        shader_off = system.alloc(0x30, 16)
        if shader_ptrs_off:
            system.pack_into("Q", shader_ptrs_off + (material.index * 8), virtual(shader_off))
        params_pointer, parameter_count, parameter_size, parameter_data_size, texture_param_count = write_shader_parameters_block(
            system,
            material,
            shader_parameter_entry_cls=shader_parameter_entry_cls,
            texture_base_vft=texture_base_vft,
            virtual=virtual,
        )
        system.pack_into("Q", shader_off + 0x00, params_pointer)
        system.pack_into("I", shader_off + 0x08, material.shader_definition.name_hash)
        system.pack_into("I", shader_off + 0x0C, 0)
        system.data[shader_off + 0x10] = parameter_count & 0xFF
        system.data[shader_off + 0x11] = material.render_bucket & 0xFF
        system.pack_into("H", shader_off + 0x12, 0x8000)
        system.pack_into("H", shader_off + 0x14, parameter_size)
        system.pack_into("H", shader_off + 0x16, parameter_data_size)
        system.pack_into("I", shader_off + 0x18, int(jenk_hash(material.shader_file_name)))
        system.pack_into("I", shader_off + 0x1C, 0)
        system.pack_into("I", shader_off + 0x20, ((1 << material.render_bucket) | 0xFF00) & 0xFFFFFFFF)
        system.pack_into("H", shader_off + 0x24, 0)
        system.data[shader_off + 0x26] = 0
        system.data[shader_off + 0x27] = texture_param_count & 0xFF
    return shader_group_off, 4
