from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from . import _native
from .numeric import Float32Array


@dataclass(frozen=True, slots=True)
class SkinnedVertices:
    positions: Float32Array
    normals: Float32Array | None = None


def _float32_array(value: object, shape_tail: tuple[int, ...], *, name: str) -> Float32Array:
    result = np.ascontiguousarray(value, dtype=np.float32)
    expected_dimensions = len(shape_tail) + 1
    if result.ndim != expected_dimensions or result.shape[1:] != shape_tail:
        shape = "x".join(("N", *(str(item) for item in shape_tail)))
        raise ValueError(f"{name} must be an {shape} array, got shape {result.shape!r}")
    if not np.isfinite(result).all():
        raise ValueError(f"{name} contains non-finite values")
    return result


def compose_skeleton_matrices(
    local_matrices: object,
    parent_indices: Sequence[int] | np.ndarray,
) -> Float32Array:
    """Compose row-vector local matrices through a skeleton hierarchy."""
    local = _float32_array(local_matrices, (4, 4), name="local_matrices")
    parents = np.ascontiguousarray(parent_indices, dtype=np.int32)
    if parents.ndim != 1 or len(parents) != len(local):
        raise ValueError("parent_indices must contain one value per local matrix")
    raw = _native._skin_compose_matrices(
        memoryview(local),
        memoryview(parents),
        len(local),
    )
    return np.frombuffer(raw, dtype=np.float32).reshape((-1, 4, 4))


def skin_vertices(
    positions: object,
    matrices: object,
    blend_indices: object,
    blend_weights: object,
    *,
    normals: object | None = None,
    normalize_weights: bool = True,
) -> SkinnedVertices:
    """Deform a vertex batch with RAGE row-vector skinning matrices."""
    position_array = _float32_array(positions, (3,), name="positions")
    matrix_array = _float32_array(matrices, (4, 4), name="matrices")
    raw_indices = np.asarray(blend_indices)
    try:
        index_array = np.ascontiguousarray(
            raw_indices.astype(np.uint32, casting="same_value", copy=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("blend_indices must contain exact non-negative integers") from exc
    weight_array = np.ascontiguousarray(blend_weights, dtype=np.float32)
    if index_array.ndim != 2 or index_array.shape[0] != len(position_array):
        raise ValueError("blend_indices must contain one row per vertex")
    if weight_array.shape != index_array.shape:
        raise ValueError("blend_weights must match the blend_indices shape")
    if index_array.shape[1] == 0:
        raise ValueError("at least one blend influence is required")
    if not np.isfinite(weight_array).all() or np.any(weight_array < 0.0):
        raise ValueError("blend_weights must contain finite non-negative values")
    normal_array = (
        None
        if normals is None
        else _float32_array(normals, (3,), name="normals")
    )
    if normal_array is not None and len(normal_array) != len(position_array):
        raise ValueError("normals must contain one row per vertex")

    position_bytes, normal_bytes = _native._skin_vertices(
        memoryview(position_array),
        memoryview(matrix_array),
        memoryview(index_array),
        memoryview(weight_array),
        None if normal_array is None else memoryview(normal_array),
        len(position_array),
        len(matrix_array),
        index_array.shape[1],
        normalize_weights,
    )
    skinned_positions = np.frombuffer(position_bytes, dtype=np.float32).reshape((-1, 3))
    skinned_normals = (
        None
        if normal_bytes is None
        else np.frombuffer(normal_bytes, dtype=np.float32).reshape((-1, 3))
    )
    return SkinnedVertices(positions=skinned_positions, normals=skinned_normals)


__all__ = ["SkinnedVertices", "compose_skeleton_matrices", "skin_vertices"]
