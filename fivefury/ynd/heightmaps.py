from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Sequence

from ..vector import Vector2, Vector3

Triangle = tuple[Vector3, Vector3, Vector3]
Bounds2D = tuple[Vector2, Vector2]


@dataclasses.dataclass(frozen=True, slots=True)
class YndJunctionHeightmap:
    min_xy: Vector2
    min_z: float
    max_z: float
    dim_x: int
    dim_y: int
    data: bytes

    @property
    def position(self) -> Vector2:
        return self.min_xy

    @property
    def values(self) -> list[float]:
        return decode_junction_heightmap(self.data, self.min_z, self.max_z)


def decode_junction_heightmap(data: bytes | bytearray | memoryview, min_z: float, max_z: float) -> list[float]:
    raw = bytes(data)
    min_z = float(min_z)
    max_z = float(max_z)
    if not raw:
        return []
    if math.isclose(min_z, max_z):
        return [min_z for _ in raw]
    scale = (max_z - min_z) / 256.0
    return [min_z + (byte * scale) for byte in raw]


def encode_junction_heightmap(values: Iterable[float], min_z: float | None = None, max_z: float | None = None) -> bytes:
    heights = [float(value) for value in values]
    if not heights:
        return b""
    min_height = quantize_junction_z(min(heights) if min_z is None else float(min_z))
    max_height = quantize_junction_z(max(heights) if max_z is None else float(max_z))
    if max_height < min_height:
        raise ValueError("junction heightmap max_z cannot be lower than min_z")
    if math.isclose(min_height, max_height):
        return bytes(0 for _ in heights)
    step = (max_height - min_height) / 256.0
    return bytes(_clamp_byte(round(max(0.0, height - min_height) / step)) for height in heights)


def build_junction_heightmap(
    *,
    samples: Iterable[Vector3] = (),
    triangles: Iterable[Triangle] = (),
    dim_x: int = 16,
    dim_y: int = 16,
    bounds: Bounds2D | None = None,
    center: Vector2 | None = None,
    size: Vector2 | float | None = None,
    min_z: float | None = None,
    max_z: float | None = None,
    fallback_z: float = 0.0,
    nearest_count: int = 4,
    inverse_distance_power: float = 2.0,
    grid_spacing: float = 2.0,
) -> YndJunctionHeightmap:
    sample_points = list(samples)
    if any(not isinstance(point, Vector3) for point in sample_points):
        raise TypeError("junction heightmap samples must be Vector3 instances")
    triangle_faces = [_triangle(face) for face in triangles]
    if not sample_points and not triangle_faces:
        raise ValueError("junction heightmap generation needs samples or triangles")

    dim_x = _byte_dim(dim_x, "dim_x")
    dim_y = _byte_dim(dim_y, "dim_y")
    min_xy = _resolve_min_xy(sample_points, triangle_faces, bounds, center, size, dim_x, dim_y, grid_spacing)

    raster_values: list[float] = []
    for y_index in range(dim_y):
        y = min_xy.y + (y_index * float(grid_spacing))
        for x_index in range(dim_x):
            x = min_xy.x + (x_index * float(grid_spacing))
            z = _sample_height(
                Vector2(x, y),
                sample_points=sample_points,
                triangles=triangle_faces,
                fallback_z=float(fallback_z),
                nearest_count=int(nearest_count),
                inverse_distance_power=float(inverse_distance_power),
            )
            raster_values.append(z)

    resolved_min_z = quantize_junction_z(min(raster_values) if min_z is None else float(min_z))
    resolved_max_z = quantize_junction_z(max(raster_values) if max_z is None else float(max_z))
    return YndJunctionHeightmap(
        min_xy=min_xy,
        min_z=resolved_min_z,
        max_z=resolved_max_z,
        dim_x=dim_x,
        dim_y=dim_y,
        data=encode_junction_heightmap(raster_values, resolved_min_z, resolved_max_z),
    )


def _sample_height(
    point: Vector2,
    *,
    sample_points: Sequence[Vector3],
    triangles: Sequence[Triangle],
    fallback_z: float,
    nearest_count: int,
    inverse_distance_power: float,
) -> float:
    for triangle in triangles:
        z = _triangle_height_at(point, triangle)
        if z is not None:
            return z
    if sample_points:
        return _interpolate_samples(
            point,
            sample_points,
            nearest_count=max(1, nearest_count),
            power=max(0.001, inverse_distance_power),
        )
    return fallback_z


