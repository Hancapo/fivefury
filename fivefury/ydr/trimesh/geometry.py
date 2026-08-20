from __future__ import annotations

import numpy
import trimesh

from ...colors import parse_css_rgba_unit
from ...matrix import (
    gta_source_transform,
    transform_normal_array,
    transform_position_array,
)
from ...mesh_source import mesh_triangles, mesh_vertices
from ...numeric import Float64Array, Int64Array
from ...vector import Vector2, Vector3
from ..build_types import YdrMeshInput


def _vertex_colours(
    mesh: trimesh.Trimesh,
    vertex_indices: Int64Array | None,
) -> list[tuple[float, float, float, float]] | None:
    visual = mesh.visual
    if not bool(getattr(visual, "defined", False)):
        return None
    raw = numpy.asarray(getattr(visual, "vertex_colors", []))
    if (
        raw.ndim != 2
        or raw.shape[0] != len(mesh.vertices)
        or raw.shape[1] not in (3, 4)
    ):
        return None
    if vertex_indices is not None:
        raw = raw[vertex_indices]
    return [parse_css_rgba_unit(tuple(value)) for value in raw]


def _source_vertex_normals(
    mesh: trimesh.Trimesh,
    vertex_indices: Int64Array | None,
) -> Float64Array | None:
    cache = getattr(getattr(mesh, "_cache", None), "cache", None)
    if not isinstance(cache, dict) or "vertex_normals" not in cache:
        return None
    normals = numpy.asarray(cache["vertex_normals"], dtype=numpy.float64)
    if normals.shape != numpy.asarray(mesh.vertices).shape:
        return None
    return normals if vertex_indices is None else normals[vertex_indices]


def mesh_to_ydr_input(
    mesh: trimesh.Trimesh,
    transform: Float64Array,
    material_name: str,
    *,
    default_colour: tuple[float, float, float, float] | None,
    face_indices: Int64Array | None = None,
) -> YdrMeshInput:
    all_vertices = mesh_vertices(mesh)
    faces = mesh_triangles(mesh)
    if face_indices is None:
        vertex_indices = None
        vertices = all_vertices
    else:
        faces = faces[face_indices]
        vertex_indices, faces = numpy.unique(
            faces,
            return_inverse=True,
            sorted=True,
        )
        vertices = all_vertices[vertex_indices]

    combined_transform = gta_source_transform(transform)
    position_rows = transform_position_array(vertices, combined_transform)
    normals_source = _source_vertex_normals(mesh, vertex_indices)
    normal_rows = (
        transform_normal_array(normals_source, combined_transform)
        if normals_source is not None
        else None
    )
    if numpy.linalg.det(combined_transform[:3, :3]) < 0.0:
        faces = faces[:, (0, 2, 1)]

    texcoords: list[list[Vector2]]
    uv = numpy.asarray(getattr(mesh.visual, "uv", []), dtype=numpy.float64)
    if uv.ndim == 2 and uv.shape[0] == len(all_vertices) and uv.shape[1] >= 2:
        if vertex_indices is not None:
            uv = uv[vertex_indices]
        uv = uv[:, :2].copy()
        uv[:, 1] = 1.0 - uv[:, 1]
        texcoords = [[Vector2.from_iterable(row) for row in uv]]
    else:
        texcoords = [[Vector2()] * len(vertices)]

    colours = _vertex_colours(mesh, vertex_indices)
    if colours is None and default_colour is not None:
        colours = [default_colour] * len(vertices)
    return YdrMeshInput(
        positions=[Vector3.from_iterable(row) for row in position_rows],
        indices=faces.reshape(-1).tolist(),
        material=material_name,
        normals=(
            [Vector3.from_iterable(row) for row in normal_rows]
            if normal_rows is not None
            else None
        ),
        texcoords=texcoords,
        colours0=colours,
    )


__all__ = ["mesh_to_ydr_input"]
