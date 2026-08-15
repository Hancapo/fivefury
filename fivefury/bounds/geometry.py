from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from .. import _native as _native_backend
from ..vector import aabb_center, aabb_from_points, sphere_radius_from_points
from .model import (
    BoundAabb,
    BoundBVH,
    BoundChild,
    BoundComposite,
    BoundCompositeFlags,
    BoundMaterial,
    BoundPolygonTriangle,
    BoundPolygonType,
    BoundTransform,
    BoundType,
)

MAX_BOUND_VERTICES_PER_CHILD = 30000
MAX_BOUND_TRIANGLES_PER_CHILD = 32000
DEFAULT_BOUND_COMPOSITE_FLAGS = BoundCompositeFlags(flags1=62, flags2=133414592)
DEFAULT_BOUND_MATERIAL = BoundMaterial(type=0)


Vector3 = tuple[float, float, float]
BoundTriangle = tuple[Vector3, Vector3, Vector3]


@dataclasses.dataclass(slots=True)
class BoundTriangleChunk:
    vertices: list[Vector3]
    triangles: list[tuple[int, int, int]]
    material_indices: list[int] = dataclasses.field(default_factory=list)


def triangle_area(vertex0: Vector3, vertex1: Vector3, vertex2: Vector3) -> float:
    return _native_backend._bounds_triangle_area(vertex0, vertex1, vertex2)


def bounds_from_vertices(vertices: list[Vector3]) -> tuple[Vector3, Vector3]:
    return aabb_from_points(vertices)


def center_from_bounds(minimum: Vector3, maximum: Vector3) -> Vector3:
    return aabb_center(minimum, maximum)


def sphere_radius_from_vertices(center: Vector3, vertices: list[Vector3]) -> float:
    return sphere_radius_from_points(center, vertices)


def identity_bound_transform() -> BoundTransform:
    return BoundTransform(
        column1=(1.0, 0.0, 0.0),
        column2=(0.0, 1.0, 0.0),
        column3=(0.0, 0.0, 1.0),
        column4=(0.0, 0.0, 0.0),
        flags1=0,
        flags2=1,
        flags3=1,
        flags4=0,
    )


def chunk_bound_triangles(
    triangles: list[BoundTriangle],
    *,
    triangle_material_indices: Sequence[int] | None = None,
    max_vertices_per_child: int = MAX_BOUND_VERTICES_PER_CHILD,
    max_triangles_per_child: int = MAX_BOUND_TRIANGLES_PER_CHILD,
) -> list[BoundTriangleChunk]:
    if triangle_material_indices is not None and len(triangle_material_indices) != len(
        triangles
    ):
        raise ValueError("triangle_material_indices length must match triangle count")

    native_chunks = _native_backend._bounds_chunk_triangles(
        triangles,
        max_vertices_per_child=max_vertices_per_child,
        max_triangles_per_child=max_triangles_per_child,
    )
    chunks: list[BoundTriangleChunk] = []
    triangle_offset = 0
    for vertices, chunk_triangles in native_chunks:
        chunk_triangle_count = len(chunk_triangles)
        material_indices = (
            [
                int(index)
                for index in triangle_material_indices[
                    triangle_offset : triangle_offset + chunk_triangle_count
                ]
            ]
            if triangle_material_indices is not None
            else []
        )
        chunks.append(
            BoundTriangleChunk(
                vertices=vertices,
                triangles=chunk_triangles,
                material_indices=material_indices,
            )
        )
        triangle_offset += chunk_triangle_count
    return chunks


