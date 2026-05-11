from __future__ import annotations

import dataclasses

from ..binary import f32 as _f32, i32 as _i32, u16 as _u16, u32 as _u32, u64 as _u64
from ..bounds import Bound, read_bound_from_pointer
from ..ydr.shaders import ShaderLibrary
from .constants import PHYSICS_LOD_GROUP_FIELDS_OFFSET, PHYSICS_LOD_MIN_SIZE
from .drawable_reader import read_fragment_drawable
from .io_helpers import (
    read_fixed_ascii,
    read_pointer_tuple,
    read_string_pointer_array,
    read_u8_array,
    read_vec3,
    try_virtual_offset,
)
from .physics import (
    YftArticulatedBodyType,
    YftPhysicsChild,
    YftPhysicsDampArchetype,
    YftPhysicsDamping,
    YftPhysicsEntity,
    YftPhysicsEventRefs,
    YftPhysicsGroup,
    YftPhysicsGroupEventRefs,
    YftPhysicsGroupFlag,
    YftPhysicsInertia,
    YftPhysicsJointType,
    YftPhysicsLod,
    YftPhysicsLodPointers,
    YftPhysicsReference,
)

_PHYSICS_GROUP_MIN_SIZE = 0xAC
_PHYSICS_CHILD_MIN_SIZE = 0xB0
_DAMPING_CONSTANT_COUNT = 6
_ARCHETYPE_DAMP_MIN_SIZE = 0xE0
_ARCHETYPE_DAMPING_OFFSET = 0x80
_ARTICULATED_BODY_TYPE_MIN_SIZE = 0xA4
_ARTICULATED_BODY_MAX_LINKS = 23
_ARTICULATED_BODY_MAX_JOINTS = _ARTICULATED_BODY_MAX_LINKS - 1


def read_group_names(
    system_data: bytes, group_names_pointer: int, count: int
) -> tuple[str, ...]:
    if count <= 0:
        return ()
    return tuple(read_string_pointer_array(system_data, group_names_pointer, count))


def read_self_collision_pairs(
    system_data: bytes,
    pointer_a: int,
    pointer_b: int,
    count: int,
) -> tuple[tuple[int, int], ...]:
    values_a = read_u8_array(system_data, pointer_a, count)
    values_b = read_u8_array(system_data, pointer_b, count)
    return tuple(zip(values_a, values_b, strict=False))


def read_float_array(system_data: bytes, pointer: int, count: int) -> tuple[float, ...]:
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or count <= 0 or offset + (count * 4) > len(system_data):
        return ()
    return tuple(
        float(_f32(system_data, offset + (index * 4))) for index in range(count)
    )


def read_inertia_array(
    system_data: bytes, pointer: int, count: int
) -> tuple[YftPhysicsInertia, ...]:
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or count <= 0 or offset + (count * 16) > len(system_data):
        return ()
    return tuple(
        YftPhysicsInertia(
            x=float(_f32(system_data, offset + (index * 16))),
            y=float(_f32(system_data, offset + (index * 16) + 4)),
            z=float(_f32(system_data, offset + (index * 16) + 8)),
            mass=float(_f32(system_data, offset + (index * 16) + 12)),
        )
        for index in range(count)
    )


def read_matrix34_array(system_data: bytes, pointer: int, count: int):
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or count <= 0 or offset + (count * 48) > len(system_data):
        return ()
    matrices = []
    for index in range(count):
        base = offset + index * 48
        matrices.append(
            (
                tuple(float(_f32(system_data, base + col * 4)) for col in range(4)),
                tuple(
                    float(_f32(system_data, base + 16 + col * 4)) for col in range(4)
                ),
                tuple(
                    float(_f32(system_data, base + 32 + col * 4)) for col in range(4)
                ),
            )
        )
    return tuple(matrices)


def read_damping_constants(
    system_data: bytes, lod_offset: int
) -> tuple[YftPhysicsDamping, ...]:
    return tuple(
        YftPhysicsDamping(
            index=index,
            x=float(_f32(system_data, lod_offset + 0x60 + (index * 16))),
            y=float(_f32(system_data, lod_offset + 0x60 + (index * 16) + 4)),
            z=float(_f32(system_data, lod_offset + 0x60 + (index * 16) + 8)),
        )
        for index in range(_DAMPING_CONSTANT_COUNT)
    )


