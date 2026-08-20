from __future__ import annotations

import dataclasses
import struct
from collections.abc import Sequence

from ..bounds import (
    Bound,
    BoundAabb,
    BoundChild,
    BoundComposite,
    calculate_bound_ref_counts,
    gen9_bound_file_vft,
    write_bound_resource,
)
from ..resource import ResourceWriter
from ..vector import Vector3
from .bound_ownership import physics_bound_owner_roots
from .bound_profiles import (
    YftPhysicsBoundProfile,
    coerce_yft_physics_bound_profile,
    profile_file_vft,
)
from .constants import DAT_VIRTUAL_BASE
from .events_writer import event_set_pointer, write_child_event_pointers
from .physics import (
    YftArticulatedBodyType,
    YftPhysicsChild,
    YftPhysicsDampArchetype,
    YftPhysicsDamping,
    YftPhysicsGroup,
    YftPhysicsInertia,
    YftPhysicsJoint1Dof,
    YftPhysicsJoint3Dof,
    YftPhysicsLod,
    YftPhysicsTransforms,
)
from .physics_authoring import normalize_physics_lod
from .resource_headers import (
    LEGACY_YFT_RUNTIME_HEADERS,
    RESOURCE_STATE,
    YftRuntimeHeaders,
)

_PHYSICS_LOD_GROUP_SIZE = 0x30
_PHYSICS_LOD_SIZE = 0x130
_PHYSICS_GROUP_SIZE = 0xB0
_PHYSICS_CHILD_SIZE = 0x100
_ARCHETYPE_DAMP_SIZE = 0xE0
_ARTICULATED_BODY_SIZE = 0xA4
_JOINT_1DOF_SIZE = 0xB0
_JOINT_3DOF_SIZE = 0xF0


def _write_resource_header(
    writer: ResourceWriter,
    offset: int,
    *,
    vft: int,
    resource_state: int,
    expected_vft: int | None,
    label: str,
) -> None:
    if not int(vft):
        raise ValueError(f"{label} requires an explicit non-zero runtime VFT")
    if expected_vft is not None and int(vft) != expected_vft:
        raise ValueError(
            f"{label} uses unsupported VFT 0x{int(vft):08X}; "
            f"expected 0x{expected_vft:08X}"
        )
    if int(resource_state) != RESOURCE_STATE:
        raise ValueError(
            f"{label} uses unsupported resource state {int(resource_state)}; "
            f"expected {RESOURCE_STATE}"
        )
    writer.pack_into("II", offset, int(vft), RESOURCE_STATE)


def write_physics_child_header(
    writer: ResourceWriter,
    offset: int,
    child: YftPhysicsChild | None = None,
    *,
    runtime_headers: YftRuntimeHeaders = LEGACY_YFT_RUNTIME_HEADERS,
) -> None:
    _write_resource_header(
        writer,
        offset,
        vft=runtime_headers.physics_child,
        resource_state=(
            child.resource_state if child is not None else RESOURCE_STATE
        ),
        expected_vft=runtime_headers.physics_child,
        label="fragTypeChild",
    )


def _virtual(offset: int) -> int:
    return DAT_VIRTUAL_BASE + int(offset)


def _write_vec3_padded(
    writer: ResourceWriter,
    offset: int,
    value: Vector3,
) -> None:
    writer.pack_into("4f", offset, value.x, value.y, value.z, 0.0)


def _write_damping(
    writer: ResourceWriter,
    offset: int,
    constants: Sequence[YftPhysicsDamping],
) -> None:
    for index, item in enumerate(constants[:6]):
        writer.pack_into("4f", offset + index * 16, item.x, item.y, item.z, 0.0)


def _write_inertia_array(
    writer: ResourceWriter,
    values: Sequence[YftPhysicsInertia],
) -> int:
    if not values:
        return 0
    offset = writer.alloc(len(values) * 16, 16, relocate_pointers=False)
    for index, inertia in enumerate(values):
        writer.pack_into("4f", offset + index * 16, *inertia.as_tuple())
    return offset


def _write_float_array(writer: ResourceWriter, values: Sequence[float]) -> int:
    if not values:
        return 0
    offset = writer.alloc(len(values) * 4, 4, relocate_pointers=False)
    for index, value in enumerate(values):
        writer.pack_into("f", offset + index * 4, float(value))
    return offset


def _write_u8_array(writer: ResourceWriter, values: Sequence[int]) -> int:
    if not values:
        return 0
    offset = writer.alloc(len(values), 1, relocate_pointers=False)
    writer.data[offset : offset + len(values)] = bytes(int(value) & 0xFF for value in values)
    return offset


def _write_pointer_array(writer: ResourceWriter, pointers: Sequence[int]) -> int:
    if not pointers:
        return 0
    offset = writer.alloc(len(pointers) * 8, 8)
    for index, pointer in enumerate(pointers):
        writer.pack_into("Q", offset + index * 8, pointer)
    return offset


