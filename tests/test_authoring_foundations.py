from __future__ import annotations

from dataclasses import dataclass

import pytest

from fivefury import (
    AssetRef,
    AssetSet,
    BuildContext,
    DiagnosticSeverity,
    GameTarget,
    ValidationError,
    ValidationReport,
)


@dataclass
class ExampleAsset:
    value: int


def test_asset_set_resolves_typed_references_by_path_or_name() -> None:
    assets = AssetSet()
    asset = ExampleAsset(7)
    assets["Stream/Example.YDR"] = asset

    assert AssetRef("example", ExampleAsset).require(assets) is asset
    assert (
        AssetRef("ignored", ExampleAsset, path="stream/example.ydr").require(assets)
        is asset
    )
    assert assets.require("example", ExampleAsset) is asset


def test_asset_set_rejects_ambiguous_names_and_accidental_replacement() -> None:
    assets = AssetSet()
    assets["a/example.ydr"] = ExampleAsset(1)
    assets["b/example.ydr"] = ExampleAsset(2)

    with pytest.raises(KeyError, match="Ambiguous"):
        assets.require("example", ExampleAsset)
    with pytest.raises(KeyError, match="already registered"):
        assets["a/example.ydr"] = ExampleAsset(3)


def test_asset_reference_enforces_its_runtime_type() -> None:
    assets = AssetSet()
    assets["example.ydr"] = object()

    with pytest.raises(TypeError, match="expected ExampleAsset"):
        AssetRef("example", ExampleAsset, path="example.ydr").require(assets)


def test_build_context_coerces_target_and_respects_strict_resolution() -> None:
    loose = BuildContext(game="enhanced", strict=False)
    strict = BuildContext(game=GameTarget.GTA5)

    assert loose.game is GameTarget.GTA5_ENHANCED
    assert loose.resolve(AssetRef("missing", ExampleAsset)) is None
    with pytest.raises(KeyError, match="Unresolved"):
        strict.resolve(AssetRef("missing", ExampleAsset))


def test_validation_report_preserves_structured_diagnostics() -> None:
    report = ValidationReport()
    report.issue("asset.warning", "Needs review", severity=DiagnosticSeverity.WARNING)
    report.issue(
        "asset.invalid", "Broken reference", asset="example.ydr", path="materials[0]"
    )

    assert not report.valid
    assert len(report.warnings) == 1
    assert len(report.errors) == 1
    with pytest.raises(ValidationError, match="asset.invalid") as raised:
        report.raise_for_errors()
    assert raised.value.report is report