def read_damping_constants_at(
    system_data: bytes, offset: int
) -> tuple[YftPhysicsDamping, ...]:
    if offset < 0 or offset + (_DAMPING_CONSTANT_COUNT * 16) > len(system_data):
        return ()
    return tuple(
        YftPhysicsDamping(
            index=index,
            x=float(_f32(system_data, offset + (index * 16))),
            y=float(_f32(system_data, offset + (index * 16) + 4)),
            z=float(_f32(system_data, offset + (index * 16) + 8)),
        )
        for index in range(_DAMPING_CONSTANT_COUNT)
    )


def _read_joint_types(
    system_data: bytes, offset: int, count: int
) -> tuple[YftPhysicsJointType | int, ...]:
    values: list[YftPhysicsJointType | int] = []
    for index in range(max(0, min(count, _ARTICULATED_BODY_MAX_JOINTS))):
        raw = system_data[offset + index]
        try:
            values.append(YftPhysicsJointType(raw))
        except ValueError:
            values.append(raw)
    return tuple(values)


def read_articulated_body_type(
    system_data: bytes, pointer: int
) -> YftArticulatedBodyType | None:
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or offset + _ARTICULATED_BODY_TYPE_MIN_SIZE > len(system_data):
        return None
    num_links = system_data[offset + 0x88]
    num_joints = system_data[offset + 0x89]
    if (
        num_links > _ARTICULATED_BODY_MAX_LINKS
        or num_joints > _ARTICULATED_BODY_MAX_JOINTS
    ):
        return None
    joint_type_pointers = read_pointer_tuple(
        system_data, _u64(system_data, offset + 0x78), num_joints
    )
    return YftArticulatedBodyType(
        pointer=pointer,
        joint_parent_indices=tuple(
            _i32(system_data, offset + 0x10 + index * 4)
            for index in range(_ARTICULATED_BODY_MAX_LINKS)
        ),
        replace_upon_reresource=float(_f32(system_data, offset + 0x6C)),
        angular_decay_rate=float(_f32(system_data, offset + 0x70)),
        joint_type_pointers=joint_type_pointers,
        resourced_ang_inertia=read_inertia_array(
            system_data, _u64(system_data, offset + 0x80), num_links
        ),
        num_links=num_links,
        num_joints=num_joints,
        joint_types=_read_joint_types(system_data, offset + 0x8A, num_joints),
        locally_owned=bool(system_data[offset + 0xA0]),
    )


def read_damp_archetype(
    system_data: bytes, pointer: int
) -> YftPhysicsDampArchetype | None:
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or offset + _ARCHETYPE_DAMP_MIN_SIZE > len(system_data):
        return None
    damping_offset = offset + _ARCHETYPE_DAMPING_OFFSET
    damping_constants = read_damping_constants_at(system_data, damping_offset)
    if len(damping_constants) != _DAMPING_CONSTANT_COUNT:
        return None
    return YftPhysicsDampArchetype(
        pointer=pointer,
        resource_type=_i32(system_data, offset + 0x10),
        filename_pointer=_u64(system_data, offset + 0x18),
        bound_pointer=_u64(system_data, offset + 0x20),
        type_flags=_u32(system_data, offset + 0x28),
        include_flags=_u32(system_data, offset + 0x2C),
        property_flags=_u16(system_data, offset + 0x30),
        mass=float(_f32(system_data, offset + 0x40)),
        inv_mass=float(_f32(system_data, offset + 0x44)),
        gravity_factor=float(_f32(system_data, offset + 0x48)),
        max_speed=float(_f32(system_data, offset + 0x4C)),
        max_ang_speed=float(_f32(system_data, offset + 0x50)),
        buoyancy_factor=float(_f32(system_data, offset + 0x54)),
        angular_inertia=read_vec3(system_data, offset + 0x60),
        inv_angular_inertia=read_vec3(system_data, offset + 0x70),
        damping_constants=damping_constants,
        damping_offset=_ARCHETYPE_DAMPING_OFFSET,
    )


def read_bound_or_none(system_data: bytes, pointer: int) -> Bound | None:
    if not pointer:
        return None
    try:
        return read_bound_from_pointer(pointer, system_data)
    except Exception:
        return None


