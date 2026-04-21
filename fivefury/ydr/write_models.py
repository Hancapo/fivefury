from __future__ import annotations

import dataclasses
import struct

from ..binary import align
from ..resource import ResourceWriter
from .defs import YdrSkeletonBinding, coerce_skeleton_binding
from .prepare import PreparedModel
from .write_buffers import GraphicsWriter, build_mesh_buffer_packs
from .write_geometry import GeometryBlock, build_geometry_block


@dataclasses.dataclass(slots=True)
class PreparedModelBlock:
    geometry_blocks: list[GeometryBlock]
    model_size: int
    render_mask: int
    flags: int
    skeleton_binding: YdrSkeletonBinding


def _pack_aabb(bounds_min: tuple[float, float, float], bounds_max: tuple[float, float, float]) -> bytes:
    return struct.pack(
        '<8f',
        bounds_min[0],
        bounds_min[1],
        bounds_min[2],
        bounds_min[0],
        bounds_max[0],
        bounds_max[1],
        bounds_max[2],
        bounds_max[0],
    )


def pack_render_mask_flags(render_mask: int, flags: int) -> int:
    return ((int(flags) & 0xFF) << 8) | (int(render_mask) & 0xFF)


def pack_skeleton_binding(binding: YdrSkeletonBinding | int) -> int:
    return int(coerce_skeleton_binding(binding))


def model_block_size(geometry_lengths: list[int]) -> int:
    geometry_count = len(geometry_lengths)
    offset = 0x30
    offset += geometry_count * 2
    if geometry_count == 1:
        offset += 6
    else:
        offset = align(offset, 16)
    offset += geometry_count * 8
    offset = align(offset, 16)
    bounds_count = geometry_count if geometry_count <= 1 else geometry_count + 1
    offset += bounds_count * 32
    for geometry_length in geometry_lengths:
        offset = align(offset, 16)
        offset += geometry_length
    return offset


def prepare_model_block(
    system: ResourceWriter,
    graphics: GraphicsWriter,
    prepared_model: PreparedModel,
    *,
    virtual,
    vertex_buffer_vft: int,
    index_buffer_vft: int,
    drawable_geometry_vft: int,
    gen9: bool = False,
) -> PreparedModelBlock:
    mesh_packs = build_mesh_buffer_packs(
        system,
        graphics,
        list(prepared_model.meshes),
        virtual=virtual,
        vertex_buffer_vft=vertex_buffer_vft,
        index_buffer_vft=index_buffer_vft,
        gen9=gen9,
    )

    geometry_lengths = [len(pack.mesh.bone_ids) for pack in mesh_packs]
    base_size = model_block_size([0x98 + (8 if count > 4 else 0) + count * 2 if count else 0x98 for count in geometry_lengths])

    geometry_blocks: list[GeometryBlock] = []
    geometry_count = len(mesh_packs)
    cursor = 0x30 + (geometry_count * 2)
    if geometry_count == 1:
        cursor += 6
    else:
        cursor = align(cursor, 16)
    cursor += geometry_count * 8
    cursor = align(cursor, 16)
    bounds_count = geometry_count if geometry_count <= 1 else geometry_count + 1
    cursor += bounds_count * 32
    for mesh_pack in mesh_packs:
        cursor = align(cursor, 16)
        geometry_blocks.append(
            build_geometry_block(
                mesh_pack,
                drawable_geometry_vft=drawable_geometry_vft,
                geometry_start=cursor,
                virtual=virtual,
            )
        )
        cursor += len(geometry_blocks[-1].geometry_bytes)

    return PreparedModelBlock(
        geometry_blocks=geometry_blocks,
        model_size=model_block_size([len(block.geometry_bytes) for block in geometry_blocks]),
        render_mask=int(prepared_model.render_mask),
        flags=int(prepared_model.flags),
        skeleton_binding=coerce_skeleton_binding(prepared_model.skeleton_binding),
    )


