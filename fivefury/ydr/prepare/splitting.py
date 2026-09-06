from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import TypeVar

from ... import _native as _native_backend
from ...mesh_math import triangle_array
from ...vector import Vector2
from ..build_types import YdrMeshInput

T = TypeVar("T")
_MAX_MESH_UNIQUE_VERTICES = 65535


def _copy_vertex_channel(
    channel: Sequence[T] | None, vertex_indices: Sequence[int]
) -> list[T] | None:
    if channel is None or len(channel) == 0:
        return None
    return [channel[index] for index in vertex_indices]


def _copy_texcoord_channels(
    channels: Sequence[Sequence[Vector2]] | None,
    vertex_indices: Sequence[int],
) -> list[list[Vector2]] | None:
    if channels is None or len(channels) == 0:
        return None
    return [_copy_vertex_channel(channel, vertex_indices) or [] for channel in channels]


def _build_split_mesh(
    mesh: YdrMeshInput, vertex_indices: Sequence[int], remapped_indices: Sequence[int]
) -> YdrMeshInput:
    return YdrMeshInput(
        positions=[mesh.positions[index] for index in vertex_indices],
        indices=list(remapped_indices),
        material=mesh.material,
        normals=_copy_vertex_channel(mesh.normals, vertex_indices),
        texcoords=_copy_texcoord_channels(mesh.texcoords, vertex_indices),
        tangents=_copy_vertex_channel(mesh.tangents, vertex_indices),
        colours0=_copy_vertex_channel(mesh.colours0, vertex_indices),
        colours1=_copy_vertex_channel(mesh.colours1, vertex_indices),
        blend_weights=_copy_vertex_channel(mesh.blend_weights, vertex_indices),
        blend_indices=_copy_vertex_channel(mesh.blend_indices, vertex_indices),
        bone_ids=list(mesh.bone_ids) if mesh.bone_ids is not None else None,
        vertex_buffer_flags=int(mesh.vertex_buffer_flags),
        declaration_flags=mesh.declaration_flags,
        declaration_types=mesh.declaration_types,
    )


def _split_mesh_by_vertex_limit(
    mesh: YdrMeshInput, *, max_vertices: int = _MAX_MESH_UNIQUE_VERTICES
) -> list[YdrMeshInput]:
    indices = triangle_array(mesh.indices, len(mesh.positions)).reshape(-1).tolist()
    normalized = dataclasses.replace(mesh, indices=indices)
    if not indices:
        return [normalized]
    chunks = _native_backend._ydr_split_mesh_indices(
        indices,
        len(mesh.positions),
        max_vertices,
    )
    if chunks is None:
        return [normalized]
    return [
        _build_split_mesh(normalized, vertex_indices, remapped_indices)
        for vertex_indices, remapped_indices in chunks
    ]