def read_physics_group(system_data: bytes, pointer: int) -> YftPhysicsGroup | None:
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or offset + _PHYSICS_GROUP_MIN_SIZE > len(system_data):
        return None
    return YftPhysicsGroup(
        pointer=pointer,
        events=YftPhysicsGroupEventRefs(
            death_event=_u64(system_data, offset),
            death_player=_u64(system_data, offset + 8),
        ),
        strength=float(_f32(system_data, offset + 0x10)),
        force_transmission_scale_up=float(_f32(system_data, offset + 0x14)),
        force_transmission_scale_down=float(_f32(system_data, offset + 0x18)),
        joint_stiffness=float(_f32(system_data, offset + 0x1C)),
        min_soft_angle_1=float(_f32(system_data, offset + 0x20)),
        max_soft_angle_1=float(_f32(system_data, offset + 0x24)),
        max_soft_angle_2=float(_f32(system_data, offset + 0x28)),
        max_soft_angle_3=float(_f32(system_data, offset + 0x2C)),
        rotation_speed=float(_f32(system_data, offset + 0x30)),
        rotation_strength=float(_f32(system_data, offset + 0x34)),
        restoring_strength=float(_f32(system_data, offset + 0x38)),
        restoring_max_torque=float(_f32(system_data, offset + 0x3C)),
        latch_strength=float(_f32(system_data, offset + 0x40)),
        total_undamaged_mass=float(_f32(system_data, offset + 0x44)),
        total_damaged_mass=float(_f32(system_data, offset + 0x48)),
        child_groups_pointers_index=system_data[offset + 0x4C],
        parent_group_pointer_index=system_data[offset + 0x4D],
        child_index=system_data[offset + 0x4E],
        num_children=system_data[offset + 0x4F],
        num_child_groups=system_data[offset + 0x50],
        glass_model_and_type=system_data[offset + 0x51],
        glass_pane_model_info_index=system_data[offset + 0x52],
        flags=YftPhysicsGroupFlag(system_data[offset + 0x53]),
        min_damage_force=float(_f32(system_data, offset + 0x54)),
        damage_health=float(_f32(system_data, offset + 0x58)),
        weapon_health=float(_f32(system_data, offset + 0x5C)),
        weapon_scale=float(_f32(system_data, offset + 0x60)),
        vehicle_scale=float(_f32(system_data, offset + 0x64)),
        ped_scale=float(_f32(system_data, offset + 0x68)),
        ragdoll_scale=float(_f32(system_data, offset + 0x6C)),
        explosion_scale=float(_f32(system_data, offset + 0x70)),
        object_scale=float(_f32(system_data, offset + 0x74)),
        ped_inv_mass_scale=float(_f32(system_data, offset + 0x78)),
        preset_applied=_i32(system_data, offset + 0x7C),
        debug_name=read_fixed_ascii(system_data, offset + 0x80, 40),
        melee_scale=float(_f32(system_data, offset + 0xA8)),
    )


def read_physics_entity(
    header,
    system_data: bytes,
    graphics_data: bytes,
    pointer: int,
    *,
    label: str,
    path: str,
    shader_library: ShaderLibrary | None,
    cache: dict[int, YftPhysicsEntity],
) -> YftPhysicsEntity | None:
    if not pointer:
        return None
    if pointer in cache:
        return cache[pointer]
    try:
        drawable = read_fragment_drawable(
            header,
            system_data,
            graphics_data,
            pointer,
            label=label,
            path=path,
            shader_library=shader_library,
        )
    except Exception:
        drawable = None
    entity = YftPhysicsEntity(pointer=pointer, label=label, drawable=drawable)
    cache[pointer] = entity
    return entity


