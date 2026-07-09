from __future__ import annotations

import struct
from pathlib import Path

from ..common import ByteSource, read_source_bytes
from ..drawable import ShaderLibrary, load_shader_library, parameter_component_count
from ..resolver import resolve_hash
from .model import (
    CDR_LOD_ORDER,
    Cdr,
    CdrBone,
    CdrEdgeSegment,
    CdrGeometryType,
    CdrIndexFlavor,
    CdrJointControlPoint,
    CdrJointRotationLimit,
    CdrJointVectorLimit,
    CdrJoints,
    CdrLod,
    CdrMaterial,
    CdrMaterialParameter,
    CdrMesh,
    CdrModel,
    CdrSkinningFlavor,
    CdrSkeleton,
)
from .resource import Ps3ResourceView, split_ps3_rsc7_sections
from .shaders import (
    get_cdr_parameter_definition,
    get_cdr_shader_definition,
    resolve_cdr_shader_file_name,
)
from .vertices import decode_edge_vertices, decode_fvf_vertices, decompress_edge_indices, parse_edge_stream, parse_fvf

_ROOT_SIZE = 0x80
_LOD_POINTER_OFFSETS = dict(zip(CDR_LOD_ORDER, (0x40, 0x44, 0x48, 0x4C), strict=True))
_LOD_DISTANCE_OFFSETS = dict(zip(CDR_LOD_ORDER, (0x50, 0x54, 0x58, 0x5C), strict=True))
_LOD_BUCKET_OFFSETS = dict(zip(CDR_LOD_ORDER, (0x60, 0x64, 0x68, 0x6C), strict=True))


def _pointer_array(view: Ps3ResourceView, pointer: int, count: int) -> list[int]:
    if not pointer or count <= 0:
        return []
    offset = view.system_offset(pointer)
    if offset + count * 4 > len(view.system):
        raise ValueError("PS3 pointer array is truncated")
    return list(struct.unpack_from(f">{count}I", view.system, offset))


def _u16_array(view: Ps3ResourceView, pointer: int, count: int) -> list[int]:
    if not pointer or count <= 0:
        return []
    raw = view.bytes_at(pointer, count * 2)
    return list(struct.unpack_from(f">{count}H", raw, 0))


def _resolve_material_name(value: int, fallback: str) -> str:
    return resolve_hash(int(value)) or fallback


def _decode_numeric_value(raw: bytes, *, type_name: str | None) -> float | tuple[float, ...] | tuple[tuple[float, ...], ...]:
    if len(raw) % 16:
        raise ValueError("PS3 shader parameter is not float4 aligned")
    component_count = parameter_component_count(type_name)
    rows = [tuple(float(value) for value in struct.unpack_from(">4f", raw, offset)[:component_count]) for offset in range(0, len(raw), 16)]
    if len(rows) == 1:
        return float(rows[0][0]) if component_count == 1 else rows[0]
    return tuple(rows)


