from __future__ import annotations

import struct

from ..binary import f32 as _f32
from ..binary import u16 as _u16
from ..binary import u32 as _u32
from ..binary import u64 as _u64
from .glass import (
    YftGlassPane,
    YftGlassPaneFlag,
    YftGlassVertexDeclaration,
    YftVehicleGlassFlag,
    YftVehicleGlassRow,
    YftVehicleGlassSpan,
    YftVehicleGlassWindow,
    YftVehicleGlassWindows,
)
from .io_helpers import read_pointer_array, read_vec3, try_virtual_offset

_GLASS_SENTINEL = 0x7F800001
_VEHICLE_GLASS_HEADER_TAG = 0x56475748
_VEHICLE_GLASS_WINDOW_TAG = 0x56475743


def _require_range(data: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"{label} points outside the YFT system section")


def _read_glass_pane(data: bytes, pointer: int) -> YftGlassPane:
    offset = try_virtual_offset(data, pointer)
    if offset is None:
        raise ValueError("glass pane pointer is invalid")
    _require_range(data, offset, 0x70, "glass pane")
    for sentinel_offset in (0x0C, 0x1C, 0x2C, 0x6C):
        if _u32(data, offset + sentinel_offset) != _GLASS_SENTINEL:
            raise ValueError("glass pane has an invalid aligned-vector sentinel")
    declaration = YftGlassVertexDeclaration(
        flags=_u32(data, offset + 0x40),
        stride=_u16(data, offset + 0x44),
        component_count=data[offset + 0x47],
        types=_u64(data, offset + 0x48),
    )
    return YftGlassPane(
        position_base=read_vec3(data, offset + 0x00),
        position_width=read_vec3(data, offset + 0x10),
        position_height=read_vec3(data, offset + 0x20),
        uv_min=struct.unpack_from("<2f", data, offset + 0x30),
        uv_max=struct.unpack_from("<2f", data, offset + 0x38),
        vertex_declaration=declaration,
        thickness=float(_f32(data, offset + 0x50)),
        flags=YftGlassPaneFlag(_u16(data, offset + 0x54)),
        glass_type=data[offset + 0x56],
        shader_index=data[offset + 0x57],
        bounds_offset_front=float(_f32(data, offset + 0x58)),
        bounds_offset_back=float(_f32(data, offset + 0x5C)),
        tangent=read_vec3(data, offset + 0x60),
    )


def read_glass_panes(data: bytes, pointer: int, count: int) -> list[YftGlassPane]:
    if count <= 0:
        return []
    pointers = read_pointer_array(data, pointer, count)
    if len(pointers) != count or any(not item for item in pointers):
        raise ValueError("glass pane owner array is incomplete")
    return [_read_glass_pane(data, item) for item in pointers]


def _read_vehicle_glass_row(data: bytes, offset: int, limit: int) -> YftVehicleGlassRow:
    _require_range(data, offset, 1, "vehicle-glass RLE row")
    start1 = data[offset]
    if start1 == 0xFF:
        return YftVehicleGlassRow.empty()
    _require_range(data, offset, 2, "vehicle-glass RLE row")
    end1 = data[offset + 1]
    if end1 < start1:
        raise ValueError("vehicle-glass RLE first span is reversed")
    cursor = offset + 2
    length1 = end1 - start1 + 1
    if cursor + length1 + 1 > limit:
        raise ValueError("vehicle-glass RLE first span is truncated")
    first = YftVehicleGlassSpan(start1, bytes(data[cursor : cursor + length1]))
    cursor += length1
    start2 = data[cursor]
    if start2 == 0xFF:
        return YftVehicleGlassRow(first)
    _require_range(data, cursor + 1, 1, "vehicle-glass RLE second span")
    end2 = data[cursor + 1]
    if end2 < start2:
        raise ValueError("vehicle-glass RLE second span is reversed")
    cursor += 2
    length2 = end2 - start2 + 1
    if cursor + length2 > limit:
        raise ValueError("vehicle-glass RLE second span is truncated")
    second = YftVehicleGlassSpan(start2, bytes(data[cursor : cursor + length2]))
    return YftVehicleGlassRow(first, second)


def _read_vehicle_glass_window(
    data: bytes, base: int, relative_offset: int, window_size: int, total_end: int
) -> YftVehicleGlassWindow:
    offset = base + relative_offset
    _require_range(data, offset, window_size, "vehicle-glass window")
    if _u32(data, offset + 0x40) != _VEHICLE_GLASS_WINDOW_TAG:
        raise ValueError("vehicle-glass window tag is invalid")
    component_id = _u16(data, offset + 0x44)
    geometry_index = _u16(data, offset + 0x46)
    columns = _u16(data, offset + 0x48)
    rows = _u16(data, offset + 0x4A)
    rle_size = _u32(data, offset + 0x4C)
    rle_offset = offset + window_size
    rle_end = rle_offset + rle_size
    if rle_end > total_end:
        raise ValueError("vehicle-glass RLE payload is truncated")

    row_values: list[YftVehicleGlassRow] = []
    if rle_size:
        table_size = rows * 2
        if table_size > rle_size:
            raise ValueError("vehicle-glass row-offset table is truncated")
        data_offset = rle_offset + table_size
        offsets = struct.unpack_from(f"<{rows}H", data, rle_offset) if rows else ()
        for index, row_offset in enumerate(offsets):
            row_limit = (
                data_offset + offsets[index + 1]
                if index + 1 < len(offsets)
                else rle_end
            )
            row_values.append(
                _read_vehicle_glass_row(data, data_offset + row_offset, row_limit)
            )

    return YftVehicleGlassWindow(
        component_id=component_id,
        geometry_index=geometry_index,
        rows=row_values,
        basis=struct.unpack_from("<16f", data, offset),
        data_min=float(_f32(data, offset + 0x58)),
        data_max=float(_f32(data, offset + 0x5C)),
        flags=YftVehicleGlassFlag(_u32(data, offset + 0x60)),
        texture_scale=float(_f32(data, offset + 0x64)),
        data_columns=columns,
        data_rows=rows,
    )


def read_vehicle_glass_windows(
    data: bytes, pointer: int
) -> YftVehicleGlassWindows | None:
    base = try_virtual_offset(data, pointer)
    if base is None:
        return None
    _require_range(data, base, 0x10, "vehicle-glass header")
    tag, window_size, count, total_size = struct.unpack_from("<IHHI", data, base)
    if tag != _VEHICLE_GLASS_HEADER_TAG:
        raise ValueError("vehicle-glass header tag is invalid")
    if window_size < 0x68:
        raise ValueError("vehicle-glass window size is too small")
    _require_range(data, base, total_size, "vehicle-glass block")
    refs_end = base + 0x0C + count * 8
    if refs_end > base + total_size:
        raise ValueError("vehicle-glass reference table is truncated")
    refs = [
        struct.unpack_from("<II", data, base + 0x0C + index * 8)
        for index in range(count)
    ]
    windows = [
        _read_vehicle_glass_window(
            data,
            base,
            relative_offset,
            window_size,
            base + total_size,
        )
        for _component_id, relative_offset in refs
    ]
    if any(
        component_id != window.component_id
        for (component_id, _), window in zip(refs, windows)
    ):
        raise ValueError("vehicle-glass reference component does not match its window")
    return YftVehicleGlassWindows(windows)


__all__ = [
    "read_glass_panes",
    "read_vehicle_glass_windows",
]
