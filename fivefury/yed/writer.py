from __future__ import annotations

import struct
from pathlib import Path

from ..binary import align
from ..resource import build_rsc7, get_resource_size_from_flags
from .constants import DEFAULT_YED_DICTIONARY_VFT, EXPRESSION_BLOCK_SIZE, SPRING_BLOCK_SIZE
from .model import ResourceListInfo, Yed, YedExpression, YedStream
from .reader import as_virtual_pointer


def build_yed_bytes(source: Yed) -> bytes:
    if source._standalone_data is not None and not source.dirty:
        return source._standalone_data
    if not source.system_data:
        source.validate()
        return build_rsc7(_build_yed_system(source), version=int(source.version), graphics_data=source.graphics_data)

    system = bytearray(source.system_data)
    for expression in source.expressions:
        if not expression.has_spring_changes:
            continue
        spring_offset = align(len(system), 16)
        if spring_offset > len(system):
            system.extend(b"\x00" * (spring_offset - len(system)))
        for spring in expression.springs:
            if len(spring.raw) != SPRING_BLOCK_SIZE:
                raise ValueError("YED spring data has an invalid size")
            system.extend(spring.raw)
        struct.pack_into("<QHHI", system, expression.offset + 0x40, as_virtual_pointer(spring_offset), len(expression.springs), len(expression.springs), 0)

    graphics_data = source.graphics_data
    system_flags = source.system_flags or None
    graphics_flags = source.graphics_flags or None
    if system_flags is not None and len(system) > get_resource_size_from_flags(system_flags):
        system_flags = None
    if graphics_flags is not None and len(graphics_data) > get_resource_size_from_flags(graphics_flags):
        graphics_flags = None
    return build_rsc7(
        bytes(system),
        version=int(source.version),
        graphics_data=graphics_data,
        system_flags=system_flags,
        graphics_flags=graphics_flags,
    )


def _alloc(system: bytearray, size: int, alignment: int = 16) -> int:
    offset = align(len(system), alignment)
    if offset > len(system):
        system.extend(b"\x00" * (offset - len(system)))
    system.extend(b"\x00" * size)
    return offset


def _write_list_info(system: bytearray, offset: int, info: ResourceListInfo) -> None:
    struct.pack_into(
        "<QHHI",
        system,
        offset,
        int(info.pointer),
        int(info.count) & 0xFFFF,
        int(info.capacity) & 0xFFFF,
        int(info.unknown),
    )


def _write_stream(system: bytearray, stream: YedStream) -> int:
    if stream.instructions and stream.has_semantic_instructions:
        stream.rebuild_buffers_from_instructions()
    data1 = bytes(stream.data1)
    data2 = bytes(stream.data2)
    data3 = bytes(stream.data3)
    if len(data3) > 0xFFFF:
        raise ValueError("YED stream instruction list cannot exceed 65535 bytes")
    offset = _alloc(system, 0x10 + len(data1) + len(data2) + len(data3), 16)
    struct.pack_into("<IIIHH", system, offset, int(stream.name_hash), len(data1), len(data2), len(data3), int(stream.depth) & 0xFFFF)
    cursor = offset + 0x10
    system[cursor : cursor + len(data1)] = data1
    cursor += len(data1)
    system[cursor : cursor + len(data2)] = data2
    cursor += len(data2)
    system[cursor : cursor + len(data3)] = data3
    return offset


