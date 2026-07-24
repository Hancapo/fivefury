from __future__ import annotations

import math
from collections.abc import Iterable

Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]
Aabb3 = tuple[Vector3, Vector3]


def vec3(value: Iterable[float]) -> Vector3:
    x, y, z = value
    return (float(x), float(y), float(z))


def vec_add(left: Vector3, right: Vector3) -> Vector3:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def vec_sub(left: Vector3, right: Vector3) -> Vector3:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def vec_scale(value: Vector3, scale: float) -> Vector3:
    return (value[0] * scale, value[1] * scale, value[2] * scale)


def vec_dot(left: Vector3, right: Vector3) -> float:
    return (left[0] * right[0]) + (left[1] * right[1]) + (left[2] * right[2])


def vec_cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        (left[1] * right[2]) - (left[2] * right[1]),
        (left[2] * right[0]) - (left[0] * right[2]),
        (left[0] * right[1]) - (left[1] * right[0]),
    )


def vec_length(value: Vector3) -> float:
    return math.sqrt(vec_dot(value, value))


def vec_distance(left: Vector3, right: Vector3) -> float:
    return vec_length(vec_sub(left, right))


def vec_normalize(value: Vector3, fallback: Vector3 = (0.0, 0.0, 1.0), *, epsilon: float = 1e-8) -> Vector3:
    length = vec_length(value)
    if length <= epsilon:
        return fallback
    return vec_scale(value, 1.0 / length)


def quat_rotate_vector(rotation: Quaternion, value: Vector3) -> Vector3:
    x, y, z, w = (float(component) for component in rotation)
    length_sq = (x * x) + (y * y) + (z * z) + (w * w)
    if length_sq <= 1e-16:
        return value
    inverse_length = 1.0 / math.sqrt(length_sq)
    q = (x * inverse_length, y * inverse_length, z * inverse_length)
    uv = vec_cross(q, value)
    uuv = vec_cross(q, uv)
    return vec_add(value, vec_add(vec_scale(uv, 2.0 * w * inverse_length), vec_scale(uuv, 2.0)))


def vec_min(values: Iterable[Vector3]) -> Vector3:
    items = list(values)
    if not items:
        raise ValueError("at least one vector is required")
    return (
        min(value[0] for value in items),
        min(value[1] for value in items),
        min(value[2] for value in items),
    )


def vec_max(values: Iterable[Vector3]) -> Vector3:
    items = list(values)
    if not items:
        raise ValueError("at least one vector is required")
    return (
        max(value[0] for value in items),
        max(value[1] for value in items),
        max(value[2] for value in items),
    )


def aabb_center(minimum: Vector3, maximum: Vector3) -> Vector3:
    return vec_scale(vec_add(minimum, maximum), 0.5)


def aabb_size(minimum: Vector3, maximum: Vector3) -> Vector3:
    return vec_sub(maximum, minimum)


def aabb_radius(minimum: Vector3, maximum: Vector3) -> float:
    size = aabb_size(minimum, maximum)
    if size[0] <= 0.0 and size[1] <= 0.0 and size[2] <= 0.0:
        return 0.0
    return vec_length(size) * 0.5


def aabb_from_center_size(center: Vector3, size: Vector3) -> Aabb3:
    half = vec_scale(size, 0.5)
    return vec_sub(center, half), vec_add(center, half)


def aabb_from_points(points: Iterable[Vector3]) -> Aabb3:
    items = list(points)
    if not items:
        raise ValueError("at least one point is required")
    return vec_min(items), vec_max(items)


def aabb_expand(bounds: Aabb3, padding: float) -> Aabb3:
    if padding <= 0.0:
        return bounds
    pad = (float(padding), float(padding), float(padding))
    return vec_sub(bounds[0], pad), vec_add(bounds[1], pad)


def aabb_merge(left: Aabb3 | None, right: Aabb3 | None) -> Aabb3 | None:
    if right is None:
        return left
    if left is None:
        return right
    return (
        (
            min(left[0][0], right[0][0]),
            min(left[0][1], right[0][1]),
            min(left[0][2], right[0][2]),
        ),
        (
            max(left[1][0], right[1][0]),
            max(left[1][1], right[1][1]),
            max(left[1][2], right[1][2]),
        ),
    )


def aabb_transform(
    bounds: Aabb3,
    *,
    translation: Vector3 = (0.0, 0.0, 0.0),
    rotation: Quaternion = (0.0, 0.0, 0.0, 1.0),
    scale: Vector3 = (1.0, 1.0, 1.0),
) -> Aabb3:
    minimum, maximum = bounds
    points: list[Vector3] = []
    for x in (minimum[0], maximum[0]):
        for y in (minimum[1], maximum[1]):
            for z in (minimum[2], maximum[2]):
                scaled = (x * scale[0], y * scale[1], z * scale[2])
                points.append(vec_add(quat_rotate_vector(rotation, scaled), translation))
    return aabb_from_points(points)


__all__ = [
    "Aabb3",
    "Quaternion",
    "Vector3",
    "aabb_center",
    "aabb_expand",
    "aabb_from_center_size",
    "aabb_from_points",
    "aabb_merge",
    "aabb_radius",
    "aabb_size",
    "aabb_transform",
    "quat_rotate_vector",
    "vec3",
    "vec_add",
    "vec_cross",
    "vec_distance",
    "vec_dot",
    "vec_length",
    "vec_max",
    "vec_min",
    "vec_normalize",
    "vec_scale",
    "vec_sub",
]
