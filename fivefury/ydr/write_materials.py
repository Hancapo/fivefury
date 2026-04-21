from __future__ import annotations

import struct
from typing import Callable, Sequence

from ..binary import align
from ..hashing import jenk_hash
from .gen9 import (
    ShaderGen9Library,
    ShaderGen9ParameterDefinition,
    ShaderParamTypeG9,
    _G9_PARAM_MULTIPLIER,
    _G9_SHADER_PRESET_META,
    _G9_TEXTURE_BLOCK_UNKNOWN_44,
    _G9_TEXTURE_DIMENSION_2D,
    _G9_TEXTURE_FLAGS,
    _G9_TEXTURE_TILE_AUTO,
    _G9_TEXTURE_USAGE_COUNT,
    build_shader_param_infos_g9,
)


def normalize_parameter_key(value: str) -> str:
    return str(value).strip().lower()


def _coerce_parameter_vector(value: float | tuple[float, ...] | int) -> tuple[float, float, float, float]:
    if isinstance(value, (int, float)):
        components = [float(value), 0.0, 0.0, 0.0]
    else:
        components = [float(component) for component in value]
        if not components or len(components) > 4:
            raise ValueError('Shader parameter tuples must have between 1 and 4 components')
        while len(components) < 4:
            components.append(0.0)
    return (components[0], components[1], components[2], components[3])


def coerce_parameter_inline(
    value: float | tuple[float, ...] | tuple[tuple[float, ...], ...] | int | str,
    *,
    expected_count: int = 1,
) -> tuple[int, bytes]:
    if isinstance(value, str):
        raise ValueError('String shader parameters are not supported by the YDR builder yet')
    if isinstance(value, tuple) and value and isinstance(value[0], tuple):
        vectors = [_coerce_parameter_vector(item) for item in value]
    else:
        vectors = [_coerce_parameter_vector(value)]
    if expected_count > 1 and len(vectors) != expected_count:
        raise ValueError(f'Shader parameter expects {expected_count} float4 values, got {len(vectors)}')
    if expected_count <= 1 and len(vectors) > 1:
        raise ValueError('Shader parameter does not accept an array value')
    return len(vectors), b''.join(struct.pack('<4f', *vector) for vector in vectors)


