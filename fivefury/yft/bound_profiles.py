from __future__ import annotations

import enum
from collections.abc import Iterator, Mapping

from ..bounds import Bound, BoundBVH, BoundComposite, BoundType


class YftPhysicsBoundProfile(enum.StrEnum):
    """Native bound family and topology used by a fragment physics LOD."""

    PROP = "prop"
    SET_PIECE = "set_piece"
    VEHICLE = "vehicle"
    PRESERVE = "preserve"


_PROFILE_VFTS: Mapping[
    YftPhysicsBoundProfile,
    Mapping[BoundType, int],
] = {
    YftPhysicsBoundProfile.PROP: {
        BoundType.SPHERE: 0x4062E108,
        BoundType.CAPSULE: 0x4062BE78,
        BoundType.BOX: 0x4062BD48,
        BoundType.CYLINDER: 0x40629678,
        BoundType.GEOMETRY: 0x4062D258,
        BoundType.COMPOSITE: 0x40629AA8,
    },
    YftPhysicsBoundProfile.SET_PIECE: {
        BoundType.SPHERE: 0x40630118,
        BoundType.CAPSULE: 0x4062DE88,
        BoundType.BOX: 0x4062DD58,
        BoundType.DISC: 0x40630048,
        BoundType.CYLINDER: 0x4062B678,
        BoundType.GEOMETRY: 0x4062F268,
        BoundType.COMPOSITE: 0x4062BAA8,
    },
    YftPhysicsBoundProfile.VEHICLE: {
        BoundType.CAPSULE: 0x4062DE78,
        BoundType.BOX: 0x4062DD48,
        BoundType.GEOMETRY: 0x4062F258,
        BoundType.GEOMETRY_BVH: 0x4062FAB8,
        BoundType.COMPOSITE: 0x4062B5D8,
    },
    YftPhysicsBoundProfile.PRESERVE: {},
}


def coerce_yft_physics_bound_profile(
    value: YftPhysicsBoundProfile | str,
) -> YftPhysicsBoundProfile:
    if isinstance(value, YftPhysicsBoundProfile):
        return value
    return YftPhysicsBoundProfile(str(value).lower())


def iter_bound_slots(root: Bound) -> Iterator[Bound | None]:
    if isinstance(root, BoundComposite):
        yield from (child.bound for child in root.children)
    else:
        yield root


def profile_file_vft(
    bound: Bound,
    profile: YftPhysicsBoundProfile | str,
) -> int:
    """Resolve a bound VFT without replacing an explicit value."""

    if bound.file_vft:
        return int(bound.file_vft)
    resolved = coerce_yft_physics_bound_profile(profile)
    if resolved is YftPhysicsBoundProfile.PRESERVE:
        raise ValueError(
            f"{bound.__class__.__name__} has no explicit file_vft to preserve"
        )
    value = _PROFILE_VFTS[resolved].get(bound.bound_type)
    if value is None:
        raise ValueError(
            f"{resolved.value} does not define a native VFT for "
            f"{bound.bound_type.name}"
        )
    return value


def expected_profile_vft(
    bound_type: BoundType | int,
    profile: YftPhysicsBoundProfile | str,
) -> int | None:
    resolved = coerce_yft_physics_bound_profile(profile)
    return _PROFILE_VFTS[resolved].get(BoundType(bound_type))


def validate_bound_profile(
    root: Bound,
    profile: YftPhysicsBoundProfile | str,
    *,
    expected_slots: int | None = None,
) -> list[str]:
    resolved = coerce_yft_physics_bound_profile(profile)
    issues: list[str] = []
    if resolved is YftPhysicsBoundProfile.PRESERVE:
        for index, bound in enumerate(root.walk()):
            if not bound.file_vft:
                issues.append(
                    f"bound {index} has no explicit file_vft to preserve"
                )
        if expected_slots is not None:
            actual_slots = (
                len(root.children)
                if isinstance(root, BoundComposite)
                else 1
            )
            if actual_slots != expected_slots:
                issues.append(
                    f"bound tree has {actual_slots} slots for "
                    f"{expected_slots} physics children"
                )
        return issues

    if not isinstance(root, BoundComposite):
        issues.append("physics LOD root must be a BoundComposite")
        return issues
    if expected_slots is not None and len(root.children) != expected_slots:
        issues.append(
            f"composite has {len(root.children)} slots for "
            f"{expected_slots} physics children"
        )

    for index, bound in enumerate(root.walk()):
        expected_vft = expected_profile_vft(bound.bound_type, resolved)
        if expected_vft is None:
            issues.append(
                f"bound {index} type {bound.bound_type.name} is not defined "
                f"for {resolved.value}"
            )
        elif bound.file_vft and bound.file_vft != expected_vft:
            issues.append(
                f"bound {index} VFT 0x{bound.file_vft:08X} does not match "
                f"{resolved.value} 0x{expected_vft:08X}"
            )

    for index, child in enumerate(root.children):
        bound = child.bound
        if bound is None:
            continue
        if isinstance(bound, BoundComposite):
            issues.append(f"slot {index} contains a nested BoundComposite")
        if (
            resolved is not YftPhysicsBoundProfile.VEHICLE
            and isinstance(bound, BoundBVH)
        ):
            issues.append(
                f"slot {index} contains BoundBVH, which is not valid for "
                f"{resolved.value}"
            )
    return issues


__all__ = [
    "YftPhysicsBoundProfile",
    "coerce_yft_physics_bound_profile",
    "expected_profile_vft",
    "iter_bound_slots",
    "profile_file_vft",
    "validate_bound_profile",
]