def _parse_materials(
    view: Ps3ResourceView,
    shader_library: ShaderLibrary,
) -> tuple[list[CdrMaterial], int]:
    shader_group_pointer = view.u32(0x08)
    if not shader_group_pointer:
        return [], 0
    shader_group_offset = view.system_offset(shader_group_pointer)
    texture_dictionary_pointer = view.u32(shader_group_offset + 0x04)
    shaders_pointer = view.u32(shader_group_offset + 0x08)
    shader_count = view.u16(shader_group_offset + 0x0C)
    shader_pointers = _pointer_array(view, shaders_pointer, shader_count)
    materials: list[CdrMaterial] = []

    for material_index, shader_pointer in enumerate(shader_pointers):
        shader_offset = view.system_offset(shader_pointer)
        entries_pointer = view.u32(shader_offset)
        shader_hash = view.u32(shader_offset + 0x04)
        parameter_count = view.u8(shader_offset + 0x08)
        render_bucket = view.u8(shader_offset + 0x09)
        parameter_hash_offset = view.u16(shader_offset + 0x0C)
        material_hash = view.u32(shader_offset + 0x10)
        draw_bucket_mask = view.u32(shader_offset + 0x14)
        ps3_shader_definition = get_cdr_shader_definition(shader_hash)
        shader_definition = shader_library.get_shader(shader_hash)
        shader_name = (
            ps3_shader_definition.name
            if ps3_shader_definition is not None
            else shader_definition.name
            if shader_definition is not None
            else resolve_hash(shader_hash)
        )
        shader_file_name = resolve_cdr_shader_file_name(shader_hash, material_hash, shader_library)
        entries_offset = view.system_offset(entries_pointer) if entries_pointer else 0
        hash_table_offset = entries_offset + parameter_hash_offset
        parameters: list[CdrMaterialParameter] = []

        for parameter_index in range(parameter_count):
            entry_offset = entries_offset + parameter_index * 8
            value_count = view.u8(entry_offset)
            register = view.u8(entry_offset + 1)
            sampler_state = view.u8(entry_offset + 2)
            value_pointer = view.u32(entry_offset + 4)
            name_hash = view.u32(hash_table_offset + parameter_index * 4)
            definition = ps3_shader_definition.get_parameter(name_hash) if ps3_shader_definition is not None else None
            if definition is None and shader_definition is not None:
                definition = shader_definition.get_parameter(name_hash)
            if definition is None:
                definition = get_cdr_parameter_definition(name_hash)
            name = _resolve_material_name(name_hash, definition.name if definition is not None else f"hash_{name_hash:08X}")
            texture_name: str | None = None
            value = None
            if value_count == 0:
                if value_pointer:
                    texture_offset = view.system_offset(value_pointer)
                    texture_name = view.c_string(view.u32(texture_offset + 0x20))
            elif value_pointer:
                raw = view.bytes_at(value_pointer, value_count * 16)
                value = _decode_numeric_value(raw, type_name=definition.type_name if definition is not None else None)
            parameters.append(
                CdrMaterialParameter(
                    name=name,
                    name_hash=name_hash,
                    register=register,
                    sampler_state=sampler_state,
                    value=value,
                    texture_name=texture_name or None,
                )
            )

        materials.append(
            CdrMaterial(
                index=material_index,
                name=_resolve_material_name(material_hash, f"material_{material_index}"),
                shader_hash=shader_hash,
                shader_name=shader_name,
                shader_file_name=shader_file_name,
                material_hash=material_hash,
                render_bucket=render_bucket,
                draw_bucket_mask=draw_bucket_mask,
                parameters=parameters,
            )
        )
    return materials, texture_dictionary_pointer


def _matrix4(view: Ps3ResourceView, pointer: int, index: int) -> tuple[tuple[float, float, float, float], ...] | None:
    if not pointer:
        return None
    raw = view.bytes_at(pointer + index * 0x40, 0x40)
    values = struct.unpack_from(">16f", raw, 0)
    return tuple(tuple(float(value) for value in values[row * 4 : row * 4 + 4]) for row in range(4))


def _parse_skeleton(view: Ps3ResourceView, pointer: int) -> CdrSkeleton | None:
    if not pointer:
        return None
    offset = view.system_offset(pointer)
    bones_pointer = view.u32(offset + 0x14)
    inverse_transforms_pointer = view.u32(offset + 0x18)
    default_transforms_pointer = view.u32(offset + 0x1C)
    parent_indices_pointer = view.u32(offset + 0x20)
    child_parent_indices_pointer = view.u32(offset + 0x24)
    bone_count = view.u16(offset + 0x3A)
    child_parent_count = view.u16(offset + 0x3C)
    bones_offset = view.system_offset(bones_pointer) if bones_pointer and bone_count else 0
    bones: list[CdrBone] = []
    for bone_index in range(bone_count):
        bone_offset = bones_offset + bone_index * 0x40
        rotation = struct.unpack_from(">4f", view.system, bone_offset)
        translation4 = struct.unpack_from(">4f", view.system, bone_offset + 0x10)
        scale4 = struct.unpack_from(">4f", view.system, bone_offset + 0x20)
        bones.append(
            CdrBone(
                name=view.c_string(view.u32(bone_offset + 0x34)),
                index=view.u16(bone_offset + 0x3A),
                bone_id=view.u16(bone_offset + 0x3C),
                parent_index=view.s16(bone_offset + 0x32),
                next_sibling_index=view.s16(bone_offset + 0x30),
                mirror_index=view.u16(bone_offset + 0x3E),
                flags=view.u16(bone_offset + 0x38),
                rotation=tuple(float(value) for value in rotation),
                translation=tuple(float(value) for value in translation4[:3]),
                scale=tuple(float(value) for value in scale4[:3]),
                inverse_bind_transform=_matrix4(view, inverse_transforms_pointer, bone_index),
                default_transform=_matrix4(view, default_transforms_pointer, bone_index),
            )
        )
    parent_indices = []
    if parent_indices_pointer and bone_count:
        raw = view.bytes_at(parent_indices_pointer, bone_count * 2)
        parent_indices = list(struct.unpack_from(f">{bone_count}h", raw, 0))
    child_parent_indices = _u16_array(view, child_parent_indices_pointer, child_parent_count)
    return CdrSkeleton(
        bones=bones,
        parent_indices=parent_indices,
        child_parent_indices=child_parent_indices,
        signature=view.u32(offset + 0x2C),
        signature_non_chiral=view.u32(offset + 0x30),
        signature_comprehensive=view.u32(offset + 0x34),
    )


