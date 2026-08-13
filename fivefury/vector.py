from __future__ import annotations

import math
from collections.abc import Callable, Iterable

from . import _native_abi3 as _ffi

Vector3 = tuple[float, float, float]
Vector4 = tuple[float, float, float, float]
Quaternion = tuple[float, float, float, float]
Aabb3 = tuple[Vector3, Vector3]


def lerp(start: float, end: float, amount: float) -> float:
    return float(start + ((end - start) * amount))


def lerp_tuple(
    start: tuple[float, ...],
    end: tuple[float, ...],
    amount: float,
) -> tuple[float, ...]:
    return tuple(
        lerp(left, right, amount) for left, right in zip(start, end, strict=True)
    )


def vec3(value: Iterable[float]) -> Vector3:
    x, y, z = value
    return (float(x), float(y), float(z))


def vec4(value: Iterable[float]) -> Vector4:
    x, y, z, w = value
    return (float(x), float(y), float(z), float(w))


def vec4_map(value: Vector4, operation: Callable[[float], float]) -> Vector4:
    return tuple(operation(component) for component in value)  # type: ignore[return-value]


def vec4_map2(
    left: Vector4,
    right: Vector4,
    operation: Callable[[float, float], float],
) -> Vector4:
    return tuple(operation(left[index], right[index]) for index in range(4))  # type: ignore[return-value]


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


def vec_normalize(
    value: Vector3, fallback: Vector3 = (0.0, 0.0, 1.0), *, epsilon: float = 1e-8
) -> Vector3:
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
    return vec_add(
        value, vec_add(vec_scale(uv, 2.0 * w * inverse_length), vec_scale(uuv, 2.0))
    )


def quat_normalize(
    value: Quaternion,
    fallback: Quaternion = (0.0, 0.0, 0.0, 1.0),
    *,
    epsilon: float = 1e-12,
) -> Quaternion:
    x, y, z, w = (float(component) for component in value)
    if not all(math.isfinite(component) for component in (x, y, z, w)):
        return fallback
    length = math.sqrt((x * x) + (y * y) + (z * z) + (w * w))
    if not math.isfinite(length) or length <= epsilon:
        return fallback
    inverse = 1.0 / length
    return (x * inverse, y * inverse, z * inverse, w * inverse)


def quat_inverse(value: Quaternion) -> Quaternion:
    x, y, z, w = quat_normalize(value)
    return (-x, -y, -z, w)


def quat_multiply_raw(left: Quaternion, right: Quaternion) -> Quaternion:
    x1, y1, z1, w1 = left
    x2, y2, z2, w2 = right
    return (
        (w1 * x2) + (x1 * w2) + (y1 * z2) - (z1 * y2),
        (w1 * y2) - (x1 * z2) + (y1 * w2) + (z1 * x2),
        (w1 * z2) + (x1 * y2) - (y1 * x2) + (z1 * w2),
        (w1 * w2) - (x1 * x2) - (y1 * y2) - (z1 * z2),
    )


def quat_multiply(left: Quaternion, right: Quaternion) -> Quaternion:
    return quat_normalize(quat_multiply_raw(left, right))


def quat_from_euler_xyz_raw(value: Vector3) -> Quaternion:
    x, y, z = value
    cx, sx = math.cos(x * 0.5), math.sin(x * 0.5)
    cy, sy = math.cos(y * 0.5), math.sin(y * 0.5)
    cz, sz = math.cos(z * 0.5), math.sin(z * 0.5)
    return (
        (sx * cy * cz) - (cx * sy * sz),
        (cx * sy * cz) + (sx * cy * sz),
        (cx * cy * sz) - (sx * sy * cz),
        (cx * cy * cz) + (sx * sy * sz),
    )


def quat_from_euler_xyz(value: Vector3) -> Quaternion:
    return quat_normalize(quat_from_euler_xyz_raw(value))


def quat_to_euler_xyz(value: Quaternion) -> Vector3:
    x, y, z, w = quat_normalize(value)
    sin_x = 2.0 * ((w * x) + (y * z))
    cos_x = 1.0 - (2.0 * ((x * x) + (y * y)))
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * ((w * y) - (z * x)))))
    roll = math.atan2(sin_x, cos_x)
    yaw = math.atan2(
        2.0 * ((w * z) + (x * y)),
        1.0 - (2.0 * ((y * y) + (z * z))),
    )
    return (roll, pitch, yaw)


def quat_nlerp(start: Quaternion, end: Quaternion, amount: float) -> Quaternion:
    alpha = float(amount)
    if not math.isfinite(alpha):
        alpha = 0.0
    alpha = max(0.0, min(1.0, alpha))

    normalized_start = quat_normalize(start)
    normalized_end = quat_normalize(end, fallback=normalized_start)
    if sum(normalized_start[index] * normalized_end[index] for index in range(4)) < 0.0:
        normalized_end = (
            -normalized_end[0],
            -normalized_end[1],
            -normalized_end[2],
            -normalized_end[3],
        )

    blended = (
        normalized_start[0] + ((normalized_end[0] - normalized_start[0]) * alpha),
        normalized_start[1] + ((normalized_end[1] - normalized_start[1]) * alpha),
        normalized_start[2] + ((normalized_end[2] - normalized_start[2]) * alpha),
        normalized_start[3] + ((normalized_end[3] - normalized_start[3]) * alpha),
    )
    fallback = normalized_start if alpha <= 0.5 else normalized_end
    return quat_normalize(blended, fallback=fallback)


def quat_canonicalize(value: Quaternion) -> Quaternion:
    normalized = quat_normalize(value)
    if normalized[3] < 0.0:
        return tuple(-component for component in normalized)  # type: ignore[return-value]
    return normalized


def interpolate_vector4_many(
    starts: Iterable[Vector4],
    ends: Iterable[Vector4],
    amount: float,
    rotations: Iterable[bool],
) -> list[Vector4]:
    return _ffi.vector_interpolate_many(
        list(starts),
        list(ends),
        float(amount),
        list(rotations),
    )


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
    items = points if isinstance(points, list) else list(points)
    if not items:
        raise ValueError("at least one point is required")
    return _ffi.bounds_from_vertices(items)


def sphere_radius_from_points(center: Vector3, points: Iterable[Vector3]) -> float:
    items = points if isinstance(points, list) else list(points)
    return (
        float(_ffi.bounds_sphere_radius_from_vertices(center, items)) if items else 0.0
    )


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
                points.append(
                    vec_add(quat_rotate_vector(rotation, scaled), translation)
                )
    return aabb_from_points(points)


__all__ = [
    "Aabb3",
    "Quaternion",
    "Vector3",
    "Vector4",
    "aabb_center",
    "aabb_expand",
    "aabb_from_center_size",
    "aabb_from_points",
    "aabb_merge",
    "aabb_radius",
    "aabb_size",
    "aabb_transform",
    "interpolate_vector4_many",
    "lerp",
    "lerp_tuple",
    "quat_canonicalize",
    "quat_from_euler_xyz",
    "quat_from_euler_xyz_raw",
    "quat_inverse",
    "quat_multiply",
    "quat_multiply_raw",
    "quat_nlerp",
    "quat_normalize",
    "quat_rotate_vector",
    "quat_to_euler_xyz",
    "sphere_radius_from_points",
    "vec3",
    "vec4",
    "vec4_map",
    "vec4_map2",
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
