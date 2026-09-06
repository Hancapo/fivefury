from __future__ import annotations

import copy
import inspect
from collections.abc import Callable

import pytest

import fivefury
from fivefury import (
    Awc,
    BoundBox,
    BuildContext,
    CutScene,
    CutsceneAssets,
    DlcContentXml,
    DlcFolderMetadata,
    DlcList,
    DlcPack,
    DlcPatch,
    DlcSetupData,
    Gta5CacheY,
    HeightMap,
    HeightMapBounds,
    PackFileMetaData,
    ValidationError,
    ValidationReport,
    Vector3,
    WaterData,
    Ybn,
    Ycd,
    Ydr,
    Yed,
    Yft,
    Ymap,
    Ynd,
    Ynv,
    Ytd,
    Ytyp,
    validate_yft_bytes,
)
from fivefury.resource import ResourceHeader

AssetFactory = Callable[[], object]


def _bound() -> BoundBox:
    return BoundBox.from_bounds(Vector3(), Vector3(1.0, 1.0, 1.0))


def _heightmap() -> HeightMap:
    return HeightMap(
        columns=1,
        rows=1,
        bounds=HeightMapBounds(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        minimum_cells=[0],
        maximum_cells=[0],
    )


ROOT_ASSETS: tuple[tuple[str, AssetFactory], ...] = (
    ("awc", Awc),
    ("bound", _bound),
    ("ybn", lambda: Ybn(43, _bound())),
    ("cut", CutScene),
    ("cut-assets", lambda: CutsceneAssets(CutScene())),
    ("dlc-pack", lambda: DlcPack("test")),
    ("dlc-patch", lambda: DlcPatch("test")),
    (
        "dlc-folder",
        lambda: DlcFolderMetadata(
            DlcSetupData("dlc_test:/", "0x00000001"),
            DlcContentXml(),
            DlcList(),
        ),
    ),
    ("cache", Gta5CacheY),
    ("heightmap", _heightmap),
    ("water", WaterData),
    ("ycd", lambda: Ycd(ResourceHeader(46, 0, 0), [], [])),
    ("ydr", lambda: Ydr(165)),
    ("yed", Yed),
    ("yft", Yft),
    ("ymap", Ymap),
    ("ymf", PackFileMetaData),
    ("ynd", Ynd),
    ("ynv", Ynv),
    ("ytd", Ytd),
    ("ytyp", Ytyp),
)


@pytest.mark.parametrize(("name", "factory"), ROOT_ASSETS, ids=lambda value: value if isinstance(value, str) else None)
def test_root_assets_follow_the_validation_contract(
    name: str,
    factory: AssetFactory,
) -> None:
    del name
    asset = factory()
    context = BuildContext(strict=False)

    direct = asset.validate(context=context)
    through_context = context.validate(asset)

    assert isinstance(direct, ValidationReport)
    assert isinstance(through_context, ValidationReport)
    for issue in through_context:
        assert issue.code
        assert issue.message
    if through_context.valid:
        through_context.raise_for_errors()
    else:
        with pytest.raises(ValidationError) as raised:
            through_context.raise_for_errors()
        assert raised.value.report is through_context


@pytest.mark.parametrize(
    "factory",
    (
        lambda: Ycd(ResourceHeader(46, 0, 0), [], []),
        lambda: Ydr(165),
        Yed,
        Yft,
        Ymap,
        Ytyp,
        CutScene,
        lambda: DlcPack("test"),
        Ynd,
        Ynv,
    ),
)
def test_validation_does_not_mutate_authoritative_asset_state(
    factory: AssetFactory,
) -> None:
    asset = factory()
    snapshot = copy.deepcopy(asset)

    BuildContext(strict=False).validate(asset)

    assert asset == snapshot


def test_warning_only_reports_do_not_block_authoring() -> None:
    report = BuildContext(strict=False).validate(Awc())

    assert report.warnings
    assert not report.errors
    report.raise_for_errors()


def test_nested_validation_failures_include_field_paths() -> None:
    report = Ynv().validate()

    assert any(issue.path == "sector_tree" for issue in report.errors)


def test_binary_validation_uses_the_shared_report_contract() -> None:
    report = validate_yft_bytes(b"")

    assert isinstance(report, ValidationReport)
    assert report.errors
    assert all(issue.code and issue.message for issue in report.errors)


def test_public_validation_api_has_no_legacy_issue_types_or_raise_switches() -> None:
    legacy_names = {
        "CutSceneValidationError",
        "CutSceneValidationIssue",
        "DlcValidationError",
        "DlcValidationIssue",
        "HeightMapValidationError",
        "WaterValidationError",
        "YdrValidationIssue",
        "YedValidationIssue",
        "YftValidationIssue",
        "YftValidationSeverity",
    }
    assert not legacy_names.intersection(fivefury.__all__)

    for name in fivefury.__all__:
        if name.startswith("validate_"):
            assert "raise_on_error" not in inspect.signature(getattr(fivefury, name)).parameters
