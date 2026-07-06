from __future__ import annotations

import dataclasses
from .. import _native as _native_backend
from ..vector import aabb_center
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


def triangle_area(vertex0: Vector3, vertex1: Vector3, vertex2: Vector3) -> float:
    return _native_backend._bounds_triangle_area(vertex0, vertex1, vertex2)


def bounds_from_vertices(vertices: list[Vector3]) -> tuple[Vector3, Vector3]:
    return _native_backend._bounds_from_vertices(vertices)


def center_from_bounds(minimum: Vector3, maximum: Vector3) -> Vector3:
    return aabb_center(minimum, maximum)


def sphere_radius_from_vertices(center: Vector3, vertices: list[Vector3]) -> float:
    return _native_backend._bounds_sphere_radius_from_vertices(center, vertices)


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
    max_vertices_per_child: int = MAX_BOUND_VERTICES_PER_CHILD,
    max_triangles_per_child: int = MAX_BOUND_TRIANGLES_PER_CHILD,
) -> list[BoundTriangleChunk]:
    return [
        BoundTriangleChunk(vertices=vertices, triangles=chunk_triangles)
        for vertices, chunk_triangles in _native_backend._bounds_chunk_triangles(
            triangles,
            max_vertices_per_child=max_vertices_per_child,
            max_triangles_per_child=max_triangles_per_child,
        )
    ]


def build_geometry_bvh_from_chunk(
    chunk: BoundTriangleChunk,
    *,
    material: BoundMaterial | None = None,
) -> BoundBVH:
    minimum, maximum = bounds_from_vertices(chunk.vertices)
    center = center_from_bounds(minimum, maximum)
    radius = sphere_radius_from_vertices(center, chunk.vertices)
    areas = _native_backend._bounds_indexed_triangle_areas(chunk.vertices, chunk.triangles)
    polygons = [
        BoundPolygonTriangle(
            polygon_type=BoundPolygonType.TRIANGLE,
            raw=b"",
            material_index=0,
            tri_area=area,
            tri_index1=index0,
            tri_index2=index1,
            tri_index3=index2,
            edge_index1=0xFFFF,
            edge_index2=0xFFFF,
            edge_index3=0xFFFF,
        )
        for (index0, index1, index2), area in zip(chunk.triangles, areas, strict=True)
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
        polygon_material_indices=[0] * len(polygons),
        materials=[material or dataclasses.replace(DEFAULT_BOUND_MATERIAL)],
        material_colours=[],
        vertex_colours=[],
        bvh_pointer=0,
        bvh=None,
    )


def build_composite_bound_from_chunks(
    chunks: list[BoundTriangleChunk],
    *,
    material: BoundMaterial | None = None,
    composite_flags: BoundCompositeFlags | None = None,
) -> BoundComposite:
    if not chunks:
        raise ValueError("At least one triangle chunk is required")
    child_flags = composite_flags or DEFAULT_BOUND_COMPOSITE_FLAGS
    children: list[BoundChild] = []
    all_vertices: list[Vector3] = []
    for chunk in chunks:
        geometry = build_geometry_bvh_from_chunk(chunk, material=material)
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
    composite_flags: BoundCompositeFlags | None = None,
    max_vertices_per_child: int = MAX_BOUND_VERTICES_PER_CHILD,
    max_triangles_per_child: int = MAX_BOUND_TRIANGLES_PER_CHILD,
) -> BoundComposite:
    if not triangles:
        raise ValueError("At least one triangle is required")
    chunks = chunk_bound_triangles(
        triangles,
        max_vertices_per_child=max_vertices_per_child,
        max_triangles_per_child=max_triangles_per_child,
    )
    bound = build_composite_bound_from_chunks(chunks, material=material, composite_flags=composite_flags)
    validation_errors = bound.validate()
    if validation_errors:
        raise ValueError(f"Generated bound validation failed: {validation_errors}")
    return bound


__all__ = [
    "BoundTriangle",
    "BoundTriangleChunk",
    "DEFAULT_BOUND_COMPOSITE_FLAGS",
    "DEFAULT_BOUND_MATERIAL",
    "MAX_BOUND_TRIANGLES_PER_CHILD",
    "MAX_BOUND_VERTICES_PER_CHILD",
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
