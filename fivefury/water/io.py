from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..xml import (
    add_value,
    child_by_name,
    child_value,
    children_by_name,
    parse_bool,
    parse_xml_root,
    xml_bytes,
)
from .model import (
    WaterCalmingQuad,
    WaterComponent,
    WaterData,
    WaterQuad,
    WaterWaveQuad,
    coerce_water_data,
)


def _int_value(element: ET.Element, name: str, default: int = 0) -> int:
    text = child_value(element, name, str(default))
    try:
        return int(text, 0)
    except ValueError:
        return default


def _float_value(element: ET.Element, name: str, default: float = 0.0) -> float:
    text = child_value(element, name, str(default))
    try:
        return float(text)
    except ValueError:
        return default


def _float_text(value: float) -> str:
    text = format(float(value), ".9g")
    return text if "." in text or "e" in text.lower() else f"{text}.0"


def _item_elements(root: ET.Element, section_name: str) -> list[ET.Element]:
    section = child_by_name(root, section_name)
    if section is None:
        return []
    return [item for item in children_by_name(section, "Item") if len(item)]


def _read_water_quad(item: ET.Element) -> WaterQuad:
    return WaterQuad(
        min_x=_int_value(item, "minX"),
        min_y=_int_value(item, "minY"),
        max_x=_int_value(item, "maxX"),
        max_y=_int_value(item, "maxY"),
        type=_int_value(item, "Type"),
        is_invisible=parse_bool(child_value(item, "IsInvisible")),
        has_limited_depth=parse_bool(child_value(item, "HasLimitedDepth")),
        z=_float_value(item, "z"),
        alpha_sw=_int_value(item, "a1", 26),
        alpha_se=_int_value(item, "a2", 26),
        alpha_ne=_int_value(item, "a3", 26),
        alpha_nw=_int_value(item, "a4", 26),
        no_stencil=parse_bool(child_value(item, "NoStencil")),
    )


def _read_calming_quad(item: ET.Element) -> WaterCalmingQuad:
    return WaterCalmingQuad(
        min_x=_int_value(item, "minX"),
        min_y=_int_value(item, "minY"),
        max_x=_int_value(item, "maxX"),
        max_y=_int_value(item, "maxY"),
        dampening=_float_value(item, "fDampening"),
    )


def _read_wave_quad(item: ET.Element) -> WaterWaveQuad:
    return WaterWaveQuad(
        min_x=_int_value(item, "minX"),
        min_y=_int_value(item, "minY"),
        max_x=_int_value(item, "maxX"),
        max_y=_int_value(item, "maxY"),
        amplitude=_float_value(item, "Amplitude"),
        direction_x=_float_value(item, "XDirection"),
        direction_y=_float_value(item, "YDirection"),
    )


def read_water(source: bytes | str | Path) -> WaterData:
    root = parse_xml_root(source)
    if root.tag.lower() != "waterdata":
        raise ValueError(f"Expected WaterData XML root, got {root.tag!r}")
    return WaterData(
        water_quads=[
            _read_water_quad(item) for item in _item_elements(root, "WaterQuads")
        ],
        calming_quads=[
            _read_calming_quad(item) for item in _item_elements(root, "CalmingQuads")
        ],
        wave_quads=[
            _read_wave_quad(item) for item in _item_elements(root, "WaveQuads")
        ],
    )


def _write_bounds(item: ET.Element, quad: WaterComponent) -> None:
    add_value(item, "minX", quad.min_x)
    add_value(item, "maxX", quad.max_x)
    add_value(item, "minY", quad.min_y)
    add_value(item, "maxY", quad.max_y)


def _water_quad_element(quad: WaterQuad) -> ET.Element:
    item = ET.Element("Item")
    _write_bounds(item, quad)
    add_value(item, "Type", int(quad.type))
    add_value(item, "IsInvisible", quad.is_invisible)
    add_value(item, "HasLimitedDepth", quad.has_limited_depth)
    add_value(item, "z", _float_text(quad.z))
    add_value(item, "a1", quad.alpha_sw)
    add_value(item, "a2", quad.alpha_se)
    add_value(item, "a3", quad.alpha_ne)
    add_value(item, "a4", quad.alpha_nw)
    add_value(item, "NoStencil", quad.no_stencil)
    return item


def _calming_quad_element(quad: WaterCalmingQuad) -> ET.Element:
    item = ET.Element("Item")
    _write_bounds(item, quad)
    add_value(item, "fDampening", _float_text(quad.dampening))
    return item


def _wave_quad_element(quad: WaterWaveQuad) -> ET.Element:
    item = ET.Element("Item")
    _write_bounds(item, quad)
    add_value(item, "Amplitude", _float_text(quad.amplitude))
    add_value(item, "XDirection", _float_text(quad.direction_x))
    add_value(item, "YDirection", _float_text(quad.direction_y))
    return item


def _append_section(
    root: ET.Element,
    name: str,
    items: list[WaterComponent],
    factory,
) -> None:
    if not items:
        return
    section = ET.SubElement(root, name)
    for item in items:
        section.append(factory(item))


def build_water_xml(source: WaterData, *, validate: bool = True) -> bytes:
    water = source.build()
    if validate:
        water.ensure_valid()
    root = ET.Element("WaterData")
    _append_section(root, "WaterQuads", water.water_quads, _water_quad_element)
    _append_section(
        root,
        "CalmingQuads",
        water.calming_quads,
        _calming_quad_element,
    )
    _append_section(root, "WaveQuads", water.wave_quads, _wave_quad_element)
    return xml_bytes(root)


def create_water(*items: WaterComponent) -> WaterData:
    return coerce_water_data(list(items))


def save_water(
    source: WaterData,
    path: str | Path,
    *,
    validate: bool = True,
) -> Path:
    return source.save(path, validate=validate)


__all__ = [
    "build_water_xml",
    "create_water",
    "read_water",
    "save_water",
]
