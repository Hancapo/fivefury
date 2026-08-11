from __future__ import annotations

from fivefury import GameFileCache, GameFileType, jenk_hash


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
