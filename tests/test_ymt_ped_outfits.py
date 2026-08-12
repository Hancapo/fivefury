from __future__ import annotations

import os
from pathlib import Path

import pytest

from fivefury import (
    CutsceneResolutionCancelled,
    GameFileCache,
    GameFileType,
    PedPropAnchor,
    Ymt,
    YmtContentType,
    coerce_ped_prop_anchor,
    iter_ped_props,
    ped_prop_file_stem,
)
from fivefury.gamefile import GameFile


def _ped_variation(prop_info: dict) -> Ymt:
    return Ymt(
        content={"propInfo": prop_info},
        content_type=YmtContentType.PED_VARIATION,
    )


def test_iter_ped_props_enumerates_every_anchor_drawable_and_texture_count() -> None:
    ymt = _ped_variation(
        {
            "numAvailProps": 4,
            "aAnchors": [
                {"anchor": 0, "props": [1, 3, 2]},
                {"anchor": 6, "props": [4]},
            ],
        }
    )

    props = list(iter_ped_props(ymt))

    assert [(item.anchor, item.drawable_index, item.texture_count) for item in props] == [
        (PedPropAnchor.HEAD, 0, 1),
        (PedPropAnchor.HEAD, 1, 3),
        (PedPropAnchor.HEAD, 2, 2),
        (PedPropAnchor.LEFT_WRIST, 0, 4),
    ]
    assert [item.slot for item in props] == [12, 12, 12, 18]
    assert [item.file_stem for item in props] == [
        "p_head_000",
        "p_head_001",
        "p_head_002",
        "p_lwrist_000",
    ]


def test_iter_ped_props_accepts_unresolved_meta_field_hashes() -> None:
    ymt = Ymt(
        content={
            "0x8590CDD8": {
                "0x09AD30FA": [
                    {"0x7019CA89": 10, "0x8856F65A": [2, 1]},
                ]
            }
        },
        content_type=YmtContentType.PED_VARIATION,
    )

    props = list(iter_ped_props(ymt))

    assert [item.anchor for item in props] == [
        PedPropAnchor.RIGHT_FOOT,
        PedPropAnchor.RIGHT_FOOT,
    ]
    assert [item.texture_count for item in props] == [2, 1]


def test_ped_prop_anchor_coercion_and_all_runtime_stems() -> None:
    assert coerce_ped_prop_anchor("p_eyes") is PedPropAnchor.EYES
    assert coerce_ped_prop_anchor("left_wrist") is PedPropAnchor.LEFT_WRIST
    assert ped_prop_file_stem(PedPropAnchor.PHYSICS_RIGHT_HAND, 7) == "ph_rhand_007"
    assert len({ped_prop_file_stem(anchor, 0) for anchor in PedPropAnchor}) == 13


def _outfit_ymt(*, texture_count: int = 2) -> Ymt:
    return Ymt(
        content={
            "availComp": [0, *([0xFF] * 11)],
            "aComponentData3": [
                {
                    "aDrawblData3": [
                        {
                            "aTexData": [{} for _ in range(texture_count)],
                            "propMask": 0,
                            "numAlternatives": 1,
                            "clothData": {"ownsCloth": True},
                        }
                    ]
                }
            ],
            "propInfo": {
                "numAvailProps": 1,
                "aAnchors": [{"anchor": 0, "props": [texture_count]}],
            },
        },
        content_type=YmtContentType.PED_VARIATION,
    )


def _outfit_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    paths = (
        "player_one.ymt",
        "update/x64/dlcpacks/test/dlc.rpf/player_one.ymt",
        "mods/player_one.ymt",
        "player_one/head_000_u.ydd",
        "player_one/head_diff_000_a_uni.ytd",
        "player_one/head_diff_000_b_uni.ytd",
        "mods/player_one_patch/head_000_u.ydd",
        "mods/player_one_patch/head_diff_000_a_uni.ytd",
        "mods/player_one_patch/head_diff_000_b_uni.ytd",
        "mods/player_one_patch/lowr_000_u.ydd",
        "player_one_p/p_head_000.ydd",
        "player_one_p/p_head_diff_000_a.ytd",
        "player_one_p/p_head_diff_000_b.ytd",
        "mods/player_one_p/p_head_000.ydd",
        "mods/player_one_p/p_head_diff_000_a.ytd",
        "mods/player_one_p/p_head_diff_000_b.ytd",
    )
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan()
    loaded: list[str] = []

    def load_asset(_cache, query):
        asset = query if hasattr(query, "path") else _cache.get_asset(query)
        assert asset is not None
        loaded.append(asset.path)
        parsed = _outfit_ymt() if asset.kind is GameFileType.YMT else object()
        return GameFile(path=asset.path, kind=asset.kind, parsed=parsed, loaded=True)

    monkeypatch.setattr(GameFileCache, "load_asset", load_asset)
    return cache, loaded


