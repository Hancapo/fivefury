from __future__ import annotations

import pytest

from fivefury import (
    CutsceneResolutionCancellation,
    CutsceneResolutionCancelled,
    CutsceneResolutionIndex,
    GameFileCache,
)
from fivefury._native import extract_ytyp_texture_relationships
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
from fivefury.hashing import jenk_hash
from fivefury.ytyp import Ytyp


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


def test_asset_texture_preparation_uses_selective_meta_index(tmp_path) -> None:
    root = tmp_path / "game"
    root.mkdir()
    ytyp = Ytyp(name="test_types")
    ytyp.archetype(
        "test_prop",
        asset_name="test_drawable",
        texture_dictionary="test_textures",
    )
    ytyp.time_archetype(
        "timed_prop",
        texture_dictionary="timed_textures",
    )
    ytyp.mlo_archetype(
        "test_mlo",
        texture_dictionary="mlo_textures",
    )
    root.joinpath("test_types.ytyp").write_bytes(ytyp.to_bytes(validate=False))
    cache = GameFileCache(root, use_index_cache=False)
    cache.scan(load_keys=False)

    cache.prepare_cutscene_resolution()

    assert cache.archetype_dict.texture_dictionaries_for_asset_hashes(
        {jenk_hash("test_prop")}
    ) == (
        jenk_hash("test_textures"),
    )
    assert cache.archetype_dict.texture_dictionaries_for_asset_hashes(
        {jenk_hash("test_drawable")}
    ) == (
        jenk_hash("test_textures"),
    )
    assert cache._archetype_view is not None
    assert cache._archetype_view._generation == -1


def test_selective_ytyp_meta_extractor_rejects_truncated_payload() -> None:
    with pytest.raises(ValueError, match="truncated"):
        extract_ytyp_texture_relationships(b"META")


def test_asset_texture_preparation_cancels_without_partial_sidecar(tmp_path) -> None:
    root = tmp_path / "game"
    root.mkdir()
    for index in range(2):
        ytyp = Ytyp(name=f"types_{index}")
        ytyp.archetype(f"prop_{index}", texture_dictionary=f"textures_{index}")
        root.joinpath(f"types_{index}.ytyp").write_bytes(ytyp.to_bytes())
    index_path = tmp_path / "game.ffindex"
    cache = GameFileCache(root, index_cache_path=index_path)
    cache.scan(load_keys=False)
    cancellation = CutsceneResolutionCancellation()

    def cancel_after_first_asset(progress) -> None:
        if (
            progress.index is CutsceneResolutionIndex.ASSET_TEXTURES
            and progress.asset is not None
        ):
            cancellation.cancel()

    with pytest.raises(CutsceneResolutionCancelled):
        cache.prepare_cutscene_resolution(
            cancellation=cancellation,
            progress=cancel_after_first_asset,
        )

    assert not asset_texture_index_path(index_path).exists()
