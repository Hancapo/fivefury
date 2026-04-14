from __future__ import annotations

import dataclasses
import math

YND_REGION_SPLIT = 32
# YND/pathfind regions use dev_ng WORLDLIMITS_REP_*, not the global WORLDLIMITS_* extents.
YND_REP_MIN_X = -8192.0
YND_REP_MAX_X = 8192.0
YND_REP_MIN_Y = -8192.0
YND_REP_MAX_Y = 8192.0
YND_REGION_SIZE_X = (YND_REP_MAX_X - YND_REP_MIN_X) / YND_REGION_SPLIT
YND_REGION_SIZE_Y = (YND_REP_MAX_Y - YND_REP_MIN_Y) / YND_REGION_SPLIT
YND_REGION_COUNT = YND_REGION_SPLIT * YND_REGION_SPLIT


@dataclasses.dataclass(frozen=True, slots=True)
class YndAreaBounds:
    area_id: int
    x_index: int
    y_index: int
    min_x: float
    max_x: float
    min_y: float
    max_y: float


def _clamp_region_index(value: float, minimum: float, size: float) -> int:
    numeric = float(value)
    if numeric > minimum:
        numeric = math.nextafter(numeric, -math.inf)
    normalized = math.floor((numeric - minimum) / size)
    return max(0, min(YND_REGION_SPLIT - 1, int(normalized)))


def get_ynd_area_id(position: tuple[float, float, float] | tuple[float, float]) -> int:
    x_index = _clamp_region_index(position[0], YND_REP_MIN_X, YND_REGION_SIZE_X)
    y_index = _clamp_region_index(position[1], YND_REP_MIN_Y, YND_REGION_SIZE_Y)
    return x_index + (y_index * YND_REGION_SPLIT)


def get_ynd_area_indices(area_id: int) -> tuple[int, int]:
    value = int(area_id)
    if value < 0 or value >= YND_REGION_COUNT:
        raise ValueError(f"YND area_id must be in [0, {YND_REGION_COUNT - 1}]")
    return (value % YND_REGION_SPLIT, value // YND_REGION_SPLIT)


def get_ynd_area_bounds(area_id: int) -> YndAreaBounds:
    x_index, y_index = get_ynd_area_indices(area_id)
    min_x = YND_REP_MIN_X + (x_index * YND_REGION_SIZE_X)
    min_y = YND_REP_MIN_Y + (y_index * YND_REGION_SIZE_Y)
    return YndAreaBounds(
        area_id=int(area_id),
        x_index=x_index,
        y_index=y_index,
        min_x=min_x,
        max_x=min_x + YND_REGION_SIZE_X,
        min_y=min_y,
        max_y=min_y + YND_REGION_SIZE_Y,
    )


def position_matches_ynd_area(area_id: int, position: tuple[float, float, float] | tuple[float, float]) -> bool:
    return get_ynd_area_id(position) == int(area_id)
