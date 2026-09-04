import numpy as np
import pytest

from fivefury import GpuSkinning, SkinnedVertices, SkinningBatch


@pytest.mark.parametrize(
    "source_slice,target_slice",
    [
        (slice(0, 2), slice(1, 3)),
        (slice(1, 3), slice(0, 2)),
        (slice(0, 2), slice(0, 2)),
    ],
)
def test_skinning_rejects_input_output_overlap_without_writing(
    source_slice, target_slice
):
    data = np.arange(9, dtype=np.float32).reshape(3, 3)
    original = data.copy()
    batch = SkinningBatch(data[source_slice], [[0], [0]], [[1.0], [1.0]])
    with pytest.raises(ValueError, match="overlap"):
        batch.skin(
            np.eye(4, dtype=np.float32)[None],
            output=SkinnedVertices(data[target_slice]),
        )
    np.testing.assert_array_equal(data, original)


def test_skinning_rejects_output_output_overlap():
    batch = SkinningBatch([[0, 0, 0]], [[0]], [[1]], normals=[[0, 0, 1]])
    output = np.zeros((1, 3), dtype=np.float32)
    with pytest.raises(ValueError, match="each other"):
        batch.skin(
            np.eye(4, dtype=np.float32)[None], output=SkinnedVertices(output, output)
        )


def test_disjoint_views_of_same_allocation_are_supported():
    data = np.arange(12, dtype=np.float32).reshape(4, 3)
    batch = SkinningBatch(data[:2], [[0], [0]], [[1], [1]])
    result = batch.skin(
        np.eye(4, dtype=np.float32)[None], output=SkinnedVertices(data[2:])
    )
    np.testing.assert_array_equal(result.positions, data[:2])


def test_palette_rejects_overlapping_numpy_view():
    matrices = np.arange(16, dtype=np.float32).reshape(1, 4, 4)
    before = matrices.copy()
    gpu = GpuSkinning([[0, 0, 0]], [[0]], [[1]])
    with pytest.raises(ValueError, match="overlap"):
        gpu.pack_palette(matrices, output=matrices.reshape(-1)[:12].reshape(1, 3, 4))
    np.testing.assert_array_equal(matrices, before)
