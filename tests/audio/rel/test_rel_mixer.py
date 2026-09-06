from __future__ import annotations

import struct

import pytest

from fivefury import (
    Dat15DynamicMixModuleSettings,
    Dat15MixCategory,
    Dat15MixerPatch,
    Dat15MixerScene,
    Dat15MixGroup,
    Dat15MixGroupCategoryMap,
    Dat15MixGroupCategoryMapEntry,
    Dat15MixGroupList,
    Dat15MixModuleInput,
    Dat15PatchFlagId,
    Dat15PatchGroup,
    Dat15SceneFlagId,
    Dat15SceneState,
    Dat15SceneStateEntry,
    Dat15SceneTransitionModuleSettings,
    Dat15SceneVariableModuleSettings,
    Dat15VehicleCollisionModuleSettings,
    Dat15VolumeInvert,
    RelDatFileType,
    RelFile,
    RelRawItem,
    RelTriState,
    build_rel_bytes,
    read_rel,
    rel_hash,
    rel_tristate,
    replace_rel_tristate,
)


def _mixer_items():
    return [
        Dat15MixerPatch(
            name="vehicle_speed_patch",
            name_hash=rel_hash("vehicle_speed_patch"),
            fade_in=100,
            fade_out=200,
            pre_delay=0.25,
            duration=1.5,
            apply_factor_curve="LINEAR_RISE",
            apply_variable="apply",
            apply_smooth_rate=0.1,
            mix_categories=[
                Dat15MixCategory(
                    name="vehicle",
                    volume=-1200,
                    volume_invert=Dat15VolumeInvert.DO_NOTHING,
                    lpf_cutoff=1200,
                    hpf_cutoff=80,
                    pitch=100,
                    frequency=0.75,
                    pitch_invert=Dat15VolumeInvert.INVERT,
                    rolloff=0.5,
                )
            ],
        ),
        Dat15SceneState(
            name="wanted_state",
            name_hash=rel_hash("wanted_state"),
            states=[Dat15SceneStateEntry("wanted_high", "wanted_scene")],
        ),
        Dat15MixerScene(
            name="wanted_scene",
            name_hash=rel_hash("wanted_scene"),
            reference_count=-2,
            patch_groups=[Dat15PatchGroup("vehicle_speed_patch", "vehicle_mix_group")],
        ),
        Dat15MixGroup(
            name="vehicle_mix_group",
            name_hash=rel_hash("vehicle_mix_group"),
            reference_count=-1,
            fade_time=0.35,
            category_map="vehicle_category_map",
        ),
        Dat15MixGroupList(
            name="vehicle_mix_groups",
            name_hash=rel_hash("vehicle_mix_groups"),
            mix_groups=["vehicle_mix_group"],
        ),
        Dat15DynamicMixModuleSettings(
            name="vehicle_module",
            name_hash=rel_hash("vehicle_module"),
            fade_in=10,
            fade_out=20,
            apply_variable="apply",
            duration=2.5,
            module_type_settings="vehicle_variable_module",
        ),
        Dat15SceneVariableModuleSettings(
            name="vehicle_variable_module",
            name_hash=rel_hash("vehicle_variable_module"),
            scene_variable="speed",
            input_output_curve="LINEAR_RISE",
            input=Dat15MixModuleInput.PLAYER_VEHICLE_VELOCITY,
            scale_min=0.0,
            scale_max=120.0,
        ),
        Dat15SceneTransitionModuleSettings(
            name="wanted_transition_module",
            name_hash=rel_hash("wanted_transition_module"),
            input=Dat15MixModuleInput.PLAYER_WANTED_LEVEL,
            threshold=3.0,
            transition="wanted_transition",
        ),
        Dat15VehicleCollisionModuleSettings(
            name="collision_module",
            name_hash=rel_hash("collision_module"),
            input=Dat15MixModuleInput.VEHICLE_BUILDING_SIDES,
            transition="collision_transition",
        ),
        Dat15MixGroupCategoryMap(
            name="vehicle_category_map",
            name_hash=rel_hash("vehicle_category_map"),
            entries=[Dat15MixGroupCategoryMapEntry("vehicle", "master")],
        ),
    ]


