from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence

from ..bounds import (
    Bound,
    BoundAabb,
    BoundBox,
    BoundChild,
    BoundComposite,
    BoundGeometry,
    BoundType,
    get_bound_material_density,
)
from ..bounds.geometry import identity_bound_transform
from .bound_ownership import apply_physics_lod_bound_ref_counts
from .bound_profiles import (
    YftPhysicsBoundProfile,
    coerce_yft_physics_bound_profile,
    profile_file_vft,
    validate_bound_profile,
)
from .physics import (
    YftArticulatedBodyType,
    YftMatrix44,
    YftPhysicsChild,
    YftPhysicsDampArchetype,
    YftPhysicsDamping,
    YftPhysicsDampingKind,
    YftPhysicsGroup,
    YftPhysicsInertia,
    YftPhysicsJoint1Dof,
    YftPhysicsJoint3Dof,
    YftPhysicsJointType,
    YftPhysicsLod,
    YftPhysicsLodPointers,
    YftPhysicsTransforms,
)
from .resource_headers import PH_ARTICULATED_BODY_TYPE_EUPHORIA_VFT

DEFAULT_DAMPING_CONSTANTS: tuple[YftPhysicsDamping, ...] = (
    YftPhysicsDamping.declare(YftPhysicsDampingKind.LINEAR_CONSTANT, (0.02, 0.02, 0.02)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.LINEAR_VELOCITY, (0.02, 0.02, 0.02)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.LINEAR_VELOCITY_SQUARED, (0.01, 0.01, 0.01)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.ANGULAR_CONSTANT, (0.02, 0.02, 0.02)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.ANGULAR_VELOCITY, (0.02, 0.02, 0.02)),
    YftPhysicsDamping.declare(YftPhysicsDampingKind.ANGULAR_VELOCITY_SQUARED, (0.01, 0.01, 0.01)),
)

IDENTITY_MATRIX44: YftMatrix44 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)

DEFAULT_PHYSICS_DENSITY = 300.0
YFT_ANGULAR_INERTIA_MAX_RATIO = 1.0e-3


@dataclasses.dataclass(frozen=True, slots=True)
class YftMassProperties:
    volume: float
    density: float
    mass: float
    center_of_gravity: tuple[float, float, float]
    angular_inertia: tuple[float, float, float]
    inverse_mass: float
    inverse_angular_inertia: tuple[float, float, float]

    def as_inertia(self) -> YftPhysicsInertia:
        return YftPhysicsInertia(*self.angular_inertia, mass=self.mass)


def _nonnegative_finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be a finite non-negative value")
    return result


