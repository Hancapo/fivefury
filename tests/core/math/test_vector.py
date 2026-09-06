from __future__ import annotations

import itertools
import math

import pytest

from fivefury.vector import (
    Aabb2,
    Aabb3,
    Quaternion,
    Vector2,
    Vector3,
    Vector4,
    interpolate_vector4_many,
    sphere_radius_from_points,
)


def test_aabb2_exposes_named_geometry_operations() -> None:
    bounds = Aabb2.from_center_size(Vector2(4.0, 6.0), Vector2(8.0, 2.0))

    assert bounds.minimum == Vector2(0.0, 5.0)
    assert bounds.maximum == Vector2(8.0, 7.0)
    assert bounds.center == Vector2(4.0, 6.0)
    assert bounds.size == Vector2(8.0, 2.0)


def test_vector_values_are_not_positional_sequences() -> None:
    value = Vector3(1.0, 2.0, 3.0)

    with pytest.raises(TypeError):
        _ = value[0]  # type: ignore[index]
    with pytest.raises(TypeError):
        len(value)  # type: ignore[arg-type]


def test_quat_nlerp_handles_equivalent_opposite_signs() -> None:
    start = Quaternion()
    end = Quaternion(0.0, 0.0, 0.0, -1.0)
    actual = start.nlerp(end, 0.5)

    assert actual.components == pytest.approx(Quaternion().components)
    assert actual.length == pytest.approx(1.0)


def test_quat_nlerp_uses_shortest_hemisphere() -> None:
    start = Quaternion()
    authored_end = Quaternion(0.0, 0.0, -math.sqrt(0.5), -math.sqrt(0.5))

    actual = start.nlerp(authored_end, 0.5)

    assert actual.components == pytest.approx(
        (0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8))
    )
    assert abs(start.nlerp(authored_end, 1.0).dot(authored_end)) == pytest.approx(1.0)


def test_quat_nlerp_preserves_positive_dot_interpolation() -> None:
    actual = Quaternion().nlerp(
        Quaternion(0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)),
        0.5,
    )

    assert actual.components == pytest.approx(
        (0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8))
    )


def test_quat_nlerp_has_finite_deterministic_fallbacks() -> None:
    assert Quaternion(0.0, 0.0, 0.0, 0.0).nlerp(
        Quaternion(0.0, 0.0, 0.0, 0.0), 0.5
    ) == Quaternion()


def test_interpolate_vector4_many_handles_linear_and_shortest_quaternion_paths() -> (
    None
):
    actual = interpolate_vector4_many(
        [Vector4(), Vector4(0.0, 0.0, 0.0, 1.0)],
        [Vector4(2.0, 4.0, 6.0, 8.0), Vector4(0.0, 0.0, -math.sqrt(0.5), -math.sqrt(0.5))],
        0.5,
        [False, True],
    )

    assert actual[0].components == pytest.approx((1.0, 2.0, 3.0, 4.0))
    assert actual[1].components == pytest.approx(
        (0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8))
    )
    assert Quaternion().nlerp(Quaternion(math.nan, 0.0, 0.0, 1.0), math.nan) == Quaternion()


def test_shared_linear_and_quaternion_helpers() -> None:
    assert Vector3(0.0, 2.0, 4.0).lerp(Vector3(2.0, 4.0, 8.0), 0.5) == Vector3(1.0, 3.0, 6.0)
    assert Quaternion(0.0, 0.0, 0.0, -2.0).canonicalized() == Quaternion()


def test_quaternion_series_preserves_shortest_path_sign_continuity() -> None:
    values = Quaternion.make_continuous(
        [
            Quaternion(0.0, 0.0, 0.999, 0.04),
            Quaternion(0.0, 0.0, 1.0, 0.0),
            Quaternion(0.0, 0.0, -0.999, 0.04),
        ]
    )

    assert values[-1].w < 0.0
    assert all(left.dot(right) >= 0.0 for left, right in itertools.pairwise(values))


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
        Quaternion.from_iterable(value).normalized_strict()


def test_shared_point_bounds_and_radius_use_consistent_geometry() -> None:
    points = [Vector3(-2.0, 1.0, 4.0), Vector3(6.0, -3.0, 0.0), Vector3(1.0, 5.0, -8.0)]

    bounds = Aabb3.from_points(points)

    assert bounds.minimum == Vector3(-2.0, -3.0, -8.0)
    assert bounds.maximum == Vector3(6.0, 5.0, 4.0)
    assert sphere_radius_from_points(Vector3(2.0, 1.0, -2.0), points) == pytest.approx(
        math.sqrt(53.0)
    )


def test_shared_point_bounds_reject_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        Aabb3.from_points([])
    assert sphere_radius_from_points(Vector3(), []) == 0.0
