from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from fivefury import (
    CutBinding,
    CutScene,
    CutsceneResolutionCancellation,
    CutsceneResolutionCancelled,
    CutTimelineEvent,
    GameFileCache,
    GameTarget,
    MetaHash,
    ResolvedCutBinding,
    YmtPedInitData,
    YmtPedMetadata,
)
from fivefury.cut.asset_kinds import CUT_MODEL_KINDS_BY_ROLE
from fivefury.cut.resolution.bindings import (
    _ped_component_variations,
    _resolve_binding_texture_chains,
)
from fivefury.cut.resolution.expressions import _resolve_ped_expression_resources
from fivefury.gamefile import GameFile, GameFileType


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
    edition, game_path = request.param
    enhanced = edition == "enhanced"
    with GameFileCache(
        game_path,
        game=GameTarget.GTA5_ENHANCED if enhanced else GameTarget.GTA5,
        use_index_cache=True,
    ) as cache:
        cache.scan()
        yield cache


def test_ped_variation_dependencies_include_props_without_default_equipment() -> None:
    scene = CutScene.create(duration=2.0)
    scene.timeline_event(
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
    scene.timeline_event(
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


def _synthetic_texture_cache(tmp_path: Path) -> GameFileCache:
    for name in (
        "model.ydr",
        "model.ytd",
        "shared_props.ytd",
        "common_parent.ytd",
    ):
        (tmp_path / name).write_bytes(b"")
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan()
    model = cache.get_asset("model", kind=GameFileType.YDR)
    assert model is not None
    cache._archetype_view = {
        model.short_hash: SimpleNamespace(
            name=MetaHash("model"),
            asset_name=MetaHash("model"),
            texture_dictionary=MetaHash("shared_props"),
        )
    }
    cache._texture_parent_view = {
        int(MetaHash("shared_props")): int(MetaHash("common_parent"))
    }
    return cache


def _resolved_prop(cache: GameFileCache, *, direct: bool) -> ResolvedCutBinding:
    model = cache.get_asset("model", kind=GameFileType.YDR)
    assert model is not None
    assets = {GameFileType.YDR: model}
    if direct:
        texture = cache.get_asset("model", kind=GameFileType.YTD)
        assert texture is not None
        assets[GameFileType.YTD] = texture
    return ResolvedCutBinding(
        binding=CutBinding.new(
            object_id=7,
            type_name="cCutscenePropObject",
            role="prop",
            name="model",
        ),
        assets=assets,
    )


def test_cut_binding_texture_resolution_merges_archetype_and_direct_chains(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _synthetic_texture_cache(tmp_path)
    monkeypatch.setattr(
        GameFileCache,
        "load_asset",
        lambda _cache, asset: GameFile(
            path=asset.path,
            kind=asset.kind,
            parsed=object(),
            loaded=True,
        ),
    )
    resolved = _resolved_prop(cache, direct=True)
    issues = []

    _resolve_binding_texture_chains(cache, {7: resolved}, issues)

    assert [asset.stem for asset in resolved.texture_assets] == [
        "shared_props",
        "common_parent",
        "model",
    ]
    assert len(resolved.texture_files) == 3
    assert not issues

    overlap = _resolved_prop(cache, direct=False)
    shared = cache.get_asset("shared_props", kind=GameFileType.YTD)
    assert shared is not None
    overlap.assets[GameFileType.YTD] = shared
    _resolve_binding_texture_chains(cache, {7: overlap}, [])
    assert [asset.stem for asset in overlap.texture_assets] == [
        "shared_props",
        "common_parent",
    ]
    cache.close()


def test_cut_binding_texture_resolution_keeps_same_name_fallback(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _synthetic_texture_cache(tmp_path)
    cache._archetype_view = {}
    monkeypatch.setattr(
        GameFileCache,
        "load_asset",
        lambda _cache, asset: GameFile(path=asset.path, kind=asset.kind, loaded=True),
    )
    resolved = _resolved_prop(cache, direct=True)

    _resolve_binding_texture_chains(cache, {7: resolved}, [])

    assert [asset.stem for asset in resolved.texture_assets] == ["model"]
    cache.close()


def test_cut_binding_texture_resolution_reports_missing_declared_dictionary(
    tmp_path,
) -> None:
    (tmp_path / "model.ydr").write_bytes(b"")
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan()
    model = cache.get_asset("model", kind=GameFileType.YDR)
    assert model is not None
    cache._archetype_view = {
        model.short_hash: SimpleNamespace(
            name=MetaHash("model"),
            asset_name=MetaHash("model"),
            texture_dictionary=MetaHash("missing_shared"),
        )
    }
    resolved = _resolved_prop(cache, direct=False)
    issues = []

    _resolve_binding_texture_chains(cache, {7: resolved}, issues)

    issue = next(
        item for item in issues if item.code == "binding.texture_dictionary_unresolved"
    )
    assert issue.object_id == 7
    assert issue.asset_path == model.path
    assert "missing_shared" in issue.message
    cache.close()


def test_cut_binding_texture_resolution_honors_cancellation(tmp_path) -> None:
    cache = _synthetic_texture_cache(tmp_path)
    resolved = _resolved_prop(cache, direct=True)

    class CancelDuringTraversal:
        checks = 0

        def check(self) -> None:
            self.checks += 1
            if self.checks >= 4:
                raise CutsceneResolutionCancelled

    with pytest.raises(CutsceneResolutionCancelled):
        _resolve_binding_texture_chains(
            cache,
            {7: resolved},
            [],
            cancellation=CancelDuringTraversal(),
        )
    cache.close()


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
    assert vehicle.vehicle_appearance is not None
    assert all(
        item.vehicle_appearance is None
        for item in bundle.bindings.values()
        if item.binding.role != "vehicle"
    )
    assert vehicle.texture_files
    assert any(asset.stem.lower() == "vehshare" for asset in vehicle.texture_assets)
    phone = next(
        item
        for item in bundle.bindings.values()
        if any(asset.stem.lower() == "prop_npc_phone" for asset in item.assets.values())
    )
    door = next(
        item
        for item in bundle.bindings.values()
        if any(
            asset.stem.lower() == "v_ilev_ss_door7"
            for asset in item.assets.values()
        )
    )
    assert any(
        asset.stem.lower() == "prop_npc_phone1" for asset in phone.texture_assets
    )
    assert any(asset.stem.lower() == "v_ilev_sweatdrs" for asset in door.texture_assets)
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


def test_resolve_cutscene_uses_shared_ped_expression_sets(
    game_cache: GameFileCache,
) -> None:
    bundle = game_cache.resolve_cutscene("pro_mcs_1.cut")
    host_hash = MetaHash("a_m_m_prolhost_01").uint
    hosts = [
        binding
        for binding in bundle.bindings.values()
        if binding.reference_hash == host_hash
    ]

    assert len(hosts) == 2
    assert all(binding.expression_file is not None for binding in hosts)
    assert all(binding.expression_file.path.endswith("/ambient.yed") for binding in hosts)
    assert all(binding.resolved_expression_set is not None for binding in hosts)
    assert all(
        "facial" in binding.resolved_expression_set.selected_expression_names
        for binding in hosts
    )
    assert not any(
        issue.code == "binding.yed_unresolved" and issue.object_id in {4, 9}
        for issue in bundle.issues
    )


@pytest.mark.parametrize(
    ("cut_name", "expected_dictionaries"),
    [
        (
            "abigail_mcs_1_concat.cut",
            {"p_m_zero", "csb_abigail"},
        ),
        (
            "pro_mcs_3_pt1.cut",
            {"p_m_two", "p_m_zero", "csb_prolsec"},
        ),
    ],
)
def test_resolve_cutscene_preserves_direct_ped_expression_dictionaries(
    game_cache: GameFileCache,
    cut_name: str,
    expected_dictionaries: set[str],
) -> None:
    bundle = game_cache.resolve_cutscene(cut_name)
    direct_peds = [
        binding
        for binding in bundle.bindings.values()
        if binding.binding.role == "ped" and binding.expression_file is not None
    ]

    assert {binding.expression_file.stem for binding in direct_peds} == (
        expected_dictionaries
    )
    assert all(binding.resolved_expression_set is None for binding in direct_peds)
    assert not any(
        issue.code == "binding.yed_unresolved" for issue in bundle.issues
    )


def test_resolve_cutscene_rejects_non_cut_assets(game_cache: GameFileCache) -> None:
    with pytest.raises(FileNotFoundError):
        game_cache.resolve_cutscene("oracle.yft")


def test_ped_expression_dictionary_follows_the_exact_ymt_init_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_hash = MetaHash("test_ped").uint
    expression_hash = MetaHash("test_expression").uint
    init_data = YmtPedInitData(
        name=MetaHash(model_hash),
        expression_dictionary_name=MetaHash(expression_hash),
    )
    ymt_asset = SimpleNamespace(path="x64/data/peds.ymt")
    ymt_file = SimpleNamespace(
        parsed=SimpleNamespace(
            ped_metadata=YmtPedMetadata(init_datas=[init_data])
        )
    )
    yed_asset = SimpleNamespace(path="test_expression.yed")
    yed_file = SimpleNamespace(parsed=object())
    binding = SimpleNamespace(
        role="ped", display_name="test_ped", object_id=4
    )
    resolved = ResolvedCutBinding(
        binding=binding,
        reference_hash=model_hash,
    )

    class Cache:
        @staticmethod
        def find_assets(query, *, kind):
            assert query == "peds.ymt"
            assert kind is GameFileType.YMT
            return [ymt_asset]

    monkeypatch.setattr(
        "fivefury.cut.resolution.expressions._preferred_asset",
        lambda _cache, value, kind: (
            yed_asset
            if value == expression_hash and kind is GameFileType.YED
            else None
        ),
    )
    monkeypatch.setattr(
        "fivefury.cut.resolution.expressions._load_file",
        lambda _cache, asset, _issues, **_kwargs: (
            ymt_file if asset is ymt_asset else yed_file if asset is yed_asset else None
        ),
    )

    issues = []
    _resolve_ped_expression_resources(Cache(), {4: resolved}, issues)

    assert resolved.ped_init_data is init_data
    assert resolved.ped_init_data_asset is ymt_asset
    assert resolved.assets[GameFileType.YED] is yed_asset
    assert resolved.expression_file is yed_file
    assert not issues


def _resolved_ped(name: str, *, object_id: int = 4) -> ResolvedCutBinding:
    model_hash = MetaHash(name).uint
    return ResolvedCutBinding(
        binding=SimpleNamespace(
            role="ped",
            display_name=name,
            object_id=object_id,
        ),
        reference_hash=model_hash,
    )


def _ped_metadata_file(*items: YmtPedInitData):
    return SimpleNamespace(
        parsed=SimpleNamespace(
            ped_metadata=YmtPedMetadata(init_datas=list(items)),
        )
    )


def test_ped_yed_is_not_guessed_from_the_model_hash() -> None:
    assert GameFileType.YED not in CUT_MODEL_KINDS_BY_ROLE["ped"]


def test_ped_expression_resolution_uses_highest_source_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _resolved_ped("test_ped")
    base_expression = MetaHash("base_expression").uint
    mod_expression = MetaHash("mod_expression").uint
    base_asset = SimpleNamespace(path="x64/data/peds.ymt")
    mod_asset = SimpleNamespace(path="mods/update/data/peds.ymt")
    base_file = _ped_metadata_file(
        YmtPedInitData(
            name=MetaHash(resolved.reference_hash),
            expression_dictionary_name=MetaHash(base_expression),
        )
    )
    mod_init = YmtPedInitData(
        name=MetaHash(resolved.reference_hash),
        expression_dictionary_name=MetaHash(mod_expression),
    )
    mod_file = _ped_metadata_file(mod_init)
    yed_asset = SimpleNamespace(path="mods/update/data/mod_expression.yed")
    yed_file = SimpleNamespace(parsed=object())
    requested_hashes = []

    class Cache:
        @staticmethod
        def find_assets(query, *, kind):
            assert (query, kind) == ("peds.ymt", GameFileType.YMT)
            return [base_asset, mod_asset]

    def preferred(_cache, value, kind):
        assert kind is GameFileType.YED
        requested_hashes.append(value)
        return yed_asset

    monkeypatch.setattr(
        "fivefury.cut.resolution.expressions._preferred_asset",
        preferred,
    )
    monkeypatch.setattr(
        "fivefury.cut.resolution.expressions._load_file",
        lambda _cache, asset, _issues, **_kwargs: {
            id(base_asset): base_file,
            id(mod_asset): mod_file,
            id(yed_asset): yed_file,
        }[id(asset)],
    )

    issues = []
    _resolve_ped_expression_resources(Cache(), {4: resolved}, issues)

    assert resolved.ped_init_data is mod_init
    assert resolved.ped_metadata_asset is mod_asset
    assert requested_hashes == [mod_expression]
    assert not issues


def test_ped_expression_resolution_rejects_same_tier_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _resolved_ped("test_ped")
    first_asset = SimpleNamespace(path="mods/a/peds.ymt")
    second_asset = SimpleNamespace(path="mods/b/peds.ymt")
    first_init = YmtPedInitData(name=MetaHash(resolved.reference_hash))
    second_init = YmtPedInitData(name=MetaHash(resolved.reference_hash))

    class Cache:
        @staticmethod
        def find_assets(_query, *, kind):
            assert kind is GameFileType.YMT
            return [first_asset, second_asset]

    monkeypatch.setattr(
        "fivefury.cut.resolution.expressions._load_file",
        lambda _cache, asset, _issues, **_kwargs: (
            _ped_metadata_file(first_init)
            if asset is first_asset
            else _ped_metadata_file(second_init)
        ),
    )

    issues = []
    _resolve_ped_expression_resources(Cache(), {4: resolved}, issues)

    assert resolved.ped_init_data_candidates == (first_init, second_init)
    assert resolved.ped_init_data is None
    assert resolved.ped_metadata_asset is None
    assert [issue.code for issue in issues] == ["binding.ymt_init_unresolved"]


def test_ped_expression_resolution_reports_missing_init_and_yed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_init = _resolved_ped("missing_init", object_id=1)
    missing_yed = _resolved_ped("missing_yed", object_id=2)
    expression_hash = MetaHash("not_installed").uint
    metadata_asset = SimpleNamespace(path="x64/data/peds.ymt")
    metadata_file = _ped_metadata_file(
        YmtPedInitData(
            name=MetaHash(missing_yed.reference_hash),
            expression_dictionary_name=MetaHash(expression_hash),
        )
    )

    class Cache:
        @staticmethod
        def find_assets(_query, *, kind):
            assert kind is GameFileType.YMT
            return [metadata_asset]

    monkeypatch.setattr(
        "fivefury.cut.resolution.expressions._load_file",
        lambda *_args, **_kwargs: metadata_file,
    )
    monkeypatch.setattr(
        "fivefury.cut.resolution.expressions._preferred_asset",
        lambda _cache, value, kind: (
            None
            if value == expression_hash and kind is GameFileType.YED
            else pytest.fail("unexpected dependency lookup")
        ),
    )

    issues = []
    _resolve_ped_expression_resources(
        Cache(),
        {1: missing_init, 2: missing_yed},
        issues,
    )

    assert [issue.code for issue in issues] == [
        "binding.ymt_init_unresolved",
        "binding.yed_unresolved",
    ]


def test_ped_expression_resolution_honors_cancellation_before_and_during_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _resolved_ped("test_ped")
    first_asset = SimpleNamespace(path="mods/a/peds.ymt")
    second_asset = SimpleNamespace(path="mods/b/peds.ymt")
    cancellation = CutsceneResolutionCancellation()

    class Cache:
        @staticmethod
        def find_assets(_query, *, kind):
            assert kind is GameFileType.YMT
            return [first_asset, second_asset]

    cancellation.cancel()
    with pytest.raises(CutsceneResolutionCancelled):
        _resolve_ped_expression_resources(
            Cache(),
            {4: resolved},
            [],
            cancellation=cancellation,
        )

    cancellation = CutsceneResolutionCancellation()

    def cancel_after_first(_cache, asset, _issues, **_kwargs):
        assert asset is first_asset
        cancellation.cancel()
        return _ped_metadata_file()

    monkeypatch.setattr(
        "fivefury.cut.resolution.expressions._load_file",
        cancel_after_first,
    )
    with pytest.raises(CutsceneResolutionCancelled):
        _resolve_ped_expression_resources(
            Cache(),
            {4: resolved},
            [],
            cancellation=cancellation,
        )

    assert resolved.ped_init_data is None
    assert resolved.expression_file is None
