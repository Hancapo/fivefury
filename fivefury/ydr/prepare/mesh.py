from __future__ import annotations

import dataclasses
import struct
from collections.abc import Mapping, Sequence

from ...vector import Vector2, Vector3, Vector4
from ..build_types import YdrMeshInput
from ..model.skeleton import YdrSkeleton
from ..shaders import ShaderLayoutDefinition
from .channels import prepare_channels
from .encoding import (
    _encode_vertex_bytes_from_declaration,
    _encode_vertex_bytes_from_layout,
)
from .material import PreparedMaterial
from .splitting import _split_mesh_by_vertex_limit


@dataclasses.dataclass(slots=True)
class PreparedMesh:
    positions: list[Vector3]
    indices: list[int]
    material_index: int
    normals: list[Vector3]
    texcoords: list[list[Vector2]]
    tangents: list[Vector4]
    colours0: list[tuple[float, float, float, float]]
    colours1: list[tuple[float, float, float, float]]
    blend_weights: list[tuple[float, float, float, float]]
    blend_indices: list[tuple[int, int, int, int]]
    bone_ids: list[int]
    declaration_flags: int
    declaration_types: int
    vertex_stride: int
    vertex_buffer_flags: int
    vertex_bytes: bytes
    index_bytes: bytes
    layout: ShaderLayoutDefinition


def prepare_meshes(
    meshes: Sequence[YdrMeshInput],
    prepared_materials: Sequence[PreparedMaterial],
    material_lookup: Mapping[str, int],
    *,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
    skeleton: YdrSkeleton | None = None,
) -> list[PreparedMesh]:
    prepared: list[PreparedMesh] = []
    for mesh in meshes:
        material_key = mesh.material.lower()
        if material_key not in material_lookup:
            raise ValueError(f"Mesh references unknown material '{mesh.material}'")
        material = prepared_materials[material_lookup[material_key]]

        normalized, layout = prepare_channels(
            mesh,
            material,
            generate_normals=generate_normals,
            generate_tangents=generate_tangents,
            fill_vertex_colours=fill_vertex_colours,
            skeleton=skeleton,
        )
        for mesh in _split_mesh_by_vertex_limit(normalized):
            positions = list(mesh.positions)
            indices = list(mesh.indices)
            normals = list(mesh.normals or ())
            texcoords = [list(channel) for channel in (mesh.texcoords or ())]
            tangents = list(mesh.tangents or ())
            colours0 = list(mesh.colours0 or ())
            colours1 = list(mesh.colours1 or ())
            blend_weights = list(mesh.blend_weights or ())
            blend_indices = list(mesh.blend_indices or ())

            if (
                mesh.declaration_flags is not None
                and mesh.declaration_types is not None
            ):
                flags, types_value, stride, vertex_bytes = (
                    _encode_vertex_bytes_from_declaration(
                        int(mesh.declaration_flags),
                        int(mesh.declaration_types),
                        positions,
                        normals,
                        texcoords,
                        tangents,
                        colours0,
                        colours1,
                        blend_weights=blend_weights or None,
                        blend_indices=blend_indices or None,
                    )
                )
            else:
                flags, types_value, stride, vertex_bytes = (
                    _encode_vertex_bytes_from_layout(
                        layout,
                        positions,
                        normals,
                        texcoords,
                        tangents,
                        colours0,
                        colours1,
                        blend_weights=blend_weights or None,
                        blend_indices=blend_indices or None,
                    )
                )
            if max(indices, default=0) > 0xFFFF:
                raise ValueError(
                    "YDR writer currently supports at most 65535 unique vertices per mesh"
                )
            index_bytes = struct.pack(f"<{len(indices)}H", *indices) if indices else b""

            prepared.append(
                PreparedMesh(
                    positions=positions,
                    indices=indices,
                    material_index=material.index,
                    normals=normals,
                    texcoords=texcoords,
                    tangents=tangents,
                    colours0=colours0,
                    colours1=colours1,
                    blend_weights=blend_weights,
                    blend_indices=blend_indices,
                    bone_ids=list(mesh.bone_ids or ()),
                    declaration_flags=flags,
                    declaration_types=types_value,
                    vertex_stride=stride,
                    vertex_buffer_flags=int(mesh.vertex_buffer_flags),
                    vertex_bytes=vertex_bytes,
                    index_bytes=index_bytes,
                    layout=layout,
                )
            )
    return prepared