def test_dat15_round_trips_every_dynamic_mixer_type() -> None:
    source = RelFile(
        rel_type=RelDatFileType.DAT15_DYNAMIC_MIXER,
        version=15,
        items=_mixer_items(),
    )

    data = build_rel_bytes(source)
    parsed = read_rel(data)
    by_name = {item.name: item for item in parsed.items}

    assert {type(item) for item in parsed.items} == {
        type(item) for item in source.items
    }
    assert by_name["wanted_scene"].reference_count == -2
    assert by_name["vehicle_module"].duration == pytest.approx(2.5)
    assert by_name["vehicle_speed_patch"].mix_categories[0].name == rel_hash("vehicle")
    assert build_rel_bytes(parsed) == data


def test_dat15_writer_uses_runtime_alignment_and_no_offset_tables() -> None:
    parsed = read_rel(
        build_rel_bytes(
            RelFile(
                rel_type=RelDatFileType.DAT15_DYNAMIC_MIXER,
                version=15,
                items=_mixer_items(),
            )
        )
    )
    aligned_types = {
        Dat15MixerPatch,
        Dat15DynamicMixModuleSettings,
        Dat15SceneVariableModuleSettings,
        Dat15SceneTransitionModuleSettings,
        Dat15VehicleCollisionModuleSettings,
    }

    assert all(
        item.data_offset % 4 == 0
        for item in parsed.items
        if type(item) in aligned_types
    )
    assert parsed.hash_table_offsets == []
    assert parsed.pack_table_offsets == []


def test_dat15_malformed_typed_item_remains_raw() -> None:
    source = RelFile(
        rel_type=RelDatFileType.DAT15_DYNAMIC_MIXER,
        version=15,
        items=[
            Dat15MixGroupList(
                name="broken_groups",
                name_hash=rel_hash("broken_groups"),
                mix_groups=["one"],
            )
        ],
    )
    data = bytearray(build_rel_bytes(source))
    data_length = struct.unpack_from("<I", data, 4)[0]
    name_table_length = struct.unpack_from("<I", data, 8 + data_length)[0]
    index_offset = 8 + data_length + 8 + name_table_length
    struct.pack_into("<I", data, index_offset + 8, 9)

    parsed = read_rel(data)

    assert isinstance(parsed.items[0], RelRawItem)


@pytest.mark.parametrize(
    ("item", "message"),
    [
        (
            Dat15MixerPatch(mix_categories=[Dat15MixCategory()] * 33),
            "at most 32",
        ),
        (
            Dat15SceneState(states=[Dat15SceneStateEntry()] * 9),
            "at most 8",
        ),
        (
            Dat15MixerScene(patch_groups=[Dat15PatchGroup()] * 17),
            "at most 16",
        ),
        (Dat15MixGroupList(mix_groups=[0] * 256), "at most 255"),
        (
            Dat15MixGroupCategoryMap(entries=[Dat15MixGroupCategoryMapEntry()] * 1025),
            "at most 1024",
        ),
    ],
)
def test_dat15_validates_runtime_capacities(item, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        item.to_data()


def test_dat15_packed_tristates_can_be_read_and_replaced() -> None:
    flags = 0xAAAAAAAA
    flags = replace_rel_tristate(
        flags,
        Dat15PatchFlagId.DISABLED_IN_PAUSE_MENU,
        RelTriState.TRUE,
    )
    flags = replace_rel_tristate(
        flags,
        Dat15SceneFlagId.CUTSCENE_QUICK_RELEASE,
        RelTriState.FALSE,
    )

    assert (
        rel_tristate(flags, Dat15PatchFlagId.DISABLED_IN_PAUSE_MENU) is RelTriState.TRUE
    )
    assert (
        rel_tristate(flags, Dat15SceneFlagId.CUTSCENE_QUICK_RELEASE)
        is RelTriState.FALSE
    )
    assert (
        rel_tristate(flags, Dat15SceneFlagId.MUTE_USER_MUSIC) is RelTriState.UNSPECIFIED
    )
