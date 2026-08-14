from __future__ import annotations

import struct

from .enums import Dat15MixModuleInput, Dat15RelType, Dat15VolumeInvert
from .mixer_types import (
    Dat15DynamicMixModuleSettings,
    Dat15MixCategory,
    Dat15MixerPatch,
    Dat15MixerScene,
    Dat15MixGroup,
    Dat15MixGroupCategoryMap,
    Dat15MixGroupCategoryMapEntry,
    Dat15MixGroupList,
    Dat15PatchGroup,
    Dat15RelItem,
    Dat15SceneState,
    Dat15SceneStateEntry,
    Dat15SceneTransitionModuleSettings,
    Dat15SceneVariableModuleSettings,
    Dat15VehicleCollisionModuleSettings,
)
from .model import RelIndexHash
from .named_parsing import named_item_header, require_exact_size


def _require_counted_size(
    data: bytes,
    fixed_size: int,
    count: int,
    stride: int,
    label: str,
) -> None:
    require_exact_size(data, fixed_size + count * stride, label)


def _mixer_patch(data: bytes, kwargs: dict[str, object]) -> Dat15MixerPatch:
    if len(data) < 33:
        raise ValueError("DAT15 mixer patch is truncated")
    values = struct.unpack_from("<HHffIIfB", data, 8)
    count = values[7]
    _require_counted_size(
        data, 33, count, Dat15MixCategory.STRUCT.size, "DAT15 mixer patch"
    )
    categories = []
    for offset in range(33, len(data), Dat15MixCategory.STRUCT.size):
        item = Dat15MixCategory.STRUCT.unpack_from(data, offset)
        categories.append(
            Dat15MixCategory(
                name=item[0],
                volume=item[1],
                volume_invert=Dat15VolumeInvert(item[2]),
                lpf_cutoff=item[3],
                hpf_cutoff=item[4],
                pitch=item[5],
                frequency=item[6],
                pitch_invert=Dat15VolumeInvert(item[7]),
                rolloff=item[8],
            )
        )
    return Dat15MixerPatch(
        **kwargs,
        fade_in=values[0],
        fade_out=values[1],
        pre_delay=values[2],
        duration=values[3],
        apply_factor_curve=values[4],
        apply_variable=values[5],
        apply_smooth_rate=values[6],
        mix_categories=categories,
    )


def _scene_state(data: bytes, kwargs: dict[str, object]) -> Dat15SceneState:
    if len(data) < 9:
        raise ValueError("DAT15 scene state is truncated")
    count = data[8]
    _require_counted_size(data, 9, count, 8, "DAT15 scene state")
    return Dat15SceneState(
        **kwargs,
        states=[
            Dat15SceneStateEntry(*struct.unpack_from("<II", data, 9 + index * 8))
            for index in range(count)
        ],
    )


def _mixer_scene(data: bytes, kwargs: dict[str, object]) -> Dat15MixerScene:
    if len(data) < 13:
        raise ValueError("DAT15 mixer scene is truncated")
    reference_count, count = struct.unpack_from("<iB", data, 8)
    _require_counted_size(data, 13, count, 8, "DAT15 mixer scene")
    return Dat15MixerScene(
        **kwargs,
        reference_count=reference_count,
        patch_groups=[
            Dat15PatchGroup(*struct.unpack_from("<II", data, 13 + index * 8))
            for index in range(count)
        ],
    )


def _mix_group_list(data: bytes, kwargs: dict[str, object]) -> Dat15MixGroupList:
    if len(data) < 9:
        raise ValueError("DAT15 mix group list is truncated")
    count = data[8]
    _require_counted_size(data, 9, count, 4, "DAT15 mix group list")
    return Dat15MixGroupList(
        **kwargs,
        mix_groups=list(struct.unpack_from(f"<{count}I", data, 9)) if count else [],
    )


def _category_map(
    data: bytes,
    kwargs: dict[str, object],
) -> Dat15MixGroupCategoryMap:
    if len(data) < 10:
        raise ValueError("DAT15 mix group category map is truncated")
    count = struct.unpack_from("<H", data, 8)[0]
    _require_counted_size(data, 10, count, 8, "DAT15 mix group category map")
    return Dat15MixGroupCategoryMap(
        **kwargs,
        entries=[
            Dat15MixGroupCategoryMapEntry(
                *struct.unpack_from("<II", data, 10 + index * 8)
            )
            for index in range(count)
        ],
    )


def parse_dat15_item(
    index: RelIndexHash,
    data: bytes,
    name_by_offset: dict[int, str],
) -> Dat15RelItem | None:
    try:
        type_id, kwargs = named_item_header(index, data, name_by_offset, "DAT15")
        if type_id == int(Dat15RelType.MIXER_PATCH):
            return _mixer_patch(data, kwargs)
        if type_id == int(Dat15RelType.SCENE_STATE):
            return _scene_state(data, kwargs)
        if type_id == int(Dat15RelType.MIXER_SCENE):
            return _mixer_scene(data, kwargs)
        if type_id == int(Dat15RelType.MIX_GROUP):
            require_exact_size(data, 20, "DAT15 mix group")
            values = struct.unpack_from("<ifI", data, 8)
            return Dat15MixGroup(
                **kwargs,
                reference_count=values[0],
                fade_time=values[1],
                category_map=values[2],
            )
        if type_id == int(Dat15RelType.MIX_GROUP_LIST):
            return _mix_group_list(data, kwargs)
        if type_id == int(Dat15RelType.DYNAMIC_MIX_MODULE_SETTINGS):
            require_exact_size(data, 24, "DAT15 dynamic mix module settings")
            values = struct.unpack_from("<HHIfI", data, 8)
            return Dat15DynamicMixModuleSettings(
                **kwargs,
                fade_in=values[0],
                fade_out=values[1],
                apply_variable=values[2],
                duration=values[3],
                module_type_settings=values[4],
            )
        if type_id == int(Dat15RelType.SCENE_VARIABLE_MODULE_SETTINGS):
            require_exact_size(data, 25, "DAT15 scene variable module settings")
            values = struct.unpack_from("<IIBff", data, 8)
            return Dat15SceneVariableModuleSettings(
                **kwargs,
                scene_variable=values[0],
                input_output_curve=values[1],
                input=Dat15MixModuleInput(values[2]),
                scale_min=values[3],
                scale_max=values[4],
            )
        if type_id == int(Dat15RelType.SCENE_TRANSITION_MODULE_SETTINGS):
            require_exact_size(data, 17, "DAT15 scene transition module settings")
            values = struct.unpack_from("<BfI", data, 8)
            return Dat15SceneTransitionModuleSettings(
                **kwargs,
                input=Dat15MixModuleInput(values[0]),
                threshold=values[1],
                transition=values[2],
            )
        if type_id == int(Dat15RelType.VEHICLE_COLLISION_MODULE_SETTINGS):
            require_exact_size(data, 13, "DAT15 vehicle collision module settings")
            values = struct.unpack_from("<BI", data, 8)
            return Dat15VehicleCollisionModuleSettings(
                **kwargs,
                input=Dat15MixModuleInput(values[0]),
                transition=values[1],
            )
        if type_id == int(Dat15RelType.MIX_GROUP_CATEGORY_MAP):
            return _category_map(data, kwargs)
    except (ValueError, struct.error):
        return None
    return None


__all__ = ["parse_dat15_item"]
