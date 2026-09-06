from __future__ import annotations

import numpy as np
import pytest

from fivefury.numeric import float64_rows, int64_array, normalized_rows


def test_float64_rows_reuses_compatible_arrays() -> None:
    source = np.arange(12, dtype=np.float64).reshape((4, 3))

    result = float64_rows(source, 3, name="points")

    assert np.shares_memory(result, source)


def test_float64_rows_rejects_nonfinite_values() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        float64_rows(((0.0, float("nan"), 0.0),), 3, name="points")


def test_int64_array_requires_value_preserving_casts() -> None:
    assert int64_array((0.0, 1.0, 2.0), name="indices").tolist() == [0, 1, 2]

    with pytest.raises(ValueError, match="exact"):
        int64_array((0.0, 1.5), name="indices")


def test_normalized_rows_uses_fallback_for_zero_vectors() -> None:
    values = np.asarray(((3.0, 0.0, 0.0), (0.0, 0.0, 0.0)))

    result = normalized_rows(values, fallback=(0.0, 0.0, 1.0), epsilon=1e-8)

    assert result.tolist() == [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
