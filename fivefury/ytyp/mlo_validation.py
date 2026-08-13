from __future__ import annotations

import math
from typing import Any

from ..binary import fits_unsigned
from .flags import PortalFlags

INVALID_ENTITY_INDEX = 0xFFFFFFFF
# Room and portal indexes are packed into 5 and 8 bits respectively, so these
# two are real runtime ceilings.  Room 0 previously carried an 11-attachment
# cap as well, but that was the largest value observed in a 174-archetype
# vanilla sample rather than a structural limit: attached_objects is a plain
# list with identical storage for every room, non-limbo vanilla rooms reach
# 345 attachments in that same field, and the vanilla room-0 histogram decays
# smoothly (…8:2, 10:3, 11:1) with no pile-up at the supposed cap.
MAX_MLO_PORTALS = 255
MAX_MLO_ROOMS = 31
PORTAL_LOCATION_BIT = 1 << 31


def _is_finite_vector(value: Any, size: int) -> bool:
    try:
        return len(value) == size and all(math.isfinite(float(component)) for component in value)
    except (TypeError, ValueError):
        return False


def _archetype_label(archetype: Any) -> str:
    name = str(getattr(archetype, "name", "")) or "<unnamed>"
    return f"MLO archetype {name}"


def build_mlo_archetype(archetype: Any) -> Any:
    """Synchronize fields derived from the MLO room/portal graph."""
    if int(archetype.physics_dictionary) == 0:
        archetype.physics_dictionary = archetype.name
    portal_counts = [0] * len(archetype.rooms)
    for portal in archetype.portals:
        room_indexes = {int(portal.room_from), int(portal.room_to)}
        for room_index in room_indexes:
            if 0 <= room_index < len(portal_counts):
                portal_counts[room_index] += 1
    for room, portal_count in zip(archetype.rooms, portal_counts, strict=True):
        room.portal_count = portal_count
    return archetype


