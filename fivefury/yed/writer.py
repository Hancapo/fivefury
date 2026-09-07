from __future__ import annotations

import struct
from pathlib import Path

from ..common import atomic_write_bytes
from ..game_target import GameTarget, coerce_game_target
from ..resource import (
    ResourceBlockSpan,
    ResourcePagesInfo,
    ResourceWriter,
    build_rsc7,
    get_resource_total_page_count,
    layout_resource_sections,
    write_resource_pages_info,
)
from .constants import EXPRESSION_BLOCK_SIZE, SPRING_BLOCK_SIZE
from .layout import validate_yed_resource_layout
from .model import ResourceListInfo, Yed, YedExpression, YedStream
from .reader import as_virtual_pointer
from .runtime_headers import YED_VERSION, YedRuntimeProfile, get_yed_runtime_profile


def build_yed_bytes(source: Yed, *, game: str | GameTarget | None = None) -> bytes:
    target = coerce_game_target(source.game if game is None else game)
    if int(source.version) != YED_VERSION:
        raise ValueError(
            f"YED resources require version {YED_VERSION}, got {source.version}"
        )
    if (
        source._standalone_data is not None
        and not source.dirty
        and target is coerce_game_target(source.game)
    ):
        source.validate_runtime_contract().raise_for_errors()
        validate_yed_resource_layout(source).raise_for_errors()
        return source._standalone_data
    source.validate().raise_for_errors()
    profile = get_yed_runtime_profile(target)
    page_counts = (0, 0)
    graphics = source.graphics_data
    graphics_blocks = [ResourceBlockSpan(0, len(graphics), False)] if graphics else []
    for _ in range(16):
        writer = _build_yed_system(source, profile, page_counts)
        system, physical, system_flags, graphics_flags = layout_resource_sections(
            writer.finish(),
            writer.block_spans,
            graphics,
            graphics_blocks,
            version=source.version,
        )
        next_counts = (
            get_resource_total_page_count(system_flags),
            get_resource_total_page_count(graphics_flags),
        )
        if next_counts == page_counts:
            return build_rsc7(
                system,
                version=source.version,
                graphics_data=physical,
                system_flags=system_flags,
                graphics_flags=graphics_flags,
            )
        page_counts = next_counts
    raise RuntimeError("YED writer page-info sizing did not converge")


def _write_list_info(
    writer: ResourceWriter, offset: int, info: ResourceListInfo
) -> None:
    writer.pack_into(
        "QHHI", offset, info.pointer, info.count, info.capacity, info.unknown
    )


def _write_array(
    writer: ResourceWriter,
    payload: bytes,
    count: int,
    *,
    pointer_offsets: tuple[int, ...] = (),
) -> ResourceListInfo:
    if not count:
        return ResourceListInfo()
    offset = writer.alloc(len(payload), pointer_offsets=pointer_offsets)
    writer.write(offset, payload)
    return ResourceListInfo(as_virtual_pointer(offset), count, count)


def _write_stream(writer: ResourceWriter, stream: YedStream) -> int:
    if stream.instructions and stream.has_semantic_instructions:
        stream.rebuild_buffers_from_instructions()
    data1, data2, data3 = bytes(stream.data1), bytes(stream.data2), bytes(stream.data3)
    if len(data3) > 0xFFFF or not 0 <= stream.depth <= 0xFFFF:
        raise ValueError("YED stream opcode count and depth must fit uint16")
    # The entire stream is one allocation, including all three parameter buffers.
    payload = (
        struct.pack(
            "<IIIHH",
            int(stream.name_hash),
            len(data1),
            len(data2),
            len(data3),
            stream.depth,
        )
        + data1
        + data2
        + data3
    )
    offset = writer.alloc(len(payload), relocate_pointers=False)
    writer.write(offset, payload)
    return offset


