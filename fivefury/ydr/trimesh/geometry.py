from __future__ import annotations

import numpy
import trimesh

from ...colors import parse_css_rgba_unit
from ...matrix import gta_source_transform, transform_normals, transform_positions
from ..build_types import YdrMeshInput


def _vertex_colours(
    mesh: trimesh.Trimesh,
    vertex_indices: numpy.ndarray | None,
) -> list[tuple[float, float, float, float]] | None:
    visual = mesh.visual
    if not bool(getattr(visual, "defined", False)):
        return None
    raw = numpy.asarray(getattr(visual, "vertex_colors", []))
    if raw.ndim != 2 or raw.shape[0] != len(mesh.vertices) or raw.shape[1] not in (3, 4):
        return None
    if vertex_indices is not None:
        raw = raw[vertex_indices]
    return [parse_css_rgba_unit(tuple(value)) for value in raw]


def _source_vertex_normals(
    mesh: trimesh.Trimesh,
    vertex_indices: numpy.ndarray | None,
) -> numpy.ndarray | None:
    cache = getattr(getattr(mesh, "_cache", None), "cache", None)
    if not isinstance(cache, dict) or "vertex_normals" not in cache:
        return None
    normals = numpy.asarray(cache["vertex_normals"], dtype=numpy.float64)
    if normals.shape != numpy.asarray(mesh.vertices).shape:
        return None
    return normals if vertex_indices is None else normals[vertex_indices]


def mesh_to_ydr_input(
    mesh: trimesh.Trimesh,
    transform: numpy.ndarray,
    material_name: str,
    *,
    default_colour: tuple[float, float, float, float] | None,
    face_indices: numpy.ndarray | None = None,
) -> YdrMeshInput:
    all_vertices = numpy.asarray(mesh.vertices, dtype=numpy.float64)
    faces = numpy.asarray(mesh.faces, dtype=numpy.int64)
    if all_vertices.ndim != 2 or all_vertices.shape[1] != 3 or not numpy.isfinite(all_vertices).all():
        raise ValueError("Trimesh vertices must be a finite Nx3 array")
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("Trimesh faces must be a triangle index array")
    if faces.size and (int(faces.min()) < 0 or int(faces.max()) >= len(all_vertices)):
        raise ValueError("Trimesh faces contain out-of-range vertex indices")
    if face_indices is None:
        vertex_indices = None
        vertices = all_vertices
    else:
        faces = faces[face_indices]
        vertex_indices, inverse = numpy.unique(faces.reshape(-1), return_inverse=True)
        faces = inverse.reshape((-1, 3))
        vertices = all_vertices[vertex_indices]

    combined_transform = gta_source_transform(transform)
    positions = transform_positions(vertices, combined_transform)
    normals_source = _source_vertex_normals(mesh, vertex_indices)
    normals = (
        transform_normals(normals_source, combined_transform)
        if normals_source is not None
        else None
    )
    if numpy.linalg.det(combined_transform[:3, :3]) < 0.0:
        faces = faces[:, (0, 2, 1)]

    texcoords: list[list[tuple[float, float]]]
    uv = numpy.asarray(getattr(mesh.visual, "uv", []), dtype=numpy.float64)
    if uv.ndim == 2 and uv.shape[0] == len(all_vertices) and uv.shape[1] >= 2:
        if vertex_indices is not None:
            uv = uv[vertex_indices]
        texcoords = [[(float(value[0]), 1.0 - float(value[1])) for value in uv]]
    else:
        texcoords = [[(0.0, 0.0)] * len(vertices)]

    colours = _vertex_colours(mesh, vertex_indices)
    if colours is None and default_colour is not None:
        colours = [default_colour] * len(vertices)
    return YdrMeshInput(
        positions=positions,
        indices=[int(value) for value in faces.reshape(-1)],
        material=material_name,
        normals=normals,
        texcoords=texcoords,
        colours0=colours,
    )


__all__ = ["mesh_to_ydr_input"]
