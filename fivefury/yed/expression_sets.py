from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from ..metahash import HashLike, MetaHash
from ..xml import (
    child_by_name,
    child_text,
    element_xml,
    item_elements,
    parse_xml_root,
    read_xml_text,
)

NULL_EXPRESSION_HASH = MetaHash("null").uint


@dataclass(slots=True, frozen=True)
class ExpressionSetRawField:
    name: str
    text: str
    attributes: tuple[tuple[str, str], ...]
    xml: str


@dataclass(slots=True, frozen=True)
class PedExpressionSet:
    name: MetaHash
    dictionary_name: MetaHash
    expression_names: tuple[MetaHash, ...]
    raw_name: str = ""
    raw_dictionary_name: str = ""
    raw_expression_names: tuple[str, ...] = ()
    raw_attributes: tuple[tuple[str, str], ...] = ()
    unknown_fields: tuple[ExpressionSetRawField, ...] = ()
    raw_xml: str = ""


@dataclass(slots=True, frozen=True)
class PedExpressionSetMetadata:
    expression_sets: tuple[PedExpressionSet, ...]
    root_tag: str = "fwExpressionSetManager"
    raw_attributes: tuple[tuple[str, str], ...] = ()
    unknown_fields: tuple[ExpressionSetRawField, ...] = ()
    raw_xml: str = ""
    source: str = ""

    def get(self, name: HashLike) -> PedExpressionSet | None:
        target = MetaHash(name).uint
        return next(
            (item for item in self.expression_sets if item.name.uint == target),
            None,
        )


def is_null_expression_reference(value: HashLike | None) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip()
        if not text or text.casefold() == "null":
            return True
        try:
            numeric = int(text, 0)
        except ValueError:
            numeric = MetaHash(text).uint
    else:
        numeric = MetaHash(value).uint
    return numeric in {0, NULL_EXPRESSION_HASH}


def _raw_field(element: ET.Element) -> ExpressionSetRawField:
    return ExpressionSetRawField(
        name=element.tag,
        text=(element.text or "").strip(),
        attributes=tuple(element.attrib.items()),
        xml=element_xml(element),
    )


def _parse_expression_set(element: ET.Element) -> PedExpressionSet:
    raw_name = element.attrib.get("key", "").strip()
    raw_dictionary_name = child_text(element, "dictionaryName")
    expressions_element = child_by_name(element, "expressions")
    raw_expression_names = tuple(
        (child.text or "").strip()
        for child in item_elements(expressions_element)
        if (child.text or "").strip()
    )
    known_tags = {"dictionaryname", "expressions"}
    return PedExpressionSet(
        name=MetaHash(raw_name),
        dictionary_name=MetaHash(raw_dictionary_name),
        expression_names=tuple(MetaHash(name) for name in raw_expression_names),
        raw_name=raw_name,
        raw_dictionary_name=raw_dictionary_name,
        raw_expression_names=raw_expression_names,
        raw_attributes=tuple(element.attrib.items()),
        unknown_fields=tuple(
            _raw_field(child)
            for child in element
            if child.tag.casefold() not in known_tags
        ),
        raw_xml=element_xml(element),
    )


def read_ped_expression_sets(
    source: bytes | str | Path,
    *,
    source_path: str = "",
) -> PedExpressionSetMetadata:
    text = read_xml_text(source)
    root = parse_xml_root(text)
    expression_sets = tuple(
        _parse_expression_set(element)
        for element in item_elements(child_by_name(root, "expressionSets"))
    )
    known_root_tags = {"expressionsets"}
    return PedExpressionSetMetadata(
        expression_sets=expression_sets,
        root_tag=root.tag,
        raw_attributes=tuple(root.attrib.items()),
        unknown_fields=tuple(
            _raw_field(child)
            for child in root
            if child.tag.casefold() not in known_root_tags
        ),
        raw_xml=text,
        source=source_path,
    )


__all__ = [
    "NULL_EXPRESSION_HASH",
    "ExpressionSetRawField",
    "PedExpressionSet",
    "PedExpressionSetMetadata",
    "is_null_expression_reference",
    "read_ped_expression_sets",
]