def _physics_bound_child_offsets(
    writer: ResourceWriter,
    bound: Bound,
    bound_offset: int,
    *,
    child_count: int,
    label: str,
) -> tuple[int, ...]:
    """Return the native bound owned by every fragment physics child.

    GTA V does not resource-construct the bound referenced by a
    ``fragDrawable``.  Vanilla fragments instead point every physics entity
    drawable at the corresponding child owned by the archetype's
    ``phBoundComposite``.  A one-child archetype may own the bound directly.
    """

    if isinstance(bound, BoundComposite):
        pointer = struct.unpack_from("<Q", writer.data, bound_offset + 0x70)[0]
        count = struct.unpack_from("<H", writer.data, bound_offset + 0xA0)[0]
        if count < child_count:
            raise ValueError(
                f"{label} composite has {count} bound children for "
                f"{child_count} fragment physics children"
            )
        if count == 0:
            return ()
        if not pointer:
            raise ValueError(f"{label} composite child pointer array is null")
        pointer_offset = pointer - DAT_VIRTUAL_BASE
        offsets: list[int] = []
        for index in range(child_count):
            child_pointer = struct.unpack_from(
                "<Q",
                writer.data,
                pointer_offset + index * 8,
            )[0]
            offsets.append(
                child_pointer - DAT_VIRTUAL_BASE if child_pointer else 0
            )
        return tuple(offsets)
    if child_count == 1:
        return (bound_offset,)
    raise ValueError(
        f"{label} must be a phBoundComposite for {child_count} "
        "fragment physics children"
    )


def _build_damaged_physics_bound(
    lod: YftPhysicsLod,
    *,
    damaged_drawable_offset: int,
) -> Bound:
    source = lod.composite_bound
    if source is None:
        raise ValueError(f"physics LOD '{lod.label}' requires a composite_bound")
    if not isinstance(source, BoundComposite):
        if len(lod.children) == 1:
            child = lod.children[0]
            if (
                child.damaged_entity is not None
                and child.damaged_entity.drawable is not None
                and child.damaged_entity.drawable.bound is not None
            ):
                return child.damaged_entity.drawable.bound
        return source

    slots: list[BoundChild] = []
    for index, child in enumerate(lod.children):
        base_slot = (
            source.children[index]
            if index < len(source.children)
            else BoundChild(bound=None)
        )
        damaged_bound = None
        if (
            child.damaged_entity is not None
            and child.damaged_entity.drawable is not None
        ):
            damaged_bound = child.damaged_entity.drawable.bound
        elif len(lod.children) == 1 and damaged_drawable_offset:
            damaged_bound = base_slot.bound
        slots.append(
            dataclasses.replace(
                base_slot,
                bound=damaged_bound,
                bounds=(
                    BoundAabb(damaged_bound.box_min, damaged_bound.box_max)
                    if damaged_bound is not None
                    else None
                ),
                flags1=base_slot.flags1 if damaged_bound is not None else None,
                flags2=base_slot.flags2 if damaged_bound is not None else None,
            )
        )
    return dataclasses.replace(
        source,
        children=slots,
        bvh=None,
    ).build()


def _sparsify_damaged_bound_children(
    writer: ResourceWriter,
    lod: YftPhysicsLod,
    damaged_bound: Bound | None,
    damaged_bound_offset: int,
    *,
    damaged_drawable_offset: int,
) -> None:
    """Null damaged composite children that have no damaged entity.

    Vanilla fragments keep the damaged composite's slot count aligned with
    ``fragPhysicsLOD::m_Children`` but leave the corresponding bound pointer
    null whenever that physics child has no damaged drawable.  Copying the
    intact bound into every slot makes importers and the runtime pair a
    damaged collision with a null damaged entity.
    """

    if not damaged_bound_offset or not isinstance(
        damaged_bound,
        BoundComposite,
    ):
        return
    children_pointer = struct.unpack_from(
        "<Q",
        writer.data,
        damaged_bound_offset + 0x70,
    )[0]
    child_count = struct.unpack_from(
        "<H",
        writer.data,
        damaged_bound_offset + 0xA0,
    )[0]
    if child_count != len(lod.children):
        raise ValueError(
            f"physics LOD '{lod.label}' damaged composite has {child_count} "
            f"bound children for {len(lod.children)} physics children"
        )
    if not children_pointer and child_count:
        raise ValueError(
            f"physics LOD '{lod.label}' damaged composite child pointer "
            "array is null"
        )
    pointer_offset = children_pointer - DAT_VIRTUAL_BASE
    for index, child in enumerate(lod.children):
        has_damaged_drawable = bool(
            child.damaged_entity is not None
            and child.damaged_entity.drawable is not None
        )
        if len(lod.children) == 1 and damaged_drawable_offset:
            has_damaged_drawable = True
        if not has_damaged_drawable:
            writer.pack_into("Q", pointer_offset + index * 8, 0)


