from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence

from ..bounds import (
    BoundGeometry,
    BoundGeometryOctants,
    BoundMaterial,
    BoundPolygonTriangle,
    BoundPolygonType,
    BoundType,
)
from ..bounds.geometry import (
    DEFAULT_BOUND_MATERIAL,
    Vector3,
    bounds_from_vertices,
    triangle_area,
)
from .bound_profiles import (
    YftPhysicsBoundProfile,
    coerce_yft_physics_bound_profile,
    profile_file_vft,
)

MAX_FRAGMENT_BOUND_VERTICES = 0x7FFF
MAX_FRAGMENT_BOUND_POLYGONS = 0xFFFF
MAX_FRAGMENT_BOUND_MATERIALS = 0xFF

IndexedTriangle = tuple[int, int, int]


def _radius_from_center(
    vertices: Sequence[Vector3],
    center: Vector3,
) -> float:
    return max((vertex - center).length for vertex in vertices)


def _box_mass_properties(
    minimum: Vector3,
    maximum: Vector3,
) -> tuple[Vector3, float, Vector3]:
    size = maximum - minimum
    center = (minimum + maximum) * 0.5
    volume = abs(size.x * size.y * size.z)
    inertia = Vector3(
        ((size.y * size.y) + (size.z * size.z)) / 12.0,
        ((size.x * size.x) + (size.z * size.z)) / 12.0,
        ((size.x * size.x) + (size.y * size.y)) / 12.0,
    )
    return center, volume, inertia


def _mesh_mass_properties(
    vertices: Sequence[Vector3],
    triangles: Sequence[IndexedTriangle],
    minimum: Vector3,
    maximum: Vector3,
) -> tuple[Vector3, float, Vector3]:
    signed_volume = 0.0
    first_moment_x = 0.0
    first_moment_y = 0.0
    first_moment_z = 0.0
    second_moment_x = 0.0
    second_moment_y = 0.0
    second_moment_z = 0.0
    for index0, index1, index2 in triangles:
        a = vertices[index0]
        b = vertices[index1]
        c = vertices[index2]
        cross = b.cross(c)
        tetra_volume = a.dot(cross) / 6.0
        signed_volume += tetra_volume
        first_moment_x += tetra_volume * (a.x + b.x + c.x) / 4.0
        first_moment_y += tetra_volume * (a.y + b.y + c.y) / 4.0
        first_moment_z += tetra_volume * (a.z + b.z + c.z) / 4.0
        second_moment_x += tetra_volume * (
            (a.x * a.x)
            + (b.x * b.x)
            + (c.x * c.x)
            + (a.x * b.x)
            + (a.x * c.x)
            + (b.x * c.x)
        ) / 10.0
        second_moment_y += tetra_volume * (
            (a.y * a.y)
            + (b.y * b.y)
            + (c.y * c.y)
            + (a.y * b.y)
            + (a.y * c.y)
            + (b.y * c.y)
        ) / 10.0
        second_moment_z += tetra_volume * (
            (a.z * a.z)
            + (b.z * b.z)
            + (c.z * c.z)
            + (a.z * b.z)
            + (a.z * c.z)
            + (b.z * c.z)
        ) / 10.0

    if not math.isfinite(signed_volume) or abs(signed_volume) <= 1.0e-9:
        return _box_mass_properties(minimum, maximum)
    sign = 1.0 if signed_volume > 0.0 else -1.0
    volume = abs(signed_volume)
    center = Vector3(
        (first_moment_x * sign) / volume,
        (first_moment_y * sign) / volume,
        (first_moment_z * sign) / volume,
    )
    moment_x = second_moment_x * sign
    moment_y = second_moment_y * sign
    moment_z = second_moment_z * sign
    inertia = Vector3(
        max(0.0, ((moment_y + moment_z) - volume * (center.y**2 + center.z**2)) / volume),
        max(0.0, ((moment_x + moment_z) - volume * (center.x**2 + center.z**2)) / volume),
        max(0.0, ((moment_x + moment_y) - volume * (center.x**2 + center.y**2)) / volume),
    )
    if not all(math.isfinite(value) for value in (*center, *inertia)):
        return _box_mass_properties(minimum, maximum)
    return center, volume, inertia