def validate_mlo_archetype(archetype: Any) -> list[str]:
    """Validate indexes and limits directly consumed by the interior runtime."""
    issues: list[str] = []
    rooms = archetype.rooms
    portals = archetype.portals
    entity_count = len(archetype.entities)
    label = _archetype_label(archetype)

    if not rooms:
        return [f"{label} has no rooms; room 0 is required"]
    if len(rooms) > MAX_MLO_ROOMS:
        issues.append(f"{label} has {len(rooms)} rooms; the runtime supports at most {MAX_MLO_ROOMS}")
    if len(portals) > MAX_MLO_PORTALS:
        issues.append(
            f"{label} has {len(portals)} portals; the runtime supports at most {MAX_MLO_PORTALS}"
        )
    if not fits_unsigned(archetype.mlo_flags, 32):
        issues.append(f"{label} mlo_flags is outside the uint32 range")

    room_names: set[str] = set()
    attachment_locations: dict[int, list[str]] = {}
    expected_portal_counts = [0] * len(rooms)

    for room_index, room in enumerate(rooms):
        path = f"{label} rooms[{room_index}]"
        if not room.name:
            issues.append(f"{path} has no name")
        elif room.name in room_names:
            issues.append(f"{path} duplicates room name {room.name!r}")
        room_names.add(room.name)

        if not _is_finite_vector(room.bb_min, 3) or not _is_finite_vector(room.bb_max, 3):
            issues.append(f"{path} bounds must contain three finite coordinates")

        seen_here: set[int] = set()
        for entity_index in room.attached_objects:
            entity_index = int(entity_index)
            if entity_index == INVALID_ENTITY_INDEX:
                continue
            if not 0 <= entity_index < entity_count:
                issues.append(f"{path} references entity index {entity_index}, but only {entity_count} entities exist")
                continue
            if entity_index in seen_here:
                issues.append(f"{path} references entity index {entity_index} more than once")
                continue
            seen_here.add(entity_index)
            attachment_locations.setdefault(entity_index, []).append(f"room {room_index}")

    for portal_index, portal in enumerate(portals):
        path = f"{label} portals[{portal_index}]"
        connected_rooms = {int(portal.room_from), int(portal.room_to)}
        for field_name, room_index in (("room_from", int(portal.room_from)), ("room_to", int(portal.room_to))):
            if not 0 <= room_index < len(rooms):
                issues.append(f"{path} {field_name}={room_index} is outside the room array")
        for room_index in connected_rooms:
            if 0 <= room_index < len(rooms):
                expected_portal_counts[room_index] += 1

        if len(portal.corners) != 4:
            issues.append(f"{path} must contain exactly four corners")
        elif any(not _is_finite_vector(corner, 3) for corner in portal.corners):
            issues.append(f"{path} corners must contain three finite coordinates")
        if not 0 <= int(portal.mirror_priority) <= 3:
            issues.append(f"{path} mirror_priority must be between 0 and 3")
        if not fits_unsigned(portal.opacity, 32):
            issues.append(f"{path} opacity is outside the uint32 range")

        seen_here: set[int] = set()
        for entity_index in portal.attached_objects:
            entity_index = int(entity_index)
            if not 0 <= entity_index < entity_count:
                issues.append(f"{path} references entity index {entity_index}, but only {entity_count} entities exist")
                continue
            if entity_index in seen_here:
                issues.append(f"{path} references entity index {entity_index} more than once")
                continue
            seen_here.add(entity_index)
            attachment_locations.setdefault(entity_index, []).append(f"portal {portal_index}")

    for room_index, (room, expected_count) in enumerate(zip(rooms, expected_portal_counts, strict=True)):
        if int(room.portal_count) != expected_count:
            issues.append(
                f"{label} rooms[{room_index}] portal_count={room.portal_count}, expected {expected_count}"
            )

    for entity_index in range(entity_count):
        locations = attachment_locations.get(entity_index, [])
        if not locations:
            issues.append(f"{label} entities[{entity_index}] is not attached to a room or portal")

    entity_set_names: set[int] = set()
    for set_index, entity_set in enumerate(archetype.entity_sets):
        path = f"{label} entity_sets[{set_index}]"
        set_name = int(entity_set.name)
        if not set_name:
            issues.append(f"{path} has no name")
        elif set_name in entity_set_names:
            issues.append(f"{path} duplicates entity set name {entity_set.name}")
        entity_set_names.add(set_name)

        if len(entity_set.locations) != len(entity_set.entities):
            issues.append(
                f"{path} has {len(entity_set.locations)} locations for {len(entity_set.entities)} entities"
            )
        for location_index, encoded_location in enumerate(entity_set.locations):
            if not fits_unsigned(encoded_location, 32):
                issues.append(f"{path} locations[{location_index}] is outside the uint32 range")
                continue
            encoded_location = int(encoded_location)
            if encoded_location & PORTAL_LOCATION_BIT:
                portal_index = encoded_location & ~PORTAL_LOCATION_BIT
                if portal_index >= len(portals):
                    issues.append(
                        f"{path} locations[{location_index}] references portal {portal_index}, "
                        f"but only {len(portals)} portals exist"
                    )
            elif encoded_location >= len(rooms):
                issues.append(
                    f"{path} locations[{location_index}] references room {encoded_location}, "
                    f"but only {len(rooms)} rooms exist"
                )

    for modifier_index, modifier in enumerate(archetype.time_cycle_modifiers):
        path = f"{label} time_cycle_modifiers[{modifier_index}]"
        if not _is_finite_vector(modifier.sphere, 4):
            issues.append(f"{path} sphere must contain four finite coordinates")
        if not math.isfinite(float(modifier.percentage)) or not math.isfinite(float(modifier.range)):
            issues.append(f"{path} percentage and range must be finite")
        if not fits_unsigned(modifier.start_hour, 32) or not fits_unsigned(modifier.end_hour, 32):
            issues.append(f"{path} hours must fit in uint32")

    return issues


def exit_portal_count(archetype: Any) -> int:
    return sum(
        1
        for portal in archetype.portals
        if not (int(portal.flags) & int(PortalFlags.LINK))
        and (int(portal.room_from) == 0 or int(portal.room_to) == 0)
    )


__all__ = [
    "INVALID_ENTITY_INDEX",
    "MAX_MLO_PORTALS",
    "MAX_MLO_ROOMS",
    "PORTAL_LOCATION_BIT",
    "build_mlo_archetype",
    "exit_portal_count",
    "validate_mlo_archetype",
]
