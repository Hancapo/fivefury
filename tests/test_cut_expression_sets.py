from __future__ import annotations

from types import SimpleNamespace

import pytest

from fivefury import (
    GameFileType,
    MetaHash,
    ResolvedCutBinding,
    Yed,
    YedExpression,
    YmtPedInitData,
    YmtPedMetadata,
    read_ped_expression_sets,
)
from fivefury.cut.resolution.expressions import _resolve_ped_expression_resources


def _asset(path: str):
    return SimpleNamespace(path=path)


def _ped_file(init_data: YmtPedInitData):
    return SimpleNamespace(
        parsed=SimpleNamespace(
            ped_metadata=YmtPedMetadata(init_datas=[init_data]),
        )
    )


def _expression_set_file(
    *,
    name: str = "expr_set_test",
    dictionary: str = "ambient",
    expressions: tuple[str, ...] = ("facial", "male_body"),
):
    expression_items = "".join(f"<Item>{item}</Item>" for item in expressions)
    metadata = read_ped_expression_sets(
        f"""\
<fwExpressionSetManager>
  <expressionSets>
    <Item type="fwExpressionSet" key="{name}">
      <dictionaryName>{dictionary}</dictionaryName>
      <expressions>{expression_items}</expressions>
    </Item>
  </expressionSets>
</fwExpressionSetManager>
"""
    )
    return SimpleNamespace(parsed=metadata)


def _yed_file(*expressions: str):
    yed = Yed(path="ambient.yed")
    yed.expressions.extend(YedExpression.create(name) for name in expressions)
    return SimpleNamespace(parsed=yed)


def _resolved_ped(name: str = "test_ped") -> ResolvedCutBinding:
    return ResolvedCutBinding(
        binding=SimpleNamespace(
            role="ped",
            display_name=name,
            object_id=4,
        ),
        reference_hash=MetaHash(name).uint,
    )


class _Cache:
    def __init__(self, *, metadata_assets=(), files=None, yed_assets=None):
        self.metadata_assets = tuple(metadata_assets)
        self.files = dict(files or {})
        self.yed_assets = dict(yed_assets or {})

    def find_assets(self, query, *, kind):
        if (query, kind) == ("peds.ymt", GameFileType.YMT):
            return [
                asset
                for asset in self.metadata_assets
                if asset.path.lower().endswith("peds.ymt")
            ]
        if (query, kind) == (
            "expression_sets.xml",
            GameFileType.EXPRESSION_SETS,
        ):
            return [
                asset
                for asset in self.metadata_assets
                if asset.path.lower().endswith("expression_sets.xml")
            ]
        raise AssertionError((query, kind))

    def find_hash(self, value, *, kind):
        assert kind is GameFileType.YED
        asset = self.yed_assets.get(int(value))
        return [asset] if asset is not None else []

    def load_asset(self, asset):
        return self.files.get(id(asset))


def _set_init_data(resolved: ResolvedCutBinding) -> YmtPedInitData:
    return YmtPedInitData(
        name=MetaHash(resolved.reference_hash),
        expression_set_name=MetaHash("expr_set_test"),
        expression_dictionary_name=MetaHash("null"),
        expression_name=MetaHash("null"),
    )


def test_cut_binding_resolves_expression_set_dictionary_and_ordered_programs() -> None:
    resolved = _resolved_ped()
    peds_asset = _asset("x64/data/peds.ymt")
    sets_asset = _asset("common.rpf/data/anim/expression_sets/expression_sets.xml")
    yed_asset = _asset("x64c.rpf/anim/expressions.rpf/ambient.yed")
    peds_file = _ped_file(_set_init_data(resolved))
    sets_file = _expression_set_file()
    yed_file = _yed_file("facial", "male_body")
    cache = _Cache(
        metadata_assets=(peds_asset, sets_asset),
        files={
            id(peds_asset): peds_file,
            id(sets_asset): sets_file,
            id(yed_asset): yed_file,
        },
        yed_assets={MetaHash("ambient").uint: yed_asset},
    )

    issues = []
    _resolve_ped_expression_resources(cache, {4: resolved}, issues)

    expression_set = resolved.resolved_expression_set
    assert expression_set is not None
    assert expression_set.source_asset is sets_asset
    assert expression_set.yed_asset is yed_asset
    assert expression_set.selected_expression_names == ("facial", "male_body")
    assert expression_set.selected_program_names == (
        "pack:/facial.expr",
        "pack:/male_body.expr",
    )
    assert resolved.expression_file is yed_file
    assert resolved.expression_dictionary is yed_file.parsed
    assert resolved.expression_set is expression_set.expression_set
    assert not issues


