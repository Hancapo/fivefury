from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Iterable, Iterator

from . import _native_abi3 as _ffi


def lerp(start: float, end: float, amount: float) -> float:
    return float(start + ((end - start) * amount))


def _components(value: Iterable[float], size: int, name: str) -> tuple[float, ...]:
    result = tuple(float(component) for component in value)
    if len(result) != size:
        raise ValueError(f"{name} requires exactly {size} components")
    return result


class _FloatValue:
    __slots__ = ()

    @property
    def components(self) -> tuple[float, ...]:
        raise NotImplementedError

    def __iter__(self) -> Iterator[float]:
        return iter(self.components)

    def __array__(self, dtype=None, copy=None):
        import numpy as np

        return np.array(self.components, dtype=dtype, copy=copy)

    def as_tuple(self) -> tuple[float, ...]:
        return self.components

    @property
    def is_finite(self) -> bool:
        return all(math.isfinite(component) for component in self.components)


@dataclasses.dataclass(frozen=True, slots=True)
class Vector2(_FloatValue):
    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))

    @classmethod
    def from_iterable(cls, value: Iterable[float]) -> Vector2:
        return cls(*_components(value, 2, cls.__name__))

    @property
    def components(self) -> tuple[float, float]:
        return (self.x, self.y)

    def __add__(self, other: Vector2) -> Vector2:
        if not isinstance(other, Vector2):
            return NotImplemented
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vector2) -> Vector2:
        if not isinstance(other, Vector2):
            return NotImplemented
        return Vector2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vector2:
        return Vector2(self.x * float(scalar), self.y * float(scalar))

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> Vector2:
        return self * (1.0 / float(scalar))

    def __neg__(self) -> Vector2:
        return Vector2(-self.x, -self.y)

    def dot(self, other: Vector2) -> float:
        return (self.x * other.x) + (self.y * other.y)

    @property
    def length_squared(self) -> float:
        return self.dot(self)

    @property
    def length(self) -> float:
        return math.sqrt(self.length_squared)

    def distance_to(self, other: Vector2) -> float:
        return (self - other).length

    def normalized(self, *, epsilon: float = 1e-8) -> Vector2:
        length = self.length
        if length <= epsilon:
            raise ValueError("Cannot normalize a zero-length Vector2")
        return self / length

    def lerp(self, other: Vector2, amount: float) -> Vector2:
        return Vector2(lerp(self.x, other.x, amount), lerp(self.y, other.y, amount))


