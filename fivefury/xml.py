from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from copy import deepcopy
from enum import IntFlag
from pathlib import Path
from typing import TypeAlias, TypeVar

from .common import atomic_write_bytes

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'
T = TypeVar("T")
XmlSource: TypeAlias = bytes | bytearray | memoryview | str | Path


def coerce_enum_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def read_xml_text(source: XmlSource) -> str:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source).decode("utf-8-sig", errors="replace")
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


def looks_like_xml(value: bytes | bytearray | memoryview | str) -> bool:
    if not isinstance(value, str):
        return bytes(value).lstrip()[:1] == b"<"
    return value.lstrip().startswith("<")


def parse_xml_root(source: XmlSource) -> ET.Element:
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


def descendant_by_name(element: ET.Element, name: str) -> ET.Element | None:
    target = name.lower()
    return next((child for child in element.iter() if child.tag.lower() == target), None)


def element_text(element: ET.Element | None, default: str = "") -> str:
    return default if element is None else (element.text or "").strip()


def element_value(element: ET.Element | None, default: str = "") -> str:
    return default if element is None else element.attrib.get("value", default)


def child_text(element: ET.Element, name: str, default: str = "") -> str:
    return element_text(child_by_name(element, name), default)


def child_value(element: ET.Element, name: str, default: str = "") -> str:
    return element_value(child_by_name(element, name), default)


def child_int(element: ET.Element, name: str, default: int = 0) -> int:
    child = child_by_name(element, name)
    if child is None:
        return default
    text = child.attrib.get("value", child.text or "")
    try:
        return int(str(text).strip(), 0)
    except ValueError:
        return default


def child_float(element: ET.Element, name: str, default: float = 0.0) -> float:
    child = child_by_name(element, name)
    if child is None:
        return default
    try:
        return float(child.attrib.get("value", child.text or ""))
    except ValueError:
        return default


def child_bool(element: ET.Element, name: str, default: bool = False) -> bool:
    child = child_by_name(element, name)
    if child is None:
        return default
    return parse_bool(child.attrib.get("value", child.text or ""), default)


def item_elements(element: ET.Element | None) -> list[ET.Element]:
    return [] if element is None else children_by_name(element, "Item")


def child_items(element: ET.Element, name: str) -> list[ET.Element]:
    return item_elements(child_by_name(element, name))


def item_texts(element: ET.Element | None) -> list[str]:
    return [text for item in item_elements(element) if (text := element_text(item))]


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


def element_xml(element: ET.Element) -> str:
    return ET.tostring(element, encoding="unicode", short_empty_elements=True)


def xml_bytes(root: ET.Element) -> bytes:
    formatted = deepcopy(root)
    ET.indent(formatted, space="  ")
    text = element_xml(formatted)
    return (XML_DECLARATION + text + "\n").encode("utf-8")


def save_xml(root: ET.Element, destination: str | Path) -> Path:
    return atomic_write_bytes(destination, xml_bytes(root))


__all__ = [
    "XML_DECLARATION",
    "XmlSource",
    "add_element_items",
    "add_items",
    "add_text",
    "add_value",
    "bool_text",
    "child_bool",
    "child_by_name",
    "child_float",
    "child_int",
    "child_item_texts",
    "child_item_values",
    "child_items",
    "child_text",
    "child_value",
    "children_by_name",
    "coerce_enum_value",
    "descendant_by_name",
    "element_text",
    "element_value",
    "element_xml",
    "flag_text",
    "item_elements",
    "item_texts",
    "looks_like_xml",
    "parse_bool",
    "parse_flag_names",
    "parse_xml_root",
    "read_xml_text",
    "save_xml",
    "xml_bytes",
]
