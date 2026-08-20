from __future__ import annotations

from typing import Any

from ..metahash import HashLike, MetaHash
from ..vector import Aabb3, Vector3
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


def entity_positions(entities: list[Any]) -> list[Vector3]:
    positions: list[Vector3] = []
    for entity in entities:
        position = getattr(entity, "position", None)
        if isinstance(position, Vector3):
            positions.append(position)
    return positions


def positions_bounds(positions: list[Vector3]) -> Aabb3:
    return Aabb3.from_points(positions)


def expand_bounds(
    bounds: Aabb3,
    padding: float,
) -> Aabb3:
    if padding <= 0:
        return bounds
    return bounds.expanded(padding)


def merge_bounds(
    current: Aabb3 | None,
    new_bounds: Aabb3 | None,
) -> Aabb3 | None:
    if current is None:
        return new_bounds
    return current if new_bounds is None else current.merged(new_bounds)


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
