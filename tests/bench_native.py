import numpy as np
import pytest

from fivefury import SkinningBatch
from fivefury._native import _ydr_split_mesh_indices
from fivefury.binary import BinaryDocument, BinaryScalarType

pytestmark = pytest.mark.performance


@pytest.fixture
def scalar_document():
    return BinaryDocument(np.arange(1_000_000, dtype=np.uint32).tobytes())


def test_binary_scalar_list_read(benchmark, scalar_document):
    values = benchmark(
        scalar_document.read_array, 0, 1_000_000, BinaryScalarType.UNSIGNED_INT
    )
    assert len(values) == 1_000_000
    assert values[-1] == 999_999


def test_binary_zero_copy_view(benchmark, scalar_document):
    values = benchmark(
        scalar_document.array, 0, 1_000_000, BinaryScalarType.UNSIGNED_INT
    )
    assert values[-1] == 999_999
    assert not values.flags.owndata
    assert not values.flags.writeable


def test_mesh_split_already_within_limit(benchmark):
    indices = (np.arange(900_000, dtype=np.uint32) % 60_000).tolist()
    assert benchmark(_ydr_split_mesh_indices, indices, 60_000, 65_535) is None


def test_skinning_reuses_output_buffers(benchmark):
    count = 60_000
    positions = np.arange(count * 3, dtype=np.float32).reshape(count, 3)
    indices = np.tile(np.arange(4, dtype=np.uint32), (count, 1))
    batch = SkinningBatch(
        positions, indices, np.full((count, 4), 0.25, dtype=np.float32)
    )
    matrices = np.repeat(np.eye(4, dtype=np.float32)[None], 4, axis=0)
    output = batch.buffers()
    result = benchmark(batch.skin, matrices, output=output)
    assert result is output
    np.testing.assert_array_equal(result.positions, positions)
