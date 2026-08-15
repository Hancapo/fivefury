from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import CutBinding, GameFileCache, ResolvedCutBinding
from fivefury.cut.resolution.vehicles import _resolve_vehicle_high_detail_models
from fivefury.gamefile import GameFile, GameFileType


def _cache(tmp_path: Path, *paths: str) -> GameFileCache:
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)
    return cache


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
