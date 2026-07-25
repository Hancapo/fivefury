from __future__ import annotations

import struct
from pathlib import Path

from .model import (
    HeightCell,
    HeightGrid,
    HeightMap,
    HeightMapBounds,
    HeightMapByteOrder,
    HeightMapCellFormat,
    HeightMapFlags,
)

_HEADER_SIZE = 44
_RLE_ROW_SIZE = 8
_TAG = b"HMAP"
_REVERSED_TAG = _TAG[::-1]


def _source_bytes(source: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    return Path(source).read_bytes()


def _endian_prefix(order: HeightMapByteOrder) -> str:
    return ">" if order is HeightMapByteOrder.BIG else "<"


def _cell_format(cell_format: HeightMapCellFormat) -> str:
    return {
        HeightMapCellFormat.UINT8: "B",
        HeightMapCellFormat.UINT16: "H",
        HeightMapCellFormat.FLOAT32: "f",
    }[cell_format]


def _unpack_cells(
    data: bytes,
    offset: int,
    count: int,
    *,
    endian: str,
    cell_format: HeightMapCellFormat,
) -> tuple[list[HeightCell], int]:
    size = int(cell_format)
    end = offset + count * size
    if end > len(data):
        raise ValueError("height-map cell data is truncated")
    if count == 0:
        return [], end
    values = struct.unpack_from(
        f"{endian}{count}{_cell_format(cell_format)}", data, offset
    )
    return list(values), end


def _pack_cells(
    values: list[HeightCell],
    *,
    endian: str,
    cell_format: HeightMapCellFormat,
) -> bytes:
    if not values:
        return b""
    return struct.pack(
        f"{endian}{len(values)}{_cell_format(cell_format)}",
        *values,
    )


def _unpack_water_mask(data: bytes, cell_count: int) -> list[bool]:
    return [bool(data[index // 8] & (1 << (index % 8))) for index in range(cell_count)]


def _pack_water_mask(cells: list[bool]) -> bytes:
    result = bytearray((len(cells) + 7) // 8)
    for index, enabled in enumerate(cells):
        if enabled:
            result[index // 8] |= 1 << (index % 8)
    return bytes(result)


def read_heightmap(
    source: bytes | bytearray | memoryview | str | Path,
) -> HeightMap:
    data = _source_bytes(source)
    if len(data) < _HEADER_SIZE:
        raise ValueError("height-map data is shorter than its 44-byte header")
    if data[:4] == _TAG:
        order = HeightMapByteOrder.BIG
    elif data[:4] == _REVERSED_TAG:
        order = HeightMapByteOrder.LITTLE
    else:
        raise ValueError("height-map data does not start with the HMAP tag")

    endian = _endian_prefix(order)
    (
        _,
        version,
        cell_size,
        raw_flags,
        columns,
        rows,
        min_x,
        min_y,
        min_z,
        max_x,
        max_y,
        max_z,
        data_size,
    ) = struct.unpack_from(f"{endian}4sBB2xIHH6fI", data)
    try:
        cell_format = HeightMapCellFormat(cell_size)
    except ValueError as exc:
        raise ValueError(f"unsupported height-map cell size: {cell_size}") from exc
    if not 1 <= columns <= 1000 or not 1 <= rows <= 1000:
        raise ValueError("height-map dimensions must be between 1 and 1000 cells")

    flags = HeightMapFlags(raw_flags)
    mask_size = (columns * rows + 7) // 8 if flags & HeightMapFlags.WATER_MASK else 0
    expected_size = _HEADER_SIZE + data_size + mask_size
    if len(data) != expected_size:
        raise ValueError(
            f"height-map size mismatch: header describes {expected_size} bytes, got {len(data)}"
        )

    payload = data[_HEADER_SIZE : _HEADER_SIZE + data_size]
    cell_count = columns * rows
    empty: HeightCell = 0.0 if cell_format is HeightMapCellFormat.FLOAT32 else 0
    minimum_cells = [empty] * cell_count
    maximum_cells = [empty] * cell_count

    if flags & HeightMapFlags.RLE_DATA:
        table_size = rows * _RLE_ROW_SIZE
        if len(payload) < table_size:
            raise ValueError("height-map RLE table is truncated")
        compact_bytes = len(payload) - table_size
        pair_size = int(cell_format) * 2
        if compact_bytes % pair_size:
            raise ValueError(
                "height-map RLE payload is not aligned to min/max cell pairs"
            )
        compact_count = compact_bytes // pair_size
        rle_rows = [
            struct.unpack_from(f"{endian}HHi", payload, row * _RLE_ROW_SIZE)
            for row in range(rows)
        ]
        offset = table_size
        maximum_compact, offset = _unpack_cells(
            payload,
            offset,
            compact_count,
            endian=endian,
            cell_format=cell_format,
        )
        minimum_compact, offset = _unpack_cells(
            payload,
            offset,
            compact_count,
            endian=endian,
            cell_format=cell_format,
        )
        if offset != len(payload):
            raise ValueError("height-map RLE payload contains trailing bytes")

        for row, (start, count, data_offset) in enumerate(rle_rows):
            if start > columns or count > columns - start:
                raise ValueError(f"height-map RLE row {row} exceeds the column count")
            compact_start = data_offset + start
            if compact_start < 0 or compact_start + count > compact_count:
                raise ValueError(
                    f"height-map RLE row {row} points outside the compact data"
                )
            dense_start = row * columns + start
            dense_stop = dense_start + count
            minimum_cells[dense_start:dense_stop] = minimum_compact[
                compact_start : compact_start + count
            ]
            maximum_cells[dense_start:dense_stop] = maximum_compact[
                compact_start : compact_start + count
            ]
    else:
        expected_data_size = cell_count * int(cell_format) * 2
        if data_size != expected_data_size:
            raise ValueError(
                f"height-map cell payload should contain {expected_data_size} bytes, got {data_size}"
            )
        maximum_cells, offset = _unpack_cells(
            payload,
            0,
            cell_count,
            endian=endian,
            cell_format=cell_format,
        )
        minimum_cells, offset = _unpack_cells(
            payload,
            offset,
            cell_count,
            endian=endian,
            cell_format=cell_format,
        )
        if offset != len(payload):
            raise ValueError("height-map cell payload contains trailing bytes")

    water_cells = None
    if mask_size:
        water_cells = _unpack_water_mask(data[-mask_size:], cell_count)

    result = HeightMap(
        columns=columns,
        rows=rows,
        bounds=HeightMapBounds(min_x, min_y, min_z, max_x, max_y, max_z),
        minimum_cells=minimum_cells,
        maximum_cells=maximum_cells,
        water_cells=water_cells,
        cell_format=cell_format,
        version=version,
        flags=flags,
        source_byte_order=order,
    )
    result.ensure_valid(game_compatible=False)
    return result


def _compact_rows(
    heightmap: HeightMap,
) -> tuple[list[tuple[int, int, int]], list[HeightCell], list[HeightCell]]:
    rows: list[tuple[int, int, int]] = []
    maximum: list[HeightCell] = []
    minimum: list[HeightCell] = []
    compact_count = 0
    ranges: list[tuple[int, int]] = []

    for row in range(heightmap.rows):
        row_offset = row * heightmap.columns
        start = 0
        stop = heightmap.columns - 1
        while start < heightmap.columns:
            index = row_offset + start
            if (
                heightmap.minimum_cells[index] != 0
                or heightmap.maximum_cells[index] != 0
            ):
                break
            start += 1
        while stop >= start:
            index = row_offset + stop
            if (
                heightmap.minimum_cells[index] != 0
                or heightmap.maximum_cells[index] != 0
            ):
                break
            stop -= 1
        count = max(0, stop - start + 1)
        rows.append(
            (start if count else 0, count, compact_count - start if count else 0)
        )
        ranges.append((row_offset + start, count))
        compact_count += count

    for start, count in ranges:
        maximum.extend(heightmap.maximum_cells[start : start + count])
    for start, count in ranges:
        minimum.extend(heightmap.minimum_cells[start : start + count])
    return rows, maximum, minimum


def build_heightmap_bytes(
    source: HeightMap,
    *,
    rle: bool | None = None,
    byte_order: HeightMapByteOrder = HeightMapByteOrder.BIG,
    game_compatible: bool = True,
) -> bytes:
    heightmap = source.build().ensure_valid(game_compatible=game_compatible)
    order = HeightMapByteOrder(byte_order)
    endian = _endian_prefix(order)
    use_rle = heightmap.uses_rle if rle is None else bool(rle)

    if use_rle:
        rows, maximum, minimum = _compact_rows(heightmap)
        table = b"".join(struct.pack(f"{endian}HHi", *row) for row in rows)
        payload = (
            table
            + _pack_cells(maximum, endian=endian, cell_format=heightmap.cell_format)
            + _pack_cells(minimum, endian=endian, cell_format=heightmap.cell_format)
        )
    else:
        payload = _pack_cells(
            heightmap.maximum_cells,
            endian=endian,
            cell_format=heightmap.cell_format,
        ) + _pack_cells(
            heightmap.minimum_cells,
            endian=endian,
            cell_format=heightmap.cell_format,
        )

    flags = int(heightmap.flags)
    if use_rle:
        flags |= int(HeightMapFlags.RLE_DATA)
    else:
        flags &= ~int(HeightMapFlags.RLE_DATA)
    if heightmap.water_cells is not None:
        flags |= int(HeightMapFlags.WATER_MASK)
        water_mask = _pack_water_mask(heightmap.water_cells)
    else:
        flags &= ~int(HeightMapFlags.WATER_MASK)
        water_mask = b""

    tag = _TAG if order is HeightMapByteOrder.BIG else _REVERSED_TAG
    bounds = heightmap.bounds
    header = struct.pack(
        f"{endian}4sBB2xIHH6fI",
        tag,
        heightmap.version,
        int(heightmap.cell_format),
        flags,
        heightmap.columns,
        heightmap.rows,
        bounds.min_x,
        bounds.min_y,
        bounds.min_z,
        bounds.max_x,
        bounds.max_y,
        bounds.max_z,
        len(payload),
    )
    return header + payload + water_mask


def create_heightmap(
    minimum: HeightGrid,
    maximum: HeightGrid | None = None,
    *,
    bounds: HeightMapBounds | tuple[float, float, float, float, float, float],
    water: list[list[bool]] | None = None,
    cell_format: HeightMapCellFormat = HeightMapCellFormat.UINT8,
) -> HeightMap:
    return HeightMap.from_height_grids(
        minimum,
        maximum,
        bounds=bounds,
        water=water,
        cell_format=cell_format,
    )


def save_heightmap(
    source: HeightMap,
    destination: str | Path,
    *,
    rle: bool | None = None,
    byte_order: HeightMapByteOrder = HeightMapByteOrder.BIG,
    game_compatible: bool = True,
) -> Path:
    return source.save(
        destination,
        rle=rle,
        byte_order=byte_order,
        game_compatible=game_compatible,
    )


__all__ = [
    "build_heightmap_bytes",
    "create_heightmap",
    "read_heightmap",
    "save_heightmap",
]