def _link_physics_entity_bounds(
    writer: ResourceWriter,
    lod: YftPhysicsLod,
    *,
    main_drawable_offset: int,
    damaged_drawable_offset: int,
    entity_drawable_offsets: dict[int, int],
    undamaged_bound_offsets: Sequence[int],
    damaged_bound_offsets: Sequence[int],
) -> None:
    linked: dict[int, int] = {}
    for index, child in enumerate(lod.children):
        for state, entity, bound_offsets in (
            ("undamaged", child.undamaged_entity, undamaged_bound_offsets),
            ("damaged", child.damaged_entity, damaged_bound_offsets),
        ):
            drawable_offset = 0
            if entity is not None and entity.drawable is not None:
                drawable_offset = entity_drawable_offsets.get(
                    id(entity.drawable),
                    0,
                )
                if not drawable_offset:
                    raise ValueError(
                        f"physics child entity '{entity.label}' was not "
                        "prepared for writing"
                    )
            elif len(lod.children) == 1:
                drawable_offset = (
                    damaged_drawable_offset
                    if state == "damaged"
                    else main_drawable_offset
                )
            if not drawable_offset:
                continue
            if index >= len(bound_offsets):
                raise ValueError(
                    f"physics child {index} has a {state} drawable but the "
                    f"{state} archetype has no matching bound child"
                )
            bound_offset = int(bound_offsets[index])
            if not bound_offset:
                # Vanilla fragments retain an empty fragDrawable for visual
                # or bone bookkeeping even when this state has no collision.
                # Its non-owning bound pointer must remain null.
                writer.pack_into(
                    "Q",
                    drawable_offset + 0xF0,
                    0,
                )
                continue
            previous = linked.get(drawable_offset)
            if previous is not None and previous != bound_offset:
                raise ValueError(
                    f"physics drawable '{entity.label if entity else state}' "
                    "is shared by children "
                    "that require different native bounds"
                )
            linked[drawable_offset] = bound_offset
            # fragDrawable::m_Bound is a non-owning reference.  The matching
            # phArchetype/phBoundComposite owns and resource-constructs it.
            writer.pack_into(
                "Q",
                drawable_offset + 0xF0,
                _virtual(bound_offset),
            )


def _write_physics_transforms(
    writer: ResourceWriter,
    transforms: YftPhysicsTransforms,
    *,
    runtime_headers: YftRuntimeHeaders,
) -> int:
    if not transforms.matrices:
        return 0
    offset = writer.alloc(0x20 + len(transforms.matrices) * 64, 16)
    _write_resource_header(
        writer,
        offset,
        vft=runtime_headers.physics_transforms,
        resource_state=transforms.resource_state,
        expected_vft=runtime_headers.physics_transforms,
        label="fragPhysTransforms",
    )
    writer.pack_into("Q", offset + 8, int(transforms.reserved_08))
    writer.pack_into("I", offset + 0x10, len(transforms.matrices))
    writer.pack_into("I", offset + 0x14, int(transforms.reserved_14))
    writer.pack_into("Q", offset + 0x18, int(transforms.reserved_18))
    for index, matrix in enumerate(transforms.matrices):
        base = offset + 0x20 + index * 64
        for row in range(4):
            writer.pack_into("4f", base + row * 16, *matrix[row])
    return offset


def _group_name_offsets(writer: ResourceWriter, lod: YftPhysicsLod) -> int:
    declared_names = tuple(lod.group_names)
    names = tuple(
        (
            declared_names[index]
            if index < len(declared_names) and declared_names[index]
            else group.name or group.debug_name or f"group_{index}"
        )
        for index, group in enumerate(lod.groups)
    )
    offsets = [writer.c_string(name) for name in names]
    # The resource constructor writes a static sentinel into slot N.
    return _write_pointer_array(
        writer,
        [*(_virtual(offset) for offset in offsets), 0],
    )


