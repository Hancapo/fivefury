from __future__ import annotations

import dataclasses
from math import sqrt

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
    edge1 = (vertex1[0] - vertex0[0], vertex1[1] - vertex0[1], vertex1[2] - vertex0[2])
    edge2 = (vertex2[0] - vertex0[0], vertex2[1] - vertex0[1], vertex2[2] - vertex0[2])
    cross = (
        (edge1[1] * edge2[2]) - (edge1[2] * edge2[1]),
        (edge1[2] * edge2[0]) - (edge1[0] * edge2[2]),
        (edge1[0] * edge2[1]) - (edge1[1] * edge2[0]),
    )
    return 0.5 * sqrt((cross[0] * cross[0]) + (cross[1] * cross[1]) + (cross[2] * cross[2]))


def bounds_from_vertices(vertices: list[Vector3]) -> tuple[Vector3, Vector3]:
    if not vertices:
        raise ValueError("At least one vertex is required")
    return (
        (min(vertex[0] for vertex in vertices), min(vertex[1] for vertex in vertices), min(vertex[2] for vertex in vertices)),
        (max(vertex[0] for vertex in vertices), max(vertex[1] for vertex in vertices), max(vertex[2] for vertex in vertices)),
    )


def center_from_bounds(minimum: Vector3, maximum: Vector3) -> Vector3:
    return ((minimum[0] + maximum[0]) * 0.5, (minimum[1] + maximum[1]) * 0.5, (minimum[2] + maximum[2]) * 0.5)


def sphere_radius_from_vertices(center: Vector3, vertices: list[Vector3]) -> float:
    return max(
        (
            sqrt(
                ((vertex[0] - center[0]) ** 2)
                + ((vertex[1] - center[1]) ** 2)
                + ((vertex[2] - center[2]) ** 2)
            )
            for vertex in vertices
        ),
        default=0.0,
    )


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
    chunks: list[BoundTriangleChunk] = []
    current_vertices: list[Vector3] = []
    current_triangles: list[tuple[int, int, int]] = []
    vertex_lookup: dict[Vector3, int] = {}

    def flush() -> None:
        nonlocal current_vertices, current_triangles, vertex_lookup
        if current_triangles:
            chunks.append(BoundTriangleChunk(vertices=current_vertices, triangles=current_triangles))
        current_vertices = []
        current_triangles = []
        vertex_lookup = {}

    for triangle in triangles:
        if current_triangles and (
            len(current_triangles) + 1 > max_triangles_per_child
            or len(current_vertices) + 3 > max_vertices_per_child
        ):
            flush()
        indices: list[int] = []
        for vertex in triangle:
            index = vertex_lookup.get(vertex)
            if index is None:
                index = len(current_vertices)
                vertex_lookup[vertex] = index
                current_vertices.append(vertex)
            indices.append(index)
        current_triangles.append((indices[0], indices[1], indices[2]))
    flush()
    return chunks


def build_geometry_bvh_from_chunk(
    chunk: BoundTriangleChunk,
    *,
    material: BoundMaterial | None = None,
) -> BoundBVH:
    minimum, maximum = bounds_from_vertices(chunk.vertices)
    center = center_from_bounds(minimum, maximum)
    radius = sphere_radius_from_vertices(center, chunk.vertices)
    polygons = [
        BoundPolygonTriangle(
            polygon_type=BoundPolygonType.TRIANGLE,
            raw=b"",
            material_index=0,
            tri_area=triangle_area(chunk.vertices[index0], chunk.vertices[index1], chunk.vertices[index2]),
            tri_index1=index0,
            tri_index2=index1,
            tri_index3=index2,
            edge_index1=0xFFFF,
            edge_index2=0xFFFF,
            edge_index3=0xFFFF,
        )
        for index0, index1, index2 in chunk.triangles
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
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
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
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
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
