from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..bounds import Bound
    from ..ydr import Ydr


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsLodPointers:
    high: int = 0
    medium: int = 0
    low: int = 0

    @property
    def has_physics(self) -> bool:
        return any(self.values())

    @property
    def active_count(self) -> int:
        return sum(1 for pointer in self.values() if pointer)

    def items(self) -> tuple[tuple[str, int], ...]:
        return (("high", self.high), ("medium", self.medium), ("low", self.low))

    def values(self) -> tuple[int, int, int]:
        return (self.high, self.medium, self.low)


class YftPhysicsGroupFlag(enum.IntFlag):
    NONE = 0
    DISAPPEARS_WHEN_DEAD = 1 << 0
    MADE_OF_GLASS = 1 << 1
    DAMAGE_WHEN_BROKEN = 1 << 2
    DOESNT_AFFECT_VEHICLES = 1 << 3
    DOESNT_PUSH_VEHICLES_DOWN = 1 << 4
    HAS_CLOTH = 1 << 5


class YftPhysicsDampingKind(enum.IntEnum):
    LINEAR_CONSTANT = 0
    LINEAR_VELOCITY = 1
    LINEAR_VELOCITY_SQUARED = 2
    ANGULAR_CONSTANT = 3
    ANGULAR_VELOCITY = 4
    ANGULAR_VELOCITY_SQUARED = 5


