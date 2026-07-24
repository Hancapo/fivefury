from __future__ import annotations

import dataclasses
import enum


class YftFragmentFlag(enum.IntFlag):
    NONE = 0
    NEEDS_CACHE_ENTRY_TO_ACTIVATE = 1 << 0
    HAS_ANY_ARTICULATED_PARTS = 1 << 1
    UNUSED = 1 << 2
    CLONE_BOUND_PARTS_IN_CACHE = 1 << 3
    ALLOCATE_TYPE_AND_INCLUDE_FLAGS = 1 << 4
    FORCE_ARTICULATED_DAMPING = 1 << 5
    FORCE_LOAD_COMMON_DRAWABLE = 1 << 6
    FORCE_ALLOCATE_LINK_ATTACHMENTS = 1 << 7
    BECOME_ROPE = 1 << 10
    IS_USER_MODIFIED = 1 << 11
    DISABLE_ACTIVATION = 1 << 12
    DISABLE_BREAKING = 1 << 13


@dataclasses.dataclass(frozen=True, slots=True)
class YftFragmentState:
    damaged_drawable_index: int = -1
    entity_class: int = 0
    art_asset_id: int = 0
    attach_bottom_end: bool = False
    flags: YftFragmentFlag = YftFragmentFlag.NONE
    client_class_id: int = 0
    unbroken_elasticity: float = 0.0
    gravity_factor: float = 0.0
    buoyancy_factor: float = 0.0
    glass_attachment_bone: int = 0
    estimated_cache_size: int = 0
    estimated_articulated_cache_size: int = 0


@dataclasses.dataclass(slots=True)
class YftFragmentPointers:
    common_drawable: int = 0
    extra_drawables: int = 0
    extra_drawable_names: int = 0
    root_child: int = 0
    tune_name: int = 0
    user_data: int = 0
    collision_event_set: int = 0
    collision_event_player: int = 0
    shared_matrix_set: int = 0
    glass_pane_model_infos: int = 0
    physics_lod_group: int = 0
    cloth_drawable: int = 0
    vehicle_glass_windows: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class YftRawField:
    offset: int
    value: int
    label: str = ""
    pointed_string: str = ""

    @property
    def is_pointer(self) -> bool:
        return bool(self.pointed_string)


__all__ = [
    "YftFragmentFlag",
    "YftFragmentPointers",
    "YftFragmentState",
    "YftRawField",
]
