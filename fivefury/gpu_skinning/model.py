from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .. import _native
from ..numeric import Float32Array
from ..skinning_data import float32_array, skinning_source
from .shaders import compute_shader, vertex_library
from .types import (
    GPU_SKINNING_INFLUENCES,
    GPU_SKINNING_LOCAL_SIZE,
    GpuShaderLanguage,
    GpuSkinningBindings,
)

UInt32Array = npt.NDArray[np.uint32]
_DEFAULT_BINDINGS = GpuSkinningBindings()


@dataclass(frozen=True, slots=True)
class GpuSkinningStreams:
    positions: Float32Array
    influences: UInt32Array
    normals: Float32Array | None = None

    @property
    def nbytes(self) -> int:
        normal_bytes = 0 if self.normals is None else self.normals.nbytes
        return self.positions.nbytes + self.influences.nbytes + normal_bytes


def _packed_influences(
    indices: UInt32Array,
    weights: Float32Array,
) -> tuple[UInt32Array, int]:
    influence_count = indices.shape[1]
    if influence_count > GPU_SKINNING_INFLUENCES:
        raise ValueError(
            f"GPU skinning supports at most {GPU_SKINNING_INFLUENCES} influences"
        )
    vertex_count = len(indices)
    padded_indices = np.zeros(
        (vertex_count, GPU_SKINNING_INFLUENCES),
        dtype=np.uint32,
    )
    padded_weights = np.zeros(
        (vertex_count, GPU_SKINNING_INFLUENCES),
        dtype=np.float32,
    )
    padded_indices[:, :influence_count] = indices
    padded_weights[:, :influence_count] = weights

    sums = padded_weights.sum(axis=1)
    active_rows = sums > 1.0e-8
    normalized = np.zeros_like(padded_weights)
    np.divide(
        padded_weights,
        sums[:, None],
        out=normalized,
        where=active_rows[:, None],
    )
    quantized = np.floor(normalized * 255.0 + 0.5).astype(np.int16)
    rows = np.flatnonzero(active_rows)
    if len(rows):
        dominant = np.argmax(normalized[rows], axis=1)
        remainder = 255 - quantized[rows].sum(axis=1)
        quantized[rows, dominant] += remainder
    if np.any((quantized < 0) | (quantized > 255)):
        raise ValueError("blend weights cannot be represented as normalized bytes")

    weighted = quantized > 0
    if np.any(padded_indices[weighted] > 255):
        raise ValueError("GPU skinning supports weighted bone indices through 255")
    padded_indices[~weighted] = 0
    required_bone_count = (
        int(padded_indices[weighted].max()) + 1 if np.any(weighted) else 0
    )
    quantized_u32 = quantized.astype(np.uint32)
    packed = np.empty((vertex_count, 2), dtype=np.uint32)
    packed[:, 0] = (
        padded_indices[:, 0]
        | (padded_indices[:, 1] << 8)
        | (padded_indices[:, 2] << 16)
        | (padded_indices[:, 3] << 24)
    )
    packed[:, 1] = (
        quantized_u32[:, 0]
        | (quantized_u32[:, 1] << 8)
        | (quantized_u32[:, 2] << 16)
        | (quantized_u32[:, 3] << 24)
    )
    packed.flags.writeable = False
    return packed, required_bone_count


class GpuSkinning:
    """GPU-resident skinning data and specialized shader sources."""

    __slots__ = ("required_bone_count", "streams")

    def __init__(
        self,
        positions: object,
        blend_indices: object,
        blend_weights: object,
        *,
        normals: object | None = None,
    ) -> None:
        source = skinning_source(
            positions,
            blend_indices,
            blend_weights,
            normals,
        )
        influences, required_bone_count = _packed_influences(
            source.blend_indices,
            source.blend_weights,
        )
        self.streams = GpuSkinningStreams(
            positions=source.positions,
            influences=influences,
            normals=source.normals,
        )
        self.required_bone_count = required_bone_count

    @property
    def vertex_count(self) -> int:
        return len(self.streams.positions)

    @property
    def has_normals(self) -> bool:
        return self.streams.normals is not None

    def palette(self, bone_count: int | None = None) -> Float32Array:
        """Allocate a reusable three-row affine palette."""
        count = self.required_bone_count if bone_count is None else int(bone_count)
        if count < self.required_bone_count:
            raise ValueError(
                f"bone_count must be at least {self.required_bone_count}"
            )
        return np.empty((count, 3, 4), dtype=np.float32)

    def pack_palette(
        self,
        matrices: object,
        *,
        output: object | None = None,
    ) -> Float32Array:
        """Pack row-vector 4x4 matrices into a reusable GPU palette."""
        matrix_array = float32_array(matrices, (4, 4), name="matrices")
        if len(matrix_array) < self.required_bone_count:
            raise ValueError(
                f"matrices must contain at least {self.required_bone_count} bones"
            )
        if output is None:
            target = np.empty((len(matrix_array), 3, 4), dtype=np.float32)
        else:
            target = np.asarray(output)
            if target.dtype != np.float32 or target.shape != (len(matrix_array), 3, 4):
                raise ValueError("output must be a bone_count x 3 x 4 float32 array")
            if not target.flags.c_contiguous or not target.flags.writeable:
                raise ValueError("output must be writable and C-contiguous")
        _native._skin_pack_palette_into(matrix_array, target, len(matrix_array))
        return target

    def dispatch_groups(self, local_size: int = GPU_SKINNING_LOCAL_SIZE) -> int:
        if local_size < 32 or local_size > 1024 or local_size & (local_size - 1):
            raise ValueError("local_size must be a power of two from 32 through 1024")
        return (self.vertex_count + local_size - 1) // local_size

    def vertex_library(
        self,
        language: GpuShaderLanguage = GpuShaderLanguage.GLSL,
        *,
        palette_binding: int = _DEFAULT_BINDINGS.palette,
    ) -> str:
        return vertex_library(language, palette_binding)

    def compute_shader(
        self,
        language: GpuShaderLanguage = GpuShaderLanguage.GLSL,
        *,
        bindings: GpuSkinningBindings = _DEFAULT_BINDINGS,
        local_size: int = GPU_SKINNING_LOCAL_SIZE,
    ) -> str:
        return compute_shader(language, bindings, self.has_normals, local_size)


__all__ = ["GpuSkinning", "GpuSkinningStreams"]
