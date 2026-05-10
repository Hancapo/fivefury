from __future__ import annotations

import xml.etree.ElementTree as ET
from enum import IntFlag
from pathlib import Path
from typing import Callable, Iterable, TypeVar


XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'
T = TypeVar("T")


def coerce_enum_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def read_xml_text(source: bytes | str | Path) -> str:
    if isinstance(source, bytes):
        return source.decode("utf-8-sig", errors="replace")
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8-sig")
    text = str(source)
    if looks_like_xml(text):
        return text
    try:
        path = Path(text)
        if path.exists():
            return path.read_text(encoding="utf-8-sig")
    except OSError:
        pass
    return text


def looks_like_xml(value: bytes | str) -> bool:
    if isinstance(value, bytes):
        return value.lstrip()[:1] == b"<"
    return value.lstrip().startswith("<")


def parse_xml_root(source: bytes | str | Path) -> ET.Element:
    return ET.fromstring(read_xml_text(source))


def child_by_name(element: ET.Element, name: str) -> ET.Element | None:
    target = name.lower()
    for child in element:
        if child.tag.lower() == target:
            return child
    return None


def children_by_name(element: ET.Element, name: str) -> list[ET.Element]:
    target = name.lower()
    return [child for child in element if child.tag.lower() == target]


def child_text(element: ET.Element, name: str, default: str = "") -> str:
    child = child_by_name(element, name)
    if child is None:
        return default
    return (child.text or "").strip()


def child_value(element: ET.Element, name: str, default: str = "") -> str:
    child = child_by_name(element, name)
    if child is None:
        return default
    return child.attrib.get("value", default)


def child_int(element: ET.Element, name: str, default: int = 0) -> int:
    child = child_by_name(element, name)
    if child is None:
        return default
    text = child.attrib.get("value", child.text or "")
    try:
        return int(str(text).strip(), 0)
    except ValueError:
        return default


def item_texts(element: ET.Element | None) -> list[str]:
    if element is None:
        return []
    return [(child.text or "").strip() for child in element if child.tag.lower() == "item" and (child.text or "").strip()]


def child_item_texts(element: ET.Element, name: str) -> list[str]:
    return item_texts(child_by_name(element, name))


def child_item_values(element: ET.Element, name: str, factory: Callable[[str], T]) -> list[T]:
    return [factory(item) for item in child_item_texts(element, name)]


def add_text(parent: ET.Element, tag: str, text: object = "") -> ET.Element:
    element = ET.SubElement(parent, tag)
    value = coerce_enum_value(text)
    if value:
        element.text = value
    return element


def add_value(parent: ET.Element, tag: str, value: object) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.set("value", bool_text(value) if isinstance(value, bool) else str(value))
    return element


def add_items(parent: ET.Element, tag: str, items: Iterable[object], *, omit_empty: bool = False) -> ET.Element | None:
    values = list(items)
    if omit_empty and not values:
        return None
    element = ET.SubElement(parent, tag)
    for item in values:
        add_text(element, "Item", coerce_enum_value(item))
    return element


def add_element_items(parent: ET.Element, tag: str, items: Iterable[ET.Element]) -> ET.Element:
    element = ET.SubElement(parent, tag)
    for item in items:
        item.tag = "Item"
        element.append(item)
    return element


def bool_text(value: object) -> str:
    if isinstance(value, str):
        return "true" if value.strip().lower() in {"1", "true", "yes", "on"} else "false"
    return "true" if bool(value) else "false"


def parse_bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_flag_names(enum_type: type[IntFlag], text: str) -> IntFlag:
    result = enum_type(0)
    for item in str(text or "").replace(",", "|").split("|"):
        name = item.strip()
        if not name:
            continue
        result |= enum_type[name]
    return result


def flag_text(flags: IntFlag) -> str:
    if int(flags) == 0:
        return ""
    return "|".join(flag.name for flag in type(flags) if flag in flags and int(flag) != 0)


def xml_bytes(root: ET.Element) -> bytes:
    ET.indent(root, space="  ")
    text = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    return (XML_DECLARATION + text + "\n").encode("utf-8")


__all__ = [
    "XML_DECLARATION",
    "add_element_items",
    "add_items",
    "add_text",
    "add_value",
    "bool_text",
    "child_by_name",
    "child_int",
    "child_item_texts",
    "child_item_values",
    "child_text",
    "child_value",
    "children_by_name",
    "coerce_enum_value",
    "flag_text",
    "item_texts",
    "looks_like_xml",
    "parse_bool",
    "parse_flag_names",
    "parse_xml_root",
    "read_xml_text",
    "xml_bytes",
]
