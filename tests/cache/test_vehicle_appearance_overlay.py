from __future__ import annotations

import pytest

from fivefury import (
    AssetSourceTier,
    GameFileCache,
    GameFileOverlay,
    GameFileType,
    GameTarget,
)
from fivefury.cache.precedence import asset_source_rank


def metadata(root, *, color=0xFF010203, model="testcar"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "carcols.meta").write_text(
        "<CVehicleModelInfoVarGlobal><Colors><Item>"
        f'<color value="{color}"/><metallicID value="7"/>'
        "<colorName>TEST</colorName></Item></Colors></CVehicleModelInfoVarGlobal>",
        encoding="utf-8",
    )
    (root / "carvariations.meta").write_text(
        "<CVehicleModelInfoVariation><variationData><Item>"
        f"<modelName>{model}</modelName><colors><Item>"
        '<indices content="char_array">0 0 0 0 0 0</indices><liveries/>'
        "</Item></colors></Item></variationData></CVehicleModelInfoVariation>",
        encoding="utf-8",
    )


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize(
    "folder,tier",
    [
        ("", AssetSourceTier.BASE),
        ("update", AssetSourceTier.UPDATE),
        ("update/x64/dlcpacks/example", AssetSourceTier.DLC),
        ("mods/update/x64/dlcpacks/example", AssetSourceTier.MODS),
    ],
)
def test_fallback_priority_is_not_a_semantic_tier(tmp_path, game, folder, tier):
    root, loose = tmp_path / "game", tmp_path / "loose"
    metadata(root / folder)
    loose.mkdir()
    with GameFileCache(root, game=game, use_index_cache=False) as cache:
        cache.scan(load_keys=False)
        with GameFileOverlay(loose, fallback=cache) as overlay:
            record = next(overlay.iter_assets(GameFileType.CAR_VARIATIONS))
            assert asset_source_rank(record)[0] == 4 + int(tier)
            assert record.source_tier is tier
            appearance = overlay.resolve_vehicle_appearance("testcar")
            assert not appearance.diagnostics
            assert appearance.primary.srgb == (1, 2, 3, 255)
            assert appearance.variation.model_name == "testcar"
            assert all(source.tier is tier for source in appearance.sources)
        assert cache.resolve_vehicle_appearance("testcar").primary.srgb == (
            1,
            2,
            3,
            255,
        )


def test_overlay_wins_conflicts_without_erasing_fallback_variations(tmp_path):
    root, loose = tmp_path / "game", tmp_path / "loose"
    metadata(root)
    metadata(root / "update", color=0xFF040506)
    metadata(root / "update/x64/dlcpacks/example", color=0xFF070809)
    metadata(root / "mods", color=0xFF101112)
    metadata(root / "other", model="fallbackcar")
    metadata(loose, color=0xFF202122)
    with GameFileCache(root, use_index_cache=False) as cache:
        cache.scan(load_keys=False)
        original = cache.resolve_vehicle_appearance("testcar")
        assert original.primary.srgb == (16, 17, 18, 255)
        assert original.primary.source.tier is AssetSourceTier.MODS
        with GameFileOverlay(loose, fallback=cache) as overlay:
            result = overlay.resolve_vehicle_appearance("testcar")
            assert not result.diagnostics
            assert result.primary.srgb == (32, 33, 34, 255)
            assert all(
                source.tier is AssetSourceTier.OVERLAY for source in result.sources
            )
            fallback = overlay.resolve_vehicle_appearance("fallbackcar")
            assert fallback.variation.model_name == "fallbackcar"
            assert fallback.primary.source.tier is AssetSourceTier.OVERLAY
            assert any(
                source.tier is AssetSourceTier.BASE for source in fallback.sources
            )
        assert cache.resolve_vehicle_appearance("testcar") == original


def test_explicit_rank_does_not_change_record_provenance(tmp_path):
    metadata(tmp_path / "update")
    with GameFileCache(tmp_path, use_index_cache=False) as cache:
        cache.scan(load_keys=False)
        record = next(cache.iter_assets(GameFileType.CAR_COLS))
        for priority in (-20, 7, 100):
            record.source_priority = priority
            assert asset_source_rank(record)[0] == priority
            assert record.source_tier is AssetSourceTier.UPDATE


def test_overlay_rebuilds_appearance_after_fallback_rescan(tmp_path):
    root, loose = tmp_path / "game", tmp_path / "loose"
    metadata(root)
    loose.mkdir()
    with GameFileCache(root, use_index_cache=False) as cache:
        cache.scan(load_keys=False)
        with GameFileOverlay(loose, fallback=cache) as overlay:
            assert overlay.resolve_vehicle_appearance("testcar").primary.srgb == (
                1,
                2,
                3,
                255,
            )
            metadata(root, color=0xFF040506)
            cache.scan(load_keys=False)
            assert overlay.resolve_vehicle_appearance("testcar").primary.srgb == (
                4,
                5,
                6,
                255,
            )


def test_remount_and_reopen_refresh_colors_without_touching_installation(tmp_path):
    root, loose = tmp_path / "game", tmp_path / "loose"
    metadata(root)
    metadata(loose, color=0xFF040506)
    with GameFileCache(root, use_index_cache=False) as cache:
        cache.scan(load_keys=False)
        with GameFileOverlay(loose, fallback=cache) as overlay:
            assert overlay.resolve_vehicle_appearance("testcar").primary.srgb == (
                4,
                5,
                6,
                255,
            )
            metadata(loose, color=0xFF070809)
            overlay.remount(loose)
            appearance = overlay.resolve_vehicle_appearance("testcar")
            assert appearance.primary.srgb == (7, 8, 9, 255)
            assert appearance.primary.source.tier is AssetSourceTier.OVERLAY
        with pytest.raises(ValueError, match="closed"):
            overlay.resolve_vehicle_appearance("testcar")
        with GameFileOverlay(loose, fallback=cache) as reopened:
            assert reopened.resolve_vehicle_appearance("testcar") == appearance
        assert cache.resolve_vehicle_appearance("testcar").primary.srgb == (
            1,
            2,
            3,
            255,
        )