@dataclasses.dataclass(frozen=True, slots=True)
class Vector3(_FloatValue):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "z", float(self.z))

    @classmethod
    def from_iterable(cls, value: Iterable[float]) -> Vector3:
        return cls(*_components(value, 3, cls.__name__))

    @property
    def components(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def __add__(self, other: Vector3) -> Vector3:
        if not isinstance(other, Vector3):
            return NotImplemented
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vector3) -> Vector3:
        if not isinstance(other, Vector3):
            return NotImplemented
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vector3:
        value = float(scalar)
        return Vector3(self.x * value, self.y * value, self.z * value)

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> Vector3:
        return self * (1.0 / float(scalar))

    def __neg__(self) -> Vector3:
        return Vector3(-self.x, -self.y, -self.z)

    def dot(self, other: Vector3) -> float:
        return (self.x * other.x) + (self.y * other.y) + (self.z * other.z)

    def cross(self, other: Vector3) -> Vector3:
        return Vector3(
            (self.y * other.z) - (self.z * other.y),
            (self.z * other.x) - (self.x * other.z),
            (self.x * other.y) - (self.y * other.x),
        )

    @property
    def length_squared(self) -> float:
        return self.dot(self)

    @property
    def length(self) -> float:
        return math.sqrt(self.length_squared)

    def distance_to(self, other: Vector3) -> float:
        return (self - other).length

    def normalized(
        self,
        *,
        fallback: Vector3 | None = None,
        epsilon: float = 1e-8,
    ) -> Vector3:
        length = self.length
        if length <= epsilon:
            if fallback is None:
                raise ValueError("Cannot normalize a zero-length Vector3")
            return fallback
        return self / length

    def lerp(self, other: Vector3, amount: float) -> Vector3:
        return Vector3(
            lerp(self.x, other.x, amount),
            lerp(self.y, other.y, amount),
            lerp(self.z, other.z, amount),
        )

    @classmethod
    def minimum(cls, values: Iterable[Vector3]) -> Vector3:
        items = tuple(values)
        if not items:
            raise ValueError("at least one vector is required")
        return cls(
            min(value.x for value in items),
            min(value.y for value in items),
            min(value.z for value in items),
        )

    @classmethod
    def maximum(cls, values: Iterable[Vector3]) -> Vector3:
        items = tuple(values)
        if not items:
            raise ValueError("at least one vector is required")
        return cls(
            max(value.x for value in items),
            max(value.y for value in items),
            max(value.z for value in items),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Vector4(_FloatValue):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "z", float(self.z))
        object.__setattr__(self, "w", float(self.w))

    @classmethod
    def from_iterable(cls, value: Iterable[float]) -> Vector4:
        return cls(*_components(value, 4, cls.__name__))

    @property
    def components(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.z, self.w)

    @property
    def xyz(self) -> Vector3:
        return Vector3(self.x, self.y, self.z)

    def __add__(self, other: Vector4) -> Vector4:
        if not isinstance(other, Vector4):
            return NotImplemented
        return Vector4(*(left + right for left, right in zip(self, other, strict=True)))

    def __sub__(self, other: Vector4) -> Vector4:
        if not isinstance(other, Vector4):
            return NotImplemented
        return Vector4(*(left - right for left, right in zip(self, other, strict=True)))

    def __mul__(self, scalar: float) -> Vector4:
        value = float(scalar)
        return Vector4(*(component * value for component in self))

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> Vector4:
        return self * (1.0 / float(scalar))

    def __neg__(self) -> Vector4:
        return Vector4(*(-component for component in self))

    def dot(self, other: Vector4) -> float:
        return sum(left * right for left, right in zip(self, other, strict=True))

    def map(self, operation: Callable[[float], float]) -> Vector4:
        return Vector4(*(operation(component) for component in self))

    def map2(
        self,
        other: Vector4,
        operation: Callable[[float, float], float],
    ) -> Vector4:
        return Vector4(
            *(operation(left, right) for left, right in zip(self, other, strict=True))
        )

    def lerp(self, other: Vector4, amount: float) -> Vector4:
        return Vector4(
            *(lerp(left, right, amount) for left, right in zip(self, other, strict=True))
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Quaternion(_FloatValue):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "z", float(self.z))
        object.__setattr__(self, "w", float(self.w))

    @classmethod
    def from_iterable(cls, value: Iterable[float]) -> Quaternion:
        return cls(*_components(value, 4, cls.__name__))

    @classmethod
    def from_euler_xyz(cls, value: Vector3, *, normalize: bool = True) -> Quaternion:
        cx, sx = math.cos(value.x * 0.5), math.sin(value.x * 0.5)
        cy, sy = math.cos(value.y * 0.5), math.sin(value.y * 0.5)
        cz, sz = math.cos(value.z * 0.5), math.sin(value.z * 0.5)
        result = cls(
            (sx * cy * cz) - (cx * sy * sz),
            (cx * sy * cz) + (sx * cy * sz),
            (cx * cy * sz) - (sx * sy * cz),
            (cx * cy * cz) + (sx * sy * sz),
        )
        return result.normalized() if normalize else result

    @property
    def components(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.z, self.w)

    @property
    def xyz(self) -> Vector3:
        return Vector3(self.x, self.y, self.z)

    def __neg__(self) -> Quaternion:
        return Quaternion(-self.x, -self.y, -self.z, -self.w)

    def dot(self, other: Quaternion) -> float:
        return sum(left * right for left, right in zip(self, other, strict=True))

    @property
    def length_squared(self) -> float:
        return self.dot(self)

    @property
    def length(self) -> float:
        return math.sqrt(self.length_squared)

    def normalized(
        self,
        *,
        fallback: Quaternion | None = None,
        epsilon: float = 1e-12,
    ) -> Quaternion:
        fallback = fallback or Quaternion()
        if not self.is_finite:
            return fallback
        length = self.length
        if not math.isfinite(length) or length <= epsilon:
            return fallback
        inverse = 1.0 / length
        return Quaternion(
            self.x * inverse,
            self.y * inverse,
            self.z * inverse,
            self.w * inverse,
        )

    def normalized_strict(self, *, epsilon: float = 1e-12) -> Quaternion:
        if not self.is_finite:
            raise ValueError("Quaternion components must be finite")
        length = self.length
        if length <= epsilon:
            raise ValueError("Quaternion length must be greater than zero")
        inverse = 1.0 / length
        return Quaternion(
            self.x * inverse,
            self.y * inverse,
            self.z * inverse,
            self.w * inverse,
        )

    def inverse(self) -> Quaternion:
        normalized = self.normalized()
        return Quaternion(-normalized.x, -normalized.y, -normalized.z, normalized.w)

    def multiplied(self, other: Quaternion, *, normalize: bool = True) -> Quaternion:
        result = Quaternion(
            (self.w * other.x)
            + (self.x * other.w)
            + (self.y * other.z)
            - (self.z * other.y),
            (self.w * other.y)
            - (self.x * other.z)
            + (self.y * other.w)
            + (self.z * other.x),
            (self.w * other.z)
            + (self.x * other.y)
            - (self.y * other.x)
            + (self.z * other.w),
            (self.w * other.w)
            - (self.x * other.x)
            - (self.y * other.y)
            - (self.z * other.z),
        )
        return result.normalized() if normalize else result

    def __mul__(self, other: Quaternion) -> Quaternion:
        if not isinstance(other, Quaternion):
            return NotImplemented
        return self.multiplied(other)

    def rotate(self, value: Vector3) -> Vector3:
        length_squared = self.length_squared
        if length_squared <= 1e-16:
            return value
        inverse_length = 1.0 / math.sqrt(length_squared)
        axis = self.xyz * inverse_length
        uv = axis.cross(value)
        uuv = axis.cross(uv)
        return value + (uv * (2.0 * self.w * inverse_length)) + (uuv * 2.0)

    def nlerp(self, other: Quaternion, amount: float) -> Quaternion:
        alpha = float(amount)
        if not math.isfinite(alpha):
            alpha = 0.0
        alpha = max(0.0, min(1.0, alpha))
        start = self.normalized()
        end = other.normalized(fallback=start)
        if start.dot(end) < 0.0:
            end = -end
        blended = Quaternion(
            lerp(start.x, end.x, alpha),
            lerp(start.y, end.y, alpha),
            lerp(start.z, end.z, alpha),
            lerp(start.w, end.w, alpha),
        )
        return blended.normalized(fallback=start if alpha <= 0.5 else end)

    def canonicalized(self) -> Quaternion:
        normalized = self.normalized()
        return -normalized if normalized.w < 0.0 else normalized

    def angular_error_degrees(self, other: Quaternion) -> float:
        if self.length <= 1e-12 or other.length <= 1e-12:
            return float("inf")
        cosine = min(max(abs(self.dot(other)) / (self.length * other.length), -1.0), 1.0)
        return math.degrees(2.0 * math.acos(cosine))

    def to_euler_xyz(self) -> Vector3:
        value = self.normalized()
        sin_x = 2.0 * ((value.w * value.x) + (value.y * value.z))
        cos_x = 1.0 - (2.0 * ((value.x * value.x) + (value.y * value.y)))
        return Vector3(
            math.atan2(sin_x, cos_x),
            math.asin(
                max(-1.0, min(1.0, 2.0 * ((value.w * value.y) - (value.z * value.x))))
            ),
            math.atan2(
                2.0 * ((value.w * value.z) + (value.x * value.y)),
                1.0 - (2.0 * ((value.y * value.y) + (value.z * value.z))),
            ),
        )

    @classmethod
    def make_continuous(cls, values: Iterable[Quaternion]) -> list[Quaternion]:
        result: list[Quaternion] = []
        for index, value in enumerate(values):
            try:
                normalized = value.normalized_strict()
            except ValueError as error:
                raise ValueError(f"Invalid quaternion at sample {index}: {error}") from error
            if result and result[-1].dot(normalized) < 0.0:
                normalized = -normalized
            result.append(normalized)
        return result


