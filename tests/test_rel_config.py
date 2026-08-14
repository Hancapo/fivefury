from __future__ import annotations

import struct

import pytest

from fivefury import (
    Dat4ConfigErPass,
    Dat4ConfigErSettings,
    Dat4ConfigFloat,
    Dat4ConfigInt,
    Dat4ConfigString,
    Dat4ConfigUnsignedInt,
    Dat4ConfigVariable,
    Dat4ConfigVariableList,
    Dat4ConfigVector3,
    Dat4ConfigWaveSlot,
    Dat4ConfigWaveSlotsList,
    RelDatFileType,
    RelFile,
    RelRawItem,
    build_rel_bytes,
    read_rel,
    rel_hash,
)


def _config_items():
    return [
        Dat4ConfigInt(name="signed_value", value=-12),
        Dat4ConfigUnsignedInt(name="unsigned_value", value=0xF0000000),
        Dat4ConfigFloat(name="float_value", value=0.75),
        Dat4ConfigString(name="string_value", value="audio/config"),
        Dat4ConfigVector3(name="listener_offset", value=(1.0, 2.0, 3.0)),
        Dat4ConfigVariableList(
            name="variables",
            variables=[Dat4ConfigVariable("volume", 0.5)],
        ),
        Dat4ConfigWaveSlot(
            name="dialogue_slot",
            load_type=1,
            max_header_size=2048,
            size=4096,
            static_bank="dialogue_static",
            max_metadata_size=1024,
            max_data_size=8192,
        ),
        Dat4ConfigWaveSlotsList(
            name="wave_slots",
            wave_slots=["dialogue_slot", "music_slot"],
        ),
        Dat4ConfigErSettings(
            name="early_reflections",
            room_size=12.0,
            room_dimensions=(8.0, 6.0, 3.0),
            listener_position=(1.0, 1.5, 1.8),
            all_passes=[Dat4ConfigErPass(0.25, 2)],
            node_gain_matrix=[(float(index), 0.0, 0.0, 1.0) for index in range(6)],
            gain_first_order=(1.0, 2.0, 3.0, 4.0),
            gain_second_order=(5.0, 6.0, 7.0, 8.0),
            gain_third_order=(9.0, 10.0, 11.0, 12.0),
            node_lpf_first_order=[(0.1, 0.2, 0.3, 0.4)],
            node_lpf_second_order=[(0.5, 0.6, 0.7, 0.8)],
            node_lpf_third_order=[(0.9, 1.0, 1.1, 1.2)],
        ),
    ]


def test_dat4_audio_config_round_trips_all_typed_values() -> None:
    source = RelFile(
        rel_type=RelDatFileType.DAT4,
        version=4,
        items=_config_items(),
        is_audio_config=True,
    )

    data = build_rel_bytes(source)
    parsed = read_rel(data)

    assert parsed.is_audio_config
    assert [type(item) for item in parsed.items] == [
        type(item) for item in source.items
    ]
    assert [item.name for item in parsed.items] == [
        item.name for item in source.items
    ]
    assert build_rel_bytes(parsed) == data


def test_dat4_audio_config_aligns_vector_values_and_indexes_hashes() -> None:
    source = RelFile(
        rel_type=RelDatFileType.DAT4,
        items=[
            Dat4ConfigVector3(name="position", value=(1.0, 2.0, 3.0)),
            Dat4ConfigWaveSlotsList(
                name="wave_slots",
                wave_slots=["first_slot", "second_slot"],
            ),
        ],
        is_audio_config=True,
    )

    parsed = read_rel(build_rel_bytes(source))
    vector, wave_slots = parsed.items

    assert vector.data_offset % 16 == 0
    assert len(parsed.hash_table_offsets) == 2
    expected = {
        8 + wave_slots.data_offset + 12,
        8 + wave_slots.data_offset + 16,
    }
    assert set(parsed.hash_table_offsets) == expected


def test_dat4_audio_config_malformed_typed_item_remains_raw() -> None:
    source = RelFile(
        rel_type=RelDatFileType.DAT4,
        items=[Dat4ConfigInt(name="broken", value=3)],
        is_audio_config=True,
    )
    data = bytearray(build_rel_bytes(source))
    data_length = struct.unpack_from("<I", data, 4)[0]
    entry_offset = 8 + data_length + 8 + 8
    name_length = data[entry_offset]
    item_length_offset = entry_offset + 1 + name_length + 4
    struct.pack_into("<I", data, item_length_offset, 8)

    parsed = read_rel(data)

    assert isinstance(parsed.items[0], RelRawItem)


def test_dat4_audio_config_validates_fixed_capacities() -> None:
    with pytest.raises(ValueError, match="at most 64 ASCII bytes"):
        Dat4ConfigString(value="x" * 65).to_data()

    with pytest.raises(ValueError, match="exactly 6 node gain vectors"):
        Dat4ConfigErSettings(node_gain_matrix=[]).to_data()


def test_dat4_audio_config_hash_fields_accept_names() -> None:
    variable = Dat4ConfigVariable("volume", 1.0)
    wave_slot = Dat4ConfigWaveSlot(static_bank="dialogue_static")

    assert struct.unpack_from("<I", variable.to_bytes())[0] == rel_hash("volume")
    assert struct.unpack_from("<I", wave_slot.to_data(), 20)[0] == rel_hash(
        "dialogue_static"
    )