def test_expression_set_metadata_uses_source_precedence_not_scan_order() -> None:
    resolved = _resolved_ped()
    peds_asset = _asset("x64/data/peds.ymt")
    base_sets_asset = _asset("common.rpf/data/anim/expression_sets/expression_sets.xml")
    mod_sets_asset = _asset("mods/update/data/anim/expression_sets/expression_sets.xml")
    mod_yed_asset = _asset("mods/update/x64/expressions/mod_expression.yed")
    files = {
        id(peds_asset): _ped_file(_set_init_data(resolved)),
        id(base_sets_asset): _expression_set_file(dictionary="base_expression"),
        id(mod_sets_asset): _expression_set_file(dictionary="mod_expression"),
        id(mod_yed_asset): _yed_file("facial", "male_body"),
    }
    cache = _Cache(
        metadata_assets=(base_sets_asset, peds_asset, mod_sets_asset),
        files=files,
        yed_assets={MetaHash("mod_expression").uint: mod_yed_asset},
    )

    issues = []
    _resolve_ped_expression_resources(cache, {4: resolved}, issues)

    assert resolved.resolved_expression_set is not None
    assert resolved.resolved_expression_set.source_asset is mod_sets_asset
    assert resolved.expression_file is files[id(mod_yed_asset)]
    assert not issues


@pytest.mark.parametrize(
    ("sets_file", "yed_file", "expected_code"),
    [
        (None, None, "binding.expression_set_metadata_unresolved"),
        (
            _expression_set_file(name="another_set"),
            None,
            "binding.expression_set_unresolved",
        ),
        (
            _expression_set_file(),
            None,
            "binding.expression_set_yed_unresolved",
        ),
        (
            _expression_set_file(),
            _yed_file("facial"),
            "binding.expression_set_program_unresolved",
        ),
    ],
)
def test_expression_set_resolution_reports_structured_failures(
    sets_file,
    yed_file,
    expected_code: str,
) -> None:
    resolved = _resolved_ped()
    peds_asset = _asset("x64/data/peds.ymt")
    sets_asset = _asset("common.rpf/data/anim/expression_sets/expression_sets.xml")
    yed_asset = _asset("x64c.rpf/anim/expressions.rpf/ambient.yed")
    metadata_assets = [peds_asset]
    files = {id(peds_asset): _ped_file(_set_init_data(resolved))}
    if sets_file is not None:
        metadata_assets.append(sets_asset)
        files[id(sets_asset)] = sets_file
    yed_assets = {}
    if yed_file is not None:
        files[id(yed_asset)] = yed_file
        yed_assets[MetaHash("ambient").uint] = yed_asset
    cache = _Cache(
        metadata_assets=metadata_assets,
        files=files,
        yed_assets=yed_assets,
    )

    issues = []
    _resolve_ped_expression_resources(cache, {4: resolved}, issues)

    assert [issue.code for issue in issues] == [expected_code]
    if expected_code == "binding.expression_set_program_unresolved":
        assert resolved.expression_file is yed_file
        assert resolved.resolved_expression_set is not None
        assert resolved.resolved_expression_set.missing_expression_names == (
            "male_body",
        )


def test_null_direct_expression_dictionary_is_absent_not_unresolved() -> None:
    resolved = _resolved_ped()
    peds_asset = _asset("x64/data/peds.ymt")
    init_data = YmtPedInitData(
        name=MetaHash(resolved.reference_hash),
        expression_dictionary_name=MetaHash("null"),
        expression_name=MetaHash("null"),
    )
    cache = _Cache(
        metadata_assets=(peds_asset,),
        files={id(peds_asset): _ped_file(init_data)},
    )

    issues = []
    _resolve_ped_expression_resources(cache, {4: resolved}, issues)

    assert resolved.expression_file is None
    assert not issues