_ZERO_VECTOR3 = Vector3()
_ONE_VECTOR3 = Vector3(1.0, 1.0, 1.0)
_UP_VECTOR3 = Vector3(0.0, 0.0, 1.0)
_IDENTITY_QUATERNION = Quaternion()


@dataclasses.dataclass(frozen=True, slots=True)
class Aabb2:
    minimum: Vector2
    maximum: Vector2

    def __post_init__(self) -> None:
        if not isinstance(self.minimum, Vector2) or not isinstance(self.maximum, Vector2):
            raise TypeError("Aabb2 minimum and maximum must be Vector2 instances")

    @classmethod
    def from_center_size(cls, center: Vector2, size: Vector2) -> Aabb2:
        half = size * 0.5
        return cls(center - half, center + half)

    def __iter__(self) -> Iterator[Vector2]:
        yield self.minimum
        yield self.maximum

    @property
    def center(self) -> Vector2:
        return (self.minimum + self.maximum) * 0.5

    @property
    def size(self) -> Vector2:
        return self.maximum - self.minimum

    def expanded(self, padding: float) -> Aabb2:
        if padding <= 0.0:
            return self
        pad = Vector2(float(padding), float(padding))
        return Aabb2(self.minimum - pad, self.maximum + pad)

    def merged(self, other: Aabb2) -> Aabb2:
        return Aabb2(
            Vector2(
                min(self.minimum.x, other.minimum.x),
                min(self.minimum.y, other.minimum.y),
            ),
            Vector2(
                max(self.maximum.x, other.maximum.x),
                max(self.maximum.y, other.maximum.y),
            ),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Aabb3:
    minimum: Vector3
    maximum: Vector3

    def __post_init__(self) -> None:
        if not isinstance(self.minimum, Vector3) or not isinstance(self.maximum, Vector3):
            raise TypeError("Aabb3 minimum and maximum must be Vector3 instances")

    @classmethod
    def from_center_size(cls, center: Vector3, size: Vector3) -> Aabb3:
        half = size * 0.5
        return cls(center - half, center + half)

    @classmethod
    def from_points(cls, points: Iterable[Vector3]) -> Aabb3:
        items = list(points)
        if not items:
            raise ValueError("at least one point is required")
        minimum, maximum = _ffi.bounds_from_vertices([point.as_tuple() for point in items])
        return cls(Vector3.from_iterable(minimum), Vector3.from_iterable(maximum))

    def __iter__(self) -> Iterator[Vector3]:
        yield self.minimum
        yield self.maximum

    @property
    def center(self) -> Vector3:
        return (self.minimum + self.maximum) * 0.5

    @property
    def size(self) -> Vector3:
        return self.maximum - self.minimum

    @property
    def radius(self) -> float:
        size = self.size
        if size.x <= 0.0 and size.y <= 0.0 and size.z <= 0.0:
            return 0.0
        return size.length * 0.5

    def expanded(self, padding: float) -> Aabb3:
        if padding <= 0.0:
            return self
        pad = Vector3(float(padding), float(padding), float(padding))
        return Aabb3(self.minimum - pad, self.maximum + pad)

    def merged(self, other: Aabb3) -> Aabb3:
        return Aabb3(
            Vector3(
                min(self.minimum.x, other.minimum.x),
                min(self.minimum.y, other.minimum.y),
                min(self.minimum.z, other.minimum.z),
            ),
            Vector3(
                max(self.maximum.x, other.maximum.x),
                max(self.maximum.y, other.maximum.y),
                max(self.maximum.z, other.maximum.z),
            ),
        )

    def transformed(
        self,
        *,
        translation: Vector3 = _ZERO_VECTOR3,
        rotation: Quaternion = _IDENTITY_QUATERNION,
        scale: Vector3 = _ONE_VECTOR3,
    ) -> Aabb3:
        points = []
        for x in (self.minimum.x, self.maximum.x):
            for y in (self.minimum.y, self.maximum.y):
                for z in (self.minimum.z, self.maximum.z):
                    scaled = Vector3(x * scale.x, y * scale.y, z * scale.z)
                    points.append(rotation.rotate(scaled) + translation)
        return Aabb3.from_points(points)


def interpolate_vector4_many(
    starts: Iterable[Vector4 | Quaternion],
    ends: Iterable[Vector4 | Quaternion],
    amount: float,
    rotations: Iterable[bool],
) -> list[Vector4 | Quaternion]:
    start_values = list(starts)
    end_values = list(ends)
    rotation_flags = list(rotations)
    values = _ffi.vector_interpolate_many(
        [value.as_tuple() for value in start_values],
        [value.as_tuple() for value in end_values],
        float(amount),
        rotation_flags,
    )
    return [
        Quaternion.from_iterable(value) if is_rotation else Vector4.from_iterable(value)
        for value, is_rotation in zip(values, rotation_flags, strict=True)
    ]


def sphere_radius_from_points(center: Vector3, points: Iterable[Vector3]) -> float:
    items = list(points)
    return (
        float(
            _ffi.bounds_sphere_radius_from_vertices(
                center.as_tuple(),
                [point.as_tuple() for point in items],
            )
        )
        if items
        else 0.0
    )


__all__ = [
    "Aabb2",
    "Aabb3",
    "Quaternion",
    "Vector2",
    "Vector3",
    "Vector4",
    "interpolate_vector4_many",
    "lerp",
    "sphere_radius_from_points",
]
