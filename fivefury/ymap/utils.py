from __future__ import annotations

from typing import Any

from ..metahash import HashLike, MetaHash
from ..vector import aabb_expand, aabb_from_points, aabb_merge
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
    return aabb_from_points(positions)


def expand_bounds(
    min_value: tuple[float, float, float],
    max_value: tuple[float, float, float],
    padding: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if padding <= 0:
        return min_value, max_value
    return aabb_expand((min_value, max_value), padding)


def merge_bounds(
    current: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
    new_bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    return aabb_merge(current, new_bounds)


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
