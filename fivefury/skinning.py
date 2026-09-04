from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from . import _native
from .numeric import Float32Array
from .skinning_data import SkinningSource, float32_array, skinning_source


@dataclass(frozen=True, slots=True)
class SkinnedVertices:
    positions: Float32Array
    normals: Float32Array | None = None


def _output_array(value: object, vertex_count: int, *, name: str) -> Float32Array:
    result = np.asarray(value)
    if result.dtype != np.float32 or result.shape != (vertex_count, 3):
        raise ValueError(f"{name} must be an Nx3 float32 array")
    if not result.flags.c_contiguous or not result.flags.writeable:
        raise ValueError(f"{name} must be writable and C-contiguous")
    return result


def _skin_into(
    source: SkinningSource,
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
        self._source = skinning_source(
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
        """Deform into output buffers disjoint from the inputs and each other."""
        matrix_array = float32_array(matrices, (4, 4), name="matrices")
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
    local = float32_array(local_matrices, (4, 4), name="local_matrices")
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
    source = skinning_source(positions, blend_indices, blend_weights, normals)
    matrix_array = float32_array(matrices, (4, 4), name="matrices")
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
