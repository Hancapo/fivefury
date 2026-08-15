from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from fivefury import CutBinding, GameFileCache, GameTarget, ResolvedCutBinding
from fivefury.cut.resolution.bindings import _resolve_binding_texture_chains
from fivefury.cut.resolution.vehicles import _resolve_vehicle_high_detail_models
from fivefury.gamefile import GameFile, GameFileType
from fivefury.metahash import MetaHash


def _cache(tmp_path: Path, *paths: str) -> GameFileCache:
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)
    return cache


def _configured_retail_game_paths() -> list[tuple[str, Path, GameTarget]]:
    result = []
    for edition, variable, game in (
        ("legacy", "FIVEFURY_GTA5_LEGACY_PATH", GameTarget.GTA5),
        ("enhanced", "FIVEFURY_GTA5_ENHANCED_PATH", GameTarget.GTA5_ENHANCED),
    ):
        value = os.environ.get(variable)
        if value and Path(value).is_dir():
            result.append((edition, Path(value), game))
    return result


_RETAIL_GAME_PATHS = _configured_retail_game_paths()


def _binding(
    cache: GameFileCache,
    stem: str,
    *,
    object_id: int,
    role: str = "vehicle",
) -> ResolvedCutBinding:
    asset = cache.get_asset(stem, kind=GameFileType.YFT)
    assert asset is not None
    base_file = GameFile(
        path=asset.path,
        kind=GameFileType.YFT,
        parsed=f"{stem}:base",
        loaded=True,
    )
    return ResolvedCutBinding(
        binding=CutBinding.new(
            object_id=object_id,
            type_name="rage__cutfVehicleModelObject",
            role=role,
            name=stem,
        ),
        assets={GameFileType.YFT: asset},
        files={GameFileType.YFT: base_file},
    )


def test_vehicle_high_detail_selects_companion_once_for_repeated_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _cache(tmp_path, "rancherxl.yft", "rancherxl_hi.yft")
    first = _binding(cache, "rancherxl", object_id=10)
    second = _binding(cache, "rancherxl", object_id=27)
    loads: list[str] = []

    def load_asset(_cache: GameFileCache, asset) -> GameFile:
        loads.append(asset.path)
        return GameFile(
            path=asset.path,
            kind=asset.kind,
            parsed="rancherxl:high",
            loaded=True,
        )

    monkeypatch.setattr(GameFileCache, "load_asset", load_asset)
    issues = []

    _resolve_vehicle_high_detail_models(
        cache,
        {10: first, 27: second},
        issues,
    )

    assert loads == [first.high_detail_model_asset.path]
    assert first.high_detail_model_asset is second.high_detail_model_asset
    assert first.high_detail_model_file is second.high_detail_model_file
    assert first.model_file is first.high_detail_model_file
    assert first.model == "rancherxl:high"
    assert first.files[GameFileType.YFT].parsed == "rancherxl:base"
    assert not issues


def test_vehicle_high_detail_absence_and_non_vehicle_roles_keep_base_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _cache(tmp_path, "rancherxl.yft", "stage.yft", "stage_hi.yft")
    vehicle = _binding(cache, "rancherxl", object_id=10)
    prop = _binding(cache, "stage", object_id=11, role="prop")
    queries: list[str] = []
    original_find_assets = GameFileCache.find_assets

    def find_assets(_cache: GameFileCache, query, **kwargs):
        queries.append(str(query))
        return original_find_assets(_cache, query, **kwargs)

    monkeypatch.setattr(GameFileCache, "find_assets", find_assets)
    issues = []

    _resolve_vehicle_high_detail_models(
        cache,
        {10: vehicle, 11: prop},
        issues,
    )

    assert queries == ["rancherxl_hi"]
    assert vehicle.model == "rancherxl:base"
    assert prop.model == "stage:base"
    assert vehicle.high_detail_model_asset is None
    assert prop.high_detail_model_asset is None
    assert not issues


