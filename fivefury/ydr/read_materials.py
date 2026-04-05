from __future__ import annotations

import struct
from typing import Callable

from .model import YdrMaterial, YdrMaterialParameterRef, YdrTextureRef
from .shaders import ShaderLibrary


def parse_texture_base(
    system_data: bytes,
    pointer: int,
    *,
    virtual_offset: Callable[[int, bytes], int],
    u64: Callable[[bytes, int], int],
    try_read_c_string: Callable[[int, bytes], str],
) -> str:
    if not pointer:
        return ""
    base_off = virtual_offset(pointer, system_data)
    name_pointer = u64(system_data, base_off + 0x28)
    return try_read_c_string(name_pointer, system_data)


def parse_material(
    system_data: bytes,
    shader_pointer: int,
    index: int,
    shader_library: ShaderLibrary | None,
    *,
    virtual_offset: Callable[[int, bytes], int],
    u32: Callable[[bytes, int], int],
    u64: Callable[[bytes, int], int],
    resolve_name: Callable[[int], str | None],
    hash_name: Callable[[str | None], int],
    decode_parameter_value: Callable[..., object | None],
    try_read_c_string: Callable[[int, bytes], str],
) -> YdrMaterial:
    shader_off = virtual_offset(shader_pointer, system_data)
    parameters_pointer = u64(system_data, shader_off + 0x00)
    shader_name_hash = u32(system_data, shader_off + 0x08)
    parameter_count = system_data[shader_off + 0x10]
    render_bucket = system_data[shader_off + 0x11]
    shader_file_hash = u32(system_data, shader_off + 0x18)

    shader_definition = None
    if shader_library is not None:
        shader_definition = shader_library.resolve_shader(
            shader_name_hash=shader_name_hash,
            shader_file_hash=shader_file_hash,
            render_bucket=render_bucket,
        )

    textures: list[YdrTextureRef] = []
    parameters: list[YdrMaterialParameterRef] = []
    if parameters_pointer and parameter_count:
        params_off = virtual_offset(parameters_pointer, system_data)
        inline_size = 0
        params: list[tuple[int, int]] = []
        for param_index in range(parameter_count):
            entry_off = params_off + (param_index * 16)
            data_type = system_data[entry_off]
            data_pointer = u64(system_data, entry_off + 0x08)
            params.append((data_type, data_pointer))
            if data_type == 1:
                inline_size += 16
            elif data_type > 1:
                inline_size += 16 * int(data_type)
        hashes_off = params_off + (parameter_count * 16) + inline_size
        if hashes_off + (parameter_count * 4) <= len(system_data):
            parameter_hashes = list(struct.unpack_from(f"<{parameter_count}I", system_data, hashes_off))
        else:
            parameter_hashes = [0] * parameter_count

        for param_index, (data_type, data_pointer) in enumerate(params):
            parameter_hash = parameter_hashes[param_index] if param_index < len(parameter_hashes) else 0
            parameter_definition = shader_definition.get_parameter(parameter_hash) if shader_definition is not None else None
            parameter_name = resolve_name(parameter_hash)
            if parameter_name is None and parameter_definition is not None:
                parameter_name = parameter_definition.name
            if parameter_name is None:
                parameter_name = f"hash_{parameter_hash:08X}" if parameter_hash else f"param_{param_index}"

            texture_ref = None
            numeric_value = None
            if data_type == 0 and data_pointer:
                texture_name = parse_texture_base(
                    system_data,
                    data_pointer,
                    virtual_offset=virtual_offset,
                    u64=u64,
                    try_read_c_string=try_read_c_string,
                )
                if texture_name:
                    texture_ref = YdrTextureRef(
                        name=texture_name,
                        parameter_hash=parameter_hash,
                        parameter_name=parameter_name,
                        name_hash=hash_name(texture_name),
                        uv_index=parameter_definition.uv_index if parameter_definition is not None else None,
                        parameter_type=parameter_definition.type_name if parameter_definition is not None else None,
                        hidden=parameter_definition.hidden if parameter_definition is not None else False,
                    )
                    textures.append(texture_ref)
            else:
                numeric_value = decode_parameter_value(
                    data_type,
                    data_pointer,
                    system_data,
                    type_name=parameter_definition.type_name if parameter_definition is not None else None,
                )

            parameters.append(
                YdrMaterialParameterRef(
                    name=parameter_name,
                    name_hash=parameter_hash,
                    type_name=parameter_definition.type_name if parameter_definition is not None else None,
                    subtype=parameter_definition.subtype if parameter_definition is not None else None,
                    uv_index=parameter_definition.uv_index if parameter_definition is not None else None,
                    count=parameter_definition.count if parameter_definition is not None else 1,
                    hidden=parameter_definition.hidden if parameter_definition is not None else False,
                    defaults=dict(parameter_definition.defaults) if parameter_definition is not None else {},
                    data_type=int(data_type),
                    texture=texture_ref,
                    value=numeric_value,
                )
            )

    shader_name = resolve_name(shader_name_hash)
    if shader_name is None and shader_definition is not None:
        shader_name = shader_definition.name
    shader_file_name = resolve_name(shader_file_hash)
    if shader_file_name is None and shader_definition is not None:
        shader_file_name = shader_definition.pick_file_name(render_bucket)

    return YdrMaterial(
        index=index,
        name=f"material_{index}",
        shader_name_hash=shader_name_hash,
        shader_name=shader_name,
        shader_file_hash=shader_file_hash,
        shader_file_name=shader_file_name,
        render_bucket=render_bucket,
        textures=textures,
        parameters=parameters,
        shader_definition=shader_definition,
    )


def parse_materials(
    system_data: bytes,
    shader_library: ShaderLibrary | None,
    *,
    root_offset: int,
    virtual_offset: Callable[[int, bytes], int],
    u16: Callable[[bytes, int], int],
    u32: Callable[[bytes, int], int],
    u64: Callable[[bytes, int], int],
    read_pointer_array: Callable[[int, int, bytes], list[int]],
    resolve_name: Callable[[int], str | None],
    hash_name: Callable[[str | None], int],
    decode_parameter_value: Callable[..., object | None],
    try_read_c_string: Callable[[int, bytes], str],
) -> tuple[list[YdrMaterial], int | None]:
    shader_group_pointer = u64(system_data, root_offset + 0x00)
    if not shader_group_pointer:
        return [], None
    shader_group_off = virtual_offset(shader_group_pointer, system_data)
    texture_dictionary_pointer = u64(system_data, shader_group_off + 0x08)
    shaders_pointer = u64(system_data, shader_group_off + 0x10)
    shader_count = u16(system_data, shader_group_off + 0x18)
    shader_pointers = read_pointer_array(shaders_pointer, shader_count, system_data)
    materials = [
        parse_material(
            system_data,
            pointer,
            index,
            shader_library,
            virtual_offset=virtual_offset,
            u32=u32,
            u64=u64,
            resolve_name=resolve_name,
            hash_name=hash_name,
            decode_parameter_value=decode_parameter_value,
            try_read_c_string=try_read_c_string,
        )
        for index, pointer in enumerate(shader_pointers)
    ]
    return materials, (texture_dictionary_pointer or None)
