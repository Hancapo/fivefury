from __future__ import annotations

import pytest

from fivefury import (
    AssetRegistration,
    CutsceneResolutionCancellation,
    CutsceneResolutionCancelled,
    DlcDataFileType,
    GameFileCache,
    GameFileOverlay,
    GameFileType,
    MetaHash,
)
from fivefury.cache.ped_index import ped_init_index_path
from fivefury.cut.resolution.expressions import _ped_init_data_by_model
from tests.cache.samples import ped_metadata_xml


def _cache(root, **kwargs):
    cache = GameFileCache(root, **kwargs)
    cache.scan(load_keys=False)
    return cache


def _record(overlay, name, issues=None, cancellation=None):
    key = int(MetaHash(name))
    matches = _ped_init_data_by_model(
        overlay, [] if issues is None else issues, cancellation, {key}
    )
    return matches[key][1][0][2] if key in matches else None


@pytest.mark.parametrize("model", ["actor", "new_actor"])
def test_primed_installation_does_not_hide_loose_metadata(tmp_path, model):
    game, loose = tmp_path / "game", tmp_path / "loose"
    game.mkdir()
    loose.mkdir()
    (game / "peds.meta").write_bytes(ped_metadata_xml("actor", "retail"))
    (loose / "custom.meta").write_bytes(ped_metadata_xml(model, "custom"))
    index = tmp_path / "installation.index"
    with _cache(game, index_cache_path=index) as fallback:
        assert _record(fallback, "actor").expression_dictionary_name == MetaHash(
            "retail"
        )
        source_index = fallback._ped_init_asset_index
        original_sidecar = ped_init_index_path(index).read_bytes()
        original_assets = [(item.id, item.path, item.kind) for item in fallback]
        with GameFileOverlay(
            loose,
            fallback=fallback,
            registrations=[
                AssetRegistration("custom.meta", DlcDataFileType.PED_METADATA)
            ],
        ) as overlay:
            assert _record(overlay, model).expression_dictionary_name == MetaHash(
                "custom"
            )
            if model != "actor":
                assert _record(overlay, "actor").expression_dictionary_name == MetaHash(
                    "retail"
                )
            assert len({asset.id for asset in overlay}) == overlay.asset_count
            for asset in overlay:
                assert overlay.records[asset.id].path == asset.path
                assert overlay.load_asset(asset).loaded
        assert fallback._ped_init_asset_index is source_index
        assert ped_init_index_path(index).read_bytes() == original_sidecar
        assert [(item.id, item.path, item.kind) for item in fallback] == original_assets
        assert _record(fallback, "actor").expression_dictionary_name == MetaHash(
            "retail"
        )


def test_remount_replaces_metadata_and_rejects_old_asset_records(tmp_path):
    path = tmp_path / "peds.meta"
    path.write_bytes(ped_metadata_xml(dictionary="before"))
    with GameFileOverlay(tmp_path) as overlay:
        assert _record(overlay, "actor").expression_dictionary_name == MetaHash(
            "before"
        )
        old_asset = overlay.find_path("peds.meta")
        old_catalog = overlay.resolve_ped_outfit_catalog("actor")
        path.write_bytes(ped_metadata_xml(dictionary="after"))
        overlay.remount(tmp_path)
        assert _record(overlay, "actor").expression_dictionary_name == MetaHash("after")
        assert overlay.resolve_ped_outfit_catalog("actor") is not old_catalog
        with pytest.raises(ValueError, match="different overlay"):
            overlay.load_asset(old_asset)
    with pytest.raises(ValueError, match="closed"):
        overlay.find_path("peds.meta")


def test_cancelled_and_failed_remount_leave_current_mount_usable(tmp_path, monkeypatch):
    (tmp_path / "peds.meta").write_bytes(ped_metadata_xml())
    with GameFileOverlay(tmp_path) as overlay:
        old = overlay.sources[0]
        cancellation = CutsceneResolutionCancellation()
        cancellation.cancel()
        with pytest.raises(CutsceneResolutionCancelled):
            overlay.remount(tmp_path, cancellation=cancellation)
        assert overlay.sources[0] is old
        with pytest.raises(FileNotFoundError):
            overlay.remount(
                tmp_path,
                registrations=[
                    AssetRegistration("absent.meta", DlcDataFileType.PED_METADATA)
                ],
            )
        assert overlay.sources[0] is old
        cancellation = CutsceneResolutionCancellation()
        scan = GameFileCache.scan

        def cancel_after_scan(self, *args, **kwargs):
            scan(self, *args, **kwargs)
            cancellation.cancel()

        monkeypatch.setattr(GameFileCache, "scan", cancel_after_scan)
        with pytest.raises(CutsceneResolutionCancelled):
            overlay.remount(tmp_path, cancellation=cancellation)
        assert overlay.sources[0] is old
        assert _record(overlay, "actor") is not None


def test_malformed_metadata_is_reported_without_poisoning_index(tmp_path):
    path = tmp_path / "peds.meta"
    path.write_bytes(b"<malformed")
    with GameFileOverlay(tmp_path) as overlay:
        issues = []
        assert _record(overlay, "actor", issues) is None
        assert any(issue.code == "asset.load_failed" for issue in issues)
        assert overlay.sources[0]._ped_init_asset_index is None
        path.write_bytes(ped_metadata_xml())
        overlay.remount(tmp_path)
        assert _record(overlay, "actor") is not None


