from __future__ import annotations

import struct
from typing import Callable

from .gen9 import ShaderGen9Library, ShaderParamTypeG9
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
        return ''
    base_off = virtual_offset(pointer, system_data)
    name_pointer = u64(system_data, base_off + 0x28)
    return try_read_c_string(name_pointer, system_data)


def _parameter_component_count(type_name: str | None) -> int:
    lowered = (type_name or '').strip().lower()
    if lowered == 'float':
        return 1
    if lowered == 'float2':
        return 2
    if lowered == 'float3':
        return 3
    return 4


def _decode_numeric_parameter(raw: bytes, *, type_name: str | None) -> object | None:
    if not raw:
        return None
    component_count = _parameter_component_count(type_name)
    if len(raw) <= 16:
        padded = raw.ljust(16, b'\x00')
        values = struct.unpack_from('<4f', padded, 0)[:component_count]
        if component_count == 1:
            return float(values[0])
        return tuple(float(component) for component in values)
    if len(raw) % 16 != 0:
        raise ValueError('Gen9 cbuffer parameter payload is misaligned')
    rows = []
    for offset in range(0, len(raw), 16):
        values = struct.unpack_from('<4f', raw, offset)
        rows.append(tuple(float(component) for component in values))
    return tuple(rows)


def _parse_gen9_param_info(data_value: int) -> tuple[int, int, int, int]:
    kind = int(data_value & 0x3)
    index = int((data_value >> 2) & 0xFF)
    param_offset = int((data_value >> 8) & 0xFFF)
    param_length = int((data_value >> 20) & 0xFFF)
    return kind, index, param_offset, param_length


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
            parameter_hashes = list(struct.unpack_from(f'<{parameter_count}I', system_data, hashes_off))
        else:
            parameter_hashes = [0] * parameter_count

        for param_index, (data_type, data_pointer) in enumerate(params):
            parameter_hash = parameter_hashes[param_index] if param_index < len(parameter_hashes) else 0
            parameter_definition = shader_definition.get_parameter(parameter_hash) if shader_definition is not None else None
            parameter_name = resolve_name(parameter_hash)
            if parameter_name is None and parameter_definition is not None:
                parameter_name = parameter_definition.name
            if parameter_name is None:
                parameter_name = f'hash_{parameter_hash:08X}' if parameter_hash else f'param_{param_index}'

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
        name=f'material_{index}',
        shader_name_hash=shader_name_hash,
        shader_name=shader_name,
        shader_file_hash=shader_file_hash,
        shader_file_name=shader_file_name,
        render_bucket=render_bucket,
        textures=textures,
        parameters=parameters,
        shader_definition=shader_definition,
    )


