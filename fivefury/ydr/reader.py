from __future__ import annotations

import struct
from pathlib import Path

from ..binary import read_c_string
from ..hashing import jenk_hash
from ..resolver import resolve_hash
from ..resource import RSC7_MAGIC, physical_to_offset, split_rsc7_sections, virtual_to_offset
from ..ytd import Ytd, read_embedded_texture_dictionary
from .defs import COMPONENT_SIZES, DAT_PHYSICAL_BASE, DAT_VIRTUAL_BASE, LOD_ORDER, LOD_POINTER_OFFSETS, VertexComponentType, VertexSemantic
from .model import Ydr, YdrLight, YdrLightType, YdrMaterial, YdrMaterialParameterRef, YdrMesh, YdrModel, YdrTextureRef
from .shaders import ShaderLibrary, load_shader_library

_ROOT_OFFSET = 0x10


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError("offset is out of range")
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("offset is out of range")
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 8 > len(data):
        raise ValueError("offset is out of range")
    return struct.unpack_from("<Q", data, offset)[0]


def _f32(data: bytes, offset: int) -> float:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("offset is out of range")
    return struct.unpack_from("<f", data, offset)[0]


def _vec3(data: bytes, offset: int) -> tuple[float, float, float]:
    if offset < 0 or offset + 12 > len(data):
        raise ValueError("offset is out of range")
    return struct.unpack_from("<3f", data, offset)


def _virtual_offset(pointer: int, data: bytes) -> int:
    offset = virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE)
    if offset < 0 or offset >= len(data):
        raise ValueError("virtual pointer is out of range")
    return offset


def _resolve_buffer(pointer: int, system_data: bytes, graphics_data: bytes) -> tuple[bytes, int]:
    if pointer >= DAT_PHYSICAL_BASE:
        offset = physical_to_offset(pointer, base=DAT_PHYSICAL_BASE)
        source = graphics_data
    else:
        offset = virtual_to_offset(pointer, base=DAT_VIRTUAL_BASE)
        source = system_data
    if offset < 0 or offset > len(source):
        raise ValueError("pointer is out of range")
    return source, offset


def _read_buffer(pointer: int, size: int, system_data: bytes, graphics_data: bytes) -> bytes:
    if not pointer or size <= 0:
        return b""
    source, offset = _resolve_buffer(pointer, system_data, graphics_data)
    end = offset + size
    if end > len(source):
        raise ValueError("buffer is truncated")
    return source[offset:end]


def _read_pointer_array(pointer: int, count: int, system_data: bytes) -> list[int]:
    if not pointer or count <= 0:
        return []
    array_off = _virtual_offset(pointer, system_data)
    end = array_off + (count * 8)
    if end > len(system_data):
        raise ValueError("pointer array is truncated")
    return [struct.unpack_from("<Q", system_data, array_off + (index * 8))[0] for index in range(count)]


def _read_ushort_array(pointer: int, count: int, system_data: bytes, graphics_data: bytes) -> list[int]:
    if not pointer or count <= 0:
        return []
    data = _read_buffer(pointer, count * 2, system_data, graphics_data)
    return list(struct.unpack_from(f"<{count}H", data, 0))


def _try_read_c_string(pointer: int, system_data: bytes) -> str:
    if not pointer:
        return ""
    try:
        return read_c_string(system_data, _virtual_offset(pointer, system_data))
    except Exception:
        return ""


def _hash_name(value: str | None) -> int:
    if not value:
        return 0
    return int(jenk_hash(value))


def _resolve_name(hash_value: int) -> str | None:
    if not hash_value:
        return None
    return resolve_hash(hash_value)


def _component_type(types_value: int, semantic_index: int) -> int:
    return int((int(types_value) >> (semantic_index * 4)) & 0xF)


def _component_offset(flags: int, types_value: int, semantic_index: int) -> int:
    offset = 0
    for index in range(semantic_index):
        if (flags >> index) & 0x1:
            offset += COMPONENT_SIZES.get(_component_type(types_value, index), 0)
    return offset