class YftPhysicsJointType(enum.IntEnum):
    ONE_DOF = 0
    THREE_DOF = 1
    PRISMATIC = 2
    INVALID = 255


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsGroupEventRefs:
    death_event: int = 0
    death_player: int = 0

    @property
    def has_any(self) -> bool:
        return self.death_event != 0 or self.death_player != 0

    @classmethod
    def declare(cls, *, death_event: int = 0, death_player: int = 0) -> YftPhysicsGroupEventRefs:
        return cls(death_event=int(death_event), death_player=int(death_player))


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsGroup:
    name: str = ""
    pointer: int = 0
    strength: float = 0.0
    force_transmission_scale_up: float = 0.0
    force_transmission_scale_down: float = 0.0
    joint_stiffness: float = 0.0
    min_soft_angle_1: float = 0.0
    max_soft_angle_1: float = 0.0
    max_soft_angle_2: float = 0.0
    max_soft_angle_3: float = 0.0
    rotation_speed: float = 0.0
    rotation_strength: float = 0.0
    restoring_strength: float = 0.0
    restoring_max_torque: float = 0.0
    latch_strength: float = 0.0
    total_undamaged_mass: float = 0.0
    total_damaged_mass: float = 0.0
    child_groups_pointers_index: int = 0xFF
    parent_group_pointer_index: int = 0xFF
    child_index: int = 0xFF
    num_children: int = 0
    num_child_groups: int = 0
    glass_model_and_type: int = 0
    glass_pane_model_info_index: int = 0
    flags: YftPhysicsGroupFlag = YftPhysicsGroupFlag.NONE
    min_damage_force: float = 0.0
    damage_health: float = 0.0
    weapon_health: float = 0.0
    weapon_scale: float = 0.0
    vehicle_scale: float = 0.0
    ped_scale: float = 0.0
    ragdoll_scale: float = 0.0
    explosion_scale: float = 0.0
    object_scale: float = 0.0
    ped_inv_mass_scale: float = 0.0
    preset_applied: int = 0
    debug_name: str = ""
    melee_scale: float = 0.0
    children: tuple[YftPhysicsChild, ...] = dataclasses.field(
        default=(), repr=False, compare=False
    )
    child_group_indices: tuple[int, ...] = ()
    child_group_names: tuple[str, ...] = ()
    events: YftPhysicsGroupEventRefs = dataclasses.field(
        default_factory=YftPhysicsGroupEventRefs
    )

    @property
    def is_root_group(self) -> bool:
        return self.parent_group_pointer_index == 0xFF

    @property
    def is_damageable(self) -> bool:
        return self.damage_health != 0.0

    @property
    def is_initially_latched(self) -> bool:
        return self.latch_strength == -1.0 or self.latch_strength > 0.0

    @property
    def disappears_when_dead(self) -> bool:
        return bool(self.flags & YftPhysicsGroupFlag.DISAPPEARS_WHEN_DEAD)

    @property
    def is_glass(self) -> bool:
        return bool(self.flags & YftPhysicsGroupFlag.MADE_OF_GLASS)

    @property
    def damages_when_broken(self) -> bool:
        return bool(self.flags & YftPhysicsGroupFlag.DAMAGE_WHEN_BROKEN)

    @property
    def has_cloth(self) -> bool:
        return bool(self.flags & YftPhysicsGroupFlag.HAS_CLOTH)

    @property
    def affects_vehicles(self) -> bool:
        return not bool(self.flags & YftPhysicsGroupFlag.DOESNT_AFFECT_VEHICLES)

    @property
    def pushes_vehicles_down(self) -> bool:
        return not bool(self.flags & YftPhysicsGroupFlag.DOESNT_PUSH_VEHICLES_DOWN)

    @property
    def is_legacy_glass(self) -> bool:
        return self.glass_model_and_type != 0xFF

    @property
    def legacy_glass_model_index(self) -> int:
        return self.glass_model_and_type & 0x1F

    @property
    def legacy_glass_type_index(self) -> int:
        return self.glass_model_and_type >> 5

    @classmethod
    def declare(
        cls,
        name: str = "",
        *,
        children: Sequence[YftPhysicsChild] = (),
        child_groups: Sequence[int | str] = (),
        flags: YftPhysicsGroupFlag | int = YftPhysicsGroupFlag.NONE,
        strength: float = 0.0,
        total_undamaged_mass: float | None = None,
        total_damaged_mass: float | None = None,
        debug_name: str = "",
    ) -> YftPhysicsGroup:
        declared_children = tuple(children)
        undamaged_mass = (
            float(total_undamaged_mass)
            if total_undamaged_mass is not None
            else sum(child.undamaged_mass for child in declared_children)
        )
        damaged_mass = (
            float(total_damaged_mass)
            if total_damaged_mass is not None
            else sum(child.damaged_mass for child in declared_children)
        )
        return cls(
            name=str(name),
            strength=float(strength),
            total_undamaged_mass=undamaged_mass,
            total_damaged_mass=damaged_mass,
            child_index=0 if declared_children else 0xFF,
            num_children=len(declared_children),
            num_child_groups=len(child_groups),
            flags=YftPhysicsGroupFlag(flags),
            debug_name=debug_name or str(name),
            children=declared_children,
            child_group_names=tuple(
                str(value) for value in child_groups if isinstance(value, str)
            ),
            child_group_indices=tuple(
                int(value) for value in child_groups if not isinstance(value, str)
            ),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsEntity:
    pointer: int = 0
    label: str = ""
    drawable: Ydr | None = dataclasses.field(default=None, repr=False, compare=False)

    @property
    def has_drawable(self) -> bool:
        return self.drawable is not None

    @classmethod
    def declare(
        cls, drawable: Ydr | None = None, *, label: str = ""
    ) -> YftPhysicsEntity:
        return cls(label=str(label), drawable=drawable)


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsInertia:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    mass: float = 0.0

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.z, self.mass)


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsDamping:
    index: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @property
    def kind(self) -> YftPhysicsDampingKind:
        return YftPhysicsDampingKind(self.index)

    @classmethod
    def declare(
        cls,
        kind: YftPhysicsDampingKind | int,
        value: tuple[float, float, float],
    ) -> YftPhysicsDamping:
        return cls(
            index=int(kind), x=float(value[0]), y=float(value[1]), z=float(value[2])
        )


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsDampArchetype:
    pointer: int = 0
    resource_type: int = 0
    filename_pointer: int = 0
    bound_pointer: int = 0
    type_flags: int = 0
    include_flags: int = 0
    property_flags: int = 0
    mass: float = 0.0
    inv_mass: float = 0.0
    gravity_factor: float = 0.0
    max_speed: float = 0.0
    max_ang_speed: float = 0.0
    buoyancy_factor: float = 0.0
    angular_inertia: tuple[float, float, float] = (0.0, 0.0, 0.0)
    inv_angular_inertia: tuple[float, float, float] = (0.0, 0.0, 0.0)
    damping_constants: tuple[YftPhysicsDamping, ...] = ()
    damping_offset: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class YftArticulatedBodyType:
    pointer: int = 0
    joint_parent_indices: tuple[int, ...] = ()
    replace_upon_reresource: float = 0.0
    angular_decay_rate: float = 0.0
    joint_type_pointers: tuple[int, ...] = ()
    resourced_ang_inertia: tuple[YftPhysicsInertia, ...] = ()
    num_links: int = 0
    num_joints: int = 0
    joint_types: tuple[YftPhysicsJointType | int, ...] = ()
    locally_owned: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsReference:
    pointer: int = 0
    label: str = ""

    @property
    def exists(self) -> bool:
        return self.pointer != 0


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsEventRefs:
    continuous: int = 0
    collision: int = 0
    break_event: int = 0
    break_from_root: int = 0
    collision_player: int = 0
    break_player: int = 0
    break_from_root_player: int = 0

    @property
    def has_any(self) -> bool:
        return any(dataclasses.astuple(self))

    @classmethod
    def declare(
        cls,
        *,
        continuous: int = 0,
        collision: int = 0,
        break_event: int = 0,
        break_from_root: int = 0,
        collision_player: int = 0,
        break_player: int = 0,
        break_from_root_player: int = 0,
    ) -> YftPhysicsEventRefs:
        return cls(
            continuous=int(continuous),
            collision=int(collision),
            break_event=int(break_event),
            break_from_root=int(break_from_root),
            collision_player=int(collision_player),
            break_player=int(break_player),
            break_from_root_player=int(break_from_root_player),
        )

    def items(self) -> tuple[tuple[str, int], ...]:
        return tuple(
            (name, int(value))
            for name, value in (
                ("continuous", self.continuous),
                ("collision", self.collision),
                ("break", self.break_event),
                ("break_from_root", self.break_from_root),
                ("collision_player", self.collision_player),
                ("break_player", self.break_player),
                ("break_from_root_player", self.break_from_root_player),
            )
            if value
        )


