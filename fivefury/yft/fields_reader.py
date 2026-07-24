from __future__ import annotations

from ..binary import f32 as _f32
from ..binary import i32 as _i32
from ..binary import u16 as _u16
from ..binary import u64 as _u64
from .constants import (
    CLOTH_DRAWABLE_POINTER_OFFSET,
    COLLISION_EVENT_PLAYER_POINTER_OFFSET,
    COLLISION_EVENT_SET_POINTER_OFFSET,
    DAMAGED_DRAWABLE_INDEX_OFFSET,
    DRAWABLE_ARRAY_POINTER_OFFSET,
    DRAWABLE_NAMES_POINTER_OFFSET,
    ESTIMATED_ARTICULATED_CACHE_SIZE_OFFSET,
    ESTIMATED_CACHE_SIZE_OFFSET,
    GLASS_PANE_MODEL_INFOS_POINTER_OFFSET,
    MAIN_DRAWABLE_POINTER_OFFSET,
    PHYSICS_LOD_GROUP_POINTER_OFFSET,
    RAW_FIELD_LABELS,
    ROOT_CHILD_POINTER_OFFSET,
    SHARED_MATRIX_SET_POINTER_OFFSET,
    TUNE_NAME_POINTER_OFFSET,
    USER_DATA_POINTER_OFFSET,
    VEHICLE_GLASS_WINDOWS_POINTER_OFFSET,
)
from .io_helpers import try_read_c_string
from .pointers import (
    YftFragmentFlag,
    YftFragmentPointers,
    YftFragmentState,
    YftRawField,
)


def read_fragment_pointers(system_data: bytes) -> YftFragmentPointers:
    return YftFragmentPointers(
        common_drawable=_u64(system_data, MAIN_DRAWABLE_POINTER_OFFSET),
        extra_drawables=_u64(system_data, DRAWABLE_ARRAY_POINTER_OFFSET),
        extra_drawable_names=_u64(system_data, DRAWABLE_NAMES_POINTER_OFFSET),
        root_child=_u64(system_data, ROOT_CHILD_POINTER_OFFSET),
        tune_name=_u64(system_data, TUNE_NAME_POINTER_OFFSET),
        user_data=_u64(system_data, USER_DATA_POINTER_OFFSET),
        collision_event_set=_u64(system_data, COLLISION_EVENT_SET_POINTER_OFFSET),
        collision_event_player=_u64(system_data, COLLISION_EVENT_PLAYER_POINTER_OFFSET),
        shared_matrix_set=_u64(system_data, SHARED_MATRIX_SET_POINTER_OFFSET),
        glass_pane_model_infos=_u64(system_data, GLASS_PANE_MODEL_INFOS_POINTER_OFFSET),
        physics_lod_group=_u64(system_data, PHYSICS_LOD_GROUP_POINTER_OFFSET),
        cloth_drawable=_u64(system_data, CLOTH_DRAWABLE_POINTER_OFFSET),
        vehicle_glass_windows=_u64(system_data, VEHICLE_GLASS_WINDOWS_POINTER_OFFSET),
    )


def read_raw_fields(system_data: bytes) -> list[YftRawField]:
    fields: list[YftRawField] = []
    header_size = min(len(system_data), 0x120)
    for offset in range(0, header_size - 7, 8):
        value = _u64(system_data, offset)
        if not value:
            continue
        fields.append(
            YftRawField(
                offset=offset,
                value=value,
                label=RAW_FIELD_LABELS.get(offset, ""),
                pointed_string=try_read_c_string(system_data, value),
            )
        )
    return fields


def read_fragment_state(system_data: bytes) -> YftFragmentState:
    return YftFragmentState(
        damaged_drawable_index=_i32(system_data, DAMAGED_DRAWABLE_INDEX_OFFSET)
        if len(system_data) >= DAMAGED_DRAWABLE_INDEX_OFFSET + 4
        else -1,
        entity_class=system_data[0xC0] if len(system_data) > 0xC0 else 0,
        art_asset_id=int.from_bytes(system_data[0xC1:0xC2], "little", signed=True)
        if len(system_data) > 0xC1
        else 0,
        attach_bottom_end=bool(system_data[0xC2]) if len(system_data) > 0xC2 else False,
        flags=YftFragmentFlag(_u16(system_data, 0xC4))
        if len(system_data) >= 0xC6
        else YftFragmentFlag.NONE,
        client_class_id=_i32(system_data, 0xC8) if len(system_data) >= 0xCC else 0,
        unbroken_elasticity=float(_f32(system_data, 0xCC))
        if len(system_data) >= 0xD0
        else 0.0,
        gravity_factor=float(_f32(system_data, 0xD0))
        if len(system_data) >= 0xD4
        else 0.0,
        buoyancy_factor=float(_f32(system_data, 0xD4))
        if len(system_data) >= 0xD8
        else 0.0,
        glass_attachment_bone=system_data[0xD8] if len(system_data) > 0xD8 else 0,
        num_glass_pane_model_infos=system_data[0xD9] if len(system_data) > 0xD9 else 0,
        estimated_cache_size=_u64(system_data, ESTIMATED_CACHE_SIZE_OFFSET)
        if len(system_data) >= ESTIMATED_CACHE_SIZE_OFFSET + 8
        else 0,
        estimated_articulated_cache_size=_u64(
            system_data, ESTIMATED_ARTICULATED_CACHE_SIZE_OFFSET
        )
        if len(system_data) >= ESTIMATED_ARTICULATED_CACHE_SIZE_OFFSET + 8
        else 0,
    )


__all__ = [
    "read_fragment_pointers",
    "read_fragment_state",
    "read_raw_fields",
]
