from __future__ import annotations

import xml.etree.ElementTree as ET

from fivefury.xml import (
    child_bool,
    child_float,
    child_items,
    descendant_by_name,
    element_data,
    element_text,
    element_value,
    looks_like_xml,
    parse_xml_root,
    save_xml,
    xml_bytes,
)


def test_xml_helpers_accept_binary_views_and_case_insensitive_items() -> None:
    source = memoryview(
        b'\xef\xbb\xbf<Root><Enabled value="true"/><Scale>2.5</Scale>'
        b"<Values><item>A</item><Item>B</Item></Values></Root>"
    )
    root = parse_xml_root(source)

    assert looks_like_xml(source)
    assert child_bool(root, "enabled")
    assert child_float(root, "scale") == 2.5
    assert [element_text(item) for item in child_items(root, "values")] == ["A", "B"]
    assert descendant_by_name(root, "item").text == "A"
    assert element_value(root.find("Enabled")) == "true"


def test_xml_serialization_does_not_mutate_the_source_tree(tmp_path) -> None:
    root = ET.fromstring("<Root><Child><Leaf /></Child></Root>")
    original_child_text = root[0].text

    data = xml_bytes(root)
    destination = save_xml(root, tmp_path / "nested" / "asset.xml")

    assert data.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
    assert destination.read_bytes() == data
    assert root[0].text == original_child_text


def test_element_data_ignores_empty_duplicate_containers() -> None:
    root = parse_xml_root(
        "<Root><Values><Item>A</Item></Values><Values />"
        "<Names /><Names><Item>B</Item></Names></Root>"
    )

    assert element_data(root) == {"Values": ["A"], "Names": ["B"]}
