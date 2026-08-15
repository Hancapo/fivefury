from __future__ import annotations

import itertools
import math

import pytest

from fivefury.vector import (
    aabb_from_points,
    interpolate_vector4_many,
    lerp_tuple,
    quat_canonicalize,
    quat_make_continuous,
    quat_nlerp,
    quat_normalize_strict,
    sphere_radius_from_points,
)


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

    assert actual == pytest.approx(
        (0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8))
    )
    assert abs(
        _dot(quat_nlerp(start, authored_end, 1.0), authored_end)
    ) == pytest.approx(1.0)


def test_quat_nlerp_preserves_positive_dot_interpolation() -> None:
    actual = quat_nlerp(
        (0.0, 0.0, 0.0, 1.0),
        (0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)),
        0.5,
    )

    assert actual == pytest.approx(
        (0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8))
    )


def test_quat_nlerp_has_finite_deterministic_fallbacks() -> None:
    assert quat_nlerp((0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), 0.5) == (
        0.0,
        0.0,
        0.0,
        1.0,
    )


def test_interpolate_vector4_many_handles_linear_and_shortest_quaternion_paths() -> (
    None
):
    actual = interpolate_vector4_many(
        [(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)],
        [(2.0, 4.0, 6.0, 8.0), (0.0, 0.0, -math.sqrt(0.5), -math.sqrt(0.5))],
        0.5,
        [False, True],
    )

    assert actual[0] == pytest.approx((1.0, 2.0, 3.0, 4.0))
    assert actual[1] == pytest.approx(
        (0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8))
    )
    assert quat_nlerp((0.0, 0.0, 0.0, 1.0), (math.nan, 0.0, 0.0, 1.0), math.nan) == (
        0.0,
        0.0,
        0.0,
        1.0,
    )


def test_shared_linear_and_quaternion_helpers() -> None:
    assert lerp_tuple((0.0, 2.0, 4.0), (2.0, 4.0, 8.0), 0.5) == (1.0, 3.0, 6.0)
    assert quat_canonicalize((0.0, 0.0, 0.0, -2.0)) == (0.0, 0.0, 0.0, 1.0)


def test_quaternion_series_preserves_shortest_path_sign_continuity() -> None:
    values = quat_make_continuous(
        [
            (0.0, 0.0, 0.999, 0.04),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, -0.999, 0.04),
        ]
    )

    assert values[-1][3] < 0.0
    assert all(_dot(left, right) >= 0.0 for left, right in itertools.pairwise(values))


@pytest.mark.parametrize(
    "value",
    [
        (0.0, 0.0, 0.0, 0.0),
        (float("nan"), 0.0, 0.0, 1.0),
        (float("inf"), 0.0, 0.0, 1.0),
    ],
)
def test_strict_quaternion_normalization_rejects_invalid_values(value) -> None:
    with pytest.raises(ValueError):
        quat_normalize_strict(value)


def test_shared_point_bounds_and_radius_use_consistent_geometry() -> None:
    points = [(-2.0, 1.0, 4.0), (6.0, -3.0, 0.0), (1.0, 5.0, -8.0)]

    minimum, maximum = aabb_from_points(points)

    assert minimum == (-2.0, -3.0, -8.0)
    assert maximum == (6.0, 5.0, 4.0)
    assert sphere_radius_from_points((2.0, 1.0, -2.0), points) == pytest.approx(
        math.sqrt(53.0)
    )


def test_shared_point_bounds_reject_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        aabb_from_points([])
    assert sphere_radius_from_points((0.0, 0.0, 0.0), []) == 0.0
