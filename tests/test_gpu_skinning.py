from __future__ import annotations

import numpy as np
import pytest

from fivefury import (
    GPU_SKINNING_INFLUENCES,
    GpuShaderLanguage,
    GpuSkinning,
    GpuSkinningBindings,
)


def _unpack(value: np.ndarray) -> np.ndarray:
    return np.column_stack(
        tuple((value >> shift) & 0xFF for shift in (0, 8, 16, 24))
    )


def test_gpu_skinning_packs_normalized_four_influence_streams() -> None:
    gpu = GpuSkinning(
        [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
        [(1, 2, 99), (999, 0, 0)],
        [(1.0, 2.0, 0.0), (0.0, 0.0, 0.0)],
    )

    indices = _unpack(gpu.streams.influences[:, 0])
    weights = _unpack(gpu.streams.influences[:, 1])

    assert GPU_SKINNING_INFLUENCES == 4
    assert indices.tolist() == [[1, 2, 0, 0], [0, 0, 0, 0]]
    assert weights.sum(axis=1).tolist() == [255, 0]
    assert gpu.required_bone_count == 3
    assert gpu.streams.influences.dtype == np.uint32
    assert not gpu.streams.influences.flags.writeable
    assert gpu.streams.influences.nbytes == gpu.vertex_count * 8


def test_gpu_skinning_rejects_unsupported_weighted_indices_and_influences() -> None:
    with pytest.raises(ValueError, match="at most 4 influences"):
        GpuSkinning([(0.0, 0.0, 0.0)], [(0, 1, 2, 3, 4)], [(0.2,) * 5])

    with pytest.raises(ValueError, match="indices through 255"):
        GpuSkinning([(0.0, 0.0, 0.0)], [(256,)], [(1.0,)])


def test_gpu_skinning_packs_reusable_affine_palettes() -> None:
    gpu = GpuSkinning([(0.0, 0.0, 0.0)], [(1,)], [(1.0,)])
    matrices = np.repeat(np.eye(4, dtype=np.float32)[None], 2, axis=0)
    matrices[1, 3, :3] = (4.0, 5.0, 6.0)
    output = gpu.palette(2)

    result = gpu.pack_palette(matrices, output=output)

    assert result is output
    np.testing.assert_array_equal(
        output[1],
        ((1.0, 0.0, 0.0, 4.0), (0.0, 1.0, 0.0, 5.0), (0.0, 0.0, 1.0, 6.0)),
    )
    with pytest.raises(ValueError, match="at least 2 bones"):
        gpu.pack_palette(matrices[:1])


def test_gpu_skinning_generates_specialized_shader_contracts() -> None:
    gpu = GpuSkinning(
        [(0.0, 0.0, 0.0)],
        [(0,)],
        [(1.0,)],
        normals=[(0.0, 0.0, 1.0)],
    )
    bindings = GpuSkinningBindings(palette=7, output_positions=8, output_normals=9)

    glsl_vertex = gpu.vertex_library(
        GpuShaderLanguage.GLSL,
        palette_binding=7,
    )
    glsl_compute = gpu.compute_shader(
        GpuShaderLanguage.GLSL,
        bindings=bindings,
        local_size=128,
    )
    hlsl_compute = gpu.compute_shader(
        GpuShaderLanguage.HLSL,
        bindings=bindings,
        local_size=128,
    )

    assert "binding = 7" in glsl_vertex
    assert "layout(local_size_x = 128)" in glsl_compute
    assert "FiveFuryOutputNormals" in glsl_compute
    assert "register(t7)" in hlsl_compute
    assert "[numthreads(128, 1, 1)]" in hlsl_compute
    assert gpu.dispatch_groups(128) == 1


def test_gpu_skinning_omits_normal_buffers_when_absent() -> None:
    gpu = GpuSkinning([(0.0, 0.0, 0.0)], [(0,)], [(1.0,)])

    source = gpu.compute_shader()

    assert "FiveFurySourceNormals" not in source
    assert "FiveFuryOutputNormals" not in source


def test_gpu_skinning_validates_bindings_and_local_size() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        GpuSkinningBindings(positions=2, influences=2)

    gpu = GpuSkinning([(0.0, 0.0, 0.0)], [(0,)], [(1.0,)])
    with pytest.raises(ValueError, match="power of two"):
        gpu.compute_shader(local_size=96)