def _write_expression(
    writer: ResourceWriter,
    offset: int,
    expression: YedExpression,
    profile: YedRuntimeProfile,
) -> None:
    stream_offsets = [_write_stream(writer, stream) for stream in expression.streams]
    streams = _write_array(
        writer,
        b"".join(
            struct.pack("<Q", as_virtual_pointer(value)) for value in stream_offsets
        ),
        len(stream_offsets),
        pointer_offsets=tuple(range(0, len(stream_offsets) * 8, 8)),
    )
    tracks = _write_array(
        writer,
        b"".join(
            struct.pack("<HBB", track.bone_id, track.track, track.flags)
            for track in expression.tracks
        ),
        len(expression.tracks),
    )
    if any(len(spring.raw) != SPRING_BLOCK_SIZE for spring in expression.springs):
        raise ValueError("YED spring data has an invalid size")
    springs = _write_array(
        writer,
        b"".join(spring.raw for spring in expression.springs),
        len(expression.springs),
    )
    variables = _write_array(
        writer,
        b"".join(struct.pack("<I", int(value)) for value in expression.variables),
        len(expression.variables),
    )
    encoded_name = expression.name.encode("ascii") + b"\0"
    name_offset = writer.alloc(len(encoded_name), alignment=8, relocate_pointers=False)
    writer.write(name_offset, encoded_name)
    max_stream_size = max(
        (0x10 + len(s.data1) + len(s.data2) + len(s.data3) for s in expression.streams),
        default=0,
    )
    writer.pack_into("II", offset, profile.expression_vft, expression.unknown_4h)
    for relative, info in (
        (0x20, streams),
        (0x30, tracks),
        (0x40, springs),
        (0x50, variables),
    ):
        _write_list_info(writer, offset + relative, info)
    writer.pack_into(
        "QHHIIIII",
        offset + 0x60,
        as_virtual_pointer(name_offset),
        len(encoded_name) - 1,
        len(encoded_name),
        0,
        expression.unknown_70h,
        expression.signature,
        expression.max_stream_size or max_stream_size,
        expression.expression_flags,
    )


def _build_yed_system(
    source: Yed, profile: YedRuntimeProfile, page_counts: tuple[int, int]
) -> ResourceWriter:
    writer = ResourceWriter(0x40, initial_pointer_offsets=(0x08, 0x20, 0x30))
    expressions = sorted(
        source.expressions, key=lambda expression: int(expression.name_hash)
    )
    pages = write_resource_pages_info(
        writer,
        ResourcePagesInfo(
            system_pages_count=page_counts[0], graphics_pages_count=page_counts[1]
        ),
    )
    offsets = [
        writer.alloc(
            EXPRESSION_BLOCK_SIZE, pointer_offsets=(0x20, 0x30, 0x40, 0x50, 0x60)
        )
        for _ in expressions
    ]
    hashes = _write_array(
        writer,
        b"".join(struct.pack("<I", int(e.name_hash)) for e in expressions),
        len(expressions),
    )
    pointers = _write_array(
        writer,
        b"".join(struct.pack("<Q", as_virtual_pointer(value)) for value in offsets),
        len(offsets),
        pointer_offsets=tuple(range(0, len(offsets) * 8, 8)),
    )
    for expression, offset in zip(expressions, offsets, strict=True):
        _write_expression(writer, offset, expression, profile)
    dictionary = source.dictionary
    writer.pack_into(
        "IIQIIII",
        0,
        profile.dictionary_vft,
        dictionary.file_unknown,
        as_virtual_pointer(pages),
        dictionary.unknown_10h,
        dictionary.unknown_14h,
        dictionary.unknown_18h,
        dictionary.unknown_1ch,
    )
    _write_list_info(writer, 0x20, hashes)
    _write_list_info(writer, 0x30, pointers)
    writer.require_explicit_pointer_fields()
    return writer


def save_yed(
    source: Yed, destination: str | Path, *, game: str | GameTarget | None = None
) -> Path:
    return atomic_write_bytes(destination, build_yed_bytes(source, game=game))


__all__ = ["build_yed_bytes", "save_yed"]