def _parse_joint_vector_limits(view: Ps3ResourceView, pointer: int, count: int) -> list[CdrJointVectorLimit]:
    if not pointer or count <= 0:
        return []
    offset = view.system_offset(pointer)
    limits: list[CdrJointVectorLimit] = []
    for index in range(count):
        item_offset = offset + index * 0x30
        limits.append(
            CdrJointVectorLimit(
                bone_id=view.s32(item_offset + 0x04),
                min=view.vec3(item_offset + 0x10),
                max=view.vec3(item_offset + 0x20),
            )
        )
    return limits


def _parse_joints(view: Ps3ResourceView, pointer: int) -> CdrJoints | None:
    if not pointer:
        return None
    offset = view.system_offset(pointer)
    rotation_pointer = view.u32(offset + 0x08)
    translation_pointer = view.u32(offset + 0x0C)
    scale_pointer = view.u32(offset + 0x10)
    rotation_count = view.u16(offset + 0x18)
    translation_count = view.u16(offset + 0x1A)
    scale_count = view.u16(offset + 0x1C)
    rotation_limits: list[CdrJointRotationLimit] = []
    if rotation_pointer and rotation_count:
        rotation_offset = view.system_offset(rotation_pointer)
        for index in range(rotation_count):
            item_offset = rotation_offset + index * 0xB0
            control_points = [
                CdrJointControlPoint(*struct.unpack_from(">3f", view.system, item_offset + 0x4C + point_index * 12))
                for point_index in range(8)
            ]
            rotation_limits.append(
                CdrJointRotationLimit(
                    bone_id=view.s32(item_offset + 0x04),
                    control_point_count=view.s32(item_offset + 0x08),
                    degrees_of_freedom=view.s32(item_offset + 0x0C),
                    zero_rotation=struct.unpack_from(">4f", view.system, item_offset + 0x10),
                    zero_rotation_euler=view.vec3(item_offset + 0x20),
                    twist_axis=view.vec3(item_offset + 0x30),
                    min_twist=view.f32(item_offset + 0x40),
                    max_twist=view.f32(item_offset + 0x44),
                    soft_limit_scale=view.f32(item_offset + 0x48),
                    control_points=control_points,
                    use_twist_limits=bool(view.u8(item_offset + 0xAC)),
                    use_euler_angles=bool(view.u8(item_offset + 0xAD)),
                    use_per_control_twist_limits=bool(view.u8(item_offset + 0xAE)),
                )
            )
    return CdrJoints(
        name=view.c_string(view.u32(offset + 0x14)),
        rotation_limits=rotation_limits,
        translation_limits=_parse_joint_vector_limits(view, translation_pointer, translation_count),
        scale_limits=_parse_joint_vector_limits(view, scale_pointer, scale_count),
    )