def _decode_half_tuple(data: bytes, offset: int, count: int) -> tuple[float, ...]:
    fmt = "<" + ("e" * count)
    size = 2 * count
    if offset < 0 or offset + size > len(data):
        raise ValueError("half tuple is truncated")
    return struct.unpack_from(fmt, data, offset)


def _decode_colour(data: bytes, offset: int) -> tuple[float, float, float, float]:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("colour is truncated")
    rgba = struct.unpack_from("<4B", data, offset)
    return tuple(channel / 255.0 for channel in rgba)


def _decode_ubyte4(data: bytes, offset: int) -> tuple[int, int, int, int]:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("ubyte4 is truncated")
    return struct.unpack_from("<4B", data, offset)


def _decode_snorm(data: bytes, offset: int) -> tuple[float, float, float, float]:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("snorm is truncated")
    values = struct.unpack_from("<4b", data, offset)
    return tuple(max(-1.0, component / 127.0) for component in values)


def _decode_component(data: bytes, offset: int, component_type: int):
    kind = VertexComponentType(component_type)
    if kind is VertexComponentType.FLOAT:
        return (struct.unpack_from("<f", data, offset)[0],)
    if kind is VertexComponentType.FLOAT2:
        return struct.unpack_from("<2f", data, offset)
    if kind is VertexComponentType.FLOAT3:
        return struct.unpack_from("<3f", data, offset)
    if kind is VertexComponentType.FLOAT4:
        return struct.unpack_from("<4f", data, offset)
    if kind is VertexComponentType.HALF2:
        return _decode_half_tuple(data, offset, 2)
    if kind is VertexComponentType.HALF4:
        return _decode_half_tuple(data, offset, 4)
    if kind is VertexComponentType.COLOUR:
        return _decode_colour(data, offset)
    if kind is VertexComponentType.UBYTE4:
        return _decode_ubyte4(data, offset)
    if kind is VertexComponentType.RGBA8_SNORM:
        return _decode_snorm(data, offset)
    return None


def _parameter_component_count(type_name: str | None) -> int:
    lowered = (type_name or "").strip().lower()
    if lowered == "float":
        return 1
    if lowered == "float2":
        return 2
    if lowered == "float3":
        return 3
    return 4


def _decode_parameter_value(data_type: int, data_pointer: int, system_data: bytes, *, type_name: str | None) -> object | None:
    if data_type <= 0 or not data_pointer:
        return None
    raw = _read_buffer(data_pointer, max(1, int(data_type)) * 16, system_data, b"")
    component_count = _parameter_component_count(type_name)
    values: list[tuple[float, ...]] = []
    for chunk_index in range(max(1, int(data_type))):
        offset = chunk_index * 16
        decoded = struct.unpack_from("<4f", raw, offset)[:component_count]
        values.append(tuple(float(component) for component in decoded))
    if len(values) == 1:
        if component_count == 1:
            return float(values[0][0])
        return values[0]
    return tuple(values)


