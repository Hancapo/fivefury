from __future__ import annotations

import struct

import pytest

from fivefury import (
    BoundBox,
    EntityDef,
    GameFileCache,
    GameFileType,
    Gta5CacheBound,
    Gta5CacheBoundAssetType,
    Gta5CacheFileDate,
    Gta5CacheInteriorProxy,
    Gta5CacheMapData,
    Gta5CacheMode,
    Gta5CacheY,
    MloArchetypeDef,
    MloInstanceDef,
    Ymap,
    YmapContentFlags,
    YmapFlags,
    YmapLodLevel,
    Ytyp,
    build_gta5_cache_y,
    read_gta5_cache_y,
)
from fivefury.gamefile import guess_game_file_type
from fivefury.ytyp import MloPortalDef


def _sample_cache() -> Gta5CacheY:
    return Gta5CacheY(
        file_dates=[
            Gta5CacheFileDate("platform:/levels/gta5/test.rpf", 133_700_000_000_000_000)
        ],
        map_data=[
            Gta5CacheMapData(
                name_hash="test_map",
                content_flags=int(YmapContentFlags.ENTITIES_HD),
                streaming_min=(-100.0, -100.0, -10.0),
                streaming_max=(100.0, 100.0, 50.0),
                physics_min=(-20.0, -30.0, 0.0),
                physics_max=(20.0, 30.0, 10.0),
                contains_block_info=True,
            )
        ],
        interior_proxies=[
            Gta5CacheInteriorProxy(
                group_id=2,
                floor_id=1,
                exit_portal_count=1,
                archetype_hash="test_mlo",
                ymap_hash="test_map",
                position=(10.0, 20.0, 30.0),
                bounds_min=(5.0, 15.0, 25.0),
                bounds_max=(15.0, 25.0, 35.0),
            )
        ],
        bounds=[
            Gta5CacheBound(
                "test_collision",
                (-20.0, -30.0, -2.0),
                (20.0, 30.0, 12.0),
                Gta5CacheBoundAssetType.MOVER,
            )
        ],
    )


def test_binary_roundtrip_preserves_all_runtime_tables() -> None:
    original = _sample_cache()
    data = original.to_bytes()
    rebuilt = read_gta5_cache_y(data)

    assert data[:13] == b"[VERSION]\n46\n"
    assert data[13:100] == bytes(87)
    assert rebuilt.to_bytes() == data
    assert int(rebuilt.map_data[0].name_hash) == int(original.map_data[0].name_hash)
    assert rebuilt.interior_proxies[0].position == pytest.approx((10.0, 20.0, 30.0))
    assert rebuilt.bounds[0].asset_type is Gta5CacheBoundAssetType.MOVER


def test_builder_derives_map_mlo_and_bound_entries() -> None:
    parent = Ymap(
        name="parent_map",
        flags=YmapFlags.NONE,
        content_flags=YmapContentFlags.ENTITIES_HD,
        streaming_extents_min=(-50.0, -50.0, -10.0),
        streaming_extents_max=(50.0, 50.0, 30.0),
        entities_extents_min=(-10.0, -10.0, 0.0),
        entities_extents_max=(10.0, 10.0, 20.0),
    )
    child = Ymap(
        name="child_map",
        parent="parent_map",
        flags=YmapFlags.SCRIPTED,
        content_flags=YmapContentFlags.MLO,
        streaming_extents_min=(90.0, 190.0, 0.0),
        streaming_extents_max=(130.0, 230.0, 50.0),
        entities_extents_min=(95.0, 195.0, 5.0),
        entities_extents_max=(125.0, 225.0, 45.0),
        entities=[
            MloInstanceDef(
                archetype_name="test_mlo",
                position=(100.0, 200.0, 10.0),
                group_id=3,
                floor_id=2,
            )
        ],
    )
    archetype = MloArchetypeDef(
        name="test_mlo",
        bb_min=(-5.0, -10.0, 0.0),
        bb_max=(5.0, 10.0, 20.0),
        portals=[MloPortalDef(room_from=0, room_to=1)],
    )
    collision = BoundBox.from_bounds((-15.0, -20.0, -2.0), (15.0, 20.0, 22.0))

    cache = build_gta5_cache_y(
        [parent, child],
        ytyps=Ytyp(name="test_types", archetypes=[archetype]),
        ybns={"test_collision": collision},
    )

    assert cache.map_data[0].is_parent
    assert not cache.map_data[1].dynamic_streaming
    assert cache.interior_proxies[0].exit_portal_count == 1
    assert cache.interior_proxies[0].bounds_min == pytest.approx((95.0, 195.0, 5.0))
    assert cache.interior_proxies[0].bounds_max == pytest.approx((125.0, 225.0, 45.0))
    assert cache.bounds[0].minimum == (-15.0, -20.0, -2.0)
    assert read_gta5_cache_y(cache.to_bytes()).to_bytes() == cache.to_bytes()


