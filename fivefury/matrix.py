from __future__ import annotations

from collections.abc import Iterable
from typing import TypeAlias

import numpy as np

from .numeric import Float64Array, float64_rows, normalized_rows, tuple_rows
from .vector import Vector3

Matrix4: TypeAlias = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]

GTA_SOURCE_AXIS_TRANSFORM = np.array(
    (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, -1.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ),
    dtype=np.float64,
)


def matrix4(value: object) -> Float64Array:
    result = np.asarray(value, dtype=np.float64, copy=None)
    if result.shape != (4, 4):
        raise ValueError(f"Expected a 4x4 matrix, got shape {result.shape!r}")
    if not np.isfinite(result).all():
        raise ValueError("Matrix contains non-finite values")
    return result


def gta_source_transform(value: object) -> Float64Array:
    return GTA_SOURCE_AXIS_TRANSFORM @ matrix4(value)


def transform_position_array(
    values: Iterable[Vector3] | np.ndarray,
    transform: object,
) -> Float64Array:
    points = float64_rows(values, 3, name="positions")
    if not len(points):
        return points
    basis = matrix4(transform)
    transformed = points @ basis[:3, :3].mT
    transformed += basis[:3, 3]
    return transformed


def transform_positions(
    values: Iterable[Vector3] | np.ndarray,
    transform: object,
) -> list[Vector3]:
    return tuple_rows(transform_position_array(values, transform), columns=3)


def transform_normal_array(
    values: Iterable[Vector3] | np.ndarray,
    transform: object,
    *,
    epsilon: float = 1e-12,
) -> Float64Array:
    normals = float64_rows(values, 3, name="normals")
    if not len(normals):
        return normals
    linear = matrix4(transform)[:3, :3]
    try:
        inverse_linear = np.linalg.inv(linear)
    except np.linalg.LinAlgError:
        inverse_linear = np.linalg.pinv(linear)
    transformed = normals @ inverse_linear
    return normalized_rows(
        transformed,
        fallback=(0.0, 0.0, 1.0),
        epsilon=epsilon,
    )


def transform_normals(
    values: Iterable[Vector3] | np.ndarray,
    transform: object,
    *,
    epsilon: float = 1e-12,
) -> list[Vector3]:
    return tuple_rows(
        transform_normal_array(values, transform, epsilon=epsilon),
        columns=3,
    )


__all__ = [
    "GTA_SOURCE_AXIS_TRANSFORM",
    "Matrix4",
    "gta_source_transform",
    "matrix4",
    "transform_normal_array",
    "transform_normals",
    "transform_position_array",
    "transform_positions",
]
