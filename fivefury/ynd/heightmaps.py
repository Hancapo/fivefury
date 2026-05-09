from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Sequence

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]
Triangle = tuple[Vec3, Vec3, Vec3]
Bounds2D = tuple[Vec2, Vec2]


@dataclasses.dataclass(frozen=True, slots=True)
class YndJunctionHeightmap:
    min_xy: Vec2
    min_z: float
    max_z: float
    dim_x: int
    dim_y: int
    data: bytes

    @property
    def position(self) -> Vec2:
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
    samples: Iterable[Vec3] = (),
    triangles: Iterable[Triangle] = (),
    dim_x: int = 16,
    dim_y: int = 16,
    bounds: Bounds2D | None = None,
    center: Vec2 | None = None,
    size: Vec2 | float | None = None,
    min_z: float | None = None,
    max_z: float | None = None,
    fallback_z: float = 0.0,
    nearest_count: int = 4,
    inverse_distance_power: float = 2.0,
    grid_spacing: float = 2.0,
) -> YndJunctionHeightmap:
    sample_points = [_vec3(point) for point in samples]
    triangle_faces = [_triangle(face) for face in triangles]
    if not sample_points and not triangle_faces:
        raise ValueError("junction heightmap generation needs samples or triangles")

    dim_x = _byte_dim(dim_x, "dim_x")
    dim_y = _byte_dim(dim_y, "dim_y")
    min_xy = _resolve_min_xy(sample_points, triangle_faces, bounds, center, size, dim_x, dim_y, grid_spacing)

    raster_values: list[float] = []
    for y_index in range(dim_y):
        y = min_xy[1] + (y_index * float(grid_spacing))
        for x_index in range(dim_x):
            x = min_xy[0] + (x_index * float(grid_spacing))
            z = _sample_height(
                (x, y),
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
    point: Vec2,
    *,
    sample_points: Sequence[Vec3],
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


def _triangle_height_at(point: Vec2, triangle: Triangle) -> float | None:
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = triangle
    px, py = point
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


def _interpolate_samples(point: Vec2, samples: Sequence[Vec3], *, nearest_count: int, power: float) -> float:
    px, py = point
    distances: list[tuple[float, float]] = []
    for x, y, z in samples:
        distance_sq = ((x - px) ** 2) + ((y - py) ** 2)
        if math.isclose(distance_sq, 0.0, abs_tol=1e-12):
            return z
        distances.append((distance_sq, z))
    distances.sort(key=lambda item: item[0])
    weighted_sum = 0.0
    weight_total = 0.0
    for distance_sq, z in distances[:nearest_count]:
        weight = 1.0 / (distance_sq ** (power * 0.5))
        weighted_sum += z * weight
        weight_total += weight
    return weighted_sum / weight_total if weight_total else samples[0][2]


def _resolve_min_xy(
    samples: Sequence[Vec3],
    triangles: Sequence[Triangle],
    bounds: Bounds2D | None,
    center: Vec2 | None,
    size: Vec2 | float | None,
    dim_x: int,
    dim_y: int,
    grid_spacing: float,
) -> Vec2:
    if grid_spacing <= 0.0:
        raise ValueError("junction heightmap grid_spacing must be positive")
    if bounds is not None:
        min_xy, max_xy = (_vec2(bounds[0]), _vec2(bounds[1]))
    elif center is not None and size is not None:
        cx, cy = _vec2(center)
        sx, sy = _size2(size)
        if sx <= 0.0 or sy <= 0.0:
            raise ValueError("junction heightmap size must be positive")
        min_xy = (cx - (sx * 0.5), cy - (sy * 0.5))
        max_xy = (cx + (sx * 0.5), cy + (sy * 0.5))
    else:
        points = list(samples)
        for triangle in triangles:
            points.extend(triangle)
        if not points:
            raise ValueError("cannot infer junction heightmap bounds without geometry")
        min_xy = (min(point[0] for point in points), min(point[1] for point in points))
        max_xy = (max(point[0] for point in points), max(point[1] for point in points))
    if max_xy[0] < min_xy[0] or max_xy[1] < min_xy[1]:
        raise ValueError("junction heightmap bounds must be ordered as ((min_x, min_y), (max_x, max_y))")
    if math.isclose(max_xy[0], min_xy[0]) or math.isclose(max_xy[1], min_xy[1]):
        raise ValueError("junction heightmap bounds must have non-zero width and height")
    stored_width = (dim_x - 1) * grid_spacing
    stored_height = (dim_y - 1) * grid_spacing
    if stored_width and max_xy[0] > (min_xy[0] + stored_width + 1e-5):
        raise ValueError("junction heightmap dim_x is too small for bounds and grid_spacing")
    if stored_height and max_xy[1] > (min_xy[1] + stored_height + 1e-5):
        raise ValueError("junction heightmap dim_y is too small for bounds and grid_spacing")
    return min_xy


def _byte_dim(value: int, name: str) -> int:
    dim = int(value)
    if dim <= 0 or dim > 255:
        raise ValueError(f"junction heightmap {name} must be in the 1..255 range")
    return dim


def _vec2(value: Sequence[float]) -> Vec2:
    return (float(value[0]), float(value[1]))


def _vec3(value: Sequence[float]) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))


def _triangle(value: Sequence[Sequence[float]]) -> Triangle:
    if len(value) != 3:
        raise ValueError("junction heightmap triangles must have exactly three vertices")
    return (_vec3(value[0]), _vec3(value[1]), _vec3(value[2]))


def _size2(value: Vec2 | float) -> Vec2:
    if isinstance(value, int | float):
        size = float(value)
        return (size, size)
    return (float(value[0]), float(value[1]))


def _clamp_byte(value: int) -> int:
    return max(0, min(255, int(value)))


def quantize_junction_z(value: float) -> float:
    return round(float(value) * 32.0) / 32.0
