from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .model import CutFile, CutNode

_INTEGER_RE = re.compile(r"^-?(?:0x[0-9A-Fa-f]+|\d+)$")
_FLOAT_RE = re.compile(r"^-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _parse_scalar_text(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return ""
    parts = stripped.split()
    if len(parts) > 1 and all(_INTEGER_RE.match(part) for part in parts):
        return [int(part, 0) for part in parts]
    if len(parts) > 1 and all(_FLOAT_RE.match(part) for part in parts):
        return [float(part) for part in parts]
    if stripped.lower() == "true":
        return True
    if stripped.lower() == "false":
        return False
    if _INTEGER_RE.match(stripped):
        return int(stripped, 0)
    if _FLOAT_RE.match(stripped):
        return float(stripped)
    return stripped


def _parse_attr_value(value: str) -> Any:
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if _INTEGER_RE.match(value):
        return int(value, 0)
    if _FLOAT_RE.match(value):
        return float(value)
    return value


def _parse_element(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        if "value" in element.attrib and len(element.attrib) == 1:
            return _parse_attr_value(element.attrib["value"])
        if set(element.attrib) >= {"x", "y", "z", "w"}:
            return (
                _parse_attr_value(element.attrib["x"]),
                _parse_attr_value(element.attrib["y"]),
                _parse_attr_value(element.attrib["z"]),
                _parse_attr_value(element.attrib["w"]),
            )
        if set(element.attrib) >= {"x", "y", "z"}:
            return (
                _parse_attr_value(element.attrib["x"]),
                _parse_attr_value(element.attrib["y"]),
                _parse_attr_value(element.attrib["z"]),
            )
        if set(element.attrib) >= {"x", "y"}:
            return (_parse_attr_value(element.attrib["x"]), _parse_attr_value(element.attrib["y"]))
        if element.attrib:
            return {key: _parse_attr_value(value) for key, value in element.attrib.items()}
        return _parse_scalar_text(element.text or "")

    if all(child.tag == "Item" for child in children):
        return [_parse_element(child) for child in children]

    fields: dict[str, Any] = {}
    for child in children:
        value = _parse_element(child)
        if child.tag in fields:
            existing = fields[child.tag]
            if not isinstance(existing, list):
                fields[child.tag] = [existing]
            fields[child.tag].append(value)
        else:
            fields[child.tag] = value
    type_name = element.attrib.get("type", element.tag)
    return CutNode(type_name=type_name, fields=fields)


def read_cutxml(data: str | bytes | Path) -> CutFile:
    if isinstance(data, Path):
        text = data.read_text(encoding="utf-8")
    elif isinstance(data, bytes):
        text = data.decode("utf-8")
    else:
        path = Path(data)
        if path.is_file():
            text = path.read_text(encoding="utf-8")
        else:
            text = data
    root = ET.fromstring(text)
    parsed = _parse_element(root)
    if not isinstance(parsed, CutNode):
        parsed = CutNode(type_name=root.tag, fields={"value": parsed})
    return CutFile(root=parsed, source="cutxml")