def test_ped_outfit_catalog_is_complete_lazy_cached_and_source_ranked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, loaded = _outfit_cache(tmp_path, monkeypatch)

    catalog = cache.resolve_ped_outfit_catalog("player_one")

    assert catalog.variation_asset is not None
    assert catalog.variation_asset.path == "mods/player_one.ymt"
    assert set(catalog.slots) == {0, 12}
    assert catalog.slots[0][0].file_stem == "head_000_u"
    assert catalog.slots[0][0].owns_cloth
    assert catalog.slots[12][0].file_stem == "p_head_000"
    assert [asset.name for asset in catalog.slots[12][0].texture_assets] == [
        "p_head_diff_000_a.ytd",
        "p_head_diff_000_b.ytd",
    ]
    assert loaded == ["mods/player_one.ymt"]
    assert cache.resolve_ped_outfit_catalog("player_one") is catalog
    with pytest.raises(TypeError):
        catalog.slots[1] = ()
    cache.close()


def test_ped_outfit_variant_loads_only_the_selected_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, loaded = _outfit_cache(tmp_path, monkeypatch)
    catalog = cache.resolve_ped_outfit_catalog("player_one")

    resolved = cache.resolve_ped_outfit_variant(catalog, 0, 0, 1)

    assert [file.path for file in resolved.drawable_files] == [
        "mods/player_one_patch/head_000_u.ydd"
    ]
    assert [file.path for file in resolved.texture_files] == [
        "mods/player_one_patch/head_diff_000_b_uni.ytd"
    ]
    assert "mods/player_one_patch/lowr_000_u.ydd" not in loaded
    assert loaded == [
        "mods/player_one.ymt",
        "mods/player_one_patch/head_000_u.ydd",
        "mods/player_one_patch/head_diff_000_b_uni.ytd",
    ]
    assert not resolved.issues
    cache.close()


def test_ped_outfit_catalog_supports_same_name_dictionaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("compact_ped.ymt", "compact_ped.ydd", "compact_ped.ytd"):
        (tmp_path / name).write_bytes(b"fixture")
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan()
    loaded = []

    def load_asset(_cache, asset):
        loaded.append(asset.path)
        parsed = _outfit_ymt(texture_count=1) if asset.kind is GameFileType.YMT else object()
        return GameFile(path=asset.path, kind=asset.kind, parsed=parsed, loaded=True)

    monkeypatch.setattr(GameFileCache, "load_asset", load_asset)

    catalog = cache.resolve_ped_outfit_catalog("compact_ped")
    option = catalog.slots[0][0]

    assert option.drawable_asset is not None
    assert option.drawable_asset.name == "compact_ped.ydd"
    assert [asset.name for asset in option.texture_assets] == ["compact_ped.ytd"]
    assert loaded == ["compact_ped.ymt"]
    cache.close()


def test_ped_outfit_selection_reports_invalid_indices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, _loaded = _outfit_cache(tmp_path, monkeypatch)
    catalog = cache.resolve_ped_outfit_catalog("player_one")

    bad_slot = cache.resolve_ped_outfit_variant(catalog, 25, 0)
    bad_drawable = cache.resolve_ped_outfit_variant(catalog, 0, 4)
    bad_texture = cache.resolve_ped_outfit_variant(catalog, 0, 0, 2)

    assert [issue.code for issue in bad_slot.issues] == ["outfit.slot_invalid"]
    assert [issue.code for issue in bad_drawable.issues] == [
        "outfit.drawable_invalid"
    ]
    assert [issue.code for issue in bad_texture.issues] == ["outfit.texture_invalid"]
    cache.close()


