from __future__ import annotations

import struct
from pathlib import Path

from ..binary import read_c_string, u16, u32, u64
from ..common import ByteSource, read_source_bytes
from ..metahash import MetaHash
from ..resource import RSC7_MAGIC, checked_virtual_offset, split_rsc7_sections
from .constants import EXPRESSION_BLOCK_SIZE, SPRING_BLOCK_SIZE, VIRTUAL_BASE
from .instructions import parse_instruction_buffers
from .model import ResourceListInfo, Yed, YedDictionary, YedExpression, YedSpring, YedStream, YedTrack


def virtual_offset(pointer: int, data: bytes) -> int:
    return checked_virtual_offset(pointer, data, base=VIRTUAL_BASE, allow_plain_offset=True)


def safe_virtual_offset(pointer: int, data: bytes) -> int | None:
    if not pointer:
        return None
    try:
        return virtual_offset(pointer, data)
    except ValueError:
        return None


def as_virtual_pointer(offset: int) -> int:
    return VIRTUAL_BASE + int(offset) if offset else 0


def _read_hash_list(data: bytes, info: ResourceListInfo) -> list[MetaHash]:
    start = safe_virtual_offset(info.pointer, data)
    if start is None or info.count <= 0:
        return []
    end = start + (info.count * 4)
    if end > len(data):
        raise ValueError("YED hash list is truncated")
    return [MetaHash(u32(data, start + index * 4)) for index in range(info.count)]


def _read_pointer_list(data: bytes, info: ResourceListInfo) -> list[int]:
    start = safe_virtual_offset(info.pointer, data)
    if start is None or info.count <= 0:
        return []
    end = start + (info.count * 8)
    if end > len(data):
        raise ValueError("YED pointer list is truncated")
    return [u64(data, start + index * 8) for index in range(info.count)]


def _read_tracks(data: bytes, info: ResourceListInfo) -> list[YedTrack]:
    start = safe_virtual_offset(info.pointer, data)
    if start is None or info.count <= 0:
        return []
    end = start + (info.count * 4)
    if end > len(data):
        raise ValueError("YED track list is truncated")
    return [
        YedTrack(
            bone_id=u16(data, start + index * 4),
            track=data[start + index * 4 + 2],
            flags=data[start + index * 4 + 3],
        )
        for index in range(info.count)
    ]


def _read_springs(data: bytes, info: ResourceListInfo) -> list[YedSpring]:
    start = safe_virtual_offset(info.pointer, data)
    if start is None or info.count <= 0:
        return []
    end = start + (info.count * SPRING_BLOCK_SIZE)
    if end > len(data):
        raise ValueError("YED spring list is truncated")
    return [
        YedSpring(bytes(data[start + index * SPRING_BLOCK_SIZE : start + (index + 1) * SPRING_BLOCK_SIZE]))
        for index in range(info.count)
    ]


def _read_stream(data: bytes, pointer: int) -> YedStream | None:
    offset = safe_virtual_offset(pointer, data)
    if offset is None:
        return None
    if offset + 0x10 > len(data):
        raise ValueError("YED stream header is truncated")
    name_hash, data1_len, data2_len = struct.unpack_from("<III", data, offset)
    data3_len = u16(data, offset + 0x0C)
    depth = u16(data, offset + 0x0E)
    total = 0x10 + data1_len + data2_len + data3_len
    if offset + total > len(data):
        raise ValueError("YED stream data is truncated")
    data1_start = offset + 0x10
    data2_start = data1_start + data1_len
    data3_start = data2_start + data2_len
    data3 = bytes(data[data3_start : data3_start + data3_len])
    instructions = parse_instruction_buffers(bytes(data[data1_start:data2_start]), bytes(data[data2_start:data3_start]), data3)
    return YedStream(
        name_hash=MetaHash(name_hash),
        depth=depth,
        data1=bytes(data[data1_start:data2_start]),
        data2=bytes(data[data2_start:data3_start]),
        data3=data3,
        instructions=instructions,
        raw=bytes(data[offset : offset + total]),
        pointer=pointer,
        offset=offset,
    )


