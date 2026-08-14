from __future__ import annotations

import struct

from ..binary import align
from .enums import Dat151ExplicitSpawnType, Dat151RelType, Dat151ZoneShape
from .game_types import (
    Dat151AmbientCondition,
    Dat151AmbientRule,
    Dat151AmbientZone,
    Dat151AmbientZoneList,
    Dat151DirectionalAmbience,
    Dat151DirectionalAmbienceRef,
    Dat151EnvironmentRule,
    Dat151RelItem,
    Dat151StaticEmitter,
    Dat151StaticEmitterList,
    Dat151ZoneVolume,
)
from .model import RelIndexHash

GAME_REL_TYPES = frozenset(
    {
        int(Dat151RelType.STATIC_EMITTER),
        int(Dat151RelType.STATIC_EMITTER_LIST),
        int(Dat151RelType.AMBIENT_ZONE),
        int(Dat151RelType.AMBIENT_RULE),
        int(Dat151RelType.AMBIENT_ZONE_LIST),
        int(Dat151RelType.ENVIRONMENT_RULE),
        int(Dat151RelType.DIRECTIONAL_AMBIENCE),
    }
)


def _item_kwargs(
    index: RelIndexHash,
    raw: bytes,
    name_by_offset: dict[int, str],
    name_table_offset: int,
) -> dict[str, object]:
    return {
        "name_hash": index.name_hash,
        "name": name_by_offset.get(name_table_offset),
        "data_offset": index.offset,
        "data_length": index.length,
        "raw_data": raw,
        "name_table_offset": name_table_offset,
    }


def _hash_list(data: bytes) -> list[int]:
    if len(data) < 8:
        raise ValueError("game REL hash list is truncated")
    count = struct.unpack_from("<I", data, 4)[0]
    expected = 8 + count * 4
    if expected != len(data):
        raise ValueError("game REL hash list length is invalid")
    return list(struct.unpack_from(f"<{count}I", data, 8)) if count else []


def _zone_volume(data: bytes, offset: int) -> Dat151ZoneVolume:
    values = Dat151ZoneVolume.STRUCT.unpack_from(data, offset)
    return Dat151ZoneVolume(
        center=values[0:3],
        reserved_center=values[3],
        size=values[4:7],
        reserved_size=values[7],
        post_rotation_offset=values[8:11],
        reserved_post_rotation=values[11],
        size_scale=values[12:15],
        reserved_scale=values[15],
        rotation_angle=values[16],
        reserved_rotation=values[17],
        reserved_04=values[18],
        reserved_05=values[19],
        reserved_06=values[20],
    )


def _ambient_rule(
    index: RelIndexHash,
    data: bytes,
    kwargs: dict[str, object],
) -> Dat151AmbientRule:
    if len(data) < 80:
        raise ValueError("AmbientRule is truncated")
    values = Dat151AmbientRule.FIXED.unpack_from(data, 4)
    count = values[25]
    unpadded_size = 80 + count * 12
    expected = align(unpadded_size, 16)
    if len(data) != expected:
        raise ValueError("AmbientRule condition array is invalid")
    conditions = []
    for offset in range(80, unpadded_size, 12):
        name, value, condition_type, bank_loading, reserved = struct.unpack_from(
            "<IfBBH", data, offset
        )
        conditions.append(
            Dat151AmbientCondition(
                name=name,
                value=value,
                condition_type=condition_type,
                bank_loading=bank_loading,
                reserved=reserved,
            )
        )
    return Dat151AmbientRule(
        **kwargs,
        flags=values[0],
        reserved_01=values[1],
        reserved_02=values[2],
        position=values[3:6],
        reserved_03=values[6],
        child_sound=values[7],
        category=values[8],
        last_play_time=values[9],
        dynamic_bank_id=values[10],
        dynamic_slot_type=values[11],
        weight=values[12],
        min_distance=values[13],
        max_distance=values[14],
        min_time_minutes=values[15],
        max_time_minutes=values[16],
        min_repeat_time=values[17],
        min_repeat_time_variance=values[18],
        spawn_height=values[19],
        explicit_spawn=Dat151ExplicitSpawnType(values[20]),
        max_local_instances=values[21],
        max_global_instances=values[22],
        blockability_factor=values[23],
        max_path_depth=values[24],
        conditions=conditions,
        trailing_padding=data[unpadded_size:],
    )


def _ambient_zone(
    index: RelIndexHash,
    data: bytes,
    kwargs: dict[str, object],
) -> Dat151AmbientZone:
    if len(data) < 240:
        raise ValueError("AmbientZone is truncated")
    flags, shape, shape_reserved, reserved_00 = struct.unpack_from("<IB3sI", data, 4)
    activation = _zone_volume(data, 16)
    positioning = _zone_volume(data, 96)
    values = Dat151AmbientZone.TAIL.unpack_from(data, 176)
    rule_count = values[15]
    rules_offset = 232
    directional_offset = rules_offset + rule_count * 4
    if directional_offset + 4 > len(data):
        raise ValueError("AmbientZone rule array is truncated")
    rules = (
        list(struct.unpack_from(f"<{rule_count}I", data, rules_offset))
        if rule_count
        else []
    )
    directional_count, directional_reserved = struct.unpack_from(
        "<B3s", data, directional_offset
    )
    directional_values_offset = directional_offset + 4
    unpadded_size = directional_values_offset + directional_count * 8
    expected = align(unpadded_size, 16)
    if len(data) != expected:
        raise ValueError("AmbientZone directional ambience array is invalid")
    directional_ambiences = [
        Dat151DirectionalAmbienceRef(
            *struct.unpack_from("<If", data, directional_values_offset + i * 8)
        )
        for i in range(directional_count)
    ]
    return Dat151AmbientZone(
        **kwargs,
        flags=flags,
        shape=Dat151ZoneShape(shape),
        shape_reserved=shape_reserved,
        reserved_00=reserved_00,
        activation=activation,
        positioning=positioning,
        built_up_factor=values[0],
        min_ped_density=values[1],
        max_ped_density=values[2],
        ped_density_tod=values[3],
        ped_density_scalar=values[4],
        max_wind_influence=values[5],
        min_wind_influence=values[6],
        wind_elevation_sounds=values[7],
        environment_rule=values[8],
        audio_scene=values[9],
        underwater_creak_factor=values[10],
        ped_walla_settings=values[11],
        randomised_radio_settings=values[12],
        rules_to_play=values[13],
        water_calculation=values[14],
        rules_reserved=values[16],
        rules=rules,
        directional_reserved=directional_reserved,
        directional_ambiences=directional_ambiences,
        trailing_padding=data[unpadded_size:],
    )