def _parse_quick_buffer_mesh(
    view: Ps3ResourceView,
    geometry_offset: int,
    material_index: int,
    material: CdrMaterial | None,
) -> CdrMesh:
    vertex_buffer_pointer = view.u32(geometry_offset + 0x0C)
    index_buffer_pointer = view.u32(geometry_offset + 0x1C)
    index_count = view.u32(geometry_offset + 0x2C)
    vertex_count = view.u16(geometry_offset + 0x34)
    bone_ids_pointer = view.u32(geometry_offset + 0x38)
    bone_ids_count = view.u16(geometry_offset + 0x3E)
    if not vertex_buffer_pointer or not index_buffer_pointer:
        raise ValueError("PS3 quick-buffer geometry has no vertex or index buffer")

    vertex_buffer_offset = view.system_offset(vertex_buffer_pointer)
    vertex_stride = view.u16(vertex_buffer_offset + 0x04)
    buffer_vertex_count = view.u32(vertex_buffer_offset + 0x0C)
    fvf_pointer = view.u32(vertex_buffer_offset + 0x18)
    vertex_data_pointer = view.u32(vertex_buffer_offset + 0x1C) or view.u32(vertex_buffer_offset + 0x08)
    vertex_format = parse_fvf(view.bytes_at(fvf_pointer, 16))
    count = int(vertex_count or buffer_vertex_count)
    stride = int(vertex_format.stride or vertex_stride)
    raw_vertices = view.bytes_at(vertex_data_pointer, count * stride)
    decoded = decode_fvf_vertices(raw_vertices, count, vertex_format)

    index_buffer_offset = view.system_offset(index_buffer_pointer)
    buffer_index_count = view.u32(index_buffer_offset + 0x04) & 0x00FFFFFF
    index_data_pointer = view.u32(index_buffer_offset + 0x08)
    count_indices = int(index_count or buffer_index_count)
    raw_indices = view.bytes_at(index_data_pointer, count_indices * 2)
    indices = list(struct.unpack_from(f">{count_indices}H", raw_indices, 0)) if count_indices else []

    return CdrMesh(
        geometry_type=CdrGeometryType.QUICK_BUFFER,
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
        bone_ids=_u16_array(view, bone_ids_pointer, bone_ids_count),
        vertex_format=vertex_format,
    )


def _read_edge_stream(view: Ps3ResourceView, pointer: int, size: int):
    return parse_edge_stream(view.bytes_at(pointer, size)) if pointer and size else None


def _remap_edge_bone_index(index: int, offsets: tuple[int, int], counts: tuple[int, int]) -> int:
    if index < counts[0]:
        return offsets[0] + index
    return offsets[1] + index - counts[0]


def _decode_edge_skin(
    raw: bytes,
    vertex_count: int,
    flavor: CdrSkinningFlavor,
    matrix_offsets: tuple[int, int],
    matrix_counts: tuple[int, int],
) -> tuple[list[tuple[float, float, float, float]], list[tuple[int, int, int, int]]]:
    if flavor is CdrSkinningFlavor.NONE or not raw:
        return [], []
    single_bone = flavor in {
        CdrSkinningFlavor.SINGLE_BONE_NO_SCALING,
        CdrSkinningFlavor.SINGLE_BONE_UNIFORM_SCALING,
        CdrSkinningFlavor.SINGLE_BONE_NON_UNIFORM_SCALING,
    }
    stride = 1 if single_bone else 8
    if len(raw) < vertex_count * stride:
        raise ValueError("EDGE skin index/weight stream is truncated")
    weights: list[tuple[float, float, float, float]] = []
    indices: list[tuple[int, int, int, int]] = []
    for vertex_index in range(vertex_count):
        base = vertex_index * stride
        if single_bone:
            bone = _remap_edge_bone_index(raw[base], matrix_offsets, matrix_counts)
            weights.append((1.0, 0.0, 0.0, 0.0))
            indices.append((bone, 0, 0, 0))
            continue
        values = raw[base : base + 8]
        if values[1] == 0xFF:
            local_indices = (0, 0, 0, 0)
            vertex_weights = (1.0, 0.0, 0.0, 0.0)
        else:
            local_indices = (values[1], values[3], values[5], values[7])
            vertex_weights = (values[0] / 255.0, values[2] / 255.0, values[4] / 255.0, values[6] / 255.0)
        indices.append(tuple(_remap_edge_bone_index(value, matrix_offsets, matrix_counts) for value in local_indices))
        weights.append(vertex_weights)
    return weights, indices


def _merge_edge_attributes(target: dict[int, list[tuple[float, ...]]], source: dict[int, list[tuple[float, ...]]]) -> None:
    for semantic, values in source.items():
        target.setdefault(semantic, []).extend(values)