def build_model_block(
    model_off: int,
    prepared_block: PreparedModelBlock,
    *,
    drawable_model_vft: int,
    virtual,
) -> bytes:
    geometry_blocks = prepared_block.geometry_blocks
    geometry_count = len(geometry_blocks)
    geometry_lengths = [len(block.geometry_bytes) for block in geometry_blocks]
    block_size = model_block_size(geometry_lengths)
    data = bytearray(block_size)

    shader_mapping_off = 0x30
    cursor = shader_mapping_off + (geometry_count * 2)
    if geometry_count == 1:
        cursor += 6
    else:
        cursor = align(cursor, 16)
    geometries_ptr_off = cursor
    cursor += geometry_count * 8
    cursor = align(cursor, 16)
    bounds_off = cursor

    bounds_chunks: list[bytes] = []
    if geometry_count > 1:
        all_positions_min = (
            min(block.bounds_min[0] for block in geometry_blocks),
            min(block.bounds_min[1] for block in geometry_blocks),
            min(block.bounds_min[2] for block in geometry_blocks),
        )
        all_positions_max = (
            max(block.bounds_max[0] for block in geometry_blocks),
            max(block.bounds_max[1] for block in geometry_blocks),
            max(block.bounds_max[2] for block in geometry_blocks),
        )
        bounds_chunks.append(_pack_aabb(all_positions_min, all_positions_max))
    for block in geometry_blocks:
        bounds_chunks.append(_pack_aabb(block.bounds_min, block.bounds_max))
    for index, chunk in enumerate(bounds_chunks):
        start = bounds_off + (index * 32)
        data[start : start + 32] = chunk
    cursor = bounds_off + (len(bounds_chunks) * 32)

    geometry_offsets: list[int] = []
    for block in geometry_blocks:
        cursor = align(cursor, 16)
        geometry_offsets.append(cursor)
        geometry_bytes = bytearray(block.geometry_bytes)
        bone_ids_count = int.from_bytes(geometry_bytes[0x72:0x74], "little")
        if bone_ids_count:
            bone_ids_pointer = model_off + cursor + 0x98 + (8 if bone_ids_count > 4 else 0)
            struct.pack_into("<Q", geometry_bytes, 0x68, virtual(bone_ids_pointer))
        data[cursor : cursor + len(geometry_bytes)] = geometry_bytes
        cursor += len(block.geometry_bytes)

    struct.pack_into('<I', data, 0x00, int(drawable_model_vft))
    struct.pack_into('<I', data, 0x04, 1)
    struct.pack_into('<Q', data, 0x08, virtual(model_off + geometries_ptr_off))
    struct.pack_into('<H', data, 0x10, geometry_count)
    struct.pack_into('<H', data, 0x12, geometry_count)
    struct.pack_into('<I', data, 0x14, 0)
    struct.pack_into('<Q', data, 0x18, virtual(model_off + bounds_off))
    struct.pack_into('<Q', data, 0x20, virtual(model_off + shader_mapping_off))
    struct.pack_into('<I', data, 0x28, pack_skeleton_binding(prepared_block.skeleton_binding))
    struct.pack_into('<H', data, 0x2C, pack_render_mask_flags(prepared_block.render_mask, prepared_block.flags))
    struct.pack_into('<H', data, 0x2E, geometry_count)

    for index, block in enumerate(geometry_blocks):
        struct.pack_into('<H', data, shader_mapping_off + (index * 2), int(block.material_index))
        struct.pack_into('<Q', data, geometries_ptr_off + (index * 8), virtual(model_off + geometry_offsets[index]))

    return bytes(data)


def write_model_block(
    system: ResourceWriter,
    model_off: int,
    prepared_block: PreparedModelBlock,
    *,
    drawable_model_vft: int,
    virtual,
) -> None:
    system.write(
        model_off,
        build_model_block(
            model_off,
            prepared_block,
            drawable_model_vft=drawable_model_vft,
            virtual=virtual,
        ),
    )


__all__ = [
    'PreparedModelBlock',
    'build_model_block',
    'model_block_size',
    'pack_render_mask_flags',
    'pack_skeleton_binding',
    'prepare_model_block',
    'write_model_block',
]