def _read_streams(data: bytes, info: ResourceListInfo) -> list[YedStream]:
    return [stream for pointer in _read_pointer_list(data, info) if (stream := _read_stream(data, pointer)) is not None]


def _read_expression(data: bytes, pointer: int, name_hash: MetaHash) -> YedExpression:
    offset = virtual_offset(pointer, data)
    if offset + EXPRESSION_BLOCK_SIZE > len(data):
        raise ValueError("YED expression block is truncated")
    streams_info = ResourceListInfo.read(data, offset + 0x20)
    tracks_info = ResourceListInfo.read(data, offset + 0x30)
    springs_info = ResourceListInfo.read(data, offset + 0x40)
    variables_info = ResourceListInfo.read(data, offset + 0x50)
    name_pointer = u64(data, offset + 0x60)
    name_offset = safe_virtual_offset(name_pointer, data)
    name = read_c_string(data, name_offset) if name_offset is not None else ""
    springs = _read_springs(data, springs_info)
    expression = YedExpression(
        name=name,
        name_hash=name_hash,
        pointer=pointer,
        offset=offset,
        vft=u32(data, offset + 0x00),
        unknown_4h=u32(data, offset + 0x04),
        unknown_70h=u32(data, offset + 0x70),
        signature=u32(data, offset + 0x74),
        max_stream_size=u32(data, offset + 0x78),
        expression_flags=u32(data, offset + 0x7C),
        header=bytes(data[offset : offset + EXPRESSION_BLOCK_SIZE]),
        streams_info=streams_info,
        tracks_info=tracks_info,
        springs_info=springs_info,
        variables_info=variables_info,
        streams=_read_streams(data, streams_info),
        tracks=_read_tracks(data, tracks_info),
        springs=springs,
        variables=_read_hash_list(data, variables_info),
        _original_spring_bones=tuple(spring.bone_id for spring in springs),
    )
    return expression


def read_yed_dictionary(system_data: bytes) -> YedDictionary:
    if len(system_data) < 0x40:
        raise ValueError("YED system section is too short for ExpressionDictionary")
    dictionary = YedDictionary(
        file_vft=u32(system_data, 0x00),
        file_unknown=u32(system_data, 0x04),
        pages_info_pointer=u64(system_data, 0x08),
        unknown_10h=u32(system_data, 0x10),
        unknown_14h=u32(system_data, 0x14),
        unknown_18h=u32(system_data, 0x18),
        unknown_1ch=u32(system_data, 0x1C),
        expression_name_hashes=ResourceListInfo.read(system_data, 0x20),
        expressions_info=ResourceListInfo.read(system_data, 0x30),
    )
    name_hashes = _read_hash_list(system_data, dictionary.expression_name_hashes)
    expression_pointers = _read_pointer_list(system_data, dictionary.expressions_info)
    for index, pointer in enumerate(expression_pointers):
        name_hash = name_hashes[index] if index < len(name_hashes) else MetaHash(0)
        dictionary.expressions.append(_read_expression(system_data, pointer, name_hash))
    return dictionary


def read_yed(source: ByteSource, *, path: str | Path = "") -> Yed:
    data = read_source_bytes(source)
    if len(data) < 16:
        raise ValueError("YED data is too short")
    if int.from_bytes(data[:4], "little") != RSC7_MAGIC:
        raise ValueError("YED data must be a standalone RSC7 resource")
    header, system_data, graphics_data = split_rsc7_sections(data)
    return Yed(
        dictionary=read_yed_dictionary(system_data),
        version=int(header.version),
        path=str(path or source) if isinstance(source, (str, Path)) or path else "",
        system_flags=int(header.system_flags),
        graphics_flags=int(header.graphics_flags),
        system_data=system_data,
        graphics_data=graphics_data,
        _standalone_data=data,
    )


__all__ = [
    "as_virtual_pointer",
    "read_yed",
    "read_yed_dictionary",
    "safe_virtual_offset",
    "virtual_offset",
]