def _write_physics_group(
    writer: ResourceWriter,
    group: YftPhysicsGroup,
    *,
    event_set_offsets: dict[int, int],
) -> int:
    offset = writer.alloc(_PHYSICS_GROUP_SIZE, 16)
    writer.pack_into(
        "Q",
        offset + 0x00,
        event_set_pointer(
            group.events.death,
            event_set_offsets,
            virtual_base=DAT_VIRTUAL_BASE,
        ),
    )
    writer.pack_into(
        "Q",
        offset + 0x08,
        int(group.events.death_player_pointer),
    )
    writer.pack_into(
        "13f",
        offset + 0x10,
        float(group.strength),
        float(group.force_transmission_scale_up),
        float(group.force_transmission_scale_down),
        float(group.joint_stiffness),
        float(group.min_soft_angle_1),
        float(group.max_soft_angle_1),
        float(group.max_soft_angle_2),
        float(group.max_soft_angle_3),
        float(group.rotation_speed),
        float(group.rotation_strength),
        float(group.restoring_strength),
        float(group.restoring_max_torque),
        float(group.latch_strength),
    )
    writer.pack_into("ff", offset + 0x44, group.total_undamaged_mass, group.total_damaged_mass)
    writer.data[offset + 0x4C] = int(group.child_groups_pointers_index) & 0xFF
    writer.data[offset + 0x4D] = int(group.parent_group_pointer_index) & 0xFF
    writer.data[offset + 0x4E] = int(group.child_index) & 0xFF
    writer.data[offset + 0x4F] = int(group.num_children) & 0xFF
    writer.data[offset + 0x50] = int(group.num_child_groups) & 0xFF
    writer.data[offset + 0x51] = int(group.glass_model_and_type or 0xFF) & 0xFF
    writer.data[offset + 0x52] = int(group.glass_pane_model_info_index) & 0xFF
    writer.data[offset + 0x53] = int(group.flags) & 0xFF
    writer.pack_into(
        "10f",
        offset + 0x54,
        group.min_damage_force,
        group.damage_health,
        group.weapon_health,
        group.weapon_scale,
        group.vehicle_scale,
        group.ped_scale,
        group.ragdoll_scale,
        group.explosion_scale,
        group.object_scale,
        group.ped_inv_mass_scale,
    )
    writer.pack_into("i", offset + 0x7C, int(group.preset_applied))
    debug_name = (group.debug_name or group.name).encode("ascii", "ignore")[:39]
    writer.data[offset + 0x80 : offset + 0x80 + len(debug_name)] = debug_name
    writer.pack_into("f", offset + 0xA8, float(group.melee_scale))
    return offset


def _child_entity_pointer(
    child: YftPhysicsChild,
    *,
    damaged: bool,
    main_drawable_offset: int,
    damaged_drawable_offset: int,
    entity_drawable_offsets: dict[int, int],
    allow_fragment_fallback: bool,
) -> int:
    entity = child.damaged_entity if damaged else child.undamaged_entity
    if entity is not None and entity.drawable is not None:
        offset = entity_drawable_offsets.get(id(entity.drawable))
        if offset is None:
            raise ValueError(
                f"physics child entity '{entity.label}' was not prepared for writing"
            )
        return _virtual(offset)
    if allow_fragment_fallback and damaged and damaged_drawable_offset:
        return _virtual(damaged_drawable_offset)
    if allow_fragment_fallback and not damaged and main_drawable_offset:
        return _virtual(main_drawable_offset)
    return 0


def _write_physics_child(
    writer: ResourceWriter,
    child: YftPhysicsChild,
    *,
    offset: int | None = None,
    main_drawable_offset: int,
    damaged_drawable_offset: int,
    entity_drawable_offsets: dict[int, int],
    event_set_offsets: dict[int, int],
    allow_fragment_fallback: bool,
    runtime_headers: YftRuntimeHeaders,
) -> int:
    child_offset = writer.alloc(_PHYSICS_CHILD_SIZE, 16) if offset is None else offset
    write_physics_child_header(
        writer,
        child_offset,
        child,
        runtime_headers=runtime_headers,
    )
    writer.pack_into("ff", child_offset + 0x08, child.undamaged_mass, child.damaged_mass)
    writer.data[child_offset + 0x10] = int(child.owner_group_pointer_index) & 0xFF
    writer.data[child_offset + 0x11] = int(child.flags) & 0xFF
    writer.pack_into("H", child_offset + 0x12, int(child.bone_id) & 0xFFFF)
    writer.pack_into(
        "Q",
        child_offset + 0xA0,
        _child_entity_pointer(
            child,
            damaged=False,
            main_drawable_offset=main_drawable_offset,
            damaged_drawable_offset=damaged_drawable_offset,
            entity_drawable_offsets=entity_drawable_offsets,
            allow_fragment_fallback=allow_fragment_fallback,
        ),
    )
    writer.pack_into(
        "Q",
        child_offset + 0xA8,
        _child_entity_pointer(
            child,
            damaged=True,
            main_drawable_offset=main_drawable_offset,
            damaged_drawable_offset=damaged_drawable_offset,
            entity_drawable_offsets=entity_drawable_offsets,
            allow_fragment_fallback=allow_fragment_fallback,
        ),
    )
    write_child_event_pointers(
        writer,
        child_offset,
        child.events,
        event_set_offsets,
        virtual_base=DAT_VIRTUAL_BASE,
    )
    return child_offset


