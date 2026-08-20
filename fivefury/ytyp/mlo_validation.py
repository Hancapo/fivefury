from __future__ import annotations

import math
from typing import Any

from ..authoring.diagnostics import ValidationReport
from ..authoring.invariants import check_unsigned
from ..vector import Vector3, Vector4
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


def _is_finite_vector3(value: Any) -> bool:
    return isinstance(value, Vector3) and value.is_finite


def _is_finite_vector4(value: Any) -> bool:
    return isinstance(value, Vector4) and value.is_finite


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


def validate_mlo_archetype(archetype: Any) -> ValidationReport:
    """Validate indexes and limits directly consumed by the interior runtime."""
    issues = ValidationReport()
    rooms = archetype.rooms
    portals = archetype.portals
    entity_count = len(archetype.entities)
    label = _archetype_label(archetype)

    if not rooms:
        issues.issue("ytyp.mlo.rooms.empty", f"{label} has no rooms; room 0 is required", path="rooms")
        return issues
    if len(rooms) > MAX_MLO_ROOMS:
        issues.issue("ytyp.mlo.rooms.capacity", f"{label} has {len(rooms)} rooms; the runtime supports at most {MAX_MLO_ROOMS}", path="rooms")
    if len(portals) > MAX_MLO_PORTALS:
        issues.issue(
            "ytyp.mlo.portals.capacity",
            f"{label} has {len(portals)} portals; the runtime supports at most {MAX_MLO_PORTALS}",
            path="portals",
        )
    check_unsigned(issues, archetype.mlo_flags, 32, code="ytyp.mlo.flags.range", path="mlo_flags")

    room_names: set[str] = set()
    attachment_locations: dict[int, list[str]] = {}
    expected_portal_counts = [0] * len(rooms)

    for room_index, room in enumerate(rooms):
        path = f"rooms[{room_index}]"
        if not room.name:
            issues.issue("ytyp.mlo.room.name.missing", f"{label} {path} has no name", path=f"{path}.name")
        elif room.name in room_names:
            issues.issue("ytyp.mlo.room.name.duplicate", f"{label} {path} duplicates room name {room.name!r}", path=f"{path}.name")
        room_names.add(room.name)

        if not _is_finite_vector3(room.bb_min) or not _is_finite_vector3(room.bb_max):
            issues.issue("ytyp.mlo.room.bounds.invalid", f"{label} {path} bounds must contain three finite coordinates", path=f"{path}.bounds")

        seen_here: set[int] = set()
        for entity_index in room.attached_objects:
            entity_index = int(entity_index)
            if entity_index == INVALID_ENTITY_INDEX:
                continue
            if not 0 <= entity_index < entity_count:
                issues.issue("ytyp.mlo.room.entity_index.invalid", f"{label} {path} references entity index {entity_index}, but only {entity_count} entities exist", path=f"{path}.attached_objects")
                continue
            if entity_index in seen_here:
                issues.issue("ytyp.mlo.room.entity_index.duplicate", f"{label} {path} references entity index {entity_index} more than once", path=f"{path}.attached_objects")
                continue
            seen_here.add(entity_index)
            attachment_locations.setdefault(entity_index, []).append(f"room {room_index}")

    for portal_index, portal in enumerate(portals):
        path = f"portals[{portal_index}]"
        connected_rooms = {int(portal.room_from), int(portal.room_to)}
        for field_name, room_index in (("room_from", int(portal.room_from)), ("room_to", int(portal.room_to))):
            if not 0 <= room_index < len(rooms):
                issues.issue("ytyp.mlo.portal.room_index.invalid", f"{label} {path} {field_name}={room_index} is outside the room array", path=f"{path}.{field_name}")
        for room_index in connected_rooms:
            if 0 <= room_index < len(rooms):
                expected_portal_counts[room_index] += 1

        if len(portal.corners) != 4:
            issues.issue("ytyp.mlo.portal.corners.count", f"{label} {path} must contain exactly four corners", path=f"{path}.corners")
        elif any(not _is_finite_vector3(corner) for corner in portal.corners):
            issues.issue("ytyp.mlo.portal.corners.invalid", f"{label} {path} corners must contain three finite coordinates", path=f"{path}.corners")
        if not 0 <= int(portal.mirror_priority) <= 3:
            issues.issue("ytyp.mlo.portal.mirror_priority.range", f"{label} {path} mirror_priority must be between 0 and 3", path=f"{path}.mirror_priority")
        check_unsigned(issues, portal.opacity, 32, code="ytyp.mlo.portal.opacity.range", path=f"{path}.opacity")

        seen_here: set[int] = set()
        for entity_index in portal.attached_objects:
            entity_index = int(entity_index)
            if not 0 <= entity_index < entity_count:
                issues.issue("ytyp.mlo.portal.entity_index.invalid", f"{label} {path} references entity index {entity_index}, but only {entity_count} entities exist", path=f"{path}.attached_objects")
                continue
            if entity_index in seen_here:
                issues.issue("ytyp.mlo.portal.entity_index.duplicate", f"{label} {path} references entity index {entity_index} more than once", path=f"{path}.attached_objects")
                continue
            seen_here.add(entity_index)
            attachment_locations.setdefault(entity_index, []).append(f"portal {portal_index}")

    for room_index, (room, expected_count) in enumerate(zip(rooms, expected_portal_counts, strict=True)):
        if int(room.portal_count) != expected_count:
            issues.issue(
                "ytyp.mlo.room.portal_count.mismatch",
                f"{label} rooms[{room_index}] portal_count={room.portal_count}, expected {expected_count}",
                path=f"rooms[{room_index}].portal_count",
            )

    for entity_index in range(entity_count):
        locations = attachment_locations.get(entity_index, [])
        if not locations:
            issues.issue("ytyp.mlo.entity.unattached", f"{label} entities[{entity_index}] is not attached to a room or portal", path=f"entities[{entity_index}]")

    entity_set_names: set[int] = set()
    for set_index, entity_set in enumerate(archetype.entity_sets):
        path = f"entity_sets[{set_index}]"
        set_name = int(entity_set.name)
        if not set_name:
            issues.issue("ytyp.mlo.entity_set.name.missing", f"{label} {path} has no name", path=f"{path}.name")
        elif set_name in entity_set_names:
            issues.issue("ytyp.mlo.entity_set.name.duplicate", f"{label} {path} duplicates entity set name {entity_set.name}", path=f"{path}.name")
        entity_set_names.add(set_name)

        if len(entity_set.locations) != len(entity_set.entities):
            issues.issue(
                "ytyp.mlo.entity_set.location_count",
                f"{label} {path} has {len(entity_set.locations)} locations for {len(entity_set.entities)} entities",
                path=f"{path}.locations",
            )
        for location_index, encoded_location in enumerate(entity_set.locations):
            location_path = f"{path}.locations[{location_index}]"
            if not 0 <= int(encoded_location) <= 0xFFFFFFFF:
                check_unsigned(issues, encoded_location, 32, code="ytyp.mlo.entity_set.location.range", path=location_path)
                continue
            encoded_location = int(encoded_location)
            if encoded_location & PORTAL_LOCATION_BIT:
                portal_index = encoded_location & ~PORTAL_LOCATION_BIT
                if portal_index >= len(portals):
                    issues.issue(
                        "ytyp.mlo.entity_set.portal_index.invalid",
                        f"{label} {location_path} references portal {portal_index}, but only {len(portals)} portals exist",
                        path=location_path,
                    )
            elif encoded_location >= len(rooms):
                issues.issue(
                    "ytyp.mlo.entity_set.room_index.invalid",
                    f"{label} {location_path} references room {encoded_location}, but only {len(rooms)} rooms exist",
                    path=location_path,
                )

    for modifier_index, modifier in enumerate(archetype.time_cycle_modifiers):
        path = f"time_cycle_modifiers[{modifier_index}]"
        if not _is_finite_vector4(modifier.sphere):
            issues.issue("ytyp.mlo.time_modifier.sphere.invalid", f"{label} {path} sphere must contain four finite coordinates", path=f"{path}.sphere")
        if not math.isfinite(float(modifier.percentage)) or not math.isfinite(float(modifier.range)):
            issues.issue("ytyp.mlo.time_modifier.values.non_finite", f"{label} {path} percentage and range must be finite", path=path)
        check_unsigned(issues, modifier.start_hour, 32, code="ytyp.mlo.time_modifier.start_hour.range", path=f"{path}.start_hour")
        check_unsigned(issues, modifier.end_hour, 32, code="ytyp.mlo.time_modifier.end_hour.range", path=f"{path}.end_hour")

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