def _decode_vertices(vertex_bytes: bytes, vertex_count: int, stride: int, flags: int, types_value: int) -> dict[str, object]:
    if stride <= 0:
        raise ValueError("vertex stride must be positive")
    available = len(vertex_bytes) // stride
    count = min(int(vertex_count), available)

    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    tangents: list[tuple[float, float, float, float]] = []
    texcoords: list[list[tuple[float, float]]] = [[] for _ in range(8)]
    colours0: list[tuple[float, float, float, float]] = []
    colours1: list[tuple[float, float, float, float]] = []
    blend_weights: list[tuple[float, float, float, float]] = []
    blend_indices: list[tuple[int, int, int, int]] = []

    for vertex_index in range(count):
        base = vertex_index * stride
        for semantic_index in range(16):
            if ((flags >> semantic_index) & 0x1) == 0:
                continue
            component_type = _component_type(types_value, semantic_index)
            component_offset = _component_offset(flags, types_value, semantic_index)
            value = _decode_component(vertex_bytes, base + component_offset, component_type)
            if value is None:
                continue
            semantic = VertexSemantic(semantic_index)
            if semantic is VertexSemantic.POSITION:
                positions.append(tuple(float(component) for component in value[:3]))
            elif semantic is VertexSemantic.NORMAL:
                normals.append(tuple(float(component) for component in value[:3]))
            elif semantic is VertexSemantic.TANGENT and len(value) >= 4:
                tangents.append(tuple(float(component) for component in value[:4]))
            elif semantic is VertexSemantic.COLOUR0:
                colours0.append(tuple(float(component) for component in value[:4]))
            elif semantic is VertexSemantic.COLOUR1:
                colours1.append(tuple(float(component) for component in value[:4]))
            elif semantic is VertexSemantic.BLEND_INDICES:
                blend_indices.append(tuple(int(component) for component in value[:4]))
            elif semantic is VertexSemantic.BLEND_WEIGHTS:
                if isinstance(value[0], int):
                    blend_weights.append(tuple(int(component) / 255.0 for component in value[:4]))
                else:
                    blend_weights.append(tuple(float(component) for component in value[:4]))
            elif VertexSemantic.TEXCOORD0 <= semantic <= VertexSemantic.TEXCOORD7:
                texcoord_index = semantic_index - int(VertexSemantic.TEXCOORD0)
                texcoords[texcoord_index].append((float(value[0]), float(value[1])))

    return {
        "positions": positions,
        "normals": normals,
        "tangents": tangents,
        "texcoords": [channel for channel in texcoords if channel],
        "colours0": colours0,
        "colours1": colours1,
        "blend_weights": blend_weights,
        "blend_indices": blend_indices,
    }


def _parse_texture_base(system_data: bytes, pointer: int) -> str:
    if not pointer:
        return ""
    base_off = _virtual_offset(pointer, system_data)
    name_pointer = _u64(system_data, base_off + 0x28)
    return _try_read_c_string(name_pointer, system_data)


