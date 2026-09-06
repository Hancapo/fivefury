from __future__ import annotations

import pytest

from fivefury import (
    Dat151AmbientCondition,
    Dat151AmbientRule,
    Dat151AmbientZone,
    Dat151AmbientZoneList,
    Dat151DirectionalAmbience,
    Dat151DirectionalAmbienceRef,
    Dat151EnvironmentRule,
    Dat151ExplicitSpawnType,
    Dat151StaticEmitter,
    Dat151StaticEmitterList,
    Dat151ZoneShape,
    Dat151ZoneVolume,
    RelDatFileType,
    RelFile,
    RelRawItem,
    Vector3,
    build_rel_bytes,
    read_rel,
    rel_hash,
)


def _world_items():
    return [
        Dat151StaticEmitterList(
            name="city_emitters",
            name_hash=rel_hash("city_emitters"),
            emitters=["traffic_emitter"],
        ),
        Dat151StaticEmitter(
            name="traffic_emitter",
            name_hash=rel_hash("traffic_emitter"),
            flags=0xAA041401,
            child_sound="traffic_sound",
            position=Vector3(10.0, 20.0, 5.0),
            min_distance=3.0,
            max_distance=80.0,
            emitted_volume=-1200,
            lpf_cutoff=400,
            hpf_cutoff=20,
            rolloff_factor=100,
            max_path_depth=3,
            undamaged_health=1000.0,
        ),
        Dat151AmbientRule(
            name="traffic_rule",
            name_hash=rel_hash("traffic_rule"),
            flags=0xAA0011A8,
            child_sound="traffic_sound",
            category="ambience_category",
            weight=1.0,
            min_distance=10.0,
            max_distance=120.0,
            min_time_minutes=360,
            max_time_minutes=1200,
            explicit_spawn=Dat151ExplicitSpawnType.WORLD_RELATIVE,
            max_local_instances=2,
            max_global_instances=8,
            conditions=[
                Dat151AmbientCondition(
                    name="traffic_density",
                    value=0.5,
                    condition_type=1,
                )
            ],
        ),
        Dat151AmbientZoneList(
            name="city_zones",
            name_hash=rel_hash("city_zones"),
            zones=["city_zone"],
        ),
        Dat151AmbientZone(
            name="city_zone",
            name_hash=rel_hash("city_zone"),
            flags=0xAA800465,
            shape=Dat151ZoneShape.BOX,
            activation=Dat151ZoneVolume(
                center=Vector3(10.0, 20.0, 5.0),
                size=Vector3(100.0, 80.0, 20.0),
            ),
            positioning=Dat151ZoneVolume(
                center=Vector3(10.0, 20.0, 5.0),
                size=Vector3(90.0, 70.0, 15.0),
            ),
            environment_rule="city_environment",
            rules_to_play=1,
            rules=["traffic_rule"],
            directional_ambiences=[
                Dat151DirectionalAmbienceRef("city_directional", 0.75)
            ],
        ),
        Dat151EnvironmentRule(
            name="city_environment",
            name_hash=rel_hash("city_environment"),
            reverb_small=0.2,
            reverb_medium=0.1,
            echo_delay=0.15,
            echo_number=2,
            echo_sound_list="city_echoes",
        ),
        Dat151DirectionalAmbience(
            name="city_directional",
            name_hash=rel_hash("city_directional"),
            sound_north="city_north",
            sound_east="city_east",
            sound_south="city_south",
            sound_west="city_west",
            volume_smoothing=0.25,
            max_distance_out_to_sea=500.0,
        ),
    ]


@pytest.mark.parametrize(
    "rel_type",
    [RelDatFileType.DAT149, RelDatFileType.DAT150, RelDatFileType.DAT151],
)
def test_game_rel_world_metadata_round_trips(rel_type: RelDatFileType) -> None:
    source = RelFile(rel_type=rel_type, version=151, items=_world_items())

    data = build_rel_bytes(source)
    parsed = read_rel(data)
    by_name = {item.name: item for item in parsed.items}

    assert isinstance(by_name["city_emitters"], Dat151StaticEmitterList)
    assert isinstance(by_name["traffic_emitter"], Dat151StaticEmitter)
    assert isinstance(by_name["traffic_rule"], Dat151AmbientRule)
    assert isinstance(by_name["city_zones"], Dat151AmbientZoneList)
    assert isinstance(by_name["city_zone"], Dat151AmbientZone)
    assert isinstance(by_name["city_environment"], Dat151EnvironmentRule)
    assert isinstance(by_name["city_directional"], Dat151DirectionalAmbience)
    assert by_name["traffic_rule"].conditions[0].name == rel_hash("traffic_density")
    assert by_name["city_zone"].rules == [rel_hash("traffic_rule")]
    assert build_rel_bytes(parsed) == data


def test_game_rel_writer_aligns_world_records() -> None:
    source = RelFile(rel_type=RelDatFileType.DAT151, items=_world_items())
    parsed = read_rel(build_rel_bytes(source))
    by_name = {item.name: item for item in parsed.items}

    assert by_name["city_emitters"].data_offset % 4 == 0
    assert by_name["traffic_rule"].data_offset % 16 == 0
    assert by_name["city_zone"].data_offset % 16 == 0


def test_game_rel_malformed_typed_item_remains_raw() -> None:
    item = Dat151StaticEmitter(
        name="broken_emitter",
        name_hash=rel_hash("broken_emitter"),
    )
    source = RelFile(rel_type=RelDatFileType.DAT151, items=[item])
    data = bytearray(build_rel_bytes(source))
    data_length = int.from_bytes(data[4:8], "little")
    name_table_length = int.from_bytes(data[8 + data_length : 12 + data_length], "little")
    index_offset = 8 + data_length + name_table_length + 8
    item_length_offset = index_offset + 8
    data[item_length_offset : item_length_offset + 4] = (8).to_bytes(4, "little")

    parsed = read_rel(data)

    assert isinstance(parsed.items[0], RelRawItem)


def test_ambient_zone_rejects_more_than_byte_sized_arrays() -> None:
    zone = Dat151AmbientZone(rules=[0] * 256)

    with pytest.raises(ValueError, match="at most 255"):
        zone.to_data()
