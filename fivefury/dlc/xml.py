from __future__ import annotations

from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET


XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'


def coerce_enum_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def read_xml_text(source: bytes | str | Path) -> str:
    if isinstance(source, bytes):
        return source.decode("utf-8-sig")
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8-sig")
    text = str(source)
    if "<" not in text and Path(text).exists():
        return Path(text).read_text(encoding="utf-8-sig")
    return text


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


def child_by_name(element: ET.Element, name: str) -> ET.Element | None:
    target = name.lower()
    for child in element:
        if child.tag.lower() == target:
            return child
    return None


def children_by_name(element: ET.Element, name: str) -> list[ET.Element]:
    target = name.lower()
    return [child for child in element if child.tag.lower() == target]


def item_texts(element: ET.Element | None) -> list[str]:
    if element is None:
        return []
    return [(child.text or "").strip() for child in element if child.tag.lower() == "item" and (child.text or "").strip()]


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


def add_items(parent: ET.Element, tag: str, items: Iterable[object]) -> ET.Element:
    element = ET.SubElement(parent, tag)
    for item in items:
        add_text(element, "Item", coerce_enum_value(item))
    return element


def bool_text(value: object) -> str:
    if isinstance(value, str):
        return "true" if value.strip().lower() in {"1", "true", "yes", "on"} else "false"
    return "true" if bool(value) else "false"


def parse_bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def xml_bytes(root: ET.Element) -> bytes:
    ET.indent(root, space="  ")
    text = ET.tostring(root, encoding="unicode", short_empty_elements=True)
    return (XML_DECLARATION + text + "\n").encode("utf-8")