def _write_damp_archetype(
    writer: ResourceWriter,
    archetype: YftPhysicsDampArchetype,
    *,
    bound_pointer: int,
    runtime_headers: YftRuntimeHeaders,
) -> int:
    offset = writer.alloc(_ARCHETYPE_DAMP_SIZE, 16)
    _write_resource_header(
        writer,
        offset,
        vft=runtime_headers.damp_archetype,
        resource_state=archetype.resource_state,
        expected_vft=runtime_headers.damp_archetype,
        label="phArchetypeDamp",
    )
    writer.pack_into("i", offset + 0x10, int(archetype.resource_type or 2))
    filename_offset = writer.c_string(archetype.filename) if archetype.filename else 0
    writer.pack_into("Q", offset + 0x18, _virtual(filename_offset) if filename_offset else 0)
    writer.pack_into("Q", offset + 0x20, int(bound_pointer))
    writer.pack_into(
        "IIHH",
        offset + 0x28,
        int(archetype.type_flags),
        int(archetype.include_flags),
        int(archetype.property_flags),
        int(archetype.ref_count),
    )
    writer.pack_into(
        "6f",
        offset + 0x40,
        float(archetype.mass),
        float(archetype.inv_mass),
        float(archetype.gravity_factor),
        float(archetype.max_speed),
        float(archetype.max_ang_speed),
        float(archetype.buoyancy_factor),
    )
    _write_vec3_padded(writer, offset + 0x60, archetype.angular_inertia)
    _write_vec3_padded(writer, offset + 0x70, archetype.inv_angular_inertia)
    _write_damping(writer, offset + 0x80, archetype.damping_constants)
    return offset


def _write_articulated_body_type(
    writer: ResourceWriter,
    body: YftArticulatedBodyType | None,
    *,
    inertia: Sequence[YftPhysicsInertia],
    runtime_headers: YftRuntimeHeaders,
) -> int:
    if body is None:
        return 0
    offset = writer.alloc(_ARTICULATED_BODY_SIZE, 16)
    _write_resource_header(
        writer,
        offset,
        vft=runtime_headers.articulated_body,
        resource_state=body.resource_state,
        expected_vft=None,
        label="phArticulatedBodyType",
    )
    parent_indices = tuple(body.joint_parent_indices) or (-1,) * 23
    for index in range(23):
        value = parent_indices[index] if index < len(parent_indices) else -1
        writer.pack_into("i", offset + 0x10 + index * 4, int(value))
    writer.pack_into("ff", offset + 0x6C, body.replace_upon_reresource, body.angular_decay_rate)
    joint_offsets = [
        _write_physics_joint(writer, joint, runtime_headers=runtime_headers)
        for joint in body.joints
    ]
    joint_pointer_offset = _write_pointer_array(
        writer, [_virtual(joint_offset) for joint_offset in joint_offsets]
    )
    inertia_offset = _write_inertia_array(writer, body.resourced_ang_inertia or tuple(inertia))
    writer.pack_into("Q", offset + 0x78, _virtual(joint_pointer_offset) if joint_pointer_offset else 0)
    writer.pack_into("Q", offset + 0x80, _virtual(inertia_offset) if inertia_offset else 0)
    writer.data[offset + 0x88] = int(body.num_links) & 0xFF
    num_joints = len(body.joints) if body.joints else int(body.num_joints)
    writer.data[offset + 0x89] = num_joints & 0xFF
    joint_types = (
        tuple(joint.joint_type for joint in body.joints)
        if body.joints
        else body.joint_types
    )
    for index, joint_type in enumerate(joint_types[:22]):
        writer.data[offset + 0x8A + index] = int(joint_type) & 0xFF
    writer.data[offset + 0xA0] = 1 if body.locally_owned else 0
    return offset


def _write_matrix44(writer: ResourceWriter, offset: int, matrix) -> None:
    for row in range(4):
        writer.pack_into("4f", offset + row * 16, *matrix[row])


