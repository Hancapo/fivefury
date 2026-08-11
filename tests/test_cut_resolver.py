from __future__ import annotations

import os
from pathlib import Path

import pytest

from fivefury import CutScene, CutTimelineEvent, GameFileCache
from fivefury.cut.resolution.bindings import _ped_component_variations
from fivefury.gamefile import GameFileType


def _configured_game_paths() -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for edition, variable in (
        ("legacy", "FIVEFURY_GTA5_LEGACY_PATH"),
        ("enhanced", "FIVEFURY_GTA5_ENHANCED_PATH"),
    ):
        value = os.environ.get(variable)
        if value and Path(value).is_dir():
            result.append((edition, Path(value)))
    return result


@pytest.fixture(
    scope="module",
    params=_configured_game_paths(),
    ids=lambda item: item[0],
)
def game_cache(request: pytest.FixtureRequest):
    _edition, game_path = request.param
    with GameFileCache(game_path, use_index_cache=True) as cache:
        cache.scan()
        yield cache


def test_ped_variation_dependencies_include_props_without_default_equipment() -> None:
    scene = CutScene.create(duration=2.0)
    scene.add_event(
        CutTimelineEvent(
            start=0.0,
            kind="set_variation",
            track="ped",
            event_name="set_variation",
            target_id=7,
            payload={
                "iObjectId": 7,
                "iComponent": 13,
                "iDrawable": 2,
                "iTexture": 1,
            },
        )
    )
    scene.add_event(
        CutTimelineEvent(
            start=1.0,
            kind="set_variation",
            track="ped",
            event_name="set_variation",
            target_id=7,
            payload={
                "iObjectId": 7,
                "iComponent": 12,
                "iDrawable": -1,
                "iTexture": 0,
            },
        )
    )

    variations = _ped_component_variations(scene, 7, {3: (31, 2), 13: (-1, 0)})

    assert variations[0] == {(0, 0)}
    assert variations[3] == {(0, 0), (31, 2)}
    assert variations[13] == {(2, 1)}
    assert 12 not in variations


def test_resolve_cutscene_loads_only_direct_cut_dependencies(
    game_cache: GameFileCache,
) -> None:
    asset = game_cache.get_asset("ah_1_int.cut", kind=GameFileType.CUT)
    assert asset is not None

    bundle = game_cache.resolve_cutscene(asset)

    assert bundle.source.path.endswith("/ah_1_int.cut")
    assert len(bundle.ycd_by_section) == 9
    assert len(bundle.scene.camera_cut_list or ()) == 8
    assert any(
        item.binding.role == "ped" and item.model is not None
        for item in bundle.bindings.values()
    )
    assert any(
        item.binding.role == "ped" and item.component_files
        for item in bundle.bindings.values()
    )
    assert any(
        item.binding.role == "ped" and item.component_texture_files
        for item in bundle.bindings.values()
    )
    assert any(
        item.binding.role == "ped"
        and any(asset.stem.lower() == "p_eyes_000" for asset in item.component_assets)
        for item in bundle.bindings.values()
    )
    assert any(
        item.binding.role == "vehicle" and item.model is not None
        for item in bundle.bindings.values()
    )
    vehicle = next(
        item for item in bundle.bindings.values() if item.binding.role == "vehicle"
    )
    assert vehicle.texture_files
    assert any(asset.stem.lower() == "vehshare" for asset in vehicle.texture_assets)
    assert bundle.audio_references
    assert bundle.audio
    assert all(item.asset.kind is GameFileType.AWC for item in bundle.audio.values())
    assert all(
        asset.kind not in {GameFileType.YMAP, GameFileType.YTYP}
        for item in bundle.bindings.values()
        for asset in item.assets.values()
    )


def test_resolve_cutscene_uses_mod_precedence(game_cache: GameFileCache) -> None:
    candidates = game_cache.find_assets("cutconv_intro.cut", kind=GameFileType.CUT)
    if not candidates:
        pytest.skip("cutconv_intro mod is not installed")

    bundle = game_cache.resolve_cutscene("cutconv_intro.cut")

    if any(asset.path.startswith("mods/") for asset in candidates):
        assert bundle.source.path.startswith("mods/")
    else:
        assert bundle.source.path in {asset.path for asset in candidates}


def test_resolve_cutscene_resolves_reachable_american_subtitles(
    game_cache: GameFileCache,
) -> None:
    asset = game_cache.get_asset("pro_mcs_1.cut", kind=GameFileType.CUT)
    assert asset is not None

    bundle = game_cache.resolve_cutscene(asset, subtitle_language="american")
    dictionary = bundle.subtitle_dictionary("PROAU")

    assert dictionary is not None
    assert dictionary.assets
    assert all("/american" in item.path.lower() for item in dictionary.assets)
    assert dictionary.assets[0].stem.lower() == "proaud"
    assert bundle.resolve_subtitle(0xD2B55F45) == "~z~Hands behind your back."


def test_resolve_cutscene_accepts_script_registered_ped_snapshot(
    game_cache: GameFileCache,
) -> None:
    bundle = game_cache.resolve_cutscene(
        "pro_mcs_1.cut",
        initial_ped_variations={
            "Michael": {3: (31, 0), 4: (26, 0)},
            "Trevor": {3: (9, 0), 13: (4, 0)},
        },
    )

    assert bundle.initial_ped_variations[3][3] == (31, 0)
    assert bundle.initial_ped_variations[3][4] == (26, 0)
    assert bundle.initial_ped_variations[10][3] == (9, 0)
    assert bundle.initial_ped_variations[10][13] == (4, 0)
    assert any(
        issue.code == "binding.initial_variation_applied" and issue.object_id == 3
        for issue in bundle.issues
    )


def test_resolve_cutscene_rejects_non_cut_assets(game_cache: GameFileCache) -> None:
    with pytest.raises(FileNotFoundError):
        game_cache.resolve_cutscene("oracle.yft")