def _static_emitter(kwargs: dict[str, object], data: bytes) -> Dat151StaticEmitter:
    if len(data) != 4 + Dat151StaticEmitter.STRUCT.size:
        raise ValueError("StaticEmitter length is invalid")
    values = Dat151StaticEmitter.STRUCT.unpack_from(data, 4)
    return Dat151StaticEmitter(
        **kwargs,
        flags=values[0],
        child_sound=values[1],
        radio_station=values[2],
        position=values[3:6],
        min_distance=values[6],
        max_distance=values[7],
        emitted_volume=values[8],
        lpf_cutoff=values[9],
        hpf_cutoff=values[10],
        rolloff_factor=values[11],
        reserved_00=values[12],
        interior=values[13],
        room=values[14],
        radio_station_for_score=values[15],
        max_leakage=values[16],
        min_leakage_distance=values[17],
        max_leakage_distance=values[18],
        alarm=values[19],
        on_break_one_shot=values[20],
        max_path_depth=values[21],
        small_reverb_send=values[22],
        medium_reverb_send=values[23],
        large_reverb_send=values[24],
        min_time_minutes=values[25],
        max_time_minutes=values[26],
        broken_health=values[27],
        undamaged_health=values[28],
    )


def _environment_rule(
    kwargs: dict[str, object], data: bytes
) -> Dat151EnvironmentRule:
    if len(data) != 4 + Dat151EnvironmentRule.STRUCT.size:
        raise ValueError("EnvironmentRule length is invalid")
    values = Dat151EnvironmentRule.STRUCT.unpack_from(data, 4)
    return Dat151EnvironmentRule(
        **kwargs,
        flags=values[0],
        reverb_small=values[1],
        reverb_medium=values[2],
        reverb_large=values[3],
        reverb_damp=values[4],
        echo_delay=values[5],
        echo_delay_variance=values[6],
        echo_attenuation=values[7],
        echo_number=values[8],
        echo_sound_list=values[9],
        base_echo_volume_modifier=values[10],
    )


def _directional_ambience(
    kwargs: dict[str, object], data: bytes
) -> Dat151DirectionalAmbience:
    if len(data) != 4 + Dat151DirectionalAmbience.STRUCT.size:
        raise ValueError("DirectionalAmbience length is invalid")
    values = Dat151DirectionalAmbience.STRUCT.unpack_from(data, 4)
    return Dat151DirectionalAmbience(
        **kwargs,
        flags=values[0],
        sound_north=values[1],
        sound_east=values[2],
        sound_south=values[3],
        sound_west=values[4],
        volume_smoothing=values[5],
        time_to_volume=values[6],
        occlusion_to_volume=values[7],
        height_to_cutoff=values[8],
        occlusion_to_cutoff=values[9],
        built_up_factor_to_volume=values[10],
        building_density_to_volume=values[11],
        tree_density_to_volume=values[12],
        water_factor_to_volume=values[13],
        instance_volume_scale=values[14],
        height_above_blanket_to_volume=values[15],
        highway_factor_to_volume=values[16],
        vehicle_count_to_volume=values[17],
        max_distance_out_to_sea=values[18],
    )


def parse_game_rel_item(
    index: RelIndexHash,
    data: bytes,
    name_by_offset: dict[int, str],
) -> Dat151RelItem | None:
    if len(data) < 4:
        return None
    packed = struct.unpack_from("<I", data)[0]
    type_id = packed & 0xFF
    if type_id not in GAME_REL_TYPES:
        return None
    name_table_offset = packed >> 8
    kwargs = _item_kwargs(index, data, name_by_offset, name_table_offset)
    try:
        if type_id == int(Dat151RelType.STATIC_EMITTER_LIST):
            return Dat151StaticEmitterList(**kwargs, emitters=_hash_list(data))
        if type_id == int(Dat151RelType.AMBIENT_ZONE_LIST):
            return Dat151AmbientZoneList(**kwargs, zones=_hash_list(data))
        if type_id == int(Dat151RelType.STATIC_EMITTER):
            return _static_emitter(kwargs, data)
        if type_id == int(Dat151RelType.AMBIENT_RULE):
            return _ambient_rule(index, data, kwargs)
        if type_id == int(Dat151RelType.AMBIENT_ZONE):
            return _ambient_zone(index, data, kwargs)
        if type_id == int(Dat151RelType.ENVIRONMENT_RULE):
            return _environment_rule(kwargs, data)
        if type_id == int(Dat151RelType.DIRECTIONAL_AMBIENCE):
            return _directional_ambience(kwargs, data)
    except (ValueError, struct.error):
        return None
    return None


__all__ = ["GAME_REL_TYPES", "parse_game_rel_item"]