def _write_physics_joint(
    writer: ResourceWriter,
    joint: YftPhysicsJoint1Dof | YftPhysicsJoint3Dof,
    *,
    runtime_headers: YftRuntimeHeaders = LEGACY_YFT_RUNTIME_HEADERS,
) -> int:
    if isinstance(joint, YftPhysicsJoint1Dof):
        size = _JOINT_1DOF_SIZE
    elif isinstance(joint, YftPhysicsJoint3Dof):
        size = _JOINT_3DOF_SIZE
    else:
        raise TypeError("YFT resources only support 1DOF and 3DOF joint types")
    offset = writer.alloc(size, 16)
    expected_vft = (
        runtime_headers.joint_1dof
        if isinstance(joint, YftPhysicsJoint1Dof)
        else runtime_headers.joint_3dof
    )
    _write_resource_header(
        writer,
        offset,
        vft=expected_vft,
        resource_state=joint.resource_state,
        expected_vft=expected_vft,
        label=type(joint).__name__,
    )
    writer.pack_into("Qf", offset + 0x08, 0, joint.default_stiffness)
    writer.data[offset + 0x14] = 1 if joint.enforce_exceeded_limits else 0
    writer.data[offset + 0x15] = int(joint.joint_type)
    writer.data[offset + 0x16] = int(joint.parent_link_index) & 0xFF
    writer.data[offset + 0x17] = int(joint.child_link_index) & 0xFF
    _write_matrix44(writer, offset + 0x20, joint.orientation_parent)
    _write_matrix44(writer, offset + 0x60, joint.orientation_child)
    if isinstance(joint, YftPhysicsJoint1Dof):
        writer.pack_into(
            "4f",
            offset + 0xA0,
            joint.hard_angle_min,
            joint.hard_angle_max,
            joint.max_muscle_torque,
            joint.min_muscle_torque,
        )
    else:
        writer.pack_into(
            "4f",
            offset + 0xA0,
            joint.hard_first_lean_angle_max,
            joint.hard_second_lean_angle_max,
            joint.hard_twist_angle_max,
            joint.soft_limit_ratio,
        )
        writer.pack_into("f", offset + 0xB0, joint.twist_offset)
        writer.data[offset + 0xB4] = 1 if joint.use_child_for_twist_axis else 0
        writer.pack_into("3f", offset + 0xC0, *joint.max_muscle_torque)
        writer.pack_into("3f", offset + 0xD0, *joint.min_muscle_torque)
        writer.pack_into(
            "2f",
            offset + 0xE0,
            joint.soft_limit_lean_strength,
            joint.soft_limit_twist_strength,
        )
    return offset


def _write_child_array(
    writer: ResourceWriter,
    lod: YftPhysicsLod,
    *,
    root_child_offset: int,
    main_drawable_offset: int,
    damaged_drawable_offset: int,
    entity_drawable_offsets: dict[int, int],
    event_set_offsets: dict[int, int],
    runtime_headers: YftRuntimeHeaders,
) -> int:
    child_offsets: list[int] = []
    for index, child in enumerate(lod.children):
        child_offsets.append(
            _write_physics_child(
                writer,
                child,
                offset=root_child_offset if index == 0 and root_child_offset else None,
                main_drawable_offset=main_drawable_offset,
                damaged_drawable_offset=damaged_drawable_offset,
                entity_drawable_offsets=entity_drawable_offsets,
                event_set_offsets=event_set_offsets,
                allow_fragment_fallback=len(lod.children) == 1,
                runtime_headers=runtime_headers,
            )
        )
    return _write_pointer_array(writer, [_virtual(offset) for offset in child_offsets])


