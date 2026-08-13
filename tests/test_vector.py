from __future__ import annotations

import math

import pytest

from fivefury.vector import interpolate_vector4_many, quat_nlerp


def _dot(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_quat_nlerp_handles_equivalent_opposite_signs() -> None:
    actual = quat_nlerp((0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, -1.0), 0.5)

    assert actual == pytest.approx((0.0, 0.0, 0.0, 1.0))
    assert math.sqrt(_dot(actual, actual)) == pytest.approx(1.0)


def test_quat_nlerp_uses_shortest_hemisphere() -> None:
    start = (0.0, 0.0, 0.0, 1.0)
    authored_end = (0.0, 0.0, -math.sqrt(0.5), -math.sqrt(0.5))

    actual = quat_nlerp(start, authored_end, 0.5)

    assert actual == pytest.approx((0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8)))
    assert abs(_dot(quat_nlerp(start, authored_end, 1.0), authored_end)) == pytest.approx(1.0)


def test_quat_nlerp_preserves_positive_dot_interpolation() -> None:
    actual = quat_nlerp(
        (0.0, 0.0, 0.0, 1.0),
        (0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)),
        0.5,
    )

    assert actual == pytest.approx((0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8)))


def test_quat_nlerp_has_finite_deterministic_fallbacks() -> None:
    assert quat_nlerp((0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), 0.5) == (
        0.0,
        0.0,
        0.0,
        1.0,
    )


def test_interpolate_vector4_many_handles_linear_and_shortest_quaternion_paths() -> None:
    actual = interpolate_vector4_many(
        [(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)],
        [(2.0, 4.0, 6.0, 8.0), (0.0, 0.0, -math.sqrt(0.5), -math.sqrt(0.5))],
        0.5,
        [False, True],
    )

    assert actual[0] == pytest.approx((1.0, 2.0, 3.0, 4.0))
    assert actual[1] == pytest.approx((0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8)))
    assert quat_nlerp((0.0, 0.0, 0.0, 1.0), (math.nan, 0.0, 0.0, 1.0), math.nan) == (
        0.0,
        0.0,
        0.0,
        1.0,
    )
