from __future__ import annotations

from typing import Any

from ..metahash import HashLike, MetaHash
from .base import ContainerLodDef, PhysicsDictionary
from .defs import _resource_text


def suggest_resource_path(value: HashLike, meta_name_value: str, extension: str, fallback: str) -> str:
    meta_text = _resource_text(meta_name_value)
    if meta_text:
        return meta_text if meta_text.lower().endswith(extension) else f"{meta_text}{extension}"
    value_text = _resource_text(value)
    if value_text:
        return value_text if value_text.lower().endswith(extension) else f"{value_text}{extension}"
    return fallback


def entity_positions(entities: list[Any]) -> list[tuple[float, float, float]]:
    positions: list[tuple[float, float, float]] = []
    for entity in entities:
        position = getattr(entity, "position", None)
        if isinstance(position, tuple) and len(position) == 3:
            positions.append((float(position[0]), float(position[1]), float(position[2])))
    return positions


def positions_bounds(positions: list[tuple[float, float, float]]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    xs = [pos[0] for pos in positions]
    ys = [pos[1] for pos in positions]
    zs = [pos[2] for pos in positions]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def expand_bounds(
    min_value: tuple[float, float, float],
    max_value: tuple[float, float, float],
    padding: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if padding <= 0:
        return min_value, max_value
    return (
        (min_value[0] - padding, min_value[1] - padding, min_value[2] - padding),
        (max_value[0] + padding, max_value[1] + padding, max_value[2] + padding),
    )


def merge_bounds(
    current: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
    new_bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    if new_bounds is None:
        return current
    if current is None:
        return new_bounds
    return (
        (
            min(current[0][0], new_bounds[0][0]),
            min(current[0][1], new_bounds[0][1]),
            min(current[0][2], new_bounds[0][2]),
        ),
        (
            max(current[1][0], new_bounds[1][0]),
            max(current[1][1], new_bounds[1][1]),
            max(current[1][2], new_bounds[1][2]),
        ),
    )


def coerce_container_lod(item: Any) -> ContainerLodDef | Any:
    if isinstance(item, ContainerLodDef):
        return item
    if isinstance(item, dict):
        return ContainerLodDef.from_meta(item)
    return item


def coerce_physics_dictionary(item: PhysicsDictionary | MetaHash | HashLike) -> PhysicsDictionary:
    return item if isinstance(item, PhysicsDictionary) else PhysicsDictionary(name=item)


__all__ = [
    "coerce_container_lod",
    "coerce_physics_dictionary",
    "entity_positions",
    "expand_bounds",
    "merge_bounds",
    "positions_bounds",
    "suggest_resource_path",
]