def _write_expression_payloads(system: bytearray, expression: YedExpression) -> tuple[ResourceListInfo, ResourceListInfo, ResourceListInfo, ResourceListInfo, int, int]:
    stream_offsets = [_write_stream(system, stream) for stream in expression.streams]
    stream_pointer_offset = 0
    if stream_offsets:
        stream_pointer_offset = _alloc(system, len(stream_offsets) * 8, 16)
        for index, stream_offset in enumerate(stream_offsets):
            struct.pack_into("<Q", system, stream_pointer_offset + index * 8, as_virtual_pointer(stream_offset))

    track_offset = 0
    if expression.tracks:
        track_offset = _alloc(system, len(expression.tracks) * 4, 16)
        for index, track in enumerate(expression.tracks):
            struct.pack_into("<HBB", system, track_offset + index * 4, int(track.bone_id) & 0xFFFF, int(track.track) & 0xFF, int(track.flags) & 0xFF)

    spring_offset = 0
    if expression.springs:
        spring_offset = _alloc(system, len(expression.springs) * SPRING_BLOCK_SIZE, 16)
        for index, spring in enumerate(expression.springs):
            if len(spring.raw) != SPRING_BLOCK_SIZE:
                raise ValueError("YED spring data has an invalid size")
            system[spring_offset + index * SPRING_BLOCK_SIZE : spring_offset + (index + 1) * SPRING_BLOCK_SIZE] = spring.raw

    variable_offset = 0
    if expression.variables:
        variable_offset = _alloc(system, len(expression.variables) * 4, 16)
        for index, variable in enumerate(expression.variables):
            struct.pack_into("<I", system, variable_offset + index * 4, int(variable))

    encoded_name = expression.name.encode("ascii", errors="ignore") + b"\x00"
    name_offset = _alloc(system, len(encoded_name), 8)
    system[name_offset : name_offset + len(encoded_name)] = encoded_name

    max_stream_size = max((0x10 + len(stream.data1) + len(stream.data2) + len(stream.data3) for stream in expression.streams), default=0)
    return (
        ResourceListInfo(as_virtual_pointer(stream_pointer_offset), len(stream_offsets), len(stream_offsets)),
        ResourceListInfo(as_virtual_pointer(track_offset), len(expression.tracks), len(expression.tracks)),
        ResourceListInfo(as_virtual_pointer(spring_offset), len(expression.springs), len(expression.springs)),
        ResourceListInfo(as_virtual_pointer(variable_offset), len(expression.variables), len(expression.variables)),
        name_offset,
        max_stream_size,
    )


def _build_yed_system(source: Yed) -> bytes:
    expressions = sorted(source.expressions, key=lambda expression: int(expression.name_hash))
    system = bytearray(0x80)
    struct.pack_into("<IIBBHI", system, 0x40, 0, 0, 1, 0, 0, 0)

    hash_offset = _alloc(system, len(expressions) * 4, 16) if expressions else 0
    pointer_offset = _alloc(system, len(expressions) * 8, 16) if expressions else 0
    expression_offsets = [_alloc(system, EXPRESSION_BLOCK_SIZE, 16) for _ in expressions]

    for index, expression in enumerate(expressions):
        struct.pack_into("<I", system, hash_offset + index * 4, int(expression.name_hash))
        struct.pack_into("<Q", system, pointer_offset + index * 8, as_virtual_pointer(expression_offsets[index]))

    for expression, expression_offset in zip(expressions, expression_offsets, strict=True):
        streams, tracks, springs, variables, name_offset, max_stream_size = _write_expression_payloads(system, expression)
        struct.pack_into(
            "<IIIIIIII",
            system,
            expression_offset,
            int(expression.vft),
            int(expression.unknown_4h),
            0,
            0,
            0,
            0,
            0,
            0,
        )
        _write_list_info(system, expression_offset + 0x20, streams)
        _write_list_info(system, expression_offset + 0x30, tracks)
        _write_list_info(system, expression_offset + 0x40, springs)
        _write_list_info(system, expression_offset + 0x50, variables)
        struct.pack_into("<QHHIIIII", system, expression_offset + 0x60, as_virtual_pointer(name_offset), len(expression.name), len(expression.name) + 1, 0, int(expression.unknown_70h), int(expression.signature), int(expression.max_stream_size or max_stream_size), int(expression.expression_flags))
        struct.pack_into("<III", system, expression_offset + 0x80, 0, 0, 0)

    struct.pack_into(
        "<IIQIIII",
        system,
        0x00,
        int(source.dictionary.file_vft or DEFAULT_YED_DICTIONARY_VFT),
        int(source.dictionary.file_unknown),
        as_virtual_pointer(0x40),
        int(source.dictionary.unknown_10h),
        int(source.dictionary.unknown_14h),
        int(source.dictionary.unknown_18h),
        int(source.dictionary.unknown_1ch),
    )
    _write_list_info(system, 0x20, ResourceListInfo(as_virtual_pointer(hash_offset), len(expressions), len(expressions)))
    _write_list_info(system, 0x30, ResourceListInfo(as_virtual_pointer(pointer_offset), len(expressions), len(expressions)))
    return bytes(system)


def save_yed(source: Yed, destination: str | Path) -> Path:
    target = Path(destination)
    target.write_bytes(build_yed_bytes(source))
    return target


__all__ = [
    "build_yed_bytes",
    "save_yed",
]