def _write_physics_lod(
    writer: ResourceWriter,
    lod: YftPhysicsLod,
    *,
    root_child_offset: int,
    main_drawable_offset: int,
    damaged_drawable_offset: int,
    entity_drawable_offsets: dict[int, int],
    event_set_offsets: dict[int, int],
    bound_profile: YftPhysicsBoundProfile,
    runtime_headers: YftRuntimeHeaders,
) -> int:
    if lod.composite_bound is None:
        raise ValueError(f"physics LOD '{lod.label}' requires a composite_bound")
    bound_offset = write_bound_resource(
        writer,
        lod.composite_bound,
        ref_counts=calculate_bound_ref_counts(
            physics_bound_owner_roots(
                lod,
                fragment_drawable_fallback=bool(main_drawable_offset),
            )
        ),
        file_vft_resolver=(
            gen9_bound_file_vft
            if runtime_headers.enhanced
            else lambda bound: profile_file_vft(bound, bound_profile)
        ),
    )
    bound_pointer = _virtual(bound_offset)
    # A phArchetype owns and resource-constructs its bound. GTA V fragments
    # with both undamaged and damaged archetypes therefore store two distinct
    # bound objects, even when their serialized geometry is identical. Sharing
    # this pointer makes the second archetype construct an already-relocated
    # bound and the streamer aborts with "Invalid fixup".
    damaged_bound = (
        _build_damaged_physics_bound(
            lod,
            damaged_drawable_offset=damaged_drawable_offset,
        )
        if lod.damaged_damp_archetype is not None
        else None
    )
    damaged_bound_offset = (
        write_bound_resource(
            writer,
            damaged_bound,
            ref_counts=calculate_bound_ref_counts(
                physics_bound_owner_roots(
                    lod,
                    root=damaged_bound,
                    damaged=True,
                    fragment_drawable_fallback=bool(damaged_drawable_offset),
                )
            ),
            file_vft_resolver=(
                gen9_bound_file_vft
                if runtime_headers.enhanced
                else lambda bound: profile_file_vft(bound, bound_profile)
            ),
        )
        if damaged_bound is not None
        else 0
    )
    damaged_bound_pointer = (
        _virtual(damaged_bound_offset) if damaged_bound_offset else 0
    )
    _sparsify_damaged_bound_children(
        writer,
        lod,
        damaged_bound,
        damaged_bound_offset,
        damaged_drawable_offset=damaged_drawable_offset,
    )
    needs_undamaged_child_bounds = bool(
        (len(lod.children) == 1 and main_drawable_offset)
        or any(
            child.undamaged_entity is not None
            and child.undamaged_entity.drawable is not None
            for child in lod.children
        )
    )
    needs_damaged_child_bounds = bool(
        (len(lod.children) == 1 and damaged_drawable_offset)
        or any(
            child.damaged_entity is not None
            and child.damaged_entity.drawable is not None
            for child in lod.children
        )
    )
    undamaged_child_bound_offsets = (
        _physics_bound_child_offsets(
            writer,
            lod.composite_bound,
            bound_offset,
            child_count=len(lod.children),
            label=f"physics LOD '{lod.label}' undamaged",
        )
        if needs_undamaged_child_bounds
        else ()
    )
    damaged_child_bound_offsets = (
        _physics_bound_child_offsets(
            writer,
            damaged_bound,
            damaged_bound_offset,
            child_count=len(lod.children),
            label=f"physics LOD '{lod.label}' damaged",
        )
        if damaged_bound_offset and needs_damaged_child_bounds
        else ()
    )
    _link_physics_entity_bounds(
        writer,
        lod,
        main_drawable_offset=main_drawable_offset,
        damaged_drawable_offset=damaged_drawable_offset,
        entity_drawable_offsets=entity_drawable_offsets,
        undamaged_bound_offsets=undamaged_child_bound_offsets,
        damaged_bound_offsets=damaged_child_bound_offsets,
    )
    undamaged_damp_offset = _write_damp_archetype(
        writer,
        lod.undamaged_damp_archetype,
        bound_pointer=bound_pointer,
        runtime_headers=runtime_headers,
    ) if lod.undamaged_damp_archetype is not None else 0
    damaged_damp_offset = _write_damp_archetype(
        writer,
        lod.damaged_damp_archetype,
        bound_pointer=damaged_bound_pointer,
        runtime_headers=runtime_headers,
    ) if lod.damaged_damp_archetype is not None else 0
    body_offset = _write_articulated_body_type(
        writer,
        lod.articulated_body_type,
        inertia=lod.undamaged_ang_inertia,
        runtime_headers=runtime_headers,
    )
    group_names_offset = _group_name_offsets(writer, lod)
    group_offsets = [
        _write_physics_group(
            writer,
            group,
            event_set_offsets=event_set_offsets,
        )
        for group in lod.groups
    ]
    groups_offset = _write_pointer_array(writer, [_virtual(offset) for offset in group_offsets])
    children_offset = _write_child_array(
        writer,
        lod,
        root_child_offset=root_child_offset,
        main_drawable_offset=main_drawable_offset,
        damaged_drawable_offset=damaged_drawable_offset,
        entity_drawable_offsets=entity_drawable_offsets,
        event_set_offsets=event_set_offsets,
        runtime_headers=runtime_headers,
    )
    min_impulses_offset = _write_float_array(writer, lod.min_breaking_impulses)
    undamaged_inertia_offset = _write_inertia_array(writer, lod.undamaged_ang_inertia)
    damaged_inertia_offset = _write_inertia_array(writer, lod.damaged_ang_inertia)
    link_attachments_offset = _write_physics_transforms(
        writer,
        lod.link_attachments,
        runtime_headers=runtime_headers,
    )
    self_collision_a_offset = _write_u8_array(writer, [first for first, _second in lod.self_collision_pairs])
    self_collision_b_offset = _write_u8_array(writer, [second for _first, second in lod.self_collision_pairs])

    offset = writer.alloc(_PHYSICS_LOD_SIZE, 16)
    _write_resource_header(
        writer,
        offset,
        vft=runtime_headers.physics_lod,
        resource_state=lod.resource_state,
        expected_vft=runtime_headers.physics_lod,
        label="fragPhysicsLOD",
    )
    writer.pack_into("fff", offset + 0x14, lod.smallest_ang_inertia, lod.largest_ang_inertia, lod.min_move_force)
    writer.pack_into("Q", offset + 0x20, _virtual(body_offset) if body_offset else 0)
    writer.pack_into("Q", offset + 0x28, _virtual(min_impulses_offset) if min_impulses_offset else 0)
    _write_vec3_padded(writer, offset + 0x30, lod.root_cg_offset)
    _write_vec3_padded(writer, offset + 0x40, lod.original_root_cg_offset)
    _write_vec3_padded(writer, offset + 0x50, lod.unbroken_cg_offset)
    _write_damping(writer, offset + 0x60, lod.damping_constants)
    writer.pack_into("Q", offset + 0xC0, _virtual(group_names_offset) if group_names_offset else 0)
    writer.pack_into("Q", offset + 0xC8, _virtual(groups_offset) if groups_offset else 0)
    writer.pack_into("Q", offset + 0xD0, _virtual(children_offset) if children_offset else 0)
    writer.pack_into("Q", offset + 0xD8, _virtual(undamaged_damp_offset) if undamaged_damp_offset else 0)
    writer.pack_into("Q", offset + 0xE0, _virtual(damaged_damp_offset) if damaged_damp_offset else 0)
    writer.pack_into("Q", offset + 0xE8, bound_pointer)
    writer.pack_into("Q", offset + 0xF0, _virtual(undamaged_inertia_offset) if undamaged_inertia_offset else 0)
    writer.pack_into("Q", offset + 0xF8, _virtual(damaged_inertia_offset) if damaged_inertia_offset else 0)
    writer.pack_into("Q", offset + 0x100, _virtual(link_attachments_offset) if link_attachments_offset else 0)
    writer.pack_into("Q", offset + 0x108, _virtual(self_collision_a_offset) if self_collision_a_offset else 0)
    writer.pack_into("Q", offset + 0x110, _virtual(self_collision_b_offset) if self_collision_b_offset else 0)
    writer.data[offset + 0x118] = len(lod.self_collision_pairs) & 0xFF
    writer.data[offset + 0x119] = max(lod.max_num_self_collisions, len(lod.self_collision_pairs)) & 0xFF
    writer.data[offset + 0x11A] = len(lod.groups) & 0xFF
    writer.data[offset + 0x11B] = int(lod.root_group_count) & 0xFF
    writer.data[offset + 0x11C] = int(lod.num_root_damage_regions) & 0xFF
    writer.data[offset + 0x11D] = int(lod.num_bony_children) & 0xFF
    writer.data[offset + 0x11E] = len(lod.children) & 0xFF
    return offset