def read_physics_child(
    system_data: bytes,
    pointer: int,
    *,
    owner_group_name: str = "",
    min_breaking_impulse: float = 0.0,
    undamaged_ang_inertia: YftPhysicsInertia | None = None,
    damaged_ang_inertia: YftPhysicsInertia | None = None,
    undamaged_entity: YftPhysicsEntity | None = None,
    damaged_entity: YftPhysicsEntity | None = None,
) -> YftPhysicsChild | None:
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or offset + _PHYSICS_CHILD_MIN_SIZE > len(system_data):
        return None
    return YftPhysicsChild(
        pointer=pointer,
        undamaged_mass=float(_f32(system_data, offset + 0x08)),
        damaged_mass=float(_f32(system_data, offset + 0x0C)),
        owner_group_pointer_index=system_data[offset + 0x10],
        flags=system_data[offset + 0x11],
        bone_id=_u16(system_data, offset + 0x12),
        undamaged_entity_pointer=_u64(system_data, offset + 0xA0),
        damaged_entity_pointer=_u64(system_data, offset + 0xA8),
        owner_group_name=owner_group_name,
        min_breaking_impulse=min_breaking_impulse,
        undamaged_ang_inertia=undamaged_ang_inertia or YftPhysicsInertia(),
        damaged_ang_inertia=damaged_ang_inertia or YftPhysicsInertia(),
        undamaged_entity=undamaged_entity,
        damaged_entity=damaged_entity,
        events=YftPhysicsEventRefs(
            continuous=_u64(system_data, offset + 0xB0)
            if offset + 0xB8 <= len(system_data)
            else 0,
            collision=_u64(system_data, offset + 0xB8)
            if offset + 0xC0 <= len(system_data)
            else 0,
            break_event=_u64(system_data, offset + 0xC0)
            if offset + 0xC8 <= len(system_data)
            else 0,
            break_from_root=_u64(system_data, offset + 0xC8)
            if offset + 0xD0 <= len(system_data)
            else 0,
            collision_player=_u64(system_data, offset + 0xD0)
            if offset + 0xD8 <= len(system_data)
            else 0,
            break_player=_u64(system_data, offset + 0xD8)
            if offset + 0xE0 <= len(system_data)
            else 0,
            break_from_root_player=_u64(system_data, offset + 0xE0)
            if offset + 0xE8 <= len(system_data)
            else 0,
        ),
    )


def read_physics_groups(
    system_data: bytes, pointers: tuple[int, ...]
) -> tuple[YftPhysicsGroup, ...]:
    groups: list[YftPhysicsGroup] = []
    for pointer in pointers:
        group = read_physics_group(system_data, pointer)
        if group is not None:
            groups.append(group)
    return tuple(groups)


def read_physics_children(
    header,
    system_data: bytes,
    graphics_data: bytes,
    pointers: tuple[int, ...],
    *,
    group_names: tuple[str, ...],
    path: str,
    lod_label: str,
    shader_library: ShaderLibrary | None,
    resolve_entities: bool,
    min_breaking_impulses: tuple[float, ...] = (),
    undamaged_ang_inertia: tuple[YftPhysicsInertia, ...] = (),
    damaged_ang_inertia: tuple[YftPhysicsInertia, ...] = (),
) -> tuple[YftPhysicsChild, ...]:
    children: list[YftPhysicsChild] = []
    entity_cache: dict[int, YftPhysicsEntity] = {}
    for index, pointer in enumerate(pointers):
        raw_child = read_physics_child(system_data, pointer)
        if raw_child is None:
            continue
        owner_name = (
            group_names[raw_child.owner_group_pointer_index]
            if raw_child.owner_group_pointer_index < len(group_names)
            else ""
        )
        undamaged_entity = None
        damaged_entity = None
        if resolve_entities:
            undamaged_entity = read_physics_entity(
                header,
                system_data,
                graphics_data,
                raw_child.undamaged_entity_pointer,
                label=f"physics_{lod_label}_child_{index}_undamaged",
                path=path,
                shader_library=shader_library,
                cache=entity_cache,
            )
            damaged_entity = read_physics_entity(
                header,
                system_data,
                graphics_data,
                raw_child.damaged_entity_pointer,
                label=f"physics_{lod_label}_child_{index}_damaged",
                path=path,
                shader_library=shader_library,
                cache=entity_cache,
            )
        child = dataclasses.replace(
            raw_child,
            owner_group_name=owner_name,
            min_breaking_impulse=(
                min_breaking_impulses[index]
                if index < len(min_breaking_impulses)
                else 0.0
            ),
            undamaged_ang_inertia=(
                undamaged_ang_inertia[index]
                if index < len(undamaged_ang_inertia)
                else YftPhysicsInertia()
            ),
            damaged_ang_inertia=(
                damaged_ang_inertia[index]
                if index < len(damaged_ang_inertia)
                else YftPhysicsInertia()
            ),
            undamaged_entity=undamaged_entity,
            damaged_entity=damaged_entity,
        )
        if child is not None:
            children.append(child)
    return tuple(children)


