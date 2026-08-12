from __future__ import annotations

from fivefury import (
    NULL_EXPRESSION_HASH,
    GameFileCache,
    GameFileType,
    MetaHash,
    is_null_expression_reference,
    read_ped_expression_sets,
)

EXPRESSION_SETS_XML = b"""\
<fwExpressionSetManager version="test">
  <expressionSets>
    <Item type="fwExpressionSet" key="expr_set_ambient_male">
      <dictionaryName>ambient</dictionaryName>
      <expressions>
        <Item>facial</Item>
        <Item>male_body</Item>
      </expressions>
      <futureField value="7" />
    </Item>
  </expressionSets>
  <futureRootField enabled="true" />
</fwExpressionSetManager>
"""


def test_expression_set_parser_preserves_order_and_unknown_fields() -> None:
    metadata = read_ped_expression_sets(EXPRESSION_SETS_XML, source_path="test.xml")
    expression_set = metadata.get("expr_set_ambient_male")

    assert expression_set is not None
    assert expression_set.name == MetaHash("expr_set_ambient_male")
    assert expression_set.dictionary_name == MetaHash("ambient")
    assert expression_set.raw_expression_names == ("facial", "male_body")
    assert expression_set.expression_names == (
        MetaHash("facial"),
        MetaHash("male_body"),
    )
    assert expression_set.unknown_fields[0].name == "futureField"
    assert expression_set.unknown_fields[0].attributes == (("value", "7"),)
    assert metadata.raw_attributes == (("version", "test"),)
    assert metadata.unknown_fields[0].name == "futureRootField"
    assert metadata.source == "test.xml"


def test_expression_null_normalization() -> None:
    for value in (None, 0, "", "null", "NULL", NULL_EXPRESSION_HASH, "0x3ADB3357"):
        assert is_null_expression_reference(value)

    assert not is_null_expression_reference("ambient")
    assert not is_null_expression_reference(1)


def test_expression_sets_are_typed_and_parsed_as_loose_metadata(tmp_path) -> None:
    path = tmp_path / "data" / "anim" / "expression_sets" / "expression_sets.xml"
    path.parent.mkdir(parents=True)
    path.write_bytes(EXPRESSION_SETS_XML)

    with GameFileCache(tmp_path, use_index_cache=False) as cache:
        cache.scan(load_keys=False)
        assets = cache.find_assets(
            "expression_sets.xml",
            kind=GameFileType.EXPRESSION_SETS,
        )
        assert len(assets) == 1
        game_file = cache.load_asset(assets[0])

    assert game_file is not None
    assert game_file.kind is GameFileType.EXPRESSION_SETS
    assert game_file.parsed.get("expr_set_ambient_male") is not None
