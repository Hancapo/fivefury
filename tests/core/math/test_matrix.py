from __future__ import annotations

import numpy as np

from fivefury.matrix import transform_normal_array, transform_position_array


def test_transform_position_array_applies_affine_transform() -> None:
    transform = np.eye(4)
    transform[:3, 3] = (10.0, 20.0, 30.0)

    result = transform_position_array(((1.0, 2.0, 3.0),), transform)

    np.testing.assert_allclose(result, ((11.0, 22.0, 33.0),))


def test_transform_normal_array_uses_inverse_linear_transform() -> None:
    transform = np.diag((2.0, 1.0, 1.0, 1.0))

    result = transform_normal_array(((2**-0.5, 2**-0.5, 0.0),), transform)

    np.testing.assert_allclose(
        result,
        ((1.0 / 5**0.5, 2.0 / 5**0.5, 0.0),),
    )


def test_transform_normal_array_falls_back_for_singular_zero_transform() -> None:
    transform = np.zeros((4, 4))

    result = transform_normal_array(((1.0, 0.0, 0.0),), transform)

    assert result.tolist() == [[0.0, 0.0, 1.0]]
