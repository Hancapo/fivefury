from __future__ import annotations

from pathlib import Path

from fivefury import GameFileCache, GameFileType, RpfArchive, jenk_hash


def _cache_with_assets() -> GameFileCache:
    cache = GameFileCache()
    cache._register_asset(
        path="x64/models/hero.ydr",
        kind=GameFileType.YDR,
        size=10,
        uncompressed_size=20,
    )
    cache._register_asset(
        path="update/models/hero.yft",
        kind=GameFileType.YFT,
        size=30,
        uncompressed_size=40,
    )
    cache._register_asset(
        path="audio/intro.awc",
        kind=GameFileType.AWC,
        size=50,
        uncompressed_size=60,
    )
    return cache


def test_asset_kind_uses_the_type_stored_by_the_index() -> None:
    cache = GameFileCache()
    asset_id = cache._register_asset(
        path="models/misleading.ydr",
        kind=GameFileType.YFT,
        size=1,
        uncompressed_size=1,
    )

    assert cache.records[asset_id].kind is GameFileType.YFT


def test_batch_hash_lookup_filters_in_the_native_index() -> None:
    cache = _cache_with_assets()
    hero_hash = jenk_hash("hero")
    intro_hash = jenk_hash("intro")

    all_groups = cache.find_hashes([hero_hash, intro_hash])
    ydr_groups = cache.find_hashes([hero_hash, intro_hash], kind=GameFileType.YDR)

    assert [asset.kind for asset in all_groups[hero_hash]] == [
        GameFileType.YDR,
        GameFileType.YFT,
    ]
    assert [asset.path for asset in ydr_groups[hero_hash]] == [
        "x64/models/hero.ydr"
    ]
    assert ydr_groups[intro_hash] == []


def test_batch_name_lookup_preserves_each_requested_name() -> None:
    cache = _cache_with_assets()

    result = cache.find_names(
        ["hero.ydr", "hero.yft", "missing.ydr"],
    )

    assert [asset.path for asset in result["hero.ydr"]] == [
        "x64/models/hero.ydr"
    ]
    assert [asset.path for asset in result["hero.yft"]] == [
        "update/models/hero.yft"
    ]
    assert result["missing.ydr"] == []
    assert [asset.path for asset in cache.find_name("hero.ydr")] == [
        "x64/models/hero.ydr"
    ]


def test_container_and_typed_stem_prefix_indexes_avoid_global_search() -> None:
    cache = GameFileCache()
    cache._register_asset(
        path="packs/player_zero/player_zero_variants/uppr_000_u.ydd",
        kind=GameFileType.YDD,
        size=1,
        uncompressed_size=1,
    )
    cache._register_asset(
        path="packs/player_one/player_one_variants/uppr_000_u.ydd",
        kind=GameFileType.YDD,
        size=1,
        uncompressed_size=1,
    )
    cache._register_asset(
        path="data/lang/proaud.gxt2",
        kind=GameFileType.GXT2,
        size=1,
        uncompressed_size=1,
    )

    assert [
        asset.path
        for asset in cache.find_container_assets(
            "player_zero", kind=GameFileType.YDD, include_prefixed=True
        )
    ] == ["packs/player_zero/player_zero_variants/uppr_000_u.ydd"]
    assert [asset.path for asset in cache.find_stem_prefix("proau", kind="gxt2")] == [
        "data/lang/proaud.gxt2"
    ]


def test_native_archive_scan_classifies_named_metadata(tmp_path: Path) -> None:
    archive = RpfArchive.empty("metadata.rpf")
    archive.file("data/vehicles.meta", b"<CVehicleModelInfo__InitDataList />")
    archive.file("data/peds.meta", b"<CPedModelInfo__InitDataList />")
    archive.file("data/gtxd.meta", b"<CMapParentTxds />")
    archive.save(tmp_path / "metadata.rpf")

    with GameFileCache(tmp_path, use_index_cache=False) as cache:
        cache.scan(load_keys=False)

        assert cache.get_asset("vehicles.meta").kind is GameFileType.VEHICLES
        assert cache.get_asset("peds.meta").kind is GameFileType.PEDS
        assert cache.get_asset("gtxd.meta").kind is GameFileType.GTXD


def test_default_loaded_file_cache_holds_large_dependency_sets() -> None:
    cache = GameFileCache()

    assert cache.max_loaded_files >= 256


def test_payload_cache_reuses_reads_and_evicts_by_byte_budget(tmp_path: Path) -> None:
    (tmp_path / "first.bin").write_bytes(b"first")
    (tmp_path / "second.bin").write_bytes(b"second")
    cache = GameFileCache(
        tmp_path,
        use_index_cache=False,
        max_cached_payload_bytes=6,
    )
    cache.scan(load_keys=False)

    first = cache.read_bytes("first.bin")
    assert cache.read_bytes("first.bin") is first
    assert cache.read_bytes("second.bin") == b"second"
    assert list(cache._payload_cache) == [(cache.get_asset("second.bin").id, True)]

    cache.clear_runtime_cache()
    assert cache._payload_cache_bytes == 0
    assert not cache._payload_cache