def resolve_physics_groups(
    groups: tuple[YftPhysicsGroup, ...],
    children: tuple[YftPhysicsChild, ...],
    group_names: tuple[str, ...],
) -> tuple[YftPhysicsGroup, ...]:
    resolved: list[YftPhysicsGroup] = []
    for index, group in enumerate(groups):
        name = group_names[index] if index < len(group_names) else group.debug_name
        group_children = (
            children[group.child_index : group.child_index + group.num_children]
            if group.child_index != 0xFF
            else tuple(
                child for child in children if child.owner_group_pointer_index == index
            )
        )
        child_group_indices = tuple(
            child_index
            for child_index, child_group in enumerate(groups)
            if child_group.parent_group_pointer_index == index
        )
        child_group_names = tuple(
            group_names[child_index]
            if child_index < len(group_names)
            else groups[child_index].debug_name
            for child_index in child_group_indices
        )
        resolved.append(
            dataclasses.replace(
                group,
                name=name,
                children=group_children,
                child_group_indices=child_group_indices,
                child_group_names=child_group_names,
            )
        )
    return tuple(resolved)


def read_physics_lod_pointers(
    system_data: bytes, group_pointer: int
) -> YftPhysicsLodPointers:
    offset = try_virtual_offset(system_data, group_pointer)
    if offset is None or offset + PHYSICS_LOD_GROUP_FIELDS_OFFSET + 24 > len(
        system_data
    ):
        return YftPhysicsLodPointers()
    fields = offset + PHYSICS_LOD_GROUP_FIELDS_OFFSET
    return YftPhysicsLodPointers(
        high=_u64(system_data, fields),
        medium=_u64(system_data, fields + 8),
        low=_u64(system_data, fields + 16),
    )


