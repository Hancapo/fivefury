from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from ..bounds import Bound, BoundBox
from .physics import (
    YftArticulatedBodyType,
    YftPhysicsChild,
    YftPhysicsDampArchetype,
    YftPhysicsDamping,
    YftPhysicsDampingKind,
    YftPhysicsGroup,
    YftPhysicsInertia,
    YftPhysicsJointType,
    YftPhysicsLod,
    YftPhysicsLodPointers,
    YftMatrix34,
)

DEFAULT_DAMPING_CONSTANTS: tuple[YftPhysicsDamping, ...] = (
    YftPhysicsDamping.declare(YftPhysicsDampingKind.LINEAR_CONSTANT, (0.02, 0.02, 0.02)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.LINEAR_VELOCITY, (0.02, 0.02, 0.02)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.LINEAR_VELOCITY_SQUARED, (0.01, 0.01, 0.01)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.ANGULAR_CONSTANT, (0.02, 0.02, 0.02)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.ANGULAR_VELOCITY, (0.02, 0.02, 0.02)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.ANGULAR_VELOCITY_SQUARED, (0.01, 0.01, 0.01)),
)

IDENTITY_MATRIX34: YftMatrix34 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
)


def box_inertia(
    size: tuple[float, float, float],
    mass: float,
) -> YftPhysicsInertia:
    x, y, z = (abs(float(value)) for value in size)
    m = max(0.0, float(mass))
    return YftPhysicsInertia(
        x=(m * ((y * y) + (z * z))) / 12.0,
        y=(m * ((x * x) + (z * z))) / 12.0,
        z=(m * ((x * x) + (y * y))) / 12.0,
        mass=m,
    )


def bound_inertia(bound: Bound | None, mass: float) -> YftPhysicsInertia:
    if bound is None:
        return box_inertia((1.0, 1.0, 1.0), mass)
    inertia = bound.compute_angular_inertia(mass)
    return YftPhysicsInertia(x=inertia[0], y=inertia[1], z=inertia[2], mass=float(mass))


def bound_mass(bound: Bound | None, *, density: float = 1.0, fallback: float = 1.0) -> float:
    if bound is None:
        return float(fallback)
    volume = bound.compute_volume()
    return max(0.0, volume * float(density)) if volume > 0.0 else float(fallback)