YftMatrix44 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsTransforms:
    matrices: tuple[YftMatrix44, ...] = ()
    resource_tag: int = 0x54534552
    resource_state: int = 0
    reserved_08: int = 0
    reserved_14: int = 0
    reserved_18: int = 0

    @property
    def count(self) -> int:
        return len(self.matrices)

    @classmethod
    def declare(
        cls, matrices: Sequence[YftMatrix44] = ()
    ) -> YftPhysicsTransforms:
        return cls(matrices=tuple(matrices))


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsChild:
    pointer: int = 0
    undamaged_mass: float = 0.0
    damaged_mass: float = 0.0
    owner_group_pointer_index: int = 0
    flags: int = 0
    bone_id: int = 0
    undamaged_entity_pointer: int = 0
    damaged_entity_pointer: int = 0
    owner_group_name: str = ""
    min_breaking_impulse: float = 0.0
    undamaged_ang_inertia: YftPhysicsInertia = dataclasses.field(
        default_factory=YftPhysicsInertia
    )
    damaged_ang_inertia: YftPhysicsInertia = dataclasses.field(
        default_factory=YftPhysicsInertia
    )
    undamaged_entity: YftPhysicsEntity | None = dataclasses.field(
        default=None, repr=False, compare=False
    )
    damaged_entity: YftPhysicsEntity | None = dataclasses.field(
        default=None, repr=False, compare=False
    )
    events: YftPhysicsEventRefs = dataclasses.field(default_factory=YftPhysicsEventRefs)

    @property
    def uses_bone(self) -> bool:
        return self.bone_id != 0

    @property
    def follows_root(self) -> bool:
        return self.bone_id == 0

    @property
    def has_damage_state(self) -> bool:
        return self.damaged_entity_pointer != 0 or self.damaged_entity is not None

    @property
    def uses_shared_entity(self) -> bool:
        return (
            self.undamaged_entity_pointer != 0
            and self.undamaged_entity_pointer == self.damaged_entity_pointer
        ) or (
            self.undamaged_entity is not None
            and self.undamaged_entity is self.damaged_entity
        )

    @property
    def has_undamaged_entity(self) -> bool:
        return self.undamaged_entity_pointer != 0

    @property
    def has_damaged_entity(self) -> bool:
        return self.damaged_entity_pointer != 0

    def entities(self) -> tuple[YftPhysicsEntity, ...]:
        return tuple(
            entity
            for entity in (self.undamaged_entity, self.damaged_entity)
            if entity is not None
        )

    @property
    def undamaged_bound(self) -> Bound | None:
        if self.undamaged_entity is None or self.undamaged_entity.drawable is None:
            return None
        return self.undamaged_entity.drawable.bound

    @property
    def damaged_bound(self) -> Bound | None:
        if self.damaged_entity is None or self.damaged_entity.drawable is None:
            return None
        return self.damaged_entity.drawable.bound

    @classmethod
    def declare(
        cls,
        *,
        undamaged_entity: YftPhysicsEntity | None = None,
        damaged_entity: YftPhysicsEntity | None = None,
        bone_id: int = 0,
        undamaged_mass: float = 1.0,
        damaged_mass: float | None = None,
        owner_group_name: str = "",
        min_breaking_impulse: float = 0.0,
        reserved_flags: int = 0,
    ) -> YftPhysicsChild:
        return cls(
            undamaged_mass=float(undamaged_mass),
            damaged_mass=float(
                damaged_mass if damaged_mass is not None else undamaged_mass
            ),
            flags=int(reserved_flags),
            bone_id=int(bone_id),
            owner_group_name=str(owner_group_name),
            min_breaking_impulse=float(min_breaking_impulse),
            undamaged_entity=undamaged_entity,
            damaged_entity=damaged_entity,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class YftPhysicsLod:
    label: str
    pointer: int = 0
    smallest_ang_inertia: float = 0.0
    largest_ang_inertia: float = 0.0
    min_move_force: float = 0.0
    body_type_pointer: int = 0
    min_breaking_impulses_pointer: int = 0
    root_cg_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    original_root_cg_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    unbroken_cg_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    group_names_pointer: int = 0
    groups_pointer: int = 0
    children_pointer: int = 0
    phys_damp_undamaged_pointer: int = 0
    phys_damp_damaged_pointer: int = 0
    composite_bounds_pointer: int = 0
    undamaged_ang_inertia_pointer: int = 0
    damaged_ang_inertia_pointer: int = 0
    link_attachments_pointer: int = 0
    self_collision_a_pointer: int = 0
    self_collision_b_pointer: int = 0
    num_self_collisions: int = 0
    max_num_self_collisions: int = 0
    num_groups: int = 0
    root_group_count: int = 0
    num_root_damage_regions: int = 0
    num_bony_children: int = 0
    num_children: int = 0
    group_names: tuple[str, ...] = ()
    group_pointers: tuple[int, ...] = ()
    child_pointers: tuple[int, ...] = ()
    groups: tuple[YftPhysicsGroup, ...] = ()
    children: tuple[YftPhysicsChild, ...] = ()
    damping_constants: tuple[YftPhysicsDamping, ...] = ()
    min_breaking_impulses: tuple[float, ...] = ()
    undamaged_ang_inertia: tuple[YftPhysicsInertia, ...] = ()
    damaged_ang_inertia: tuple[YftPhysicsInertia, ...] = ()
    link_attachments: YftPhysicsTransforms = dataclasses.field(
        default_factory=YftPhysicsTransforms
    )
    body_type: YftPhysicsReference = dataclasses.field(
        default_factory=YftPhysicsReference
    )
    phys_damp_undamaged: YftPhysicsReference = dataclasses.field(
        default_factory=YftPhysicsReference
    )
    phys_damp_damaged: YftPhysicsReference = dataclasses.field(
        default_factory=YftPhysicsReference
    )
    articulated_body_type: YftArticulatedBodyType | None = dataclasses.field(
        default=None, repr=False, compare=False
    )
    undamaged_damp_archetype: YftPhysicsDampArchetype | None = dataclasses.field(
        default=None, repr=False, compare=False
    )
    damaged_damp_archetype: YftPhysicsDampArchetype | None = dataclasses.field(
        default=None, repr=False, compare=False
    )
    self_collision_pairs: tuple[tuple[int, int], ...] = ()
    composite_bound: Bound | None = dataclasses.field(
        default=None, repr=False, compare=False
    )

    @property
    def has_children(self) -> bool:
        return self.num_children > 0

    @property
    def child_entity_pointers(self) -> tuple[int, ...]:
        pointers = {
            pointer
            for child in self.children
            for pointer in (
                child.undamaged_entity_pointer,
                child.damaged_entity_pointer,
            )
            if pointer
        }
        return tuple(sorted(pointers))

    @property
    def root_groups(self) -> tuple[YftPhysicsGroup, ...]:
        return tuple(group for group in self.groups if group.is_root_group)

    def group(self, key: int | str) -> YftPhysicsGroup | None:
        if isinstance(key, int):
            return self.groups[key] if 0 <= key < len(self.groups) else None
        lowered = key.lower()
        return next(
            (
                group
                for group in self.groups
                if group.name.lower() == lowered or group.debug_name.lower() == lowered
            ),
            None,
        )

    def children_for_group(
        self, key: int | str | YftPhysicsGroup
    ) -> tuple[YftPhysicsChild, ...]:
        group = key if isinstance(key, YftPhysicsGroup) else self.group(key)
        return group.children if group is not None else ()

    def child(self, key: int | str) -> YftPhysicsChild | None:
        if isinstance(key, int):
            return self.children[key] if 0 <= key < len(self.children) else None
        lowered = key.lower()
        return next(
            (
                child
                for child in self.children
                if child.owner_group_name.lower() == lowered
            ),
            None,
        )

    def children_for_bone(self, bone_id: int) -> tuple[YftPhysicsChild, ...]:
        return tuple(child for child in self.children if child.bone_id == int(bone_id))

    @property
    def damageable_groups(self) -> tuple[YftPhysicsGroup, ...]:
        return tuple(group for group in self.groups if group.is_damageable)

    @property
    def total_undamaged_mass(self) -> float:
        return sum(child.undamaged_mass for child in self.children)

    @property
    def total_damaged_mass(self) -> float:
        return sum(child.damaged_mass for child in self.children)

    @property
    def is_all_glass(self) -> bool:
        return bool(self.groups) and all(group.is_glass for group in self.groups)

    def archetype(self, *, damaged: bool = False) -> YftPhysicsDampArchetype | None:
        return self.damaged_damp_archetype if damaged else self.undamaged_damp_archetype

    @property
    def self_collision_group_pairs(
        self,
    ) -> tuple[tuple[YftPhysicsGroup, YftPhysicsGroup], ...]:
        return tuple(
            (self.groups[first], self.groups[second])
            for first, second in self.self_collision_pairs
            if first < len(self.groups) and second < len(self.groups)
        )

    @property
    def event_references(self) -> dict[str, tuple[tuple[str, int], ...]]:
        refs: dict[str, tuple[tuple[str, int], ...]] = {}
        for index, child in enumerate(self.children):
            items = child.events.items()
            if items:
                refs[f"child_{index}"] = items
        for index, group in enumerate(self.groups):
            if group.events.has_any:
                refs[f"group_{index}"] = (
                    ("death_event", group.events.death_event),
                    ("death_player", group.events.death_player),
                )
        return refs

    @property
    def glass_groups(self) -> tuple[YftPhysicsGroup, ...]:
        return tuple(group for group in self.groups if group.is_glass or group.is_legacy_glass)

    @property
    def cloth_groups(self) -> tuple[YftPhysicsGroup, ...]:
        return tuple(group for group in self.groups if group.has_cloth)

    @property
    def vehicle_passive_groups(self) -> tuple[YftPhysicsGroup, ...]:
        return tuple(group for group in self.groups if not group.affects_vehicles)

    @classmethod
    def declare(
        cls,
        label: str = "high",
        *,
        groups: Sequence[YftPhysicsGroup] = (),
        children: Sequence[YftPhysicsChild] = (),
        damping_constants: Sequence[YftPhysicsDamping] = (),
        root_cg_offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> YftPhysicsLod:
        declared_groups = tuple(groups)
        group_names = tuple(group.name or group.debug_name for group in declared_groups)
        resolved_groups: list[YftPhysicsGroup] = []
        declared_children: list[YftPhysicsChild] = []
        child_cursor = 0
        for index, group in enumerate(declared_groups):
            group_name = group.name or group.debug_name
            group_children = tuple(
                dataclasses.replace(
                    child,
                    owner_group_pointer_index=index,
                    owner_group_name=group_name,
                )
                for child in group.children
            )
            resolved_groups.append(
                dataclasses.replace(
                    group,
                    child_index=child_cursor if group_children else 0xFF,
                    num_children=len(group_children),
                    children=group_children,
                )
            )
            child_cursor += len(group_children)
            declared_children.extend(group_children)
        if children:
            declared_children = list(children)
            if not resolved_groups:
                resolved_groups = [
                    YftPhysicsGroup.declare(
                        "default",
                        children=declared_children,
                    )
                ]
                group_names = ("default",)
        return cls(
            label=str(label),
            root_cg_offset=tuple(float(value) for value in root_cg_offset),
            original_root_cg_offset=tuple(float(value) for value in root_cg_offset),
            unbroken_cg_offset=tuple(float(value) for value in root_cg_offset),
            num_groups=len(resolved_groups),
            root_group_count=sum(1 for group in resolved_groups if group.is_root_group),
            num_bony_children=sum(1 for child in declared_children if child.uses_bone),
            num_children=len(declared_children),
            group_names=group_names,
            groups=tuple(resolved_groups),
            children=tuple(declared_children),
            damping_constants=tuple(damping_constants),
            min_breaking_impulses=tuple(
                child.min_breaking_impulse for child in declared_children
            ),
            undamaged_ang_inertia=tuple(
                child.undamaged_ang_inertia for child in declared_children
            ),
            damaged_ang_inertia=tuple(
                child.damaged_ang_inertia for child in declared_children
            ),
        )

    def with_group(self, group: YftPhysicsGroup) -> YftPhysicsLod:
        return type(self).declare(
            self.label,
            groups=(*self.groups, group),
            damping_constants=self.damping_constants,
            root_cg_offset=self.root_cg_offset,
        )

    def with_child(
        self, child: YftPhysicsChild, *, group: int | str = 0
    ) -> YftPhysicsLod:
        groups = list(self.groups)
        if not groups:
            groups.append(
                YftPhysicsGroup.declare(
                    str(group) if isinstance(group, str) else "default"
                )
            )
        group_index = (
            group
            if isinstance(group, int)
            else next(
                (
                    index
                    for index, item in enumerate(groups)
                    if item.name == group or item.debug_name == group
                ),
                0,
            )
        )
        groups[group_index] = dataclasses.replace(
            groups[group_index],
            children=(*groups[group_index].children, child),
        )
        return type(self).declare(
            self.label,
            groups=groups,
            damping_constants=self.damping_constants,
            root_cg_offset=self.root_cg_offset,
        )


__all__ = [
    "YftArticulatedBodyType",
    "YftMatrix44",
    "YftPhysicsChild",
    "YftPhysicsDampArchetype",
    "YftPhysicsDamping",
    "YftPhysicsDampingKind",
    "YftPhysicsEntity",
    "YftPhysicsEventRefs",
    "YftPhysicsGroup",
    "YftPhysicsGroupEventRefs",
    "YftPhysicsGroupFlag",
    "YftPhysicsInertia",
    "YftPhysicsJointType",
    "YftPhysicsLod",
    "YftPhysicsLodPointers",
    "YftPhysicsReference",
    "YftPhysicsTransforms",
]
