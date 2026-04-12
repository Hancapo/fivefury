from __future__ import annotations

import dataclasses
import struct

from .prepare import compute_bounds
from .write_buffers import MeshBufferPack


@dataclasses.dataclass(slots=True)
class GeometryBlock:
    material_index: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    geometry_bytes: bytes


def geometry_block_size(bone_ids_count: int) -> int:
    size = 0x98
    if bone_ids_count > 0:
        if bone_ids_count > 4:
            size += 8
        size += bone_ids_count * 2
    return size


def bone_ids_tail_offset(bone_ids_count: int) -> int:
    return 0x98 + (8 if int(bone_ids_count) > 4 else 0)


def _pack_bone_ids(mesh_pack: MeshBufferPack, *, geometry_start: int) -> tuple[int, bytes]:
    bone_ids = list(mesh_pack.mesh.bone_ids)
    if not bone_ids:
        return 0, b''
    payload = bytearray()
    if len(bone_ids) > 4:
        payload.extend(b'\x00' * 8)
    payload.extend(struct.pack(f'<{len(bone_ids)}H', *bone_ids))
    pointer = geometry_start + bone_ids_tail_offset(len(bone_ids))
    return pointer, bytes(payload)


def build_geometry_block(
    mesh_pack: MeshBufferPack,
    *,
    drawable_geometry_vft: int,
    geometry_start: int,
    virtual,
) -> GeometryBlock:
    bone_ids_pointer, bone_payload = _pack_bone_ids(mesh_pack, geometry_start=geometry_start)
    data = bytearray(geometry_block_size(len(mesh_pack.mesh.bone_ids)))
    struct.pack_into('<I', data, 0x00, int(drawable_geometry_vft))
    struct.pack_into('<I', data, 0x04, 1)
    struct.pack_into('<Q', data, 0x08, 0)
    struct.pack_into('<Q', data, 0x10, 0)
    struct.pack_into('<Q', data, 0x18, virtual(mesh_pack.vertex_buffer_off))
    struct.pack_into('<Q', data, 0x20, 0)
    struct.pack_into('<Q', data, 0x28, 0)
    struct.pack_into('<Q', data, 0x30, 0)
    struct.pack_into('<Q', data, 0x38, virtual(mesh_pack.index_buffer_off))
    struct.pack_into('<Q', data, 0x40, 0)
    struct.pack_into('<Q', data, 0x48, 0)
    struct.pack_into('<Q', data, 0x50, 0)
    struct.pack_into('<I', data, 0x58, len(mesh_pack.mesh.indices))
    struct.pack_into('<I', data, 0x5C, len(mesh_pack.mesh.indices) // 3)
    struct.pack_into('<H', data, 0x60, len(mesh_pack.mesh.positions))
    struct.pack_into('<H', data, 0x62, 3)
    struct.pack_into('<I', data, 0x64, 0)
    struct.pack_into('<Q', data, 0x68, virtual(bone_ids_pointer) if bone_ids_pointer else 0)
    struct.pack_into('<H', data, 0x70, int(mesh_pack.mesh.vertex_stride))
    struct.pack_into('<H', data, 0x72, len(mesh_pack.mesh.bone_ids))
    struct.pack_into('<I', data, 0x74, 0)
    struct.pack_into('<Q', data, 0x78, virtual(mesh_pack.vertex_data_off))
    struct.pack_into('<Q', data, 0x80, 0)
    struct.pack_into('<Q', data, 0x88, 0)
    struct.pack_into('<Q', data, 0x90, 0)
    if bone_payload:
        data[0x98 : 0x98 + len(bone_payload)] = bone_payload
    return GeometryBlock(
        material_index=int(mesh_pack.mesh.material_index),
        bounds_min=mesh_pack.bounds_min,
        bounds_max=mesh_pack.bounds_max,
        geometry_bytes=bytes(data),
    )


__all__ = [
    'GeometryBlock',
    'bone_ids_tail_offset',
    'build_geometry_block',
    'compute_bounds',
    'geometry_block_size',
]