def simple_physics_bound(
    *,
    center: tuple[float, float, float] = (0.0, 0.0, 0.0),
    size: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> BoundBox:
    return BoundBox.from_center_size(center, size).build()


def default_damp_archetype(
    *,
    bound: Bound | None,
    mass: float,
    damping_constants: Sequence[YftPhysicsDamping] = DEFAULT_DAMPING_CONSTANTS,
) -> YftPhysicsDampArchetype:
    inertia = bound_inertia(bound, mass)
    inv_mass = 1.0 / mass if mass > 0.0 else 0.0
    inv_inertia = tuple(1.0 / value if value > 0.0 else 0.0 for value in (inertia.x, inertia.y, inertia.z))
    return YftPhysicsDampArchetype(
        resource_type=2,
        mass=float(mass),
        inv_mass=inv_mass,
        gravity_factor=1.0,
        max_speed=500.0,
        max_ang_speed=6.2831854820251465,
        buoyancy_factor=0.0,
        angular_inertia=(inertia.x, inertia.y, inertia.z),
        inv_angular_inertia=inv_inertia,
        damping_constants=tuple(damping_constants),
        damping_offset=0x80,
    )


def default_articulated_body_type(
    *,
    link_count: int,
    joint_type: YftPhysicsJointType = YftPhysicsJointType.ONE_DOF,
) -> YftArticulatedBodyType:
    links = max(1, min(23, int(link_count)))
    joints = max(0, min(22, links - 1))
    parent_indices = [-1, *range(joints)]
    parent_indices.extend([-1] * (23 - len(parent_indices)))
    return YftArticulatedBodyType(
        joint_parent_indices=tuple(parent_indices[:23]),
        num_links=links,
        num_joints=joints,
        joint_types=tuple(joint_type for _ in range(joints)),
        locally_owned=True,
    )


def normalize_physics_lod(
    lod: YftPhysicsLod,
    *,
    composite_bound: Bound | None = None,
    density: float = 1.0,
) -> YftPhysicsLod:
    bound = composite_bound or lod.composite_bound
    groups = tuple(lod.groups)
    children = tuple(lod.children)
    if not groups:
        child = YftPhysicsChild.declare(
            undamaged_mass=bound_mass(bound, density=density),
            owner_group_name="default",
        )
        groups = (YftPhysicsGroup.declare("default", children=(child,)),)
        declared = YftPhysicsLod.declare(lod.label, groups=groups, root_cg_offset=lod.root_cg_offset)
        return normalize_physics_lod(declared, composite_bound=bound, density=density)

    resolved_groups = []
    resolved_children: list[YftPhysicsChild] = []
    cursor = 0
    for index, group in enumerate(groups):
        group_name = group.name or group.debug_name or f"group_{index}"
        group_children = tuple(group.children)
        if not group_children and group.child_index != 0xFF:
            group_children = children[group.child_index : group.child_index + group.num_children]
        normalized_children = []
        for child in group_children:
            mass = child.undamaged_mass if child.undamaged_mass > 0.0 else bound_mass(bound, density=density)
            damaged_mass = child.damaged_mass if child.damaged_mass > 0.0 else mass
            undamaged_inertia = (
                child.undamaged_ang_inertia
                if child.undamaged_ang_inertia.mass > 0.0
                else bound_inertia(bound, mass)
            )
            damaged_inertia = (
                child.damaged_ang_inertia
                if child.damaged_ang_inertia.mass > 0.0
                else bound_inertia(bound, damaged_mass)
            )
            normalized_children.append(
                dataclasses.replace(
                    child,
                    owner_group_pointer_index=index,
                    owner_group_name=group_name,
                    undamaged_mass=mass,
                    damaged_mass=damaged_mass,
                    undamaged_ang_inertia=undamaged_inertia,
                    damaged_ang_inertia=damaged_inertia,
                )
            )
        resolved_children.extend(normalized_children)
        resolved_groups.append(
            dataclasses.replace(
                group,
                name=group_name,
                debug_name=group.debug_name or group_name,
                child_index=cursor if normalized_children else 0xFF,
                num_children=len(normalized_children),
                total_undamaged_mass=sum(child.undamaged_mass for child in normalized_children),
                total_damaged_mass=sum(child.damaged_mass for child in normalized_children),
            )
        )
        cursor += len(normalized_children)

    damping_constants = tuple(lod.damping_constants) or DEFAULT_DAMPING_CONSTANTS
    if len(damping_constants) < 6:
        damping_constants = (*damping_constants, *DEFAULT_DAMPING_CONSTANTS[len(damping_constants):])
    min_impulses = tuple(lod.min_breaking_impulses) or tuple(
        child.min_breaking_impulse for child in resolved_children
    )
    undamaged_inertia = tuple(lod.undamaged_ang_inertia) or tuple(
        child.undamaged_ang_inertia for child in resolved_children
    )
    damaged_inertia = tuple(lod.damaged_ang_inertia) or tuple(
        child.damaged_ang_inertia for child in resolved_children
    )
    link_attachments = tuple(lod.link_attachments) or tuple(
        IDENTITY_MATRIX34 for _ in resolved_children
    )
    smallest = min((item.x for item in undamaged_inertia if item.x > 0.0), default=0.0)
    largest = max(
        (max(item.x, item.y, item.z) for item in undamaged_inertia),
        default=0.0,
    )
    total_mass = sum(child.undamaged_mass for child in resolved_children)
    damp_undamaged = lod.undamaged_damp_archetype or default_damp_archetype(
        bound=bound,
        mass=total_mass,
        damping_constants=damping_constants,
    )
    damp_damaged = lod.damaged_damp_archetype or default_damp_archetype(
        bound=bound,
        mass=sum(child.damaged_mass for child in resolved_children) or total_mass,
        damping_constants=damping_constants,
    )
    articulated = lod.articulated_body_type
    if articulated is None and len(resolved_children) > 1:
        articulated = default_articulated_body_type(link_count=len(resolved_children))
    return dataclasses.replace(
        lod,
        num_groups=len(resolved_groups),
        root_group_count=sum(1 for group in resolved_groups if group.is_root_group),
        num_root_damage_regions=max(1, sum(1 for group in resolved_groups if group.is_damageable)),
        num_bony_children=sum(1 for child in resolved_children if child.uses_bone),
        num_children=len(resolved_children),
        group_names=tuple(group.name or group.debug_name for group in resolved_groups),
        groups=tuple(resolved_groups),
        children=tuple(resolved_children),
        damping_constants=damping_constants[:6],
        min_breaking_impulses=min_impulses[: len(resolved_children)],
        undamaged_ang_inertia=undamaged_inertia[: len(resolved_children)],
        damaged_ang_inertia=damaged_inertia[: len(resolved_children)],
        link_attachments=link_attachments[: len(resolved_children)],
        smallest_ang_inertia=lod.smallest_ang_inertia or smallest,
        largest_ang_inertia=lod.largest_ang_inertia or largest,
        min_move_force=lod.min_move_force or 0.0,
        composite_bound=bound,
        undamaged_damp_archetype=damp_undamaged,
        damaged_damp_archetype=damp_damaged,
        articulated_body_type=articulated,
    )


def physics_lod_pointers_for(lods: Sequence[YftPhysicsLod]) -> YftPhysicsLodPointers:
    labels = {lod.label.lower(): lod.pointer for lod in lods}
    return YftPhysicsLodPointers(
        high=labels.get("high", 0),
        medium=labels.get("medium", 0),
        low=labels.get("low", 0),
    )


__all__ = [
    "DEFAULT_DAMPING_CONSTANTS",
    "IDENTITY_MATRIX34",
    "bound_inertia",
    "bound_mass",
    "box_inertia",
    "default_articulated_body_type",
    "default_damp_archetype",
    "normalize_physics_lod",
    "physics_lod_pointers_for",
    "simple_physics_bound",
]
