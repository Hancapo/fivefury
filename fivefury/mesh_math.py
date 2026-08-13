from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .numeric import Int64Array, float64_rows, int64_array, normalized_rows, tuple_rows


def triangle_array(
    indices: Sequence[int] | np.ndarray,
    vertex_count: int,
) -> Int64Array:
    triangles = int64_array(indices, name="triangle indices")
    if triangles.ndim == 1:
        if triangles.size % 3:
            raise ValueError("triangle index count must be divisible by three")
        triangles = triangles.reshape((-1, 3))
    elif triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError(
            f"triangle indices must be an Nx3 array, got shape {triangles.shape!r}"
        )
    if triangles.size and (
        int(triangles.min()) < 0 or int(triangles.max()) >= int(vertex_count)
    ):
        raise ValueError("triangle indices reference a vertex outside positions")
    return triangles


def generate_vertex_normals(
    positions: Sequence[tuple[float, float, float]] | np.ndarray,
    indices: Sequence[int] | np.ndarray,
    *,
    epsilon: float = 1e-8,
) -> list[tuple[float, float, float]]:
    points = float64_rows(positions, 3, name="positions")
    triangles = triangle_array(indices, len(points))
    accumulated = np.zeros_like(points)
    if len(triangles):
        face_normals = np.linalg.cross(
            points[triangles[:, 1]] - points[triangles[:, 0]],
            points[triangles[:, 2]] - points[triangles[:, 0]],
        )
        for corner in range(3):
            np.add.at(accumulated, triangles[:, corner], face_normals)
    return tuple_rows(
        normalized_rows(
            accumulated,
            fallback=(0.0, 0.0, 1.0),
            epsilon=epsilon,
        ),
        columns=3,
    )


def generate_vertex_tangents(
    positions: Sequence[tuple[float, float, float]] | np.ndarray,
    normals: Sequence[tuple[float, float, float]] | np.ndarray,
    texcoords: Sequence[tuple[float, float]] | np.ndarray,
    indices: Sequence[int] | np.ndarray,
    *,
    epsilon: float = 1e-8,
) -> list[tuple[float, float, float, float]]:
    points = float64_rows(positions, 3, name="positions")
    normal_rows = float64_rows(normals, 3, name="normals")
    uv = float64_rows(texcoords, 2, name="texture coordinates")
    if len(normal_rows) != len(points) or len(uv) != len(points):
        raise ValueError("normal and texture-coordinate counts must match positions")
    triangles = triangle_array(indices, len(points))
    tangent_sum = np.zeros_like(points)
    bitangent_sum = np.zeros_like(points)
    if len(triangles):
        p0 = points[triangles[:, 0]]
        edge1 = points[triangles[:, 1]] - p0
        edge2 = points[triangles[:, 2]] - p0
        uv0 = uv[triangles[:, 0]]
        delta_uv1 = uv[triangles[:, 1]] - uv0
        delta_uv2 = uv[triangles[:, 2]] - uv0
        determinant = (
            delta_uv1[:, 0] * delta_uv2[:, 1] - delta_uv2[:, 0] * delta_uv1[:, 1]
        )
        valid = np.abs(determinant) > float(epsilon)
        if valid.any():
            reciprocal = 1.0 / determinant[valid]
            tangent = (
                delta_uv2[valid, 1, None] * edge1[valid]
                - delta_uv1[valid, 1, None] * edge2[valid]
            ) * reciprocal[:, None]
            bitangent = (
                delta_uv1[valid, 0, None] * edge2[valid]
                - delta_uv2[valid, 0, None] * edge1[valid]
            ) * reciprocal[:, None]
            valid_triangles = triangles[valid]
            for corner in range(3):
                np.add.at(tangent_sum, valid_triangles[:, corner], tangent)
                np.add.at(bitangent_sum, valid_triangles[:, corner], bitangent)

    projected = (
        tangent_sum - normal_rows * np.vecdot(normal_rows, tangent_sum, axis=1)[:, None]
    )
    tangent_rows = normalized_rows(
        projected,
        fallback=(1.0, 0.0, 0.0),
        epsilon=epsilon,
    )
    handedness = np.where(
        np.vecdot(np.linalg.cross(normal_rows, tangent_rows), bitangent_sum, axis=1)
        >= 0.0,
        1.0,
        -1.0,
    )
    return tuple_rows(
        np.concat((tangent_rows, handedness[:, None]), axis=1),
        columns=4,
    )


__all__ = [
    "generate_vertex_normals",
    "generate_vertex_tangents",
    "triangle_array",
]