def test_ped_outfit_catalog_accepts_asset_file_and_hash_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, _loaded = _outfit_cache(tmp_path, monkeypatch)
    asset = cache.get_asset("mods/player_one.ymt", kind=GameFileType.YMT)
    assert asset is not None
    game_file = GameFile(
        path=asset.path,
        kind=GameFileType.YMT,
        parsed=_outfit_ymt(),
        loaded=True,
    )

    from_asset = cache.resolve_ped_outfit_catalog(asset)
    from_file = cache.resolve_ped_outfit_catalog(game_file)
    from_hash = cache.resolve_ped_outfit_catalog(asset.short_hash)

    assert from_asset is from_file
    assert from_file is from_hash
    cache.close()


def test_ped_outfit_resolution_honors_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, _loaded = _outfit_cache(tmp_path, monkeypatch)

    class CancelDuringEnumeration:
        checks = 0

        def check(self) -> None:
            self.checks += 1
            if self.checks == 3:
                raise CutsceneResolutionCancelled

    with pytest.raises(CutsceneResolutionCancelled):
        cache.resolve_ped_outfit_catalog(
            "player_one",
            cancellation=CancelDuringEnumeration(),
        )

    catalog = cache.resolve_ped_outfit_catalog("player_one")
    cancelled = CancelDuringEnumeration()
    cancelled.checks = 2
    with pytest.raises(CutsceneResolutionCancelled):
        cache.resolve_ped_outfit_variant(
            catalog,
            0,
            0,
            cancellation=cancelled,
        )
    cache.close()


def test_ped_outfit_catalog_reports_missing_variation_metadata(tmp_path: Path) -> None:
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan()

    catalog = cache.resolve_ped_outfit_catalog("missing_ped")

    assert not catalog.slots
    assert [issue.code for issue in catalog.issues] == [
        "outfit.variation_unresolved"
    ]
    cache.close()


def test_ped_outfit_catalog_reports_malformed_variation_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "broken_ped.ymt").write_bytes(b"broken")
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan()

    def load_asset(_cache, asset):
        return GameFile(
            path=asset.path,
            kind=asset.kind,
            parsed=b"not a YMT",
            loaded=True,
        )

    monkeypatch.setattr(GameFileCache, "load_asset", load_asset)

    catalog = cache.resolve_ped_outfit_catalog("broken_ped")

    assert not catalog.slots
    assert [issue.code for issue in catalog.issues] == ["outfit.variation_invalid"]
    cache.close()


@pytest.mark.skipif(
    not os.environ.get("FIVEFURY_GTA5_ENHANCED_PATH"),
    reason="set FIVEFURY_GTA5_ENHANCED_PATH to run the retail ped outfit audit",
)
def test_retail_protagonist_catalog_exceeds_prologue_cut_dependencies() -> None:
    root = Path(os.environ["FIVEFURY_GTA5_ENHANCED_PATH"])
    with GameFileCache(root, use_index_cache=True) as cache:
        cache.scan_game(gen9=True)
        bundle = cache.resolve_cutscene("pro_mcs_1.cut")
        binding = next(
            item
            for item in bundle.bindings.values()
            if any(asset.stem == "player_zero" for asset in item.assets.values())
        )
        reachable_paths = tuple(asset.path for asset in binding.component_assets)
        catalog = cache.resolve_ped_outfit_catalog(binding)
        player_one = cache.resolve_ped_outfit_catalog("player_one")
        selected = cache.resolve_ped_outfit_variant(player_one, 3, 0, 0)

    option_count = sum(len(options) for options in catalog.slots.values())
    reachable_count = len(binding.component_assets)
    assert option_count == 204
    assert option_count > reachable_count
    assert tuple(asset.path for asset in binding.component_assets) == reachable_paths
    assert not catalog.issues
    assert sum(len(options) for options in player_one.slots.values()) == 181
    assert not player_one.issues
    assert not selected.issues
    assert len(selected.drawable_files) == 1
    assert len(selected.texture_files) == 1
    assert "/player_one/" in selected.drawable_files[0].path.replace("\\", "/")
    assert "/player_one/" in selected.texture_files[0].path.replace("\\", "/")