def _parse_material(system_data: bytes, shader_pointer: int, index: int, shader_library: ShaderLibrary | None) -> YdrMaterial:
    shader_off = _virtual_offset(shader_pointer, system_data)
    parameters_pointer = _u64(system_data, shader_off + 0x00)
    shader_name_hash = _u32(system_data, shader_off + 0x08)
    parameter_count = system_data[shader_off + 0x10]
    render_bucket = system_data[shader_off + 0x11]
    shader_file_hash = _u32(system_data, shader_off + 0x18)

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
        params_off = _virtual_offset(parameters_pointer, system_data)
        inline_size = 0
        params: list[tuple[int, int]] = []
        for param_index in range(parameter_count):
            entry_off = params_off + (param_index * 16)
            data_type = system_data[entry_off]
            data_pointer = _u64(system_data, entry_off + 0x08)
            params.append((data_type, data_pointer))
            if data_type == 1:
                inline_size += 16
            elif data_type > 1:
                inline_size += 16 * int(data_type)
        if params_off + (parameter_count * 16) + inline_size + (parameter_count * 4) <= len(system_data):
            parameter_hashes = list(struct.unpack_from(f"<{parameter_count}I", system_data, params_off + (parameter_count * 16) + inline_size))
        else:
            parameter_hashes = [0] * parameter_count

        for param_index, (data_type, data_pointer) in enumerate(params):
            parameter_hash = parameter_hashes[param_index] if param_index < len(parameter_hashes) else 0
            parameter_definition = shader_definition.get_parameter(parameter_hash) if shader_definition is not None else None
            parameter_name = _resolve_name(parameter_hash)
            if parameter_name is None and parameter_definition is not None:
                parameter_name = parameter_definition.name
            if parameter_name is None:
                parameter_name = f"hash_{parameter_hash:08X}" if parameter_hash else f"param_{param_index}"

            texture_ref = None
            numeric_value = None
            if data_type == 0 and data_pointer:
                texture_name = _parse_texture_base(system_data, data_pointer)
                if texture_name:
                    texture_ref = YdrTextureRef(
                        name=texture_name,
                        parameter_hash=parameter_hash,
                        parameter_name=parameter_name,
                        name_hash=_hash_name(texture_name),
                        uv_index=parameter_definition.uv_index if parameter_definition is not None else None,
                        parameter_type=parameter_definition.type_name if parameter_definition is not None else None,
                        hidden=parameter_definition.hidden if parameter_definition is not None else False,
                    )
                    textures.append(texture_ref)
            else:
                numeric_value = _decode_parameter_value(
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

    shader_name = _resolve_name(shader_name_hash)
    if shader_name is None and shader_definition is not None:
        shader_name = shader_definition.name
    shader_file_name = _resolve_name(shader_file_hash)
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


def _parse_materials(system_data: bytes, shader_library: ShaderLibrary | None) -> tuple[list[YdrMaterial], int | None]:
    shader_group_pointer = _u64(system_data, _ROOT_OFFSET + 0x00)
    if not shader_group_pointer:
        return [], None
    shader_group_off = _virtual_offset(shader_group_pointer, system_data)
    texture_dictionary_pointer = _u64(system_data, shader_group_off + 0x08)
    shaders_pointer = _u64(system_data, shader_group_off + 0x10)
    shader_count = _u16(system_data, shader_group_off + 0x18)
    shader_pointers = _read_pointer_array(shaders_pointer, shader_count, system_data)
    materials = [_parse_material(system_data, pointer, index, shader_library) for index, pointer in enumerate(shader_pointers)]
    return materials, (texture_dictionary_pointer or None)


def _parse_model_list(pointer: int, system_data: bytes) -> list[int]:
    if not pointer:
        return []
    header_off = _virtual_offset(pointer, system_data)
    data_pointer = _u64(system_data, header_off + 0x00)
    count = _u16(system_data, header_off + 0x08)
    return _read_pointer_array(data_pointer, count, system_data)


def _parse_inline_simple_list(header_off: int, system_data: bytes) -> tuple[int, int]:
    data_pointer = _u64(system_data, header_off + 0x00)
    count = _u16(system_data, header_off + 0x08)
    if not data_pointer or count <= 0:
        return 0, 0
    return _virtual_offset(data_pointer, system_data), int(count)


def _parse_light(system_data: bytes, light_off: int) -> YdrLight:
    return YdrLight(
        unknown_0h=_u32(system_data, light_off + 0x00),
        unknown_4h=_u32(system_data, light_off + 0x04),
        position=_vec3(system_data, light_off + 0x08),
        unknown_14h=_u32(system_data, light_off + 0x14),
        color=struct.unpack_from("<3B", system_data, light_off + 0x18),
        flashiness=system_data[light_off + 0x1B],
        intensity=_f32(system_data, light_off + 0x1C),
        flags=_u32(system_data, light_off + 0x20),
        bone_id=_u16(system_data, light_off + 0x24),
        light_type=YdrLightType(system_data[light_off + 0x26]) if system_data[light_off + 0x26] in {1, 2, 4} else YdrLightType.POINT,
        group_id=system_data[light_off + 0x27],
        time_flags=_u32(system_data, light_off + 0x28),
        falloff=_f32(system_data, light_off + 0x2C),
        falloff_exponent=_f32(system_data, light_off + 0x30),
        culling_plane_normal=_vec3(system_data, light_off + 0x34),
        culling_plane_offset=_f32(system_data, light_off + 0x40),
        shadow_blur=system_data[light_off + 0x44],
        unknown_45h=system_data[light_off + 0x45],
        unknown_46h=_u16(system_data, light_off + 0x46),
        unknown_48h=_u32(system_data, light_off + 0x48),
        volume_intensity=_f32(system_data, light_off + 0x4C),
        volume_size_scale=_f32(system_data, light_off + 0x50),
        volume_outer_color=struct.unpack_from("<3B", system_data, light_off + 0x54),
        light_hash=system_data[light_off + 0x57],
        volume_outer_intensity=_f32(system_data, light_off + 0x58),
        corona_size=_f32(system_data, light_off + 0x5C),
        volume_outer_exponent=_f32(system_data, light_off + 0x60),
        light_fade_distance=system_data[light_off + 0x64],
        shadow_fade_distance=system_data[light_off + 0x65],
        specular_fade_distance=system_data[light_off + 0x66],
        volumetric_fade_distance=system_data[light_off + 0x67],
        shadow_near_clip=_f32(system_data, light_off + 0x68),
        corona_intensity=_f32(system_data, light_off + 0x6C),
        corona_z_bias=_f32(system_data, light_off + 0x70),
        direction=_vec3(system_data, light_off + 0x74),
        tangent=_vec3(system_data, light_off + 0x80),
        cone_inner_angle=_f32(system_data, light_off + 0x8C),
        cone_outer_angle=_f32(system_data, light_off + 0x90),
        extent=_vec3(system_data, light_off + 0x94),
        projected_texture_hash=_u32(system_data, light_off + 0xA0),
        unknown_a4h=_u32(system_data, light_off + 0xA4),
    )


def _parse_lights(system_data: bytes) -> list[YdrLight]:
    lights_off, light_count = _parse_inline_simple_list(_ROOT_OFFSET + 0xA0, system_data)
    if not lights_off or light_count <= 0:
        return []
    light_stride = 0xA8
    end = lights_off + (light_count * light_stride)
    if end > len(system_data):
        raise ValueError("light list is truncated")
    return [_parse_light(system_data, lights_off + (index * light_stride)) for index in range(light_count)]


def _parse_mesh(system_data: bytes, graphics_data: bytes, geometry_pointer: int, material: YdrMaterial | None, material_index: int, render_mask: int, flags: int) -> YdrMesh:
    geometry_off = _virtual_offset(geometry_pointer, system_data)
    vertex_buffer_pointer = _u64(system_data, geometry_off + 0x18)
    index_buffer_pointer = _u64(system_data, geometry_off + 0x38)
    indices_count = _u32(system_data, geometry_off + 0x58)
    vertices_count = _u16(system_data, geometry_off + 0x60)
    bone_ids_pointer = _u64(system_data, geometry_off + 0x68)
    vertex_stride = _u16(system_data, geometry_off + 0x70)
    bone_ids_count = _u16(system_data, geometry_off + 0x72)

    vertex_buffer_off = _virtual_offset(vertex_buffer_pointer, system_data)
    vb_stride = _u16(system_data, vertex_buffer_off + 0x08)
    vertex_data_pointer = _u64(system_data, vertex_buffer_off + 0x10) or _u64(system_data, vertex_buffer_off + 0x20)
    vertex_count = _u32(system_data, vertex_buffer_off + 0x18)
    info_pointer = _u64(system_data, vertex_buffer_off + 0x30)

    declaration_off = _virtual_offset(info_pointer, system_data)
    declaration_flags = _u32(system_data, declaration_off + 0x00)
    declaration_stride = _u16(system_data, declaration_off + 0x04)
    declaration_types = _u64(system_data, declaration_off + 0x08)

    stride = int(declaration_stride or vb_stride or vertex_stride)
    count = int(vertices_count or vertex_count)
    vertex_bytes = _read_buffer(vertex_data_pointer, stride * count, system_data, graphics_data)
    decoded = _decode_vertices(vertex_bytes, count, stride, declaration_flags, declaration_types)

    index_buffer_off = _virtual_offset(index_buffer_pointer, system_data)
    indices_pointer = _u64(system_data, index_buffer_off + 0x10)
    index_bytes = _read_buffer(indices_pointer, int(indices_count) * 2, system_data, graphics_data)
    indices = list(struct.unpack_from(f"<{indices_count}H", index_bytes, 0)) if indices_count else []
    bone_ids = _read_ushort_array(bone_ids_pointer, bone_ids_count, system_data, graphics_data)

    return YdrMesh(
        material_index=material_index,
        material=material,
        indices=indices,
        positions=list(decoded["positions"]),
        normals=list(decoded["normals"]),
        tangents=list(decoded["tangents"]),
        texcoords=list(decoded["texcoords"]),
        colours0=list(decoded["colours0"]),
        colours1=list(decoded["colours1"]),
        blend_weights=list(decoded["blend_weights"]),
        blend_indices=list(decoded["blend_indices"]),
        bone_ids=bone_ids,
        vertex_stride=stride,
        declaration_flags=declaration_flags,
        declaration_types=declaration_types,
        render_mask=render_mask,
        flags=flags,
    )


def _parse_model(system_data: bytes, graphics_data: bytes, model_pointer: int, materials: list[YdrMaterial], lod: str) -> YdrModel:
    model_off = _virtual_offset(model_pointer, system_data)
    geometries_pointer = _u64(system_data, model_off + 0x08)
    geometry_count = _u16(system_data, model_off + 0x10)
    shader_mapping_pointer = _u64(system_data, model_off + 0x20)
    skeleton_binding = _u32(system_data, model_off + 0x28)
    render_mask_flags = _u16(system_data, model_off + 0x2C)

    geometry_pointers = _read_pointer_array(geometries_pointer, geometry_count, system_data)
    shader_mapping = _read_ushort_array(shader_mapping_pointer, geometry_count, system_data, b"")

    render_mask = render_mask_flags & 0xFF
    flags = (render_mask_flags >> 8) & 0xFF
    meshes: list[YdrMesh] = []
    for geometry_index, geometry_pointer in enumerate(geometry_pointers):
        material_index = shader_mapping[geometry_index] if geometry_index < len(shader_mapping) else -1
        material = materials[material_index] if 0 <= material_index < len(materials) else None
        meshes.append(_parse_mesh(system_data, graphics_data, geometry_pointer, material, material_index, render_mask, flags))

    return YdrModel(
        index=0,
        lod=lod,
        meshes=meshes,
        render_mask=render_mask,
        flags=flags,
        skeleton_binding=skeleton_binding,
    )


def _parse_lods(system_data: bytes, graphics_data: bytes, materials: list[YdrMaterial]) -> dict[str, list[YdrModel]]:
    lods: dict[str, list[YdrModel]] = {}
    for lod_name in LOD_ORDER:
        pointer = _u64(system_data, _ROOT_OFFSET + LOD_POINTER_OFFSETS[lod_name])
        model_pointers = _parse_model_list(pointer, system_data)
        if not model_pointers:
            continue
        lod_models = [_parse_model(system_data, graphics_data, model_pointer, materials, lod_name) for model_pointer in model_pointers]
        for model_index, model in enumerate(lod_models):
            model.index = model_index
        lods[lod_name] = lod_models
    return lods


def _parse_embedded_textures(system_data: bytes, graphics_data: bytes, version: int, texture_dictionary_pointer: int | None) -> Ytd | None:
    if not texture_dictionary_pointer:
        return None
    try:
        return read_embedded_texture_dictionary(system_data, graphics_data, version=version, pointer=texture_dictionary_pointer)
    except Exception:
        return None


def _read_source_bytes(source: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    return bytes(source)


def read_ydr(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    path: str | Path = "",
    shader_library: ShaderLibrary | None = None,
) -> Ydr:
    data = _read_source_bytes(source)
    if len(data) < 16:
        raise ValueError("YDR data is too short")
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic != RSC7_MAGIC:
        raise ValueError("YDR data must be a standalone RSC7 resource")

    header, system_data, graphics_data = split_rsc7_sections(data)
    active_shader_library = shader_library if shader_library is not None else load_shader_library()
    materials, texture_dictionary_pointer = _parse_materials(system_data, active_shader_library)
    lods = _parse_lods(system_data, graphics_data, materials)
    lights = _parse_lights(system_data)
    embedded_textures = _parse_embedded_textures(system_data, graphics_data, int(header.version), texture_dictionary_pointer)

    return Ydr(
        version=int(header.version),
        path=str(path or source) if isinstance(source, (str, Path)) or path else "",
        materials=materials,
        lods=lods,
        bounding_center=_vec3(system_data, _ROOT_OFFSET + 0x10),
        bounding_sphere_radius=_f32(system_data, _ROOT_OFFSET + 0x1C),
        bounding_box_min=_vec3(system_data, _ROOT_OFFSET + 0x20),
        bounding_box_max=_vec3(system_data, _ROOT_OFFSET + 0x30),
        lights=lights,
        embedded_textures=embedded_textures,
    )


__all__ = [
    "read_ydr",
]