def test_builder_expands_distant_lod_streaming_bounds_to_world_physics() -> None:
    distant = Ymap(
        name="distant_lights",
        content_flags=YmapContentFlags.DISTANT_LOD_LIGHTS,
        streaming_extents_min=(-10.0, -10.0, -10.0),
        streaming_extents_max=(10.0, 10.0, 10.0),
        entities_extents_min=(-5.0, -5.0, -5.0),
        entities_extents_max=(5.0, 5.0, 5.0),
    )
    world = Ymap(
        name="world",
        streaming_extents_min=(-100.0, -200.0, -30.0),
        streaming_extents_max=(300.0, 400.0, 50.0),
        entities_extents_min=(-80.0, -150.0, -20.0),
        entities_extents_max=(250.0, 350.0, 40.0),
    )

    entry = build_gta5_cache_y([distant, world]).map_data[0]

    assert entry.streaming_min == (-80.0, -150.0, -20.0)
    assert entry.streaming_max == (250.0, 350.0, 40.0)


def test_ymap_runtime_flags_are_not_inferred_from_lod_content() -> None:
    parent = Ymap(flags=YmapFlags.MANUAL_STREAM_ONLY | YmapFlags.IS_PARENT)
    parent.recalculate_flags()
    lod_map = Ymap(entities=[EntityDef(lod_level=YmapLodLevel.DEPTH_LOD)])
    lod_map.recalculate_flags()

    assert parent.flags == YmapFlags.MANUAL_STREAM_ONLY | YmapFlags.IS_PARENT
    assert lod_map.flags is YmapFlags.NONE


def test_reader_rejects_misaligned_module_payload() -> None:
    data = bytearray(_sample_cache().to_bytes())
    module_name = b"fwMapDataStore\n"
    size_offset = data.index(module_name) + len(module_name)
    struct.pack_into("<I", data, size_offset, 63)

    with pytest.raises(ValueError, match="not divisible by 64"):
        read_gta5_cache_y(data)


def test_dlc_cache_requires_archive_dates() -> None:
    cache = Gta5CacheY(mode=Gta5CacheMode.DLC)
    with pytest.raises(ValueError, match="RPF file date"):
        cache.to_bytes()


def test_dlc_cache_enforces_the_runtime_buffer_limit() -> None:
    cache = Gta5CacheY(
        mode=Gta5CacheMode.DLC,
        file_dates=[
            Gta5CacheFileDate("dlcpacks:/test/test.rpf", 133_700_000_000_000_000)
        ],
        bounds=[
            Gta5CacheBound(index + 1, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
            for index in range(8200)
        ],
    )

    with pytest.raises(ValueError, match="262144-byte runtime limit"):
        cache.to_bytes()


def test_file_date_uses_windows_filetime(tmp_path) -> None:
    archive = tmp_path / "test.rpf"
    archive.write_bytes(b"RPF7")
    entry = Gta5CacheFileDate.from_file("dlcpacks:/test/test.rpf", archive)

    assert int(entry.name_hash) != 0
    assert entry.timestamp > 116_444_736_000_000_000


def test_game_file_cache_detects_and_decodes_gta5_cache(tmp_path) -> None:
    path = tmp_path / "gta5_cache_y.dat"
    path.write_bytes(_sample_cache().to_bytes())

    assert guess_game_file_type(path) is GameFileType.GTA5_CACHE
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan()
    game_file = cache.get_file(path.name)

    assert game_file is not None
    assert game_file.kind is GameFileType.GTA5_CACHE
    assert isinstance(game_file.parsed, Gta5CacheY)
    assert len(cache.Gta5CacheDict) == 1
