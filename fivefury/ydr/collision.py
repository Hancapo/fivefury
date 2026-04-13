from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from ..bounds.geometry import (
    MAX_BOUND_TRIANGLES_PER_CHILD,
    MAX_BOUND_VERTICES_PER_CHILD,
    BoundTriangle,
    build_bound_from_triangles,
    build_composite_bound_from_chunks,
    chunk_bound_triangles,
    triangle_area,
)
from ..bounds.model import BoundComposite, BoundCompositeFlags, BoundMaterial
from .defs import YdrLod

if TYPE_CHECKING:
    from .model import Ydr, YdrMesh


@dataclasses.dataclass(slots=True)
class YdrCollisionStats:
    meshes: int
    source_vertices: int
    source_triangles: int
    collision_vertices: int
    collision_triangles: int
    children: int


def mesh_collision_triangles(mesh: "YdrMesh", *, min_area: float = 1e-10) -> list[BoundTriangle]:
    positions = [tuple(float(component) for component in position) for position in (mesh.positions or [])]
    indices = [int(index) for index in (mesh.indices or [])]
    triangles: list[BoundTriangle] = []
    for offset in range(0, len(indices) - 2, 3):
        index0, index1, index2 = indices[offset : offset + 3]
        if min(index0, index1, index2) < 0 or max(index0, index1, index2) >= len(positions):
            continue
        vertex0 = positions[index0]
        vertex1 = positions[index1]
        vertex2 = positions[index2]
        if triangle_area(vertex0, vertex1, vertex2) <= min_area:
            continue
        triangles.append((vertex0, vertex1, vertex2))
    return triangles


def build_bound_from_render_geometry(
    ydr: "Ydr",
    *,
    lod: YdrLod | str | None = None,
    material: BoundMaterial | None = None,
    composite_flags: BoundCompositeFlags | None = None,
    max_vertices_per_child: int = MAX_BOUND_VERTICES_PER_CHILD,
    max_triangles_per_child: int = MAX_BOUND_TRIANGLES_PER_CHILD,
) -> BoundComposite:
    triangles = [triangle for mesh in ydr.iter_meshes(lod=lod) for triangle in mesh_collision_triangles(mesh)]
    if not triangles:
        raise ValueError("YDR has no valid render triangles to convert into collision")
    return build_bound_from_triangles(
        triangles,
        material=material,
        composite_flags=composite_flags,
        max_vertices_per_child=max_vertices_per_child,
        max_triangles_per_child=max_triangles_per_child,
    )


def set_bound_from_render_geometry(
    ydr: "Ydr",
    *,
    lod: YdrLod | str | None = None,
    material: BoundMaterial | None = None,
    composite_flags: BoundCompositeFlags | None = None,
    max_vertices_per_child: int = MAX_BOUND_VERTICES_PER_CHILD,
    max_triangles_per_child: int = MAX_BOUND_TRIANGLES_PER_CHILD,
) -> YdrCollisionStats:
    meshes = list(ydr.iter_meshes(lod=lod))
    triangles = [triangle for mesh in meshes for triangle in mesh_collision_triangles(mesh)]
    source_vertices = sum(len(mesh.positions or []) for mesh in meshes)
    if not triangles:
        raise ValueError("YDR has no valid render triangles to convert into collision")
    chunks = chunk_bound_triangles(
        triangles,
        max_vertices_per_child=max_vertices_per_child,
        max_triangles_per_child=max_triangles_per_child,
    )
    bound = build_composite_bound_from_chunks(chunks, material=material, composite_flags=composite_flags)
    validation_errors = bound.validate()
    if validation_errors:
        raise ValueError(f"Generated bound validation failed: {validation_errors}")
    ydr.set_bound(bound)
    return YdrCollisionStats(
        meshes=len(meshes),
        source_vertices=source_vertices,
        source_triangles=len(triangles),
        collision_vertices=sum(len(chunk.vertices) for chunk in chunks),
        collision_triangles=sum(len(chunk.triangles) for chunk in chunks),
        children=len(chunks),
    )


__all__ = [
    "YdrCollisionStats",
    "build_bound_from_render_geometry",
    "mesh_collision_triangles",
    "set_bound_from_render_geometry",
]
