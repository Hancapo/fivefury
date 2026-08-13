from __future__ import annotations

from collections.abc import Iterable
from typing import TypeAlias

import numpy

from .vector import Vector3

Matrix4: TypeAlias = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]

GTA_SOURCE_AXIS_TRANSFORM = numpy.array(
    (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, -1.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ),
    dtype=numpy.float64,
)


def matrix4(value: object) -> numpy.ndarray:
    result = numpy.asarray(value, dtype=numpy.float64)
    if result.shape != (4, 4):
        raise ValueError(f"Expected a 4x4 matrix, got shape {result.shape!r}")
    if not numpy.isfinite(result).all():
        raise ValueError("Matrix contains non-finite values")
    return result


def gta_source_transform(value: object) -> numpy.ndarray:
    return GTA_SOURCE_AXIS_TRANSFORM @ matrix4(value)


def transform_positions(
    values: Iterable[Vector3],
    transform: object,
) -> list[Vector3]:
    points = numpy.asarray(list(values), dtype=numpy.float64)
    if points.size == 0:
        return []
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f"Expected an Nx3 position array, got shape {points.shape!r}")
    basis = matrix4(transform)
    homogeneous = numpy.column_stack((points, numpy.ones(len(points))))
    transformed = homogeneous @ basis.T
    return [tuple(map(float, point[:3])) for point in transformed]


def transform_normals(
    values: Iterable[Vector3],
    transform: object,
    *,
    epsilon: float = 1e-12,
) -> list[Vector3]:
    normals = numpy.asarray(list(values), dtype=numpy.float64)
    if normals.size == 0:
        return []
    if normals.ndim != 2 or normals.shape[1] != 3:
        raise ValueError(f"Expected an Nx3 normal array, got shape {normals.shape!r}")
    linear = matrix4(transform)[:3, :3]
    try:
        normal_matrix = numpy.linalg.inv(linear).T
    except numpy.linalg.LinAlgError:
        normal_matrix = numpy.linalg.pinv(linear).T
    transformed = normals @ normal_matrix.T
    lengths = numpy.linalg.norm(transformed, axis=1)
    valid = lengths > float(epsilon)
    transformed[valid] /= lengths[valid, None]
    transformed[~valid] = (0.0, 0.0, 1.0)
    return [tuple(map(float, normal)) for normal in transformed]


__all__ = [
    "GTA_SOURCE_AXIS_TRANSFORM",
    "Matrix4",
    "gta_source_transform",
    "matrix4",
    "transform_normals",
    "transform_positions",
]