def build_fragment_geometry_bound(
    vertices: Sequence[Vector3],
    triangles: Sequence[IndexedTriangle],
    materials: Sequence[BoundMaterial] = (),
    *,
    material_indices: Sequence[int] | None = None,
    profile: YftPhysicsBoundProfile | str = YftPhysicsBoundProfile.PROP,
    margin: float = 0.04,
) -> BoundGeometry:
    """Build one direct fragment collision leaf without a YBN-style BVH."""

    resolved_profile = coerce_yft_physics_bound_profile(profile)
    if resolved_profile is YftPhysicsBoundProfile.PRESERVE:
        raise ValueError("PRESERVE cannot choose a VFT for new geometry")
    resolved_margin = float(margin)
    if not math.isfinite(resolved_margin) or resolved_margin < 0.0:
        raise ValueError("fragment geometry margin must be finite and non-negative")

    target_vertices = list(vertices)
    if any(not isinstance(vertex, Vector3) for vertex in target_vertices):
        raise TypeError("fragment geometry vertices must be Vector3 values")
    target_triangles: list[IndexedTriangle] = []
    for index, triangle in enumerate(triangles):
        if len(triangle) != 3:
            raise ValueError(f"triangle {index} must contain three indices")
        target_triangles.append(
            (int(triangle[0]), int(triangle[1]), int(triangle[2]))
        )
    if not target_vertices:
        raise ValueError("fragment geometry requires at least one vertex")
    if not target_triangles:
        raise ValueError("fragment geometry requires at least one triangle")
    if len(target_vertices) > MAX_FRAGMENT_BOUND_VERTICES:
        raise ValueError(
            f"fragment geometry exceeds {MAX_FRAGMENT_BOUND_VERTICES} vertices"
        )
    if len(target_triangles) > MAX_FRAGMENT_BOUND_POLYGONS:
        raise ValueError(
            f"fragment geometry exceeds {MAX_FRAGMENT_BOUND_POLYGONS} polygons"
        )
    if not all(math.isfinite(value) for vertex in target_vertices for value in vertex):
        raise ValueError("fragment geometry vertices must be finite")
    for index, triangle in enumerate(target_triangles):
        if len(set(triangle)) != 3:
            raise ValueError(f"triangle {index} is degenerate")
        if any(vertex < 0 or vertex >= len(target_vertices) for vertex in triangle):
            raise ValueError(f"triangle {index} references an invalid vertex")

    target_materials = (
        list(materials)
        if materials
        else [dataclasses.replace(DEFAULT_BOUND_MATERIAL)]
    )
    if len(target_materials) > MAX_FRAGMENT_BOUND_MATERIALS:
        raise ValueError(
            f"fragment geometry exceeds {MAX_FRAGMENT_BOUND_MATERIALS} materials"
        )
    for index, material in enumerate(target_materials):
        if material.data1 or material.data2:
            if not (
                0 <= int(material.data1) <= 0xFFFFFFFF
                and 0 <= int(material.data2) <= 0xFFFFFFFF
            ):
                raise ValueError(f"material {index} raw data must fit in 32 bits")
            continue
        for label, value, maximum in (
            ("type", material.type, 0xFF),
            ("procedural_id", material.procedural_id, 0xFF),
            ("room_id", material.room_id, 0x1F),
            ("ped_density", material.ped_density, 0x07),
            ("flags", material.flags, 0xFFFF),
            ("material_color_index", material.material_color_index, 0xFF),
            ("reserved", material.reserved, 0xFFFF),
        ):
            if not 0 <= int(value) <= maximum:
                raise ValueError(
                    f"material {index} {label} must fit in "
                    f"{maximum.bit_length()} bits"
                )
    polygon_materials = (
        [int(value) for value in material_indices]
        if material_indices is not None
        else [0] * len(target_triangles)
    )
    if len(polygon_materials) != len(target_triangles):
        raise ValueError("material_indices length must match triangle count")
    if any(
        value < 0 or value >= len(target_materials)
        for value in polygon_materials
    ):
        raise ValueError("fragment geometry references an invalid material")

    minimum, maximum = bounds_from_vertices(target_vertices)
    center_geom = (minimum + maximum) * 0.5
    center_of_gravity, volume, inertia = _mesh_mass_properties(
        target_vertices,
        target_triangles,
        minimum,
        maximum,
    )
    sphere_radius = _radius_from_center(
        target_vertices,
        center_of_gravity,
    )
    polygons = [
        BoundPolygonTriangle(
            polygon_type=BoundPolygonType.TRIANGLE,
            raw=b"",
            index=index,
            material_index=material_index,
            tri_area=triangle_area(
                target_vertices[index0],
                target_vertices[index1],
                target_vertices[index2],
            ),
            tri_index1=index0,
            tri_index2=index1,
            tri_index3=index2,
        )
        for index, ((index0, index1, index2), material_index) in enumerate(
            zip(target_triangles, polygon_materials, strict=True)
        )
    ]
    geometry = BoundGeometry(
        bound_type=BoundType.GEOMETRY,
        sphere_radius=sphere_radius,
        box_max=maximum,
        margin=resolved_margin,
        box_min=minimum,
        box_center=center_geom,
        sphere_center=center_of_gravity,
        file_vft=0,
        ref_count=1,
        angular_inertia=inertia,
        volume=volume,
        quantum=Vector3(1.0, 1.0, 1.0),
        center_geom=center_geom,
        vertices=target_vertices,
        vertices_shrunk=list(target_vertices),
        polygons=polygons,
        polygon_material_indices=polygon_materials,
        materials=target_materials,
        octants=BoundGeometryOctants.from_vertices(target_vertices),
    )
    geometry.file_vft = profile_file_vft(geometry, resolved_profile)
    issues = geometry.validate()
    if issues:
        raise ValueError(f"invalid fragment geometry: {issues}")
    return geometry


__all__ = [
    "MAX_FRAGMENT_BOUND_MATERIALS",
    "MAX_FRAGMENT_BOUND_POLYGONS",
    "MAX_FRAGMENT_BOUND_VERTICES",
    "IndexedTriangle",
    "build_fragment_geometry_bound",
]
