from __future__ import annotations

from collections.abc import Sequence

from .enums import YmapLodLightCategory
from .lodlight_generation import GeneratedLodLight

MAX_LOD_LIGHTS_PER_CELL = 800


def partition_lod_lights(
    lights: Sequence[GeneratedLodLight],
    *,
    max_lights_per_cell: int = MAX_LOD_LIGHTS_PER_CELL,
) -> list[list[GeneratedLodLight]]:
    if max_lights_per_cell <= 0:
        raise ValueError("max_lights_per_cell must be positive")
    pending = [list(lights)] if lights else []
    cells: list[list[GeneratedLodLight]] = []
    while pending:
        cell = pending.pop()
        if len(cell) <= max_lights_per_cell:
            cells.append(cell)
            continue
        axis = _widest_xy_axis(cell)
        cell.sort(
            key=lambda item: (
                item.light.position[axis],
                item.light.position[1 - axis],
                int(item.light.hash),
            )
        )
        midpoint = len(cell) // 2
        pending.append(cell[midpoint:])
        pending.append(cell[:midpoint])
    cells.sort(key=_cell_sort_key)
    return cells


def partition_lod_lights_by_category(
    lights: Sequence[GeneratedLodLight],
    *,
    max_lights_per_cell: int = MAX_LOD_LIGHTS_PER_CELL,
) -> dict[YmapLodLightCategory, list[list[GeneratedLodLight]]]:
    result: dict[YmapLodLightCategory, list[list[GeneratedLodLight]]] = {}
    for category in YmapLodLightCategory:
        category_lights = [light for light in lights if light.category == category]
        if category_lights:
            result[category] = partition_lod_lights(
                category_lights,
                max_lights_per_cell=max_lights_per_cell,
            )
    return result


def _widest_xy_axis(lights: Sequence[GeneratedLodLight]) -> int:
    x_values = [light.light.position[0] for light in lights]
    y_values = [light.light.position[1] for light in lights]
    return 0 if max(x_values) - min(x_values) >= max(y_values) - min(y_values) else 1


def _cell_sort_key(lights: Sequence[GeneratedLodLight]) -> tuple[float, float, int]:
    return (
        min(light.light.position[0] for light in lights),
        min(light.light.position[1] for light in lights),
        min(int(light.light.hash) for light in lights),
    )


__all__ = [
    "MAX_LOD_LIGHTS_PER_CELL",
    "partition_lod_lights",
    "partition_lod_lights_by_category",
]