def write_physics_lod_group(
    writer: ResourceWriter,
    lods: Sequence[YftPhysicsLod],
    *,
    root_child_offset: int,
    main_drawable_offset: int,
    damaged_drawable_offset: int,
    entity_drawable_offsets: dict[int, int],
    event_set_offsets: dict[int, int],
    fallback_bound: Bound | None = None,
    bound_profile: YftPhysicsBoundProfile | str = (
        YftPhysicsBoundProfile.PROP
    ),
    runtime_headers: YftRuntimeHeaders = LEGACY_YFT_RUNTIME_HEADERS,
) -> tuple[int, tuple[YftPhysicsLod, ...]]:
    if not lods:
        return 0, ()
    resolved_profile = coerce_yft_physics_bound_profile(bound_profile)
    normalized = tuple(
        normalize_physics_lod(
            lod,
            composite_bound=lod.composite_bound or fallback_bound,
            has_damaged_drawable=bool(damaged_drawable_offset),
            profile=resolved_profile,
        )
        for lod in lods
    )
    offsets: dict[str, int] = {}
    for lod_index, lod in enumerate(normalized):
        owns_fragment_root = lod_index == 0 and lod.label.lower() == "high"
        offsets[lod.label.lower()] = _write_physics_lod(
            writer,
            lod,
            root_child_offset=root_child_offset if owns_fragment_root else 0,
            main_drawable_offset=main_drawable_offset if owns_fragment_root else 0,
            damaged_drawable_offset=(
                damaged_drawable_offset if owns_fragment_root else 0
            ),
            entity_drawable_offsets=entity_drawable_offsets,
            event_set_offsets=event_set_offsets,
            bound_profile=resolved_profile,
            runtime_headers=runtime_headers,
        )
    group_offset = writer.alloc(_PHYSICS_LOD_GROUP_SIZE, 16)
    _write_resource_header(
        writer,
        group_offset,
        vft=runtime_headers.physics_lod_group,
        resource_state=RESOURCE_STATE,
        expected_vft=runtime_headers.physics_lod_group,
        label="fragPhysicsLODGroup",
    )
    writer.pack_into("Q", group_offset + 0x10, _virtual(offsets["high"]) if "high" in offsets else 0)
    writer.pack_into("Q", group_offset + 0x18, _virtual(offsets["medium"]) if "medium" in offsets else 0)
    writer.pack_into("Q", group_offset + 0x20, _virtual(offsets["low"]) if "low" in offsets else 0)
    return group_offset, tuple(
        dataclasses.replace(lod, pointer=_virtual(offsets[lod.label.lower()]))
        for lod in normalized
    )


__all__ = [
    "write_physics_child_header",
    "write_physics_lod_group",
]
