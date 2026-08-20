from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterator, Sequence

from ..vector import Vector2, Vector3


@dataclasses.dataclass(frozen=True, slots=True)
class WaterBounds:
    min_x: int
    min_y: int
    max_x: int
    max_y: int

    def __iter__(self) -> Iterator[int]:
        return iter((self.min_x, self.min_y, self.max_x, self.max_y))


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class WaterCornerAlphas:
    southwest: int = 26
    southeast: int = 26
    northeast: int = 26
    northwest: int = 26

    def values(self) -> tuple[int, int, int, int]:
        return (
            int(self.southwest),
            int(self.southeast),
            int(self.northeast),
            int(self.northwest),
        )


WaterAlpha = int | WaterCornerAlphas


def _coerce_alphas(value: WaterAlpha) -> tuple[int, int, int, int]:
    if isinstance(value, int):
        return value, value, value, value
    if isinstance(value, WaterCornerAlphas):
        return value.values()
    raise TypeError("alpha must be an integer or WaterCornerAlphas")


def _grid_integer(value: float, *, label: str) -> int:
    number = float(value)
    rounded = round(number)
    if not math.isfinite(number) or not math.isclose(
        number,
        rounded,
        abs_tol=1e-9,
    ):
        raise ValueError(f"{label} must be an integer water coordinate")
    return rounded


def _centered_bounds(
    center: Vector2,
    size: Vector2,
) -> WaterBounds:
    if not isinstance(center, Vector2) or not isinstance(size, Vector2):
        raise TypeError("center and size must be Vector2 instances")
    center_x, center_y = center.x, center.y
    width, height = size.x, size.y
    if not all(math.isfinite(value) for value in (center_x, center_y, width, height)):
        raise ValueError("center and size must be finite")
    if width <= 0.0 or height <= 0.0:
        raise ValueError("size components must be greater than zero")
    raw_bounds = (
        center_x - width * 0.5,
        center_y - height * 0.5,
        center_x + width * 0.5,
        center_y + height * 0.5,
    )
    try:
        values = tuple(
            _grid_integer(value, label="center and size result") for value in raw_bounds
        )
        return WaterBounds(*values)
    except ValueError as exc:
        raise ValueError("center and size must produce integer water bounds") from exc


def _coerce_bounds(bounds: WaterBounds) -> WaterBounds:
    if not isinstance(bounds, WaterBounds):
        raise TypeError("bounds must be a WaterBounds")
    return WaterBounds(
        *(_grid_integer(value, label="bounds component") for value in bounds)
    )


def _contains_xy(
    points: Sequence[Vector3],
    x: float,
    y: float,
) -> bool:
    if not points:
        return False
    signs: list[float] = []
    for index, point in enumerate(points):
        following = points[(index + 1) % len(points)]
        x1, y1 = point.x, point.y
        x2, y2 = following.x, following.y
        signs.append((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1))
    tolerance = 1e-9
    return all(sign >= -tolerance for sign in signs) or all(
        sign <= tolerance for sign in signs
    )


__all__ = [
    "WaterAlpha",
    "WaterBounds",
    "WaterCornerAlphas",
]