def _triangle_height_at(point: Vector2, triangle: Triangle) -> float | None:
    a, b, c = triangle
    ax, ay, az = a.x, a.y, a.z
    bx, by, bz = b.x, b.y, b.z
    cx, cy, cz = c.x, c.y, c.z
    px, py = point.x, point.y
    denominator = ((by - cy) * (ax - cx)) + ((cx - bx) * (ay - cy))
    if math.isclose(denominator, 0.0, abs_tol=1e-9):
        return None
    weight_a = (((by - cy) * (px - cx)) + ((cx - bx) * (py - cy))) / denominator
    weight_b = (((cy - ay) * (px - cx)) + ((ax - cx) * (py - cy))) / denominator
    weight_c = 1.0 - weight_a - weight_b
    tolerance = 1e-5
    if weight_a < -tolerance or weight_b < -tolerance or weight_c < -tolerance:
        return None
    return (weight_a * az) + (weight_b * bz) + (weight_c * cz)


def _interpolate_samples(point: Vector2, samples: Sequence[Vector3], *, nearest_count: int, power: float) -> float:
    px, py = point.x, point.y
    distances: list[tuple[float, float]] = []
    for sample in samples:
        distance_sq = ((sample.x - px) ** 2) + ((sample.y - py) ** 2)
        if math.isclose(distance_sq, 0.0, abs_tol=1e-12):
            return sample.z
        distances.append((distance_sq, sample.z))
    distances.sort(key=lambda item: item[0])
    weighted_sum = 0.0
    weight_total = 0.0
    for distance_sq, z in distances[:nearest_count]:
        weight = 1.0 / (distance_sq ** (power * 0.5))
        weighted_sum += z * weight
        weight_total += weight
    return weighted_sum / weight_total if weight_total else samples[0].z


def _resolve_min_xy(
    samples: Sequence[Vector3],
    triangles: Sequence[Triangle],
    bounds: Bounds2D | None,
    center: Vector2 | None,
    size: Vector2 | float | None,
    dim_x: int,
    dim_y: int,
    grid_spacing: float,
) -> Vector2:
    if grid_spacing <= 0.0:
        raise ValueError("junction heightmap grid_spacing must be positive")
    if bounds is not None:
        min_xy, max_xy = bounds
        if not isinstance(min_xy, Vector2) or not isinstance(max_xy, Vector2):
            raise TypeError("junction heightmap bounds must contain Vector2 values")
    elif center is not None and size is not None:
        if not isinstance(center, Vector2):
            raise TypeError("junction heightmap center must be a Vector2")
        resolved_size = _size2(size)
        cx, cy = center.x, center.y
        sx, sy = resolved_size.x, resolved_size.y
        if sx <= 0.0 or sy <= 0.0:
            raise ValueError("junction heightmap size must be positive")
        min_xy = Vector2(cx - (sx * 0.5), cy - (sy * 0.5))
        max_xy = Vector2(cx + (sx * 0.5), cy + (sy * 0.5))
    else:
        points = list(samples)
        for triangle in triangles:
            points.extend(triangle)
        if not points:
            raise ValueError("cannot infer junction heightmap bounds without geometry")
        min_xy = Vector2(min(point.x for point in points), min(point.y for point in points))
        max_xy = Vector2(max(point.x for point in points), max(point.y for point in points))
    if max_xy.x < min_xy.x or max_xy.y < min_xy.y:
        raise ValueError("junction heightmap bounds must be ordered as ((min_x, min_y), (max_x, max_y))")
    if math.isclose(max_xy.x, min_xy.x) or math.isclose(max_xy.y, min_xy.y):
        raise ValueError("junction heightmap bounds must have non-zero width and height")
    stored_width = (dim_x - 1) * grid_spacing
    stored_height = (dim_y - 1) * grid_spacing
    if stored_width and max_xy.x > (min_xy.x + stored_width + 1e-5):
        raise ValueError("junction heightmap dim_x is too small for bounds and grid_spacing")
    if stored_height and max_xy.y > (min_xy.y + stored_height + 1e-5):
        raise ValueError("junction heightmap dim_y is too small for bounds and grid_spacing")
    return min_xy


def _byte_dim(value: int, name: str) -> int:
    dim = int(value)
    if dim <= 0 or dim > 255:
        raise ValueError(f"junction heightmap {name} must be in the 1..255 range")
    return dim


def _triangle(value: Sequence[Vector3]) -> Triangle:
    if len(value) != 3:
        raise ValueError("junction heightmap triangles must have exactly three vertices")
    if any(not isinstance(vertex, Vector3) for vertex in value):
        raise TypeError("junction heightmap triangle vertices must be Vector3 instances")
    return (value[0], value[1], value[2])


def _size2(value: Vector2 | float) -> Vector2:
    if isinstance(value, int | float):
        size = float(value)
        return Vector2(size, size)
    if not isinstance(value, Vector2):
        raise TypeError("junction heightmap size must be a Vector2 or scalar")
    return value


def _clamp_byte(value: int) -> int:
    return max(0, min(255, int(value)))


def quantize_junction_z(value: float) -> float:
    return round(float(value) * 32.0) / 32.0
