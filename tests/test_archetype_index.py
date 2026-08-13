from __future__ import annotations

from fivefury import GameFileCache
from fivefury.cache.archetype_index import (
    asset_texture_index_path,
    load_asset_texture_index,
    load_texture_parent_index,
    save_asset_texture_index,
    save_texture_parent_index,
    texture_parent_index_path,
)
from fivefury.cache.ped_index import (
    load_ped_init_index,
    ped_init_index_path,
    save_ped_init_index,
)


def test_asset_texture_index_roundtrip_and_source_validation(tmp_path) -> None:
    source = tmp_path / "game.ffindex"
    source.write_bytes(b"index-v1")
    values = {
        30: (300, 301),
        10: (100,),
        20: (200, 200),
    }

    destination = save_asset_texture_index(source, values)

    assert destination == asset_texture_index_path(source)
    assert load_asset_texture_index(source) == {
        10: (100,),
        20: (200,),
        30: (300, 301),
    }

    source.write_bytes(b"index-v2-with-a-different-size")
    assert load_asset_texture_index(source) is None


def test_texture_parent_index_roundtrip(tmp_path) -> None:
    source = tmp_path / "game.ffindex"
    source.write_bytes(b"index")

    destination = save_texture_parent_index(source, {10: 20, 30: 40})

    assert destination == texture_parent_index_path(source)
    assert load_texture_parent_index(source) == {10: 20, 30: 40}


def test_ped_init_index_roundtrip_and_source_validation(tmp_path) -> None:
    source = tmp_path / "game.ffindex"
    source.write_bytes(b"index-v1")

    destination = save_ped_init_index(source, {10: (3,), 20: (4, 5)})

    assert destination == ped_init_index_path(source)
    assert load_ped_init_index(source) == {10: (3,), 20: (4, 5)}

    source.write_bytes(b"index-v2")
    assert load_ped_init_index(source) is None


def test_clear_index_cache_removes_dependency_sidecars(tmp_path) -> None:
    source = tmp_path / "game.ffindex"
    source.write_bytes(b"index")
    save_asset_texture_index(source, {1: (2,)})
    save_ped_init_index(source, {1: (2,)})
    cache = GameFileCache(tmp_path, index_cache_path=source)

    cache.clear_index_cache()

    assert not source.exists()
    assert not asset_texture_index_path(source).exists()
    assert not texture_parent_index_path(source).exists()
    assert not ped_init_index_path(source).exists()