def read_physics_lod(
    header,
    system_data: bytes,
    graphics_data: bytes,
    pointer: int,
    label: str,
    *,
    path: str,
    shader_library: ShaderLibrary | None,
    resolve_entities: bool,
) -> YftPhysicsLod | None:
    offset = try_virtual_offset(system_data, pointer)
    if offset is None or offset + PHYSICS_LOD_MIN_SIZE > len(system_data):
        return None
    num_groups = system_data[offset + 0x11A]
    num_self_collisions = system_data[offset + 0x118]
    num_children = system_data[offset + 0x11E]
    group_names_pointer = _u64(system_data, offset + 0xC0)
    groups_pointer = _u64(system_data, offset + 0xC8)
    children_pointer = _u64(system_data, offset + 0xD0)
    phys_damp_undamaged_pointer = _u64(system_data, offset + 0xD8)
    phys_damp_damaged_pointer = _u64(system_data, offset + 0xE0)
    composite_bounds_pointer = _u64(system_data, offset + 0xE8)
    self_collision_a_pointer = _u64(system_data, offset + 0x108)
    self_collision_b_pointer = _u64(system_data, offset + 0x110)
    group_pointers = read_pointer_tuple(system_data, groups_pointer, num_groups)
    child_pointers = read_pointer_tuple(system_data, children_pointer, num_children)
    group_names = read_group_names(system_data, group_names_pointer, num_groups)
    min_breaking_impulses_pointer = _u64(system_data, offset + 0x28)
    undamaged_ang_inertia_pointer = _u64(system_data, offset + 0xF0)
    damaged_ang_inertia_pointer = _u64(system_data, offset + 0xF8)
    min_breaking_impulses = read_float_array(
        system_data, min_breaking_impulses_pointer, num_children
    )
    undamaged_ang_inertia = read_inertia_array(
        system_data, undamaged_ang_inertia_pointer, num_children
    )
    damaged_ang_inertia = read_inertia_array(
        system_data, damaged_ang_inertia_pointer, num_children
    )
    link_attachments_pointer = _u64(system_data, offset + 0x100)
    children = read_physics_children(
        header,
        system_data,
        graphics_data,
        child_pointers,
        group_names=group_names,
        path=path,
        lod_label=label,
        shader_library=shader_library,
        resolve_entities=resolve_entities,
        min_breaking_impulses=min_breaking_impulses,
        undamaged_ang_inertia=undamaged_ang_inertia,
        damaged_ang_inertia=damaged_ang_inertia,
    )
    groups = resolve_physics_groups(
        read_physics_groups(system_data, group_pointers), children, group_names
    )
    return YftPhysicsLod(
        label=label,
        pointer=pointer,
        smallest_ang_inertia=float(_f32(system_data, offset + 0x14)),
        largest_ang_inertia=float(_f32(system_data, offset + 0x18)),
        min_move_force=float(_f32(system_data, offset + 0x1C)),
        body_type_pointer=_u64(system_data, offset + 0x20),
        min_breaking_impulses_pointer=min_breaking_impulses_pointer,
        root_cg_offset=read_vec3(system_data, offset + 0x30),
        original_root_cg_offset=read_vec3(system_data, offset + 0x40),
        unbroken_cg_offset=read_vec3(system_data, offset + 0x50),
        group_names_pointer=group_names_pointer,
        groups_pointer=groups_pointer,
        children_pointer=children_pointer,
        phys_damp_undamaged_pointer=phys_damp_undamaged_pointer,
        phys_damp_damaged_pointer=phys_damp_damaged_pointer,
        composite_bounds_pointer=composite_bounds_pointer,
        undamaged_ang_inertia_pointer=undamaged_ang_inertia_pointer,
        damaged_ang_inertia_pointer=damaged_ang_inertia_pointer,
        link_attachments_pointer=link_attachments_pointer,
        self_collision_a_pointer=self_collision_a_pointer,
        self_collision_b_pointer=self_collision_b_pointer,
        num_self_collisions=num_self_collisions,
        max_num_self_collisions=system_data[offset + 0x119],
        num_groups=num_groups,
        root_group_count=system_data[offset + 0x11B],
        num_root_damage_regions=system_data[offset + 0x11C],
        num_bony_children=system_data[offset + 0x11D],
        num_children=num_children,
        group_names=group_names,
        group_pointers=group_pointers,
        child_pointers=child_pointers,
        groups=groups,
        children=children,
        damping_constants=read_damping_constants(system_data, offset),
        min_breaking_impulses=min_breaking_impulses,
        undamaged_ang_inertia=undamaged_ang_inertia,
        damaged_ang_inertia=damaged_ang_inertia,
        link_attachments=read_matrix34_array(
            system_data, link_attachments_pointer, num_children
        ),
        body_type=YftPhysicsReference(
            _u64(system_data, offset + 0x20), "phArticulatedBodyType"
        ),
        phys_damp_undamaged=YftPhysicsReference(
            phys_damp_undamaged_pointer, "phArchetypeDamp:undamaged"
        ),
        phys_damp_damaged=YftPhysicsReference(
            phys_damp_damaged_pointer, "phArchetypeDamp:damaged"
        ),
        articulated_body_type=read_articulated_body_type(
            system_data, _u64(system_data, offset + 0x20)
        ),
        undamaged_damp_archetype=read_damp_archetype(
            system_data, phys_damp_undamaged_pointer
        ),
        damaged_damp_archetype=read_damp_archetype(
            system_data, phys_damp_damaged_pointer
        ),
        self_collision_pairs=read_self_collision_pairs(
            system_data,
            self_collision_a_pointer,
            self_collision_b_pointer,
            num_self_collisions,
        ),
        composite_bound=read_bound_or_none(system_data, composite_bounds_pointer),
    )


def read_physics_lods(
    header,
    system_data: bytes,
    graphics_data: bytes,
    pointers: YftPhysicsLodPointers,
    *,
    path: str,
    shader_library: ShaderLibrary | None,
    resolve_entities: bool = True,
) -> list[YftPhysicsLod]:
    lods: list[YftPhysicsLod] = []
    for label, pointer in pointers.items():
        if not pointer:
            continue
        lod = read_physics_lod(
            header,
            system_data,
            graphics_data,
            pointer,
            label,
            path=path,
            shader_library=shader_library,
            resolve_entities=resolve_entities,
        )
        if lod is not None:
            lods.append(lod)
    return lods


__all__ = [
    "read_bound_or_none",
    "read_damping_constants",
    "read_damping_constants_at",
    "read_articulated_body_type",
    "read_damp_archetype",
    "read_float_array",
    "read_group_names",
    "read_inertia_array",
    "read_matrix34_array",
    "read_physics_child",
    "read_physics_children",
    "read_physics_entity",
    "read_physics_group",
    "read_physics_groups",
    "read_physics_lod",
    "read_physics_lod_pointers",
    "read_physics_lods",
    "read_self_collision_pairs",
]