def _coerce_gen9_cbuffer_bytes(
    value: float | tuple[float, ...] | tuple[tuple[float, ...], ...] | int | str,
    *,
    parameter: ShaderGen9ParameterDefinition,
) -> bytes:
    length = int(parameter.param_length or 0)
    if length <= 0:
        return b''
    if isinstance(value, str):
        raise ValueError(f"String Gen9 shader parameter '{parameter.name}' is not supported")
    if isinstance(value, tuple) and value and isinstance(value[0], tuple):
        vectors = [_coerce_parameter_vector(item) for item in value]
        expected_vectors = max(1, length // 16)
        if len(vectors) != expected_vectors:
            raise ValueError(
                f"Gen9 shader parameter '{parameter.name}' expects {expected_vectors} float4 values, got {len(vectors)}"
            )
        payload = b''.join(struct.pack('<4f', *vector) for vector in vectors)
        if len(payload) != length:
            payload = payload[:length].ljust(length, b'\x00')
        return payload
    vector = _coerce_parameter_vector(value)
    return struct.pack('<4f', *vector)[:length].ljust(length, b'\x00')


def merge_shader_parameter_defaults(
    parameters: dict[str, float | tuple[float, ...] | tuple[tuple[float, ...], ...] | int | str],
    shader_definition,
) -> dict[str, float | tuple[float, ...] | tuple[tuple[float, ...], ...] | int | str]:
    merged: dict[str, float | tuple[float, ...] | tuple[tuple[float, ...], ...] | int | str] = {}
    for definition in shader_definition.parameters:
        if definition.is_texture or definition.default_value is None:
            continue
        merged[definition.name] = definition.default_value
    for name, value in parameters.items():
        merged[str(name)] = value
    return merged


def _resolve_legacy_shader_for_gen9(material, shader_library, resolve_shader: Callable, gen9_definition) -> tuple[object, str, int]:
    candidates = [gen9_definition.file_name, gen9_definition.name, str(material.shader)]
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            shader_definition, shader_file_name, resolved_render_bucket = resolve_shader(
                candidate,
                int(material.render_bucket),
                shader_library,
            )
            return shader_definition, shader_file_name, resolved_render_bucket
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError(f"Unable to resolve legacy shader layout for Gen9 shader '{gen9_definition.name}'")


def _normalize_gen9_textures(gen9_definition, normalized_textures) -> dict[str, object]:
    textures: dict[str, object] = {}
    for slot_name, texture in normalized_textures.items():
        parameter = next(
            (
                candidate
                for candidate in gen9_definition.texture_parameters
                if any(name.lower() == str(slot_name).lower() for name in candidate.candidate_names)
            ),
            None,
        )
        if parameter is None:
            parameter = gen9_definition.require_parameter(slot_name)
        if parameter.kind_enum is not ShaderParamTypeG9.TEXTURE:
            raise ValueError(
                f"Material texture slot '{slot_name}' does not map to a texture parameter in Gen9 shader '{gen9_definition.file_name}'"
            )
        textures[parameter.name] = texture
    return textures


def _merge_gen9_defaults(shader_definition, gen9_definition, parameters) -> dict[str, object]:
    merged: dict[str, object] = {}
    for definition in shader_definition.parameters:
        if definition.is_texture or definition.default_value is None:
            continue
        gen9_parameter = gen9_definition.get_parameter(definition.name)
        if gen9_parameter is None or gen9_parameter.kind_enum is not ShaderParamTypeG9.CBUFFER:
            continue
        merged[gen9_parameter.name] = definition.default_value
    for name, value in parameters.items():
        merged[str(name)] = value
    return merged


def _normalize_gen9_parameters(gen9_definition, parameters: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for raw_name, value in parameters.items():
        parameter = gen9_definition.require_parameter(raw_name)
        if parameter.kind_enum is ShaderParamTypeG9.TEXTURE:
            raise ValueError(
                f"Gen9 texture parameter '{raw_name}' must be bound through textures=, not parameters="
            )
        normalized[parameter.name] = value
    return normalized


def prepare_materials(
    materials,
    shader_library,
    *,
    prepared_material_cls,
    normalize_material_textures: Callable,
    resolve_shader: Callable,
    enhanced: bool = False,
    gen9_library: ShaderGen9Library | None = None,
) -> tuple[list[object], dict[str, int]]:
    prepared: list[object] = []
    index_by_name: dict[str, int] = {}
    for index, material in enumerate(materials):
        key = material.name.lower()
        if key in index_by_name:
            raise ValueError(f"Duplicate YDR material name '{material.name}'")

        if enhanced:
            if gen9_library is None:
                raise ValueError('Gen9 YDR writing requires a Gen9 shader library')
            gen9_definition = gen9_library.require_shader(material.shader)
            shader_definition, _legacy_shader_file_name, resolved_render_bucket = _resolve_legacy_shader_for_gen9(
                material,
                shader_library,
                resolve_shader,
                gen9_definition,
            )
            normalized_textures = _normalize_gen9_textures(gen9_definition, normalize_material_textures(material.textures))
            normalized_parameters = _normalize_gen9_parameters(
                gen9_definition,
                _merge_gen9_defaults(
                    shader_definition,
                    gen9_definition,
                    {str(name): value for name, value in material.parameters.items()},
                ),
            )
            prepared.append(
                prepared_material_cls(
                    index=index,
                    name=material.name,
                    shader_definition=shader_definition,
                    shader_file_name=gen9_definition.file_name,
                    render_bucket=int(resolved_render_bucket),
                    textures=normalized_textures,
                    parameters=normalized_parameters,
                    gen9_definition=gen9_definition,
                )
            )
            index_by_name[key] = index
            continue

        shader_definition, shader_file_name, resolved_render_bucket = resolve_shader(material.shader, int(material.render_bucket), shader_library)
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
                render_bucket=int(resolved_render_bucket),
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
            system.pack_into('I', texture_base_off + 0x00, texture_base_vft)
            system.pack_into('I', texture_base_off + 0x04, 1)
            system.pack_into('Q', texture_base_off + 0x28, virtual(texture_name_off))
            system.pack_into('H', texture_base_off + 0x30, 1)
            system.pack_into('H', texture_base_off + 0x32, 2)
            entries.append(shader_parameter_entry_cls(definition=definition, data_type=0, data_pointer=virtual(texture_base_off)))
            continue
        if key not in numeric_params:
            continue
        data_type, inline_data = coerce_parameter_inline(numeric_params[key], expected_count=int(definition.count))
        entries.append(shader_parameter_entry_cls(definition=definition, data_type=data_type, inline_data=inline_data))
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
    parameter_block_base_size = 32 + parameter_size + (parameter_count * 4)
    parameter_data_size = align(parameter_block_base_size, 16)
    parameter_block_size = parameter_block_base_size + (parameter_data_size * 4)
    params_off = system.alloc(parameter_block_size, 16)

    inline_off = params_off + (parameter_count * 16)
    for index, entry in enumerate(entries):
        entry_off = params_off + (index * 16)
        system.data[entry_off] = entry.data_type & 0xFF
        if entry.data_type == 0:
            system.pack_into('Q', entry_off + 0x08, entry.data_pointer)
        else:
            system.write(inline_off, entry.inline_data)
            system.pack_into('Q', entry_off + 0x08, virtual(inline_off))
            inline_off += len(entry.inline_data)

    hashes_off = params_off + parameter_size
    for index, entry in enumerate(entries):
        system.pack_into('I', hashes_off + (index * 4), entry.definition.name_hash)

    texture_count = sum(1 for entry in entries if entry.data_type == 0)
    return virtual(params_off), parameter_count, parameter_size, parameter_data_size, texture_count


def _write_gen9_texture_base(system, texture_name: str, *, virtual: Callable[[int], int]) -> int:
    name_off = system.c_string(texture_name)
    texture_base_off = system.alloc(0x50, 16)
    system.pack_into('I', texture_base_off + 0x00, 0)
    system.pack_into('I', texture_base_off + 0x04, 1)
    system.pack_into('I', texture_base_off + 0x10, _G9_TEXTURE_FLAGS)
    system.data[texture_base_off + 0x1E] = _G9_TEXTURE_DIMENSION_2D & 0xFF
    system.data[texture_base_off + 0x20] = _G9_TEXTURE_TILE_AUTO & 0xFF
    system.pack_into('Q', texture_base_off + 0x28, virtual(name_off))
    system.pack_into('H', texture_base_off + 0x30, _G9_TEXTURE_USAGE_COUNT)
    system.pack_into('I', texture_base_off + 0x44, _G9_TEXTURE_BLOCK_UNKNOWN_44)
    return texture_base_off


def _build_gen9_parameter_data(system, material, *, virtual: Callable[[int], int]) -> tuple[int, int, int, int]:
    shader = material.gen9_definition
    if shader is None:
        raise ValueError('Gen9 parameter data requires material.gen9_definition')

    multiplier = _G9_PARAM_MULTIPLIER
    texture_ptrs: list[int] = [0] * max(0, int(shader.texture_count))
    for parameter in shader.texture_parameters:
        texture_input = material.textures.get(parameter.name)
        if texture_input is None:
            continue
        texture_base_off = _write_gen9_texture_base(system, texture_input.name, virtual=virtual)
        texture_ptrs[int(parameter.index)] = virtual(texture_base_off)

    buffer_contents = [bytearray(int(size)) for size in shader.buffer_sizes]
    for parameter in shader.cbuffer_parameters:
        if parameter.name not in material.parameters:
            continue
        buffer_index = int(parameter.buffer_index or 0)
        if buffer_index >= len(buffer_contents):
            raise ValueError(
                f"Gen9 shader '{shader.name}' expects cbuffer index {buffer_index} for parameter '{parameter.name}', but only {len(buffer_contents)} buffers are declared"
            )
        payload = _coerce_gen9_cbuffer_bytes(material.parameters[parameter.name], parameter=parameter)
        start = int(parameter.param_offset or 0)
        end = start + len(payload)
        if end > len(buffer_contents[buffer_index]):
            raise ValueError(
                f"Gen9 shader parameter '{parameter.name}' overflows cbuffer {buffer_index} ({end} > {len(buffer_contents[buffer_index])})"
            )
        buffer_contents[buffer_index][start:end] = payload

    ptrs_length = len(buffer_contents) * 8 * multiplier
    single_buffers_size = sum(len(content) for content in buffer_contents)
    buffers_length = single_buffers_size * multiplier
    textures_length = len(texture_ptrs) * 8 * multiplier
    unknowns_length = int(shader.unknown_count) * 8 * multiplier
    samplers_length = int(shader.sampler_count)
    total_length = ptrs_length + buffers_length + textures_length + unknowns_length + samplers_length
    params_off = system.alloc(total_length, 16)

    single_buffer_offsets: list[int] = []
    cursor = params_off + ptrs_length
    for content in buffer_contents:
        single_buffer_offsets.append(cursor)
        cursor += len(content)

    for copy_index in range(multiplier):
        ptr_base = params_off + (copy_index * len(buffer_contents) * 8)
        buffer_base = params_off + ptrs_length + (copy_index * single_buffers_size)
        running = buffer_base
        for buffer_index, content in enumerate(buffer_contents):
            system.pack_into('Q', ptr_base + (buffer_index * 8), virtual(running))
            system.write(running, bytes(content))
            running += len(content)

    textures_base = params_off + ptrs_length + buffers_length
    for copy_index in range(multiplier):
        copy_off = textures_base + (copy_index * len(texture_ptrs) * 8)
        for texture_index, pointer in enumerate(texture_ptrs):
            system.pack_into('Q', copy_off + (texture_index * 8), int(pointer))

    samplers = [0] * int(shader.sampler_count)
    for parameter in shader.sampler_parameters:
        sampler_index = int(parameter.index)
        if sampler_index >= len(samplers):
            continue
        samplers[sampler_index] = int(parameter.sampler_value or 0) & 0xFF
    samplers_off = textures_base + textures_length + unknowns_length
    if samplers:
        system.write(samplers_off, bytes(samplers))

    return params_off, total_length, textures_base - params_off, textures_base + textures_length - params_off


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
        system.pack_into('Q', shader_group_off + 0x10, virtual(shader_ptrs_off))
        system.pack_into('H', shader_group_off + 0x18, len(materials))
        system.pack_into('H', shader_group_off + 0x1A, len(materials))
    system.pack_into('I', shader_group_off + 0x00, shader_group_vft)
    system.pack_into('I', shader_group_off + 0x04, 1)
    system.pack_into('I', shader_group_off + 0x30, 4)

    for material in materials:
        shader_off = system.alloc(0x30, 16)
        if shader_ptrs_off:
            system.pack_into('Q', shader_ptrs_off + (material.index * 8), virtual(shader_off))
        params_pointer, parameter_count, parameter_size, parameter_data_size, texture_param_count = write_shader_parameters_block(
            system,
            material,
            shader_parameter_entry_cls=shader_parameter_entry_cls,
            texture_base_vft=texture_base_vft,
            virtual=virtual,
        )
        system.pack_into('Q', shader_off + 0x00, params_pointer)
        system.pack_into('I', shader_off + 0x08, material.shader_definition.name_hash)
        system.pack_into('I', shader_off + 0x0C, 0)
        system.data[shader_off + 0x10] = parameter_count & 0xFF
        system.data[shader_off + 0x11] = material.render_bucket & 0xFF
        system.pack_into('H', shader_off + 0x12, 0x8000)
        system.pack_into('H', shader_off + 0x14, parameter_size)
        system.pack_into('H', shader_off + 0x16, parameter_data_size)
        system.pack_into('I', shader_off + 0x18, int(jenk_hash(material.shader_file_name)))
        system.pack_into('I', shader_off + 0x1C, 0)
        system.pack_into('I', shader_off + 0x20, ((1 << material.render_bucket) | 0xFF00) & 0xFFFFFFFF)
        system.pack_into('H', shader_off + 0x24, 0)
        system.data[shader_off + 0x26] = 0
        system.data[shader_off + 0x27] = texture_param_count & 0xFF
    return shader_group_off, 4


def write_shader_blocks_gen9(
    system,
    materials: Sequence[object],
    *,
    shader_group_vft: int,
    virtual: Callable[[int], int],
) -> tuple[int, int]:
    shader_group_off = system.alloc(0x40, 16)
    shader_ptrs_off = system.alloc(len(materials) * 8, 8) if materials else 0
    if materials:
        system.pack_into('Q', shader_group_off + 0x10, virtual(shader_ptrs_off))
        system.pack_into('H', shader_group_off + 0x18, len(materials))
        system.pack_into('H', shader_group_off + 0x1A, len(materials))
    system.pack_into('I', shader_group_off + 0x00, shader_group_vft)
    system.pack_into('I', shader_group_off + 0x04, 1)
    system.pack_into('I', shader_group_off + 0x30, 4)

    for material in materials:
        shader = material.gen9_definition
        if shader is None:
            raise ValueError(f"Material '{material.name}' is missing Gen9 shader metadata")
        param_infos_off = system.alloc(8 + (len(shader.parameters) * 8), 16)
        system.write(param_infos_off, build_shader_param_infos_g9(shader))
        params_off, parameter_data_size, textures_offset, unknowns_offset = _build_gen9_parameter_data(
            system,
            material,
            virtual=virtual,
        )
        shader_off = system.alloc(0x40, 16)
        if shader_ptrs_off:
            system.pack_into('Q', shader_ptrs_off + (material.index * 8), virtual(shader_off))
        system.pack_into('I', shader_off + 0x00, shader.name_hash)
        system.pack_into('I', shader_off + 0x04, _G9_SHADER_PRESET_META)
        system.pack_into('Q', shader_off + 0x08, virtual(params_off))
        system.pack_into('Q', shader_off + 0x10, virtual(params_off + textures_offset) if shader.texture_count else 0)
        system.pack_into('Q', shader_off + 0x18, virtual(params_off + unknowns_offset) if shader.unknown_count else 0)
        system.pack_into('Q', shader_off + 0x20, virtual(param_infos_off))
        system.pack_into('Q', shader_off + 0x28, 0)
        system.pack_into('Q', shader_off + 0x30, 0)
        system.data[shader_off + 0x38] = 0
        system.data[shader_off + 0x39] = material.render_bucket & 0xFF
        system.pack_into('H', shader_off + 0x3A, parameter_data_size)
        system.pack_into('I', shader_off + 0x3C, ((1 << material.render_bucket) | 0xFF00) & 0xFFFFFFFF)
    return shader_group_off, 4
