from __future__ import annotations

import dataclasses

from ..binary import align
from ..resource import ResourceWriter
from .prepare import PreparedMesh, compute_bounds


@dataclasses.dataclass(slots=True)
class GraphicsWriter:
    data: bytearray = dataclasses.field(default_factory=bytearray)
    block_sizes: list[int] = dataclasses.field(default_factory=list)

    def alloc(self, value: bytes, alignment: int = 16) -> int:
        offset = align(len(self.data), alignment)
        if offset > len(self.data):
            self.data.extend(b'\x00' * (offset - len(self.data)))
        self.data.extend(value)
        self.block_sizes.append(len(value))
        return offset

    def finish(self) -> bytes:
        return bytes(self.data)


@dataclasses.dataclass(slots=True)
class MeshBufferPack:
    mesh: PreparedMesh
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    declaration_off: int
    vertex_data_off: int
    index_data_off: int
    vertex_buffer_off: int
    index_buffer_off: int


def build_mesh_buffer_pack(
    system: ResourceWriter,
    graphics: GraphicsWriter,
    mesh: PreparedMesh,
    *,
    virtual,
    vertex_buffer_vft: int,
    index_buffer_vft: int,
) -> MeshBufferPack:
    declaration_off = system.alloc(0x10, 16)
    system.pack_into('I', declaration_off + 0x00, int(mesh.declaration_flags))
    system.pack_into('H', declaration_off + 0x04, int(mesh.vertex_stride))
    system.data[declaration_off + 0x06] = 0
    system.data[declaration_off + 0x07] = max(1, int(mesh.declaration_flags).bit_count())
    system.pack_into('Q', declaration_off + 0x08, int(mesh.declaration_types))

    vertex_data_off = system.alloc(len(mesh.vertex_bytes), 16)
    system.write(vertex_data_off, mesh.vertex_bytes)
    index_data_off = system.alloc(len(mesh.index_bytes), 16) if mesh.index_bytes else 0
    if index_data_off:
        system.write(index_data_off, mesh.index_bytes)

    vertex_buffer_off = system.alloc(0x80, 16)
    system.pack_into('I', vertex_buffer_off + 0x00, int(vertex_buffer_vft))
    system.pack_into('I', vertex_buffer_off + 0x04, 1)
    system.pack_into('H', vertex_buffer_off + 0x08, int(mesh.vertex_stride))
    system.pack_into('H', vertex_buffer_off + 0x0A, int(mesh.vertex_buffer_flags) & 0xFFFF)
    system.pack_into('I', vertex_buffer_off + 0x0C, 0)
    system.pack_into('Q', vertex_buffer_off + 0x10, virtual(vertex_data_off))
    system.pack_into('I', vertex_buffer_off + 0x18, len(mesh.positions))
    system.pack_into('I', vertex_buffer_off + 0x1C, 0)
    system.pack_into('Q', vertex_buffer_off + 0x20, virtual(vertex_data_off))
    system.pack_into('Q', vertex_buffer_off + 0x30, virtual(declaration_off))

    index_buffer_off = system.alloc(0x60, 16)
    system.pack_into('I', index_buffer_off + 0x00, int(index_buffer_vft))
    system.pack_into('I', index_buffer_off + 0x04, 1)
    system.pack_into('I', index_buffer_off + 0x08, len(mesh.indices))
    system.pack_into('I', index_buffer_off + 0x0C, 0)
    system.pack_into('Q', index_buffer_off + 0x10, virtual(index_data_off) if index_data_off else 0)

    _center, bounds_min, bounds_max, _radius = compute_bounds(mesh.positions)
    return MeshBufferPack(
        mesh=mesh,
        bounds_min=bounds_min,
        bounds_max=bounds_max,
        declaration_off=declaration_off,
        vertex_data_off=vertex_data_off,
        index_data_off=index_data_off,
        vertex_buffer_off=vertex_buffer_off,
        index_buffer_off=index_buffer_off,
    )


def build_mesh_buffer_packs(
    system: ResourceWriter,
    graphics: GraphicsWriter,
    meshes: list[PreparedMesh],
    *,
    virtual,
    vertex_buffer_vft: int,
    index_buffer_vft: int,
) -> list[MeshBufferPack]:
    return [
        build_mesh_buffer_pack(
            system,
            graphics,
            mesh,
            virtual=virtual,
            vertex_buffer_vft=vertex_buffer_vft,
            index_buffer_vft=index_buffer_vft,
        )
        for mesh in meshes
    ]


__all__ = [
    'GraphicsWriter',
    'MeshBufferPack',
    'build_mesh_buffer_pack',
    'build_mesh_buffer_packs',
]
