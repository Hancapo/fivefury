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


@dataclass(frozen=True, slots=True)
class _SkinningSource:
    positions: Float32Array
    blend_indices: np.ndarray
    blend_weights: Float32Array
    normals: Float32Array | None


def _float32_array(
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


def _skinning_source(
    positions: object,
    blend_indices: object,
    blend_weights: object,
    normals: object | None,
) -> _SkinningSource:
    position_array = _float32_array(positions, (3,), name="positions")
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
        None if normals is None else _float32_array(normals, (3,), name="normals")
    )
    if normal_array is not None and len(normal_array) != len(position_array):
        raise ValueError("normals must contain one row per vertex")
    return _SkinningSource(
        positions=position_array,
        blend_indices=index_array,
        blend_weights=weight_array,
        normals=normal_array,
    )


def _output_array(value: object, vertex_count: int, *, name: str) -> Float32Array:
    result = np.asarray(value)
    if result.dtype != np.float32 or result.shape != (vertex_count, 3):
        raise ValueError(f"{name} must be an Nx3 float32 array")
    if not result.flags.c_contiguous or not result.flags.writeable:
        raise ValueError(f"{name} must be writable and C-contiguous")
    return result


def _skin_into(
    source: _SkinningSource,
    matrices: Float32Array,
    output: SkinnedVertices,
    *,
    normalize_weights: bool,
) -> SkinnedVertices:
    output_positions = _output_array(
        output.positions,
        len(source.positions),
        name="output positions",
    )
    if source.normals is None:
        if output.normals is not None:
            raise ValueError("output normals require source normals")
        output_normals = None
    else:
        if output.normals is None:
            raise ValueError(
                "output normals are required when source normals are present"
            )
        output_normals = _output_array(
            output.normals,
            len(source.positions),
            name="output normals",
        )
    _native._skin_vertices_into(
        source.positions,
        matrices,
        source.blend_indices,
        source.blend_weights,
        source.normals,
        output_positions,
        output_normals,
        len(source.positions),
        len(matrices),
        source.blend_indices.shape[1],
        normalize_weights,
    )
    return output


class SkinningBatch:
    """Validated static skinning inputs for repeated per-frame deformation."""

    __slots__ = ("_normalize_weights", "_source")

    def __init__(
        self,
        positions: object,
        blend_indices: object,
        blend_weights: object,
        *,
        normals: object | None = None,
        normalize_weights: bool = True,
    ) -> None:
        self._source = _skinning_source(
            positions,
            blend_indices,
            blend_weights,
            normals,
        )
        self._normalize_weights = bool(normalize_weights)

    @property
    def vertex_count(self) -> int:
        return len(self._source.positions)

    @property
    def influence_count(self) -> int:
        return self._source.blend_indices.shape[1]

    def buffers(self) -> SkinnedVertices:
        """Allocate an output set that can be reused across frames."""
        return SkinnedVertices(
            positions=np.empty_like(self._source.positions),
            normals=(
                None
                if self._source.normals is None
                else np.empty_like(self._source.normals)
            ),
        )

    def skin(
        self,
        matrices: object,
        *,
        output: SkinnedVertices | None = None,
    ) -> SkinnedVertices:
        """Deform into a supplied reusable output set or a new allocation."""
        matrix_array = _float32_array(matrices, (4, 4), name="matrices")
        target = self.buffers() if output is None else output
        return _skin_into(
            self._source,
            matrix_array,
            target,
            normalize_weights=self._normalize_weights,
        )


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
    source = _skinning_source(positions, blend_indices, blend_weights, normals)
    matrix_array = _float32_array(matrices, (4, 4), name="matrices")
    output = SkinnedVertices(
        positions=np.empty_like(source.positions),
        normals=None if source.normals is None else np.empty_like(source.normals),
    )
    return _skin_into(
        source,
        matrix_array,
        output,
        normalize_weights=normalize_weights,
    )


__all__ = [
    "SkinnedVertices",
    "SkinningBatch",
    "compose_skeleton_matrices",
    "skin_vertices",
]