def test_identical_records_agree_and_conflicts_remain_visible(tmp_path):
    for folder, dictionary in [("a", "one"), ("b", "one")]:
        directory = tmp_path / folder
        directory.mkdir()
        (directory / "peds.meta").write_bytes(ped_metadata_xml(dictionary=dictionary))
    with GameFileOverlay(tmp_path) as overlay:
        key = int(MetaHash("actor"))
        matches = _ped_init_data_by_model(overlay, [], None, {key})[key][1]
        assert len(matches) == 2
        assert matches[0][2] == matches[1][2]
        (tmp_path / "b" / "peds.meta").write_bytes(ped_metadata_xml(dictionary="two"))
        overlay.remount(tmp_path)
        matches = _ped_init_data_by_model(overlay, [], None, {key})[key][1]
        assert len(matches) == 2
        assert (
            matches[0][2].expression_dictionary_name
            != matches[1][2].expression_dictionary_name
        )


def test_queries_and_payloads_keep_layer_precedence_and_unique_ids(tmp_path):
    game, loose = tmp_path / "game", tmp_path / "loose"
    for root, payload in ((game, b"base"), (loose, b"override")):
        (root / "actor").mkdir(parents=True)
        (root / "actor" / "sample.bin").write_bytes(payload)
    with (
        _cache(game, use_index_cache=False) as fallback,
        GameFileOverlay(loose, fallback=fallback) as overlay,
    ):
        matches = overlay.find_assets("sample.bin")
        assert [overlay.read_bytes(asset) for asset in matches] == [
            b"override",
            b"base",
        ]
        assert len({asset.id for asset in matches}) == 2
        assert overlay.read_bytes("actor/sample.bin") == b"override"
        assert overlay.assets["actor/sample.bin"].id == matches[0].id
        assert len(overlay.find_container_assets("actor")) == 2
        assert len(overlay.find_names(["sample.bin"])["sample.bin"]) == 2
        assert (
            len(overlay.find_hashes([MetaHash("sample")])[int(MetaHash("sample"))]) == 2
        )


def test_overlay_never_rescans_installation_or_loads_world_assets(
    tmp_path, monkeypatch
):
    game, loose = tmp_path / "game", tmp_path / "loose"
    game.mkdir()
    loose.mkdir()
    (game / "peds.meta").write_bytes(ped_metadata_xml())
    (game / "unrelated.ymap").write_bytes(b"not requested")
    (game / "unrelated.ybn").write_bytes(b"not requested")
    with _cache(game, use_index_cache=False) as fallback:
        scan = GameFileCache.scan
        load = GameFileCache.get_file

        def checked_scan(self, *args, **kwargs):
            assert self is not fallback
            return scan(self, *args, **kwargs)

        def checked_load(self, query):
            asset = self._coerce_asset(query)
            assert asset is None or asset.kind not in (
                GameFileType.YMAP,
                GameFileType.YBN,
            )
            return load(self, query)

        monkeypatch.setattr(GameFileCache, "scan", checked_scan)
        monkeypatch.setattr(GameFileCache, "get_file", checked_load)
        with GameFileOverlay(loose, fallback=fallback) as overlay:
            overlay.prepare_cutscene_resolution()
            assert _record(overlay, "actor") is not None


def test_named_expression_registration_is_used_by_expression_set_resolver(tmp_path):
    from fivefury.cut.resolution.expressions import _expression_sets_by_hash

    (tmp_path / "sets.meta").write_text(
        '<fwExpressionSetManager><expressionSets><Item type="fwExpressionSet" key="custom">'
        "<dictionaryName>face</dictionaryName><expressions><Item>facial</Item></expressions>"
        "</Item></expressionSets></fwExpressionSetManager>",
        encoding="utf-8",
    )
    registration = AssetRegistration("sets.meta", DlcDataFileType.EXPRESSION_SETS)
    with GameFileOverlay(tmp_path, registrations=[registration]) as overlay:
        matches, available = _expression_sets_by_hash(overlay, [], None)
        assert available
        assert int(MetaHash("custom")) in matches
        assert matches[int(MetaHash("custom"))][0].path == "sets.meta"


def test_overlay_reads_borrowed_nested_archives_without_closing_them(tmp_path):
    from fivefury import RpfArchive

    game, loose = tmp_path / "game", tmp_path / "loose"
    game.mkdir()
    loose.mkdir()
    archive = RpfArchive.empty("data.rpf")
    _, nested = archive.nested_archive("nested.rpf")
    nested.file("payload.bin", b"borrowed")
    archive.save(game / "data.rpf")
    with _cache(game, use_index_cache=False) as fallback:
        with GameFileOverlay(loose, fallback=fallback) as overlay:
            asset = overlay.find_path("data.rpf/nested.rpf/payload.bin")
            assert overlay.read_bytes(asset) == b"borrowed"
            assert overlay.get_entry(asset).read() == b"borrowed"
        assert fallback.read_bytes("data.rpf/nested.rpf/payload.bin") == b"borrowed"
