from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..bounds import Bound, BoundComposite, BoundGeometry
from ..metahash import MetaHash


def iter_collision_room_ids(source: Any) -> Iterator[int]:
    """Yield room IDs actually consumed by collision shapes and polygons."""
    bound = getattr(source, "bound", source)
    if not isinstance(bound, Bound):
        return
    for item in bound.walk():
        if isinstance(item, BoundGeometry):
            material_indices = {
                int(polygon.material_index)
                if int(polygon.material_index) >= 0
                else int(item.polygon_material_indices[index])
                for index, polygon in enumerate(item.polygons)
                if int(polygon.material_index) >= 0 or index < len(item.polygon_material_indices)
            }
            for material_index in material_indices:
                material = item.get_material(material_index)
                if material is not None:
                    yield int(material.room_id)
        elif not isinstance(item, BoundComposite):
            yield int(item.room_id)


def collision_room_ids(source: Any) -> frozenset[int]:
    return frozenset(iter_collision_room_ids(source))


def set_collision_room(source: Any, room_id: int) -> Any:
    """Assign every collision shape in a YBN/bound tree to one MLO room."""
    room_id = int(room_id)
    if not 0 <= room_id < 31:
        raise ValueError("MLO collision room_id must be between 0 and 30")
    bound = getattr(source, "bound", source)
    if not isinstance(bound, Bound):
        raise TypeError("source must be a YBN or Bound")
    for item in bound.walk():
        if isinstance(item, BoundGeometry):
            for material in item.materials:
                material.room_id = room_id
        elif not isinstance(item, BoundComposite):
            item.room_id = room_id
    return source


def validate_mlo_collision(source: Any, archetype: Any) -> list[str]:
    """Validate the room encoding and identity of an MLO static-bound YBN."""
    issues: list[str] = []
    room_count = len(getattr(archetype, "rooms", ()) or ())
    name = getattr(archetype, "name", 0)
    label = f"MLO collision {name}"

    if not 1 <= room_count <= 31:
        issues.append(f"{label} requires between 1 and 31 archetype rooms")

    room_ids = collision_room_ids(source)
    for room_id in sorted(room_ids):
        if not 0 <= room_id < room_count:
            issues.append(
                f"{label} uses room_id {room_id}, but the archetype only has {room_count} rooms"
            )

    path = str(getattr(source, "path", "") or "")
    if path:
        stem = Path(path.replace("\\", "/")).stem
        if stem and int(MetaHash.from_value(stem)) != int(name):
            issues.append(
                f"{label} is stored as {stem}.ybn; an MLO static-bound YBN must match the archetype name"
            )
    return issues


__all__ = [
    "collision_room_ids",
    "iter_collision_room_ids",
    "set_collision_room",
    "validate_mlo_collision",
]