def calculate_bound_mass_properties(
    bound: Bound | None,
    *,
    density: float | None = None,
    mass: float | None = None,
    fallback_mass: float = 1.0,
) -> YftMassProperties:
    resolved_density = bound_density(bound) if density is None else _nonnegative_finite(density, "density")
    fallback = _nonnegative_finite(fallback_mass, "fallback_mass")
    volume = 0.0 if bound is None else float(bound.compute_volume())
    if not math.isfinite(volume) or volume < 0.0:
        raise ValueError("bound volume must be a finite non-negative value")
    resolved_mass = (
        _nonnegative_finite(mass, "mass")
        if mass is not None
        else (volume * resolved_density if volume > 0.0 else fallback)
    )
    if bound is None:
        inertia = box_inertia((1.0, 1.0, 1.0), resolved_mass)
        center = (0.0, 0.0, 0.0)
    else:
        values = bound.compute_angular_inertia(resolved_mass)
        if not all(math.isfinite(value) and value >= 0.0 for value in values):
            raise ValueError("bound inertia must contain finite non-negative values")
        inertia = YftPhysicsInertia(*values, mass=resolved_mass)
        center = (
            bound.compute_center_of_gravity()
            if isinstance(bound, BoundComposite)
            else tuple(float(value) for value in bound.sphere_center)
        )
    if not all(math.isfinite(value) for value in center):
        raise ValueError("bound center of gravity must contain finite values")
    inverse_mass = 1.0 / resolved_mass if resolved_mass > 0.0 else 0.0
    inverse_inertia = tuple(
        1.0 / value if value > 0.0 else 0.0
        for value in (inertia.x, inertia.y, inertia.z)
    )
    return YftMassProperties(
        volume=volume,
        density=resolved_density,
        mass=resolved_mass,
        center_of_gravity=center,
        angular_inertia=(inertia.x, inertia.y, inertia.z),
        inverse_mass=inverse_mass,
        inverse_angular_inertia=inverse_inertia,
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
    return calculate_bound_mass_properties(bound, mass=mass).as_inertia()


def bound_mass(
    bound: Bound | None,
    *,
    density: float | None = None,
    fallback: float = 1.0,
) -> float:
    return calculate_bound_mass_properties(
        bound,
        density=density,
        fallback_mass=fallback,
    ).mass


def _primary_material_index(bound: Bound) -> int:
    if isinstance(bound, BoundGeometry) and bound.materials:
        return int(bound.materials[0].type)
    return int(bound.material_index)


def bound_density(
    bound: Bound | None,
    *,
    fallback: float = DEFAULT_PHYSICS_DENSITY,
) -> float:
    resolved_fallback = _nonnegative_finite(fallback, "fallback")
    if bound is None:
        return resolved_fallback
    if isinstance(bound, BoundComposite):
        weighted_density = 0.0
        total_volume = 0.0
        for slot in bound.children:
            child = slot.bound
            if child is None:
                continue
            volume = float(child.compute_volume())
            if not math.isfinite(volume) or volume <= 0.0:
                continue
            weighted_density += bound_density(child, fallback=resolved_fallback) * volume
            total_volume += volume
        if total_volume > 0.0:
            return weighted_density / total_volume
        return resolved_fallback
    material_density = get_bound_material_density(_primary_material_index(bound))
    return resolved_fallback if material_density is None else material_density


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
    child_inertias: Sequence[YftPhysicsInertia] = (),
    child_bounds: Sequence[Bound | None] = (),
) -> YftPhysicsDampArchetype:
    if isinstance(bound, BoundComposite) and child_inertias:
        mass_values = tuple(item.mass for item in child_inertias)
        inertia_values = tuple((item.x, item.y, item.z) for item in child_inertias)
        composite = dataclasses.replace(
            bound,
            children=[
                dataclasses.replace(
                    slot,
                    bound=(
                        child_bounds[index]
                        if index < len(child_bounds)
                        else slot.bound
                    ),
                )
                for index, slot in enumerate(bound.children)
            ],
        )
        values = composite.compute_composite_angular_inertia(
            mass,
            masses=mass_values,
            inertias=inertia_values,
        )
        inertia = YftPhysicsInertia(*values, mass=mass)
    else:
        inertia = bound_inertia(bound, mass)
    inv_mass = 1.0 / mass if mass > 0.0 else 0.0
    inv_inertia = tuple(1.0 / value if value > 0.0 else 0.0 for value in (inertia.x, inertia.y, inertia.z))
    return YftPhysicsDampArchetype(
        resource_type=2,
        # RAGE's phArchetype defaults are DEFAULT_TYPE (bit 0) and
        # INCLUDE_FLAGS_ALL.  Vanilla GTA V fragments serialize these values
        # explicitly before fragManager applies its game-specific defaults at
        # page-in time.
        type_flags=1,
        include_flags=0xFFFFFFFF,
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
    if joint_type is YftPhysicsJointType.PRISMATIC:
        raise ValueError("GTA V fragment resources do not construct prismatic joints")
    joint_class = (
        YftPhysicsJoint3Dof
        if joint_type is YftPhysicsJointType.THREE_DOF
        else YftPhysicsJoint1Dof
    )
    declared_joints = tuple(
        joint_class(
            parent_link_index=index,
            child_link_index=index + 1,
            orientation_parent=IDENTITY_MATRIX44,
            orientation_child=IDENTITY_MATRIX44,
        )
        for index in range(joints)
    )
    return YftArticulatedBodyType(
        vft=PH_ARTICULATED_BODY_TYPE_EUPHORIA_VFT,
        joint_parent_indices=tuple(parent_indices[:23]),
        num_links=links,
        num_joints=joints,
        joints=declared_joints,
        joint_types=tuple(joint_type for _ in range(joints)),
        locally_owned=True,
    )


def _composite_for_leaf(
    bound: Bound,
    profile: YftPhysicsBoundProfile,
) -> BoundComposite:
    composite = BoundComposite(
        bound_type=BoundType.COMPOSITE,
        sphere_radius=float(bound.sphere_radius),
        box_max=tuple(bound.box_max),
        margin=float(bound.margin),
        box_min=tuple(bound.box_min),
        box_center=tuple(bound.box_center),
        sphere_center=tuple(bound.sphere_center),
        file_vft=0,
        ref_count=1,
        angular_inertia=tuple(bound.angular_inertia),
        volume=float(bound.compute_volume()),
        children=[
            BoundChild(
                bound=bound,
                transform=identity_bound_transform(),
                bounds=BoundAabb(
                    minimum=tuple(bound.box_min),
                    maximum=tuple(bound.box_max),
                ),
            )
        ],
    )
    composite.file_vft = profile_file_vft(composite, profile)
    return composite


def prepare_physics_bound(
    bound: Bound,
    *,
    profile: YftPhysicsBoundProfile | str = YftPhysicsBoundProfile.PROP,
) -> Bound:
    resolved = coerce_yft_physics_bound_profile(profile)
    if (
        resolved is not YftPhysicsBoundProfile.PRESERVE
        and not isinstance(bound, BoundComposite)
    ):
        return _composite_for_leaf(bound, resolved)
    return bound


def _bound_for_child(
    root: Bound | None,
    child: YftPhysicsChild,
    index: int,
    *,
    damaged: bool,
) -> Bound | None:
    entity_bound = child.damaged_bound if damaged else child.undamaged_bound
    if damaged:
        return entity_bound
    if isinstance(root, BoundComposite):
        if index < len(root.children):
            slot_bound = root.children[index].bound
            if slot_bound is not None:
                return slot_bound
        return entity_bound
    if index == 0:
        return root or entity_bound
    return entity_bound


def normalize_physics_lod(
    lod: YftPhysicsLod,
    *,
    composite_bound: Bound | None = None,
    density: float | None = None,
    has_damaged_drawable: bool = False,
    profile: YftPhysicsBoundProfile | str = YftPhysicsBoundProfile.PROP,
    recalculate_mass_properties: bool = False,
) -> YftPhysicsLod:
    resolved_profile = coerce_yft_physics_bound_profile(profile)
    source_bound = composite_bound or lod.composite_bound
    bound = (
        prepare_physics_bound(source_bound, profile=resolved_profile)
        if source_bound is not None
        else None
    )
    groups = tuple(lod.groups)
    children = tuple(lod.children)
    if not groups:
        child = YftPhysicsChild.declare(
            undamaged_mass=bound_mass(bound, density=density),
            owner_group_name="default",
        )
        groups = (YftPhysicsGroup.declare("default", children=(child,)),)
        declared = YftPhysicsLod.declare(lod.label, groups=groups, root_cg_offset=lod.root_cg_offset)
        return normalize_physics_lod(
            declared,
            composite_bound=bound,
            density=density,
            has_damaged_drawable=has_damaged_drawable,
            profile=resolved_profile,
            recalculate_mass_properties=recalculate_mass_properties,
        )

    resolved_groups = []
    resolved_children: list[YftPhysicsChild] = []
    undamaged_child_bounds: list[Bound | None] = []
    damaged_child_bounds: list[Bound | None] = []
    declared_child_count = sum(len(group.children) for group in groups) or len(children)
    cursor = 0
    for index, group in enumerate(groups):
        group_name = group.name or group.debug_name or f"group_{index}"
        group_children = tuple(group.children)
        if not group_children and group.child_index != 0xFF:
            group_children = children[group.child_index : group.child_index + group.num_children]
        normalized_children = []
        for child_index, child in enumerate(group_children, start=cursor):
            child_bound = _bound_for_child(
                bound,
                child,
                child_index,
                damaged=False,
            )
            damaged_bound = _bound_for_child(
                bound,
                child,
                child_index,
                damaged=True,
            )
            if damaged_bound is None and has_damaged_drawable and declared_child_count == 1:
                damaged_bound = child_bound
            mass = (
                bound_mass(child_bound, density=density)
                if recalculate_mass_properties or child.undamaged_mass <= 0.0
                else child.undamaged_mass
            )
            damaged_mass = (
                (
                    bound_mass(damaged_bound, density=density)
                    if damaged_bound is not None
                    else mass
                )
                if recalculate_mass_properties or child.damaged_mass <= 0.0
                else child.damaged_mass
            )
            undamaged_inertia = (
                bound_inertia(child_bound, mass)
                if recalculate_mass_properties
                or child.undamaged_ang_inertia.mass <= 0.0
                else child.undamaged_ang_inertia
            )
            damaged_inertia = (
                (
                    bound_inertia(damaged_bound, damaged_mass)
                    if damaged_bound is not None
                    else YftPhysicsInertia(mass=damaged_mass)
                )
                if recalculate_mass_properties
                or child.damaged_ang_inertia.mass <= 0.0
                else child.damaged_ang_inertia
            )
            undamaged_child_bounds.append(child_bound)
            damaged_child_bounds.append(damaged_bound)
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
                children=tuple(normalized_children),
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
    declared_undamaged_inertia = tuple(lod.undamaged_ang_inertia)
    declared_damaged_inertia = tuple(lod.damaged_ang_inertia)
    undamaged_inertia = (
        declared_undamaged_inertia
        if not recalculate_mass_properties
        and len(declared_undamaged_inertia) == len(resolved_children)
        and all(item.mass > 0.0 for item in declared_undamaged_inertia)
        else tuple(child.undamaged_ang_inertia for child in resolved_children)
    )
    damaged_inertia = (
        declared_damaged_inertia
        if not recalculate_mass_properties
        and len(declared_damaged_inertia) == len(resolved_children)
        and all(item.mass > 0.0 for item in declared_damaged_inertia)
        else tuple(child.damaged_ang_inertia for child in resolved_children)
    )
    link_attachments = lod.link_attachments
    if not link_attachments.matrices:
        link_attachments = YftPhysicsTransforms.declare(
            IDENTITY_MATRIX44 for _ in resolved_children
        )
    elif len(link_attachments.matrices) != len(resolved_children):
        raise ValueError(
            "link attachment count must match the physics child count"
        )
    largest = max(
        (
            max(item.x, item.y, item.z)
            for item in (*undamaged_inertia, *damaged_inertia)
        ),
        default=0.0,
    )
    smallest = largest * YFT_ANGULAR_INERTIA_MAX_RATIO
    total_mass = sum(child.undamaged_mass for child in resolved_children)
    damp_undamaged = (
        None if recalculate_mass_properties else lod.undamaged_damp_archetype
    ) or default_damp_archetype(
        bound=bound,
        mass=total_mass,
        damping_constants=damping_constants,
        child_inertias=undamaged_inertia,
        child_bounds=undamaged_child_bounds,
    )
    has_damage_state = has_damaged_drawable or any(
        child.has_damage_state for child in resolved_children
    )
    damp_damaged = (
        None if recalculate_mass_properties else lod.damaged_damp_archetype
    )
    if damp_damaged is None and has_damage_state:
        damp_damaged = default_damp_archetype(
            bound=bound,
            mass=(
                sum(child.damaged_mass for child in resolved_children)
                or total_mass
            ),
            damping_constants=damping_constants,
            child_inertias=damaged_inertia,
            child_bounds=damaged_child_bounds,
        )
    normalized = dataclasses.replace(
        lod,
        num_groups=len(resolved_groups),
        root_group_count=sum(1 for group in resolved_groups if group.is_root_group),
        # This is the number of damage regions on the root child, not the
        # number of damageable groups in the hierarchy.  The generic fragment
        # authoring path does not create multiple root-child damage regions.
        num_root_damage_regions=1,
        # ``numBonyChildren`` is the length of the leading bone-driven child
        # range. Bone id 0 is the skeleton root and is therefore a valid bony
        # child. Preserve the count supplied by the format-specific authoring
        # path instead of deriving it from ``bone_id != 0``.
        num_bony_children=max(
            0,
            min(int(lod.num_bony_children), len(resolved_children)),
        ),
        num_children=len(resolved_children),
        group_names=tuple(group.name or group.debug_name for group in resolved_groups),
        groups=tuple(resolved_groups),
        children=tuple(resolved_children),
        damping_constants=damping_constants[:6],
        min_breaking_impulses=min_impulses[: len(resolved_children)],
        undamaged_ang_inertia=undamaged_inertia[: len(resolved_children)],
        damaged_ang_inertia=damaged_inertia[: len(resolved_children)],
        link_attachments=dataclasses.replace(
            link_attachments,
            matrices=link_attachments.matrices[: len(resolved_children)],
        ),
        smallest_ang_inertia=(
            smallest
            if recalculate_mass_properties
            else lod.smallest_ang_inertia or smallest
        ),
        largest_ang_inertia=(
            largest
            if recalculate_mass_properties
            else lod.largest_ang_inertia or largest
        ),
        min_move_force=lod.min_move_force or 0.0,
        composite_bound=bound,
        undamaged_damp_archetype=damp_undamaged,
        damaged_damp_archetype=damp_damaged,
        articulated_body_type=lod.articulated_body_type,
    )
    if normalized.composite_bound is None:
        raise ValueError(f"physics LOD '{lod.label}' requires a composite bound")
    profile_issues = validate_bound_profile(
        normalized.composite_bound,
        resolved_profile,
        expected_slots=len(normalized.children),
    )
    profile_issues.raise_for_errors()
    apply_physics_lod_bound_ref_counts(normalized)
    return normalized


def physics_lod_pointers_for(lods: Sequence[YftPhysicsLod]) -> YftPhysicsLodPointers:
    labels = {lod.label.lower(): lod.pointer for lod in lods}
    return YftPhysicsLodPointers(
        high=labels.get("high", 0),
        medium=labels.get("medium", 0),
        low=labels.get("low", 0),
    )


__all__ = [
    "DEFAULT_DAMPING_CONSTANTS",
    "DEFAULT_PHYSICS_DENSITY",
    "IDENTITY_MATRIX44",
    "YftMassProperties",
    "bound_density",
    "bound_inertia",
    "bound_mass",
    "box_inertia",
    "calculate_bound_mass_properties",
    "default_articulated_body_type",
    "default_damp_archetype",
    "normalize_physics_lod",
    "physics_lod_pointers_for",
    "prepare_physics_bound",
    "simple_physics_bound",
]
