from __future__ import annotations

import struct

import pytest

from fivefury import (
    Aabb2,
    GameFileCache,
    GameFileType,
    HeightMap,
    HeightMapBounds,
    HeightMapByteOrder,
    HeightMapCellFormat,
    HeightMapFlags,
    ValidationError,
    Vector2,
    create_heightmap,
    read_heightmap,
)
from fivefury.gamefile import guess_game_file_type


def _sample_heightmap(*, water_mask: bool = True) -> HeightMap:
    heightmap = HeightMap.empty(
        columns=10,
        rows=10,
        bounds=HeightMapBounds(-250.0, -250.0, 0.0, 250.0, 250.0, 800.0),
        water_mask=water_mask,
    )
    heightmap.set_height(3, 2, minimum=12.0, maximum=45.0)
    heightmap.set_height(4, 2, minimum=15.0, maximum=60.0)
    heightmap.set_height(8, 7, minimum=100.0, maximum=180.0)
    if water_mask:
        heightmap.set_water(4, 2)
        heightmap.set_water(8, 7)
    return heightmap


def test_rle_roundtrip_preserves_cells_and_water_mask() -> None:
    original = _sample_heightmap()
    encoded = original.to_bytes()

    assert encoded[:4] == b"HMAP"
    header = struct.unpack_from(">4sBB2xIHH6fI", encoded)
    assert header[1:6] == (
        1,
        HeightMapCellFormat.UINT8,
        int(HeightMapFlags.RLE_DATA | HeightMapFlags.WATER_MASK),
        10,
        10,
    )

    rebuilt = read_heightmap(encoded)
    assert rebuilt.columns == 10
    assert rebuilt.rows == 10
    assert rebuilt.bounds == original.bounds
    assert rebuilt.minimum_cells == original.minimum_cells
    assert rebuilt.maximum_cells == original.maximum_cells
    assert rebuilt.water_cells == original.water_cells
    assert rebuilt.height_range(0, 0) is None
    assert rebuilt.height_range(4, 2) == pytest.approx(original.height_range(4, 2))
    assert rebuilt.is_water(4, 2)
    assert rebuilt.to_bytes() == encoded


def test_rle_rows_match_the_game_offset_convention() -> None:
    encoded = _sample_heightmap(water_mask=False).to_bytes()
    table_offset = 44

    empty_row = struct.unpack_from(">HHi", encoded, table_offset)
    occupied_row = struct.unpack_from(">HHi", encoded, table_offset + 2 * 8)
    later_row = struct.unpack_from(">HHi", encoded, table_offset + 7 * 8)

    assert empty_row == (0, 0, 0)
    assert occupied_row == (3, 2, -3)
    assert later_row == (8, 1, -6)


def test_non_rle_and_little_endian_variants_are_readable() -> None:
    original = _sample_heightmap(water_mask=False)
    encoded = original.to_bytes(rle=False, byte_order=HeightMapByteOrder.LITTLE)

    assert encoded[:4] == b"PAMH"
    rebuilt = read_heightmap(encoded)
    assert rebuilt.source_byte_order is HeightMapByteOrder.LITTLE
    assert not rebuilt.uses_rle
    assert rebuilt.minimum_cells == original.minimum_cells
    assert rebuilt.maximum_cells == original.maximum_cells


def test_uint16_tool_heightmap_roundtrips_when_game_check_is_disabled() -> None:
    heightmap = HeightMap.empty(
        columns=2,
        rows=2,
        bounds=(0.0, 0.0, -100.0, 2.0, 2.0, 900.0),
        cell_format=HeightMapCellFormat.UINT16,
    )
    heightmap.set_height(0, 0, minimum=12.25, maximum=15.75)

    with pytest.raises(ValidationError, match="UINT8"):
        heightmap.to_bytes()

    encoded = heightmap.to_bytes(game_compatible=False)
    rebuilt = read_heightmap(encoded)
    assert rebuilt.cell_format is HeightMapCellFormat.UINT16
    assert rebuilt.minimum_cells == heightmap.minimum_cells
    assert rebuilt.maximum_cells == heightmap.maximum_cells


def test_declarative_grid_creation_and_spatial_queries() -> None:
    minimum = [[None for _ in range(10)] for _ in range(10)]
    maximum = [[None for _ in range(10)] for _ in range(10)]
    water = [[False for _ in range(10)] for _ in range(10)]
    minimum[4][6] = 20.0
    maximum[4][6] = 50.0
    water[4][6] = True

    heightmap = create_heightmap(
        minimum,
        maximum,
        bounds=(100.0, 200.0, 0.0, 600.0, 700.0, 800.0),
        water=water,
    )

    assert heightmap.world_to_cell(425.0, 425.0) == (6, 4)
    assert heightmap.cell_center(6, 4) == Vector2(425.0, 425.0)
    assert heightmap.cell_bounds(6, 4) == Aabb2(
        Vector2(400.0, 400.0),
        Vector2(450.0, 450.0),
    )
    assert heightmap.height_range_at(425.0, 425.0) == pytest.approx(
        heightmap.height_range(6, 4)
    )
    assert heightmap.height_range_in_bounds(400.0, 400.0, 450.0, 450.0) == (
        heightmap.height_range(6, 4)
    )
    assert heightmap.is_water(6, 4)
    assert heightmap.is_water_at(425.0, 425.0)
    assert heightmap.world_to_cell(600.0, 425.0) is None


def test_reader_rejects_invalid_rle_pointers_and_sizes() -> None:
    encoded = bytearray(_sample_heightmap(water_mask=False).to_bytes())
    struct.pack_into(">HHi", encoded, 44 + 2 * 8, 3, 2, 1000)
    with pytest.raises(ValueError, match="outside the compact data"):
        read_heightmap(encoded)

    with pytest.raises(ValueError, match="size mismatch"):
        read_heightmap(bytes(encoded) + b"\x00")


def test_game_file_detection_and_cache_decoding(tmp_path) -> None:
    path = tmp_path / "heightmapheistisland.dat"
    path.write_bytes(_sample_heightmap().to_bytes())

    assert guess_game_file_type(path) is GameFileType.HEIGHTMAP
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan()
    game_file = cache.get_file(path.name)

    assert game_file is not None
    assert game_file.kind is GameFileType.HEIGHTMAP
    assert isinstance(game_file.parsed, HeightMap)
    assert len(cache.HeightMapDict) == 1
