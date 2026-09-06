from __future__ import annotations

from itertools import pairwise
from pathlib import Path

from fivefury import (
    CutsceneIndexPreparationStatus,
    CutsceneResolutionIndex,
    GameFileCache,
    GameTarget,
)
from fivefury.cache.rel_sound_index import (
    load_rel_sound_index,
    rel_sound_index_path,
    save_rel_sound_index,
)
from fivefury.cache.vehicle_appearance_index import vehicle_appearance_index_path
from fivefury.rel import RelSoundIndex, RelSoundRecord


def _write_vehicle_metadata(root: Path) -> None:
    data = root / "common" / "data"
    data.mkdir(parents=True)
    data.joinpath("carcols.meta").write_text(
        "<CVehicleModelInfoVarGlobal><Colors><Item>"
        '<color value="4278256131"/><metallicID value="7"/>'
        "<colorName>TEST_COLOR</colorName>"
        "</Item></Colors></CVehicleModelInfoVarGlobal>",
        encoding="utf-8",
    )
    data.joinpath("carvariations.meta").write_text(
        "<CVehicleModelInfoVariation><variationData><Item>"
        "<modelName>testcar</modelName><colors><Item>"
        '<indices content="char_array">0 0 0 0 0 0</indices>'
        "<liveries><Item value=\"true\"/></liveries>"
        "</Item></colors><kits><Item>0_default_modkit</Item></kits>"
        "</Item></variationData></CVehicleModelInfoVariation>",
        encoding="utf-8",
    )


def _status(result, index: CutsceneResolutionIndex) -> CutsceneIndexPreparationStatus:
    return next(item.status for item in result.indexes if item.index is index)


def test_vehicle_appearance_sidecar_avoids_clean_process_metadata_parse(
    tmp_path,
) -> None:
    root = tmp_path / "game"
    index_path = tmp_path / "index.ffindex"
    _write_vehicle_metadata(root)

    with GameFileCache(root, index_cache_path=index_path) as cache:
        cache.scan(load_keys=False)
        progress = []
        first = cache.prepare_cutscene_resolution(progress=progress.append)
        expected = cache.resolve_vehicle_appearance("testcar")

    with GameFileCache(root, index_cache_path=index_path) as cache:
        cache.scan(load_keys=False)
        second = cache.prepare_cutscene_resolution()
        actual = cache.resolve_vehicle_appearance("testcar")

    assert _status(first, CutsceneResolutionIndex.VEHICLE_APPEARANCES) is (
        CutsceneIndexPreparationStatus.REBUILT
    )
    assert _status(second, CutsceneResolutionIndex.VEHICLE_APPEARANCES) is (
        CutsceneIndexPreparationStatus.LOADED
    )
    assert actual == expected
    assert vehicle_appearance_index_path(index_path).is_file()
    vehicle_progress = [
        item
        for item in progress
        if item.index is CutsceneResolutionIndex.VEHICLE_APPEARANCES
        and item.asset is not None
    ]
    assert {Path(item.asset).name for item in vehicle_progress} == {
        "carcols.meta",
        "carvariations.meta",
    }
    assert all(
        left.completed <= right.completed for left, right in pairwise(progress)
    )


def test_rel_sound_sidecar_roundtrips_graph_without_rel_objects(tmp_path) -> None:
    index_path = tmp_path / "index.ffindex"
    index_path.write_bytes(b"main-index")
    expected = RelSoundIndex.from_records(
        [
            RelSoundRecord(1, (2,), (), ()),
            RelSoundRecord(2, (), (3,), (4,)),
        ]
    )

    save_rel_sound_index(index_path, expected, ("warning",))
    loaded = load_rel_sound_index(index_path)

    assert loaded is not None
    actual, errors = loaded
    assert actual.resolve(1) == expected.resolve(1)
    assert not actual.sounds
    assert errors == ("warning",)


def test_sidecar_digest_rejects_a_changed_main_index(tmp_path) -> None:
    index_path = tmp_path / "index.ffindex"
    index_path.write_bytes(b"first-index")
    sound_index = RelSoundIndex.from_records([RelSoundRecord(1, (), (), ())])
    save_rel_sound_index(index_path, sound_index)
    sidecar = rel_sound_index_path(index_path)
    assert sidecar.is_file()

    index_path.write_bytes(b"second-index")

    assert load_rel_sound_index(index_path) is None


def test_index_cache_identity_distinguishes_game_targets(tmp_path) -> None:
    root = tmp_path / "game"
    root.mkdir()

    legacy = GameFileCache(root, game=GameTarget.GTA5)
    enhanced = GameFileCache(root, game=GameTarget.GTA5_ENHANCED)

    assert legacy.get_index_cache_path() != enhanced.get_index_cache_path()
