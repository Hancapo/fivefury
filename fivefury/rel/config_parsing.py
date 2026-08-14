from __future__ import annotations

import struct

from .config_types import (
    Dat4ConfigErPass,
    Dat4ConfigErSettings,
    Dat4ConfigFloat,
    Dat4ConfigInt,
    Dat4ConfigItem,
    Dat4ConfigString,
    Dat4ConfigUnsignedInt,
    Dat4ConfigVariable,
    Dat4ConfigVariableList,
    Dat4ConfigVector3,
    Dat4ConfigWaveSlot,
    Dat4ConfigWaveSlotsList,
)
from .enums import Dat4ConfigType
from .model import RelIndexHash


def _header(
    index: RelIndexHash, data: bytes, name_by_offset: dict[int, str]
) -> tuple[int, dict[str, object]]:
    if len(data) < 8:
        raise ValueError("DAT4 config header is truncated")
    packed, flags = struct.unpack_from("<II", data)
    type_id = packed & 0xFF
    name_table_offset = packed >> 8
    return type_id, {
        "name_hash": index.name_hash,
        "name": name_by_offset.get(name_table_offset),
        "data_offset": index.offset,
        "data_length": index.length,
        "raw_data": data,
        "name_table_offset": name_table_offset,
        "flags": flags,
    }


def _exact(data: bytes, size: int, label: str) -> None:
    if len(data) != size:
        raise ValueError(f"{label} length is invalid")


def _counted_hashes(data: bytes) -> list[int]:
    if len(data) < 12:
        raise ValueError("DAT4 hash list is truncated")
    count = struct.unpack_from("<i", data, 8)[0]
    if count < 0 or len(data) != 12 + count * 4:
        raise ValueError("DAT4 hash list count is invalid")
    return list(struct.unpack_from(f"<{count}I", data, 12)) if count else []


def _variable_list(data: bytes, kwargs: dict[str, object]) -> Dat4ConfigVariableList:
    if len(data) < 12:
        raise ValueError("DAT4 variable list is truncated")
    count = struct.unpack_from("<i", data, 8)[0]
    if count < 0 or len(data) != 12 + count * 8:
        raise ValueError("DAT4 variable list count is invalid")
    return Dat4ConfigVariableList(
        **kwargs,
        variables=[
            Dat4ConfigVariable(*struct.unpack_from("<If", data, 12 + index * 8))
            for index in range(count)
        ],
    )


def _vec4_array(data: bytes, offset: int, count: int) -> tuple[list[tuple[float, ...]], int]:
    if count < 0 or offset + count * 16 > len(data):
        raise ValueError("DAT4 ER vector array is invalid")
    values = [struct.unpack_from("<4f", data, offset + index * 16) for index in range(count)]
    return values, offset + count * 16


def _er_settings(data: bytes, kwargs: dict[str, object]) -> Dat4ConfigErSettings:
    if len(data) < 196:
        raise ValueError("DAT4 ER settings are truncated")
    room_size, *values = struct.unpack_from("<f3f3fi", data, 8)
    all_pass_count = values[6]
    if all_pass_count < 0:
        raise ValueError("DAT4 ER all-pass count is invalid")
    offset = 40
    if offset + all_pass_count * 8 + 144 + 12 > len(data):
        raise ValueError("DAT4 ER all-pass array is truncated")
    all_passes = [
        Dat4ConfigErPass(*struct.unpack_from("<fi", data, offset + index * 8))
        for index in range(all_pass_count)
    ]
    offset += all_pass_count * 8
    node_gain_matrix, offset = _vec4_array(data, offset, 6)
    gain_first_order = struct.unpack_from("<4f", data, offset)
    gain_second_order = struct.unpack_from("<4f", data, offset + 16)
    gain_third_order = struct.unpack_from("<4f", data, offset + 32)
    offset += 48
    arrays: list[list[tuple[float, ...]]] = []
    for _ in range(3):
        if offset + 4 > len(data):
            raise ValueError("DAT4 ER filter count is truncated")
        count = struct.unpack_from("<i", data, offset)[0]
        offset += 4
        array, offset = _vec4_array(data, offset, count)
        arrays.append(array)
    if offset != len(data):
        raise ValueError("DAT4 ER settings contain trailing data")
    return Dat4ConfigErSettings(
        **kwargs,
        room_size=room_size,
        room_dimensions=tuple(values[0:3]),
        listener_position=tuple(values[3:6]),
        all_passes=all_passes,
        node_gain_matrix=node_gain_matrix,
        gain_first_order=gain_first_order,
        gain_second_order=gain_second_order,
        gain_third_order=gain_third_order,
        node_lpf_first_order=arrays[0],
        node_lpf_second_order=arrays[1],
        node_lpf_third_order=arrays[2],
    )


def parse_dat4_config_item(
    index: RelIndexHash,
    data: bytes,
    name_by_offset: dict[int, str],
) -> Dat4ConfigItem | None:
    try:
        type_id, kwargs = _header(index, data, name_by_offset)
        if type_id == int(Dat4ConfigType.INT):
            _exact(data, 12, "DAT4 int")
            return Dat4ConfigInt(**kwargs, value=struct.unpack_from("<i", data, 8)[0])
        if type_id == int(Dat4ConfigType.UNSIGNED_INT):
            _exact(data, 12, "DAT4 unsigned int")
            return Dat4ConfigUnsignedInt(
                **kwargs, value=struct.unpack_from("<I", data, 8)[0]
            )
        if type_id == int(Dat4ConfigType.FLOAT):
            _exact(data, 12, "DAT4 float")
            return Dat4ConfigFloat(**kwargs, value=struct.unpack_from("<f", data, 8)[0])
        if type_id == int(Dat4ConfigType.STRING):
            _exact(data, 72, "DAT4 string")
            raw_value = data[8:72]
            separator = raw_value.find(b"\x00")
            value_end = len(raw_value) if separator < 0 else separator
            return Dat4ConfigString(
                **kwargs,
                value=raw_value[:value_end].decode("ascii"),
                string_padding=raw_value[value_end:],
            )
        if type_id == int(Dat4ConfigType.VECTOR3):
            _exact(data, 32, "DAT4 vector3")
            return Dat4ConfigVector3(
                **kwargs,
                prefix_padding=data[8:16],
                value=struct.unpack_from("<3f", data, 16),
                suffix_padding=data[28:32],
            )
        if type_id == int(Dat4ConfigType.VARIABLE_LIST):
            return _variable_list(data, kwargs)
        if type_id == int(Dat4ConfigType.WAVE_SLOT):
            _exact(data, 32, "DAT4 wave slot")
            values = struct.unpack_from("<iIIIII", data, 8)
            return Dat4ConfigWaveSlot(
                **kwargs,
                load_type=values[0],
                max_header_size=values[1],
                size=values[2],
                static_bank=values[3],
                max_metadata_size=values[4],
                max_data_size=values[5],
            )
        if type_id == int(Dat4ConfigType.WAVE_SLOTS_LIST):
            return Dat4ConfigWaveSlotsList(**kwargs, wave_slots=_counted_hashes(data))
        if type_id == int(Dat4ConfigType.ER_SETTINGS):
            return _er_settings(data, kwargs)
    except (UnicodeDecodeError, ValueError, struct.error):
        return None
    return None


__all__ = ["parse_dat4_config_item"]