def build_geometry_bvh_from_chunk(
    chunk: BoundTriangleChunk,
    *,
    material: BoundMaterial | None = None,
    materials: Sequence[BoundMaterial] | None = None,
) -> BoundBVH:
    if material is not None and materials is not None:
        raise ValueError("material and materials are mutually exclusive")
    target_materials = (
        list(materials)
        if materials is not None
        else [material or dataclasses.replace(DEFAULT_BOUND_MATERIAL)]
    )
    if not target_materials:
        raise ValueError("At least one bound material is required")
    if len(target_materials) > 0xFF:
        raise ValueError("Bound geometry cannot contain more than 255 materials")
    material_indices = (
        list(chunk.material_indices)
        if chunk.material_indices
        else [0] * len(chunk.triangles)
    )
    if len(material_indices) != len(chunk.triangles):
        raise ValueError("Chunk material index count must match triangle count")
    if any(index < 0 or index >= len(target_materials) for index in material_indices):
        raise ValueError("Chunk references an invalid bound material index")

    minimum, maximum = bounds_from_vertices(chunk.vertices)
    center = center_from_bounds(minimum, maximum)
    radius = sphere_radius_from_vertices(center, chunk.vertices)
    areas = _native_backend._bounds_indexed_triangle_areas(
        chunk.vertices, chunk.triangles
    )
    polygons = [
        BoundPolygonTriangle(
            polygon_type=BoundPolygonType.TRIANGLE,
            raw=b"",
            material_index=material_index,
            tri_area=area,
            tri_index1=index0,
            tri_index2=index1,
            tri_index3=index2,
            edge_index1=0xFFFF,
            edge_index2=0xFFFF,
            edge_index3=0xFFFF,
        )
        for (index0, index1, index2), area, material_index in zip(
            chunk.triangles,
            areas,
            material_indices,
            strict=True,
        )
    ]
    return BoundBVH(
        bound_type=BoundType.GEOMETRY_BVH,
        sphere_radius=radius,
        box_max=maximum,
        margin=0.04,
        box_min=minimum,
        box_center=center,
        sphere_center=center,
        material_index=0,
        procedural_id=0,
        room_id=0,
        ped_density=0,
        unk_flags=0,
        poly_flags=0,
        material_color_index=0,
        ref_count=1,
        angular_inertia=(0.0, 0.0, 0.0),
        volume=0.0,
        quantum=(1.0, 1.0, 1.0),
        center_geom=center,
        vertices=chunk.vertices,
        vertices_shrunk=[],
        polygons=polygons,
        polygon_material_indices=material_indices,
        materials=target_materials,
        material_colours=[],
        vertex_colours=[],
        bvh_pointer=0,
        bvh=None,
    )


def build_composite_bound_from_chunks(
    chunks: list[BoundTriangleChunk],
    *,
    material: BoundMaterial | None = None,
    materials: Sequence[BoundMaterial] | None = None,
    composite_flags: BoundCompositeFlags | None = None,
) -> BoundComposite:
    if not chunks:
        raise ValueError("At least one triangle chunk is required")
    child_flags = composite_flags or DEFAULT_BOUND_COMPOSITE_FLAGS
    children: list[BoundChild] = []
    all_vertices: list[Vector3] = []
    for chunk in chunks:
        geometry = build_geometry_bvh_from_chunk(
            chunk,
            material=material,
            materials=materials,
        )
        minimum = tuple(float(value) for value in geometry.box_min)
        maximum = tuple(float(value) for value in geometry.box_max)
        all_vertices.extend(chunk.vertices)
        children.append(
            BoundChild(
                bound=geometry,
                transform=identity_bound_transform(),
                bounds=BoundAabb(minimum=minimum, maximum=maximum),
                flags1=child_flags,
                flags2=child_flags,
            )
        )
    minimum, maximum = bounds_from_vertices(all_vertices)
    center = center_from_bounds(minimum, maximum)
    radius = sphere_radius_from_vertices(center, all_vertices)
    return BoundComposite(
        bound_type=BoundType.COMPOSITE,
        sphere_radius=radius,
        box_max=maximum,
        margin=0.04,
        box_min=minimum,
        box_center=center,
        sphere_center=center,
        material_index=0,
        procedural_id=0,
        room_id=0,
        ped_density=0,
        unk_flags=0,
        poly_flags=0,
        material_color_index=0,
        ref_count=1,
        angular_inertia=(0.0, 0.0, 0.0),
        volume=0.0,
        children=children,
        bvh_pointer=0,
    )


def build_bound_from_triangles(
    triangles: list[BoundTriangle],
    *,
    material: BoundMaterial | None = None,
    materials: Sequence[BoundMaterial] | None = None,
    triangle_material_indices: Sequence[int] | None = None,
    composite_flags: BoundCompositeFlags | None = None,
    max_vertices_per_child: int = MAX_BOUND_VERTICES_PER_CHILD,
    max_triangles_per_child: int = MAX_BOUND_TRIANGLES_PER_CHILD,
) -> BoundComposite:
    if not triangles:
        raise ValueError("At least one triangle is required")
    chunks = chunk_bound_triangles(
        triangles,
        triangle_material_indices=triangle_material_indices,
        max_vertices_per_child=max_vertices_per_child,
        max_triangles_per_child=max_triangles_per_child,
    )
    bound = build_composite_bound_from_chunks(
        chunks,
        material=material,
        materials=materials,
        composite_flags=composite_flags,
    )
    bound.validate().raise_for_errors()
    return bound


__all__ = [
    "DEFAULT_BOUND_COMPOSITE_FLAGS",
    "DEFAULT_BOUND_MATERIAL",
    "MAX_BOUND_TRIANGLES_PER_CHILD",
    "MAX_BOUND_VERTICES_PER_CHILD",
    "BoundTriangle",
    "BoundTriangleChunk",
    "Vector3",
    "bounds_from_vertices",
    "build_bound_from_triangles",
    "build_composite_bound_from_chunks",
    "build_geometry_bvh_from_chunk",
    "center_from_bounds",
    "chunk_bound_triangles",
    "identity_bound_transform",
    "sphere_radius_from_vertices",
    "triangle_area",
]