def test_vehicle_high_detail_uses_normal_asset_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _cache(
        tmp_path,
        "policeold2.yft",
        "policeold2_hi.yft",
        "mods/policeold2_hi.yft",
    )
    resolved = _binding(cache, "policeold2", object_id=27)

    monkeypatch.setattr(
        GameFileCache,
        "load_asset",
        lambda _cache, asset: GameFile(
            path=asset.path,
            kind=asset.kind,
            parsed=asset.path,
            loaded=True,
        ),
    )

    _resolve_vehicle_high_detail_models(cache, {27: resolved}, [])

    assert resolved.high_detail_model_asset is not None
    assert resolved.high_detail_model_asset.path == "mods/policeold2_hi.yft"
    assert resolved.model == "mods/policeold2_hi.yft"


def test_vehicle_high_detail_invalid_companion_warns_and_keeps_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _cache(tmp_path, "rancherxl.yft", "rancherxl_hi.yft")
    resolved = _binding(cache, "rancherxl", object_id=10)

    def fail_load(_cache: GameFileCache, asset) -> GameFile:
        raise ValueError(f"invalid resource: {asset.path}")

    monkeypatch.setattr(GameFileCache, "load_asset", fail_load)
    issues = []

    _resolve_vehicle_high_detail_models(cache, {10: resolved}, issues)

    assert resolved.model == "rancherxl:base"
    assert resolved.high_detail_model_asset is None
    assert resolved.high_detail_model_file is None
    assert len(issues) == 1
    assert issues[0].code == "binding.vehicle_high_detail_invalid"
    assert issues[0].object_id == 10
    assert issues[0].asset_path.endswith("rancherxl_hi.yft")


def test_vehicle_high_detail_and_base_models_are_texture_resolution_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _cache(
        tmp_path,
        "rancherxl.yft",
        "rancherxl_hi.yft",
        "rancherxl_base.ytd",
        "rancherxl_high.ytd",
    )
    resolved = _binding(cache, "rancherxl", object_id=10)
    base_asset = resolved.assets[GameFileType.YFT]
    high_asset = cache.get_asset("rancherxl_hi", kind=GameFileType.YFT)
    assert high_asset is not None
    cache._archetype_view = {
        base_asset.short_hash: SimpleNamespace(
            name=MetaHash("rancherxl"),
            asset_name=MetaHash("rancherxl"),
            texture_dictionary=MetaHash("rancherxl_base"),
        ),
        high_asset.short_hash: SimpleNamespace(
            name=MetaHash("rancherxl_hi"),
            asset_name=MetaHash("rancherxl_hi"),
            texture_dictionary=MetaHash("rancherxl_high"),
        ),
    }

    monkeypatch.setattr(
        GameFileCache,
        "load_asset",
        lambda _cache, asset: GameFile(
            path=asset.path,
            kind=asset.kind,
            parsed=asset.stem,
            loaded=True,
        ),
    )
    issues = []

    _resolve_vehicle_high_detail_models(cache, {10: resolved}, issues)
    _resolve_binding_texture_chains(cache, {10: resolved}, issues)

    assert [asset.stem for asset in resolved.texture_assets] == [
        "rancherxl_high",
        "rancherxl_base",
    ]
    assert not issues


@pytest.mark.parametrize(
    ("_edition", "game_path", "game"),
    _RETAIL_GAME_PATHS,
    ids=[entry[0] for entry in _RETAIL_GAME_PATHS],
)
def test_retail_pro_mcs_5_resolves_vehicle_high_detail_models(
    _edition: str,
    game_path: Path,
    game: GameTarget,
) -> None:
    with GameFileCache(
        game_path,
        game=game,
        load_audio=False,
        load_peds=False,
        load_vehicles=True,
        use_index_cache=True,
    ) as cache:
        cache.scan()
        bundle = cache.resolve_cutscene("pro_mcs_5.cut")

    for object_id, base_stem in ((10, "rancherxl"), (27, "policeold2")):
        resolved = bundle.bindings[object_id]
        assert resolved.assets[GameFileType.YFT].stem.casefold() == base_stem
        assert resolved.high_detail_model_asset is not None
        assert resolved.high_detail_model_asset.stem.casefold() == f"{base_stem}_hi"
        assert resolved.high_detail_model_file is not None
        assert resolved.model_file is resolved.high_detail_model_file
    assert not {
        issue.object_id
        for issue in bundle.issues
        if issue.code == "binding.vehicle_high_detail_invalid"
    } & {10, 27}
