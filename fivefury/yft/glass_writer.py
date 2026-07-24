from __future__ import annotations

import struct
from collections.abc import Sequence

from ..binary import align
from ..resource import ResourceWriter
from .glass import (
    YftGlassPane,
    YftVehicleGlassRow,
    YftVehicleGlassWindow,
    YftVehicleGlassWindows,
)

_GLASS_SENTINEL = 0x7F800001
_VEHICLE_GLASS_HEADER_TAG = 0x56475748
_VEHICLE_GLASS_WINDOW_TAG = 0x56475743
_VEHICLE_GLASS_WINDOW_SIZE = 0x70


def _virtual(offset: int, virtual_base: int) -> int:
    return int(virtual_base) + int(offset)


def _write_vec3(system: ResourceWriter, offset: int, value) -> None:
    system.pack_into("3f", offset, *(float(item) for item in value))
    system.pack_into("I", offset + 0x0C, _GLASS_SENTINEL)


def write_glass_panes(
    system: ResourceWriter,
    panes: Sequence[YftGlassPane],
    *,
    virtual_base: int,
) -> int:
    if not panes:
        return 0
    pane_offsets: list[int] = []
    for pane in panes:
        offset = system.alloc(0x70, 16)
        pane_offsets.append(offset)
        _write_vec3(system, offset + 0x00, pane.position_base)
        _write_vec3(system, offset + 0x10, pane.position_width)
        _write_vec3(system, offset + 0x20, pane.position_height)
        system.pack_into("2f", offset + 0x30, *pane.uv_min)
        system.pack_into("2f", offset + 0x38, *pane.uv_max)
        declaration = pane.vertex_declaration
        system.pack_into("I", offset + 0x40, int(declaration.flags))
        system.pack_into("H", offset + 0x44, int(declaration.stride))
        system.data[offset + 0x46] = 0
        system.data[offset + 0x47] = declaration.count & 0xFF
        system.pack_into("Q", offset + 0x48, int(declaration.types))
        system.pack_into("f", offset + 0x50, float(pane.thickness))
        system.pack_into("H", offset + 0x54, int(pane.flags))
        system.data[offset + 0x56] = int(pane.glass_type) & 0xFF
        system.data[offset + 0x57] = int(pane.shader_index) & 0xFF
        system.pack_into(
            "2f",
            offset + 0x58,
            float(pane.bounds_offset_front),
            float(pane.bounds_offset_back),
        )
        _write_vec3(system, offset + 0x60, pane.tangent)

    owner_offset = system.alloc(len(pane_offsets) * 8, 8)
    for index, pane_offset in enumerate(pane_offsets):
        system.pack_into(
            "Q", owner_offset + index * 8, _virtual(pane_offset, virtual_base)
        )
    return owner_offset


def _encode_row(row: YftVehicleGlassRow) -> bytes:
    if row.first is None:
        return b"\xff"
    result = bytearray((row.first.start, row.first.end))
    result.extend(row.first.values)
    if row.second is None:
        result.append(0xFF)
    else:
        result.extend((row.second.start, row.second.end))
        result.extend(row.second.values)
    return bytes(result)


def _encode_rle(window: YftVehicleGlassWindow) -> bytes:
    if not window.rows:
        return b""
    encoded = [_encode_row(row) for row in window.rows]
    offsets: list[int] = []
    cursor = 0
    for row in encoded:
        offsets.append(cursor)
        cursor += len(row)
    return struct.pack(f"<{len(offsets)}H", *offsets) + b"".join(encoded)


def _encode_window(window: YftVehicleGlassWindow) -> bytes:
    rle = _encode_rle(window)
    result = bytearray(_VEHICLE_GLASS_WINDOW_SIZE + len(rle))
    struct.pack_into("<16f", result, 0x00, *window.basis)
    struct.pack_into("<I", result, 0x40, _VEHICLE_GLASS_WINDOW_TAG)
    struct.pack_into(
        "<HHHHI",
        result,
        0x44,
        int(window.component_id),
        int(window.geometry_index),
        window.column_count,
        window.row_count,
        len(rle),
    )
    struct.pack_into(
        "<ffIf",
        result,
        0x58,
        float(window.data_min),
        float(window.data_max),
        int(window.flags),
        float(window.texture_scale),
    )
    result[_VEHICLE_GLASS_WINDOW_SIZE:] = rle
    return bytes(result)


def build_vehicle_glass_windows(value: YftVehicleGlassWindows) -> bytes:
    windows = sorted(value.windows, key=lambda item: item.component_id)
    count = len(windows)
    data_start = align(0x0C + count * 8, 16)
    result = bytearray(data_start)
    encoded_windows: list[tuple[YftVehicleGlassWindow, bytes, int]] = []
    cursor = data_start
    for window in windows:
        encoded = _encode_window(window)
        encoded_windows.append((window, encoded, cursor))
        cursor += align(len(encoded), 16)
    result.extend(b"\x00" * (cursor - len(result)))
    struct.pack_into(
        "<IHHI",
        result,
        0,
        _VEHICLE_GLASS_HEADER_TAG,
        _VEHICLE_GLASS_WINDOW_SIZE,
        count,
        cursor,
    )
    for index, (window, encoded, offset) in enumerate(encoded_windows):
        struct.pack_into(
            "<II", result, 0x0C + index * 8, int(window.component_id), offset
        )
        result[offset : offset + len(encoded)] = encoded
    return bytes(result)


def write_vehicle_glass_windows(
    system: ResourceWriter, value: YftVehicleGlassWindows | None
) -> int:
    if value is None or not value.windows:
        return 0
    payload = build_vehicle_glass_windows(value)
    offset = system.alloc(len(payload), 16)
    system.write(offset, payload)
    return offset


__all__ = [
    "build_vehicle_glass_windows",
    "write_glass_panes",
    "write_vehicle_glass_windows",
]
