from __future__ import annotations

import struct
from pathlib import Path

from ..binary import read_c_string, u16 as _u16, u32 as _u32, u64 as _u64, f32 as _f32, vec3 as _vec3
from ..bounds import read_bound_from_pointer
from ..hashing import jenk_hash
from ..resolver import resolve_hash
from ..resource import RSC7_MAGIC, checked_virtual_offset, physical_to_offset, read_virtual_pointer_array, split_rsc7_sections, virtual_to_offset
from ..ytd import Ytd, read_embedded_texture_dictionary
from .defs import COMPONENT_SIZES, DAT_PHYSICAL_BASE, DAT_VIRTUAL_BASE, LOD_ORDER, LOD_POINTER_OFFSETS, VertexComponentType, VertexSemantic, YdrLod, YdrSkeletonBinding
from .model import Ydr, YdrMaterial, YdrMesh, YdrModel
from .read_lights import parse_lights
from .read_materials import parse_materials
from .read_joints import parse_joints
from .read_skeleton import parse_skeleton
from .shaders import ShaderLibrary, load_shader_library

_ROOT_OFFSET = 0x10


def _virtual_offset(pointer: int, data: bytes) -> int:
    return checked_virtual_offset(pointer, data, base=DAT_VIRTUAL_BASE)


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
    return read_virtual_pointer_array(system_data, pointer, count, base=DAT_VIRTUAL_BASE)


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
    max_texcoord_index = -1
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
            semantic = VertexSemantic(semantic_index)
            if semantic is VertexSemantic.BLEND_INDICES and COMPONENT_SIZES.get(component_type) == 4:
                blend_indices.append(tuple(int(component) for component in _decode_ubyte4(vertex_bytes, base + component_offset)))
                continue
            value = _decode_component(vertex_bytes, base + component_offset, component_type)
            if value is None:
                continue
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
                max_texcoord_index = max(max_texcoord_index, texcoord_index)
                texcoords[texcoord_index].append((float(value[0]), float(value[1])))

    return {
        "positions": positions,
        "normals": normals,
        "tangents": tangents,
        "texcoords": texcoords[: max_texcoord_index + 1] if max_texcoord_index >= 0 else [],
        "colours0": colours0,
        "colours1": colours1,
        "blend_weights": blend_weights,
        "blend_indices": blend_indices,
    }


def _parse_model_list(pointer: int, system_data: bytes) -> list[int]:
    if not pointer:
        return []
    header_off = _virtual_offset(pointer, system_data)
    data_pointer = _u64(system_data, header_off + 0x00)
    count = _u16(system_data, header_off + 0x08)
    return _read_pointer_array(data_pointer, count, system_data)


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
    vb_flags = _u16(system_data, vertex_buffer_off + 0x0A)
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
        vertex_buffer_flags=vb_flags,
        render_mask=render_mask,
        flags=flags,
    )


def _parse_model(system_data: bytes, graphics_data: bytes, model_pointer: int, materials: list[YdrMaterial], lod: YdrLod) -> YdrModel:
    model_off = _virtual_offset(model_pointer, system_data)
    geometries_pointer = _u64(system_data, model_off + 0x08)
    geometry_count = _u16(system_data, model_off + 0x10)
    shader_mapping_pointer = _u64(system_data, model_off + 0x20)
    skeleton_binding = YdrSkeletonBinding.from_int(_u32(system_data, model_off + 0x28))
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


def _parse_lods(system_data: bytes, graphics_data: bytes, materials: list[YdrMaterial]) -> dict[YdrLod, list[YdrModel]]:
    lods: dict[YdrLod, list[YdrModel]] = {}
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
    materials, texture_dictionary_pointer = parse_materials(
        system_data,
        active_shader_library,
        root_offset=_ROOT_OFFSET,
        virtual_offset=_virtual_offset,
        u16=_u16,
        u32=_u32,
        u64=_u64,
        read_pointer_array=_read_pointer_array,
        resolve_name=_resolve_name,
        hash_name=_hash_name,
        decode_parameter_value=_decode_parameter_value,
        try_read_c_string=_try_read_c_string,
    )
    lods = _parse_lods(system_data, graphics_data, materials)
    skeleton = parse_skeleton(
        system_data,
        _u64(system_data, _ROOT_OFFSET + 0x08),
        virtual_offset=_virtual_offset,
        u16=_u16,
        u32=_u32,
        u64=_u64,
        f32=_f32,
    )
    joints = parse_joints(
        system_data,
        _u64(system_data, _ROOT_OFFSET + 0x80),
        virtual_offset=_virtual_offset,
        u16=_u16,
        u32=_u32,
        u64=_u64,
        f32=_f32,
        vec3=_vec3,
    )
    lights = parse_lights(
        system_data,
        root_offset=_ROOT_OFFSET,
        virtual_offset=_virtual_offset,
        u16=_u16,
        u32=_u32,
        u64=_u64,
        f32=_f32,
        vec3=_vec3,
    )
    bound_pointer = _u64(system_data, _ROOT_OFFSET + 0xB8)
    try:
        bound = read_bound_from_pointer(bound_pointer, system_data) if bound_pointer else None
    except Exception:
        bound = None
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
        skeleton=skeleton,
        joints=joints,
        lights=lights,
        embedded_textures=embedded_textures,
        bound=bound,
        lod_distances={
            YdrLod.HIGH: _f32(system_data, _ROOT_OFFSET + 0x60),
            YdrLod.MEDIUM: _f32(system_data, _ROOT_OFFSET + 0x64),
            YdrLod.LOW: _f32(system_data, _ROOT_OFFSET + 0x68),
            YdrLod.VERY_LOW: _f32(system_data, _ROOT_OFFSET + 0x6C),
        },
        render_mask_flags={
            YdrLod.HIGH: _u32(system_data, _ROOT_OFFSET + 0x70),
            YdrLod.MEDIUM: _u32(system_data, _ROOT_OFFSET + 0x74),
            YdrLod.LOW: _u32(system_data, _ROOT_OFFSET + 0x78),
            YdrLod.VERY_LOW: _u32(system_data, _ROOT_OFFSET + 0x7C),
        },
        unknown_98=_u16(system_data, _ROOT_OFFSET + 0x88),
        unknown_9c=_u32(system_data, _ROOT_OFFSET + 0x8C),
    )


__all__ = [
    "read_ydr",
]