def parse_material_gen9(
    system_data: bytes,
    shader_pointer: int,
    index: int,
    shader_library: ShaderLibrary | None,
    gen9_library: ShaderGen9Library | None,
    *,
    virtual_offset: Callable[[int, bytes], int],
    u32: Callable[[bytes, int], int],
    u64: Callable[[bytes, int], int],
    resolve_name: Callable[[int], str | None],
    hash_name: Callable[[str | None], int],
    try_read_c_string: Callable[[int, bytes], str],
) -> YdrMaterial:
    shader_off = virtual_offset(shader_pointer, system_data)
    shader_name_hash = u32(system_data, shader_off + 0x00)
    parameters_pointer = u64(system_data, shader_off + 0x08)
    texture_refs_pointer = u64(system_data, shader_off + 0x10)
    param_infos_pointer = u64(system_data, shader_off + 0x20)
    render_bucket = system_data[shader_off + 0x39]
    parameter_data_size = int.from_bytes(system_data[shader_off + 0x3A : shader_off + 0x3C], 'little')

    gen9_definition = gen9_library.get_shader(shader_name_hash) if gen9_library is not None else None
    shader_definition = None
    if shader_library is not None:
        if gen9_definition is not None:
            shader_definition = shader_library.resolve_shader(
                shader_name=gen9_definition.name,
                shader_file_name=gen9_definition.file_name,
                render_bucket=render_bucket,
            )
        if shader_definition is None:
            shader_definition = shader_library.resolve_shader(shader_name_hash=shader_name_hash, render_bucket=render_bucket)

    shader_name = resolve_name(shader_name_hash)
    if shader_name is None and gen9_definition is not None:
        shader_name = gen9_definition.name
    shader_file_name = gen9_definition.file_name if gen9_definition is not None else None
    shader_file_hash = hash_name(shader_file_name)

    textures: list[YdrTextureRef] = []
    parameters: list[YdrMaterialParameterRef] = []
    if parameters_pointer and param_infos_pointer and parameter_data_size > 0:
        params_off = virtual_offset(parameters_pointer, system_data)
        infos_off = virtual_offset(param_infos_pointer, system_data)
        num_buffers = system_data[infos_off + 0x00]
        num_textures = system_data[infos_off + 0x01]
        num_unknowns = system_data[infos_off + 0x02]
        num_samplers = system_data[infos_off + 0x03]
        num_params = system_data[infos_off + 0x04]
        multiplier = max(1, system_data[infos_off + 0x07])
        infos = []
        for param_index in range(num_params):
            entry_off = infos_off + 0x08 + (param_index * 8)
            parameter_hash = u32(system_data, entry_off + 0x00)
            packed = u32(system_data, entry_off + 0x04)
            infos.append((parameter_hash, *_parse_gen9_param_info(packed)))

        if gen9_definition is not None:
            buffer_sizes = [int(size) for size in gen9_definition.buffer_sizes]
        else:
            buffer_sizes = [0] * int(num_buffers)
        ptrs_length = int(num_buffers) * 8 * int(multiplier)
        if num_buffers:
            first_buffer_ptrs = list(struct.unpack_from(f'<{num_buffers}Q', system_data, params_off))
            if not any(buffer_sizes):
                single_buffers_length = max(0, virtual_offset(texture_refs_pointer, system_data) - params_off - ptrs_length) if texture_refs_pointer else 0
                running = 0
                for buffer_index in range(num_buffers):
                    if buffer_index + 1 < num_buffers:
                        next_size = int(first_buffer_ptrs[buffer_index + 1]) - int(first_buffer_ptrs[buffer_index])
                    else:
                        next_size = max(0, single_buffers_length - running)
                    buffer_sizes[buffer_index] = next_size
                    running += next_size
        else:
            first_buffer_ptrs = []
        single_buffers_length = sum(buffer_sizes)
        textures_length = int(num_textures) * 8 * int(multiplier)
        unknowns_length = int(num_unknowns) * 8 * int(multiplier)
        textures_off = params_off + ptrs_length + (single_buffers_length * int(multiplier))
        if texture_refs_pointer:
            texture_ptrs_all = list(struct.unpack_from(f'<{num_textures * multiplier}Q', system_data, virtual_offset(texture_refs_pointer, system_data))) if num_textures else []
        else:
            texture_ptrs_all = list(struct.unpack_from(f'<{num_textures * multiplier}Q', system_data, textures_off)) if num_textures else []
        texture_ptrs = texture_ptrs_all[:num_textures]
        samplers_off = textures_off + textures_length + unknowns_length
        samplers = system_data[samplers_off : samplers_off + int(num_samplers)] if num_samplers else b''

        for param_index, (parameter_hash, kind, raw_index, param_offset, param_length) in enumerate(infos):
            parameter_definition = gen9_definition.get_parameter(parameter_hash) if gen9_definition is not None else None
            parameter_name = None
            if parameter_definition is not None:
                parameter_name = parameter_definition.legacy_name or parameter_definition.name
            if parameter_name is None:
                parameter_name = resolve_name(parameter_hash)
            if parameter_name is None:
                parameter_name = f'hash_{parameter_hash:08X}' if parameter_hash else f'param_{param_index}'
            legacy_parameter_definition = shader_definition.get_parameter(parameter_name) if shader_definition is not None else None

            texture_ref = None
            value = None
            data_type = 0
            if kind == int(ShaderParamTypeG9.TEXTURE):
                pointer = texture_ptrs[raw_index] if raw_index < len(texture_ptrs) else 0
                if pointer:
                    texture_name = parse_texture_base(
                        system_data,
                        pointer,
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
                            uv_index=legacy_parameter_definition.uv_index if legacy_parameter_definition is not None else None,
                            parameter_type=legacy_parameter_definition.type_name if legacy_parameter_definition is not None else None,
                            hidden=legacy_parameter_definition.hidden if legacy_parameter_definition is not None else False,
                        )
                        textures.append(texture_ref)
            elif kind == int(ShaderParamTypeG9.CBUFFER):
                data_type = max(1, int(param_length) // 16) if int(param_length) > 16 else 1
                if raw_index < len(first_buffer_ptrs):
                    buffer_base_off = virtual_offset(first_buffer_ptrs[raw_index], system_data)
                    raw = system_data[buffer_base_off + int(param_offset) : buffer_base_off + int(param_offset) + int(param_length)]
                    value = _decode_numeric_parameter(
                        raw,
                        type_name=legacy_parameter_definition.type_name if legacy_parameter_definition is not None else None,
                    )
            elif kind == int(ShaderParamTypeG9.SAMPLER):
                data_type = 1
                value = int(samplers[raw_index]) if raw_index < len(samplers) else 0

            parameters.append(
                YdrMaterialParameterRef(
                    name=parameter_name,
                    name_hash=parameter_hash,
                    type_name=legacy_parameter_definition.type_name if legacy_parameter_definition is not None else None,
                    subtype=legacy_parameter_definition.subtype if legacy_parameter_definition is not None else None,
                    uv_index=legacy_parameter_definition.uv_index if legacy_parameter_definition is not None else None,
                    count=legacy_parameter_definition.count if legacy_parameter_definition is not None else 1,
                    hidden=legacy_parameter_definition.hidden if legacy_parameter_definition is not None else False,
                    defaults=dict(legacy_parameter_definition.defaults) if legacy_parameter_definition is not None else {},
                    data_type=data_type,
                    texture=texture_ref,
                    value=value,
                )
            )

    return YdrMaterial(
        index=index,
        name=f'material_{index}',
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
    enhanced: bool = False,
    gen9_library: ShaderGen9Library | None = None,
) -> tuple[list[YdrMaterial], int | None]:
    shader_group_pointer = u64(system_data, root_offset + 0x00)
    if not shader_group_pointer:
        return [], None
    shader_group_off = virtual_offset(shader_group_pointer, system_data)
    texture_dictionary_pointer = u64(system_data, shader_group_off + 0x08)
    shaders_pointer = u64(system_data, shader_group_off + 0x10)
    shader_count = u16(system_data, shader_group_off + 0x18)
    shader_pointers = read_pointer_array(shaders_pointer, shader_count, system_data)
    materials: list[YdrMaterial] = []
    for index, pointer in enumerate(shader_pointers):
        if enhanced:
            materials.append(
                parse_material_gen9(
                    system_data,
                    pointer,
                    index,
                    shader_library,
                    gen9_library,
                    virtual_offset=virtual_offset,
                    u32=u32,
                    u64=u64,
                    resolve_name=resolve_name,
                    hash_name=hash_name,
                    try_read_c_string=try_read_c_string,
                )
            )
        else:
            materials.append(
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
            )
    return materials, (texture_dictionary_pointer or None)
