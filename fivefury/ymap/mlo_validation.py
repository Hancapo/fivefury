from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ..binary import fits_unsigned
from ..metahash import MetaHash
from ..ybn import validate_mlo_collision
from ..ytyp.mlo_validation import build_mlo_archetype, exit_portal_count
from .base import PhysicsDictionary
from .entities import MloInstanceDef


def _iter_ytyps(ytyps: Any) -> Iterable[Any]:
    if ytyps is None:
        return ()
    if isinstance(ytyps, Mapping):
        ytyps = ytyps.values()
    if hasattr(ytyps, "archetypes"):
        return (ytyps,)
    return ytyps


def archetypes_by_hash(ytyps: Any) -> dict[int, Any]:
    archetypes: dict[int, Any] = {}
    for ytyp in _iter_ytyps(ytyps):
        if hasattr(ytyp, "rooms") and hasattr(ytyp, "portals"):
            archetypes[int(ytyp.name)] = ytyp
            continue
        for archetype in getattr(ytyp, "archetypes", ()):
            if hasattr(archetype, "name"):
                archetypes[int(archetype.name)] = archetype
    return archetypes


def mlo_archetypes_by_hash(ytyps: Any) -> dict[int, Any]:
    return {
        name_hash: archetype
        for name_hash, archetype in archetypes_by_hash(ytyps).items()
        if hasattr(archetype, "rooms") and hasattr(archetype, "portals")
    }


def mlo_collisions_by_hash(ybns: Any) -> dict[int, Any]:
    if ybns is None:
        return {}
    if isinstance(ybns, Mapping):
        return {int(MetaHash.from_value(key)): value for key, value in ybns.items()}
    if hasattr(ybns, "bound"):
        ybns = (ybns,)
    collisions: dict[int, Any] = {}
    for ybn in ybns:
        path = str(getattr(ybn, "path", "") or "")
        if path:
            collisions[int(MetaHash.from_value(Path(path.replace("\\", "/")).stem))] = ybn
    return collisions


def build_mlo_instance(instance: MloInstanceDef, archetype: Any | None = None) -> MloInstanceDef:
    if archetype is not None:
        instance.num_exit_portals = exit_portal_count(archetype)
    return instance


def validate_mlo_instance(instance: MloInstanceDef, archetype: Any | None = None) -> list[str]:
    label = f"MLO instance {instance.archetype_name}"
    issues: list[str] = []
    if not 0 <= int(instance.group_id) < 255:
        issues.append(f"{label} group_id must be between 0 and 254")
    if not fits_unsigned(instance.floor_id, 32):
        issues.append(f"{label} floor_id is outside the uint32 range")
    if not fits_unsigned(instance.num_exit_portals, 32):
        issues.append(f"{label} num_exit_portals is outside the uint32 range")

    if archetype is None:
        return issues

    expected_exit_portals = exit_portal_count(archetype)
    if int(instance.num_exit_portals) != expected_exit_portals:
        issues.append(
            f"{label} num_exit_portals={instance.num_exit_portals}, expected {expected_exit_portals}"
        )

    available_sets = {int(entity_set.name) for entity_set in archetype.entity_sets}
    seen_sets: set[int] = set()
    for entity_set in instance.default_entity_sets:
        entity_set_hash = int(entity_set)
        if entity_set_hash in seen_sets:
            issues.append(f"{label} repeats default entity set {entity_set}")
        elif entity_set_hash not in available_sets:
            issues.append(f"{label} references unknown default entity set {entity_set}")
        seen_sets.add(entity_set_hash)
    return issues


def build_ymap_mlo_instances(ymap: Any, ytyps: Any = None) -> Any:
    archetypes = mlo_archetypes_by_hash(ytyps)
    physics_hashes = {int(item.name) for item in ymap.physics_dictionaries}
    for entity in ymap.entities:
        if isinstance(entity, MloInstanceDef):
            archetype = archetypes.get(int(entity.archetype_name))
            if archetype is not None:
                build_mlo_archetype(archetype)
            build_mlo_instance(entity, archetype)
            if archetype is None:
                continue
            physics_dictionary = getattr(archetype, "physics_dictionary", 0)
            physics_hash = int(physics_dictionary)
            if physics_hash and physics_hash not in physics_hashes:
                ymap.physics_dictionaries.append(PhysicsDictionary(physics_dictionary))
                physics_hashes.add(physics_hash)
    return ymap


def validate_ymap_mlo_instances(ymap: Any, ytyps: Any = None, ybns: Any = None) -> list[str]:
    issues: list[str] = []
    archetypes = mlo_archetypes_by_hash(ytyps)
    collisions = mlo_collisions_by_hash(ybns)
    physics_hashes = {int(item.name) for item in ymap.physics_dictionaries}
    require_archetype = ytyps is not None
    require_collision = ybns is not None
    for entity_index, entity in enumerate(ymap.entities):
        if not isinstance(entity, MloInstanceDef):
            continue
        archetype = archetypes.get(int(entity.archetype_name))
        if require_archetype and archetype is None:
            issues.append(
                f"YMAP entities[{entity_index}] references MLO archetype {entity.archetype_name}, "
                "which is absent from the supplied YTYPs"
            )
            continue
        issues.extend(validate_mlo_instance(entity, archetype))
        if archetype is None:
            continue

        physics_dictionary = int(getattr(archetype, "physics_dictionary", 0))
        if physics_dictionary and physics_dictionary not in physics_hashes:
            issues.append(
                f"YMAP entities[{entity_index}] MLO physics dictionary "
                f"{getattr(archetype, 'physics_dictionary', 0)} is absent from physics_dictionaries"
            )

        collision = collisions.get(int(archetype.name))
        if require_collision and collision is None:
            issues.append(
                f"YMAP entities[{entity_index}] has no YBN static bound for MLO archetype "
                f"{archetype.name}"
            )
        elif collision is not None:
            issues.extend(validate_mlo_collision(collision, archetype))
    return issues


__all__ = [
    "archetypes_by_hash",
    "build_mlo_instance",
    "build_ymap_mlo_instances",
    "mlo_archetypes_by_hash",
    "mlo_collisions_by_hash",
    "validate_mlo_instance",
    "validate_ymap_mlo_instances",
]
