from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .numeric import Float32Array


@dataclass(frozen=True, slots=True)
class SkinningSource:
    positions: Float32Array
    blend_indices: np.ndarray
    blend_weights: Float32Array
    normals: Float32Array | None


def float32_array(
    value: object,
    shape_tail: tuple[int, ...],
    *,
    name: str,
) -> Float32Array:
    result = np.ascontiguousarray(value, dtype=np.float32)
    expected_dimensions = len(shape_tail) + 1
    if result.ndim != expected_dimensions or result.shape[1:] != shape_tail:
        shape = "x".join(("N", *(str(item) for item in shape_tail)))
        raise ValueError(f"{name} must be an {shape} array, got shape {result.shape!r}")
    if not np.isfinite(result).all():
        raise ValueError(f"{name} contains non-finite values")
    return result


def skinning_source(
    positions: object,
    blend_indices: object,
    blend_weights: object,
    normals: object | None,
) -> SkinningSource:
    position_array = float32_array(positions, (3,), name="positions")
    raw_indices = np.asarray(blend_indices)
    try:
        index_array = np.ascontiguousarray(
            raw_indices.astype(np.uint32, casting="same_value", copy=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "blend_indices must contain exact non-negative integers"
        ) from exc
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
        None if normals is None else float32_array(normals, (3,), name="normals")
    )
    if normal_array is not None and len(normal_array) != len(position_array):
        raise ValueError("normals must contain one row per vertex")
    return SkinningSource(
        positions=position_array,
        blend_indices=index_array,
        blend_weights=weight_array,
        normals=normal_array,
    )


__all__ = ["SkinningSource", "float32_array", "skinning_source"]