def _edge_vec3(values: list[tuple[float, ...]]) -> list[tuple[float, float, float]]:
    return [(float(value[0]), float(value[1]), float(value[2])) for value in values]


def _edge_vec4(values: list[tuple[float, ...]], default_w: float = 1.0) -> list[tuple[float, float, float, float]]:
    return [
        (
            float(value[0]),
            float(value[1]) if len(value) > 1 else 0.0,
            float(value[2]) if len(value) > 2 else 0.0,
            float(value[3]) if len(value) > 3 else default_w,
        )
        for value in values
    ]


def _parse_edge_segment(view: Ps3ResourceView, offset: int) -> CdrEdgeSegment:
    input_format_id = view.u8(offset + 0x02)
    secondary_input_format_id = view.u8(offset + 0x03)
    output_format_id = view.u8(offset + 0x04)
    flavors = view.u8(offset + 0x06)
    index_flavor = CdrIndexFlavor((flavors >> 4) & 0xF)
    skinning_flavor = CdrSkinningFlavor(flavors & 0xF)
    vertex_count = view.u16(offset + 0x08)
    index_count = view.u16(offset + 0x0A)
    indexes_pointer = view.u32(offset + 0x10)
    indexes_size = view.u16(offset + 0x14) + view.u16(offset + 0x16)
    vertex_pointers = (view.u32(offset + 0x18), view.u32(offset + 0x1C))
    vertex_sizes = tuple(view.u16(offset + 0x20 + index * 2) for index in range(6))
    rsx_pointer = view.u32(offset + 0x2C)
    rsx_size = view.u32(offset + 0x30)
    skin_sizes = (view.u16(offset + 0x3C), view.u16(offset + 0x3E))
    skin_pointer = view.u32(offset + 0x40)
    matrix_offsets = (view.u16(offset + 0x34) // 48, view.u16(offset + 0x36) // 48)
    matrix_counts = (view.u16(offset + 0x38) // 48, view.u16(offset + 0x3A) // 48)
    fixed_sizes = (view.u32(offset + 0x58), view.u32(offset + 0x5C))
    fixed_pointers = (view.u32(offset + 0x60), view.u32(offset + 0x64))
    descriptor_pointers = (view.u32(offset + 0x68), view.u32(offset + 0x6C))
    rsx_descriptor_pointer = view.u32(offset + 0x74)
    descriptor_sizes = (view.u16(offset + 0x78), view.u16(offset + 0x7A))
    rsx_descriptor_size = view.u16(offset + 0x7E)

    raw_indices = view.bytes_at(indexes_pointer, indexes_size)
    if index_flavor in {CdrIndexFlavor.COMPRESSED_TRIANGLE_LIST_CW, CdrIndexFlavor.COMPRESSED_TRIANGLE_LIST_CCW}:
        indices = decompress_edge_indices(raw_indices, index_count)
    else:
        required = index_count * 2
        if len(raw_indices) < required:
            raise ValueError("EDGE u16 index stream is truncated")
        indices = list(struct.unpack_from(f">{index_count}H", raw_indices, 0))

    primary_size = sum(vertex_sizes[:3])
    secondary_size = sum(vertex_sizes[3:])
    raw_primary = view.bytes_at(vertex_pointers[0], primary_size)
    raw_secondary = view.bytes_at(vertex_pointers[1], secondary_size)
    raw_rsx = view.bytes_at(rsx_pointer, rsx_size)
    input_stream = _read_edge_stream(view, descriptor_pointers[0], descriptor_sizes[0])
    secondary_stream = _read_edge_stream(view, descriptor_pointers[1], descriptor_sizes[1])
    rsx_stream = _read_edge_stream(view, rsx_descriptor_pointer, rsx_descriptor_size)
    attributes: dict[int, list[tuple[float, ...]]] = {}

    if input_stream is not None:
        fixed_raw = view.bytes_at(fixed_pointers[0], fixed_sizes[0])
        fixed_offsets = struct.unpack_from(f">{len(fixed_raw) // 4}i", fixed_raw, 0) if fixed_raw else ()
        _merge_edge_attributes(attributes, decode_edge_vertices(raw_primary, vertex_count, input_stream, fixed_offsets=fixed_offsets))
    if secondary_stream is not None:
        fixed_raw = view.bytes_at(fixed_pointers[1], fixed_sizes[1])
        fixed_offsets = struct.unpack_from(f">{len(fixed_raw) // 4}i", fixed_raw, 0) if fixed_raw else ()
        _merge_edge_attributes(attributes, decode_edge_vertices(raw_secondary, vertex_count, secondary_stream, fixed_offsets=fixed_offsets))
    if rsx_stream is not None:
        _merge_edge_attributes(attributes, decode_edge_vertices(raw_rsx, vertex_count, rsx_stream))
    raw_skin = view.bytes_at(skin_pointer, sum(skin_sizes))
    blend_weights, blend_indices = _decode_edge_skin(
        raw_skin,
        vertex_count,
        skinning_flavor,
        matrix_offsets,
        matrix_counts,
    )

    return CdrEdgeSegment(
        vertex_count=vertex_count,
        index_count=index_count,
        index_flavor=index_flavor,
        skinning_flavor=skinning_flavor,
        input_format_id=input_format_id,
        secondary_input_format_id=secondary_input_format_id,
        output_format_id=output_format_id,
        indices=indices,
        attributes=attributes,
        blend_weights=blend_weights,
        blend_indices=blend_indices,
        matrix_group_offsets=matrix_offsets,
        matrix_group_counts=matrix_counts,
        input_stream=input_stream,
        secondary_input_stream=secondary_stream,
        rsx_stream=rsx_stream,
        skin_indices_and_weights=raw_skin,
        raw_indices=raw_indices,
        raw_vertices=raw_primary,
        raw_secondary_vertices=raw_secondary,
        raw_rsx_vertices=raw_rsx,
    )


def _parse_edge_mesh(
    view: Ps3ResourceView,
    geometry_offset: int,
    material_index: int,
    material: CdrMaterial | None,
) -> CdrMesh:
    segments_pointer = view.u32(geometry_offset + 0x0C)
    geometry_offset_xyz = view.vec3(geometry_offset + 0x10)
    segment_count = view.u32(geometry_offset + 0x20)
    segments_offset = view.system_offset(segments_pointer)
    segments = [_parse_edge_segment(view, segments_offset + index * 0x90) for index in range(segment_count)]
    indices: list[int] = []
    attributes: dict[int, list[tuple[float, ...]]] = {}
    vertex_base = 0
    blend_weights: list[tuple[float, float, float, float]] = []
    blend_indices: list[tuple[int, int, int, int]] = []
    for segment in segments:
        indices.extend(index + vertex_base for index in segment.indices)
        _merge_edge_attributes(attributes, segment.attributes)
        vertex_base += segment.vertex_count
        blend_weights.extend(segment.blend_weights)
        blend_indices.extend(segment.blend_indices)
    positions = [
        (value[0] + geometry_offset_xyz[0], value[1] + geometry_offset_xyz[1], value[2] + geometry_offset_xyz[2])
        for value in _edge_vec3(attributes.get(1, []))
    ]
    texcoord_ids = (5, 6, 7, 8, 17, 18)
    texcoords = [[(float(value[0]), float(value[1])) for value in attributes[semantic]] for semantic in texcoord_ids if semantic in attributes]
    return CdrMesh(
        geometry_type=CdrGeometryType.EDGE,
        material_index=material_index,
        material=material,
        indices=indices,
        positions=positions,
        normals=_edge_vec3(attributes.get(2, [])),
        tangents=_edge_vec4(attributes.get(3, [])),
        texcoords=texcoords,
        colours0=_edge_vec4(attributes.get(9, [])),
        colours1=_edge_vec4(attributes.get(19, [])),
        blend_weights=blend_weights,
        blend_indices=blend_indices,
        edge_segments=segments,
    )


def _parse_model(
    view: Ps3ResourceView,
    pointer: int,
    materials: list[CdrMaterial],
    lod: CdrLod,
    index: int,
) -> CdrModel:
    offset = view.system_offset(pointer)
    geometries_pointer = view.u32(offset + 0x04)
    geometry_count = view.u16(offset + 0x08)
    aabbs_pointer = view.u32(offset + 0x0C)
    shader_indices_pointer = view.u32(offset + 0x10)
    geometry_pointers = _pointer_array(view, geometries_pointer, geometry_count)
    shader_indices = _u16_array(view, shader_indices_pointer, geometry_count)
    meshes: list[CdrMesh] = []
    for geometry_index, geometry_pointer in enumerate(geometry_pointers):
        geometry_offset = view.system_offset(geometry_pointer)
        geometry_type = CdrGeometryType(view.u32(geometry_offset + 0x08))
        material_index = shader_indices[geometry_index] if geometry_index < len(shader_indices) else -1
        material = materials[material_index] if 0 <= material_index < len(materials) else None
        if geometry_type is CdrGeometryType.QUICK_BUFFER:
            mesh = _parse_quick_buffer_mesh(view, geometry_offset, material_index, material)
        else:
            mesh = _parse_edge_mesh(view, geometry_offset, material_index, material)
        meshes.append(mesh)

    bbox_min = bbox_max = None
    if aabbs_pointer:
        aabb_offset = view.system_offset(aabbs_pointer)
        bbox_min = view.vec3(aabb_offset)
        bbox_max = view.vec3(aabb_offset + 0x10)
    return CdrModel(
        lod=lod,
        index=index,
        meshes=meshes,
        matrix_count=view.u8(offset + 0x14),
        flags=view.u8(offset + 0x15),
        model_type=view.u8(offset + 0x16),
        matrix_index=view.u8(offset + 0x17),
        render_mask=view.u8(offset + 0x18),
        skin_flags=view.u8(offset + 0x19),
        bounding_box_min=bbox_min,
        bounding_box_max=bbox_max,
    )


def _parse_lods(view: Ps3ResourceView, materials: list[CdrMaterial]) -> dict[CdrLod, list[CdrModel]]:
    lods: dict[CdrLod, list[CdrModel]] = {}
    for lod in CDR_LOD_ORDER:
        lod_pointer = view.u32(_LOD_POINTER_OFFSETS[lod])
        if not lod_pointer:
            continue
        lod_offset = view.system_offset(lod_pointer)
        models_pointer = view.u32(lod_offset)
        model_count = view.u16(lod_offset + 0x04)
        model_pointers = _pointer_array(view, models_pointer, model_count)
        lods[lod] = [_parse_model(view, pointer, materials, lod, index) for index, pointer in enumerate(model_pointers)]
    return lods


def read_cdr(
    source: ByteSource,
    *,
    path: str | Path = "",
    shader_library: ShaderLibrary | None = None,
) -> Cdr:
    data = read_source_bytes(source)
    header, system_data, graphics_data = split_ps3_rsc7_sections(data)
    if len(system_data) < _ROOT_SIZE:
        raise ValueError("CDR system section does not contain a drawable root")
    view = Ps3ResourceView(system_data, graphics_data)
    active_shader_library = shader_library if shader_library is not None else load_shader_library()
    materials, texture_dictionary_pointer = _parse_materials(view, active_shader_library)
    skeleton_pointer = view.u32(0x0C)
    joint_data_pointer = view.u32(0x70)
    resource_path = str(path or source) if isinstance(source, (str, Path)) or path else ""
    return Cdr(
        version=int(header.version),
        path=resource_path,
        materials=materials,
        lods=_parse_lods(view, materials),
        bounding_center=view.vec3(0x10),
        bounding_sphere_radius=view.f32(0x1C),
        bounding_box_min=view.vec3(0x20),
        bounding_box_max=view.vec3(0x30),
        lod_distances={lod: view.f32(offset) for lod, offset in _LOD_DISTANCE_OFFSETS.items()},
        render_bucket_masks={lod: view.u32(offset) for lod, offset in _LOD_BUCKET_OFFSETS.items()},
        texture_dictionary_pointer=texture_dictionary_pointer,
        skeleton_pointer=skeleton_pointer,
        skeleton=_parse_skeleton(view, skeleton_pointer),
        joint_data_pointer=joint_data_pointer,
        joints=_parse_joints(view, joint_data_pointer),
        page_map_pointer=view.u32(0x04),
        debug_name=view.c_string(view.u32(0x7C)),
        system_data=system_data,
        graphics_data=graphics_data,
    )


__all__ = ["read_cdr"]
