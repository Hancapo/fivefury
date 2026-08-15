from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..xml import (
    append_value,
    child_bool,
    child_float,
    child_int,
    child_items,
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


def _float_text(value: float) -> str:
    text = format(float(value), ".9g")
    return text if "." in text or "e" in text.lower() else f"{text}.0"


def _item_elements(root: ET.Element, section_name: str) -> list[ET.Element]:
    return [item for item in child_items(root, section_name) if len(item)]


def _read_water_quad(item: ET.Element) -> WaterQuad:
    return WaterQuad(
        min_x=child_int(item, "minX"),
        min_y=child_int(item, "minY"),
        max_x=child_int(item, "maxX"),
        max_y=child_int(item, "maxY"),
        type=child_int(item, "Type"),
        is_invisible=child_bool(item, "IsInvisible"),
        has_limited_depth=child_bool(item, "HasLimitedDepth"),
        z=child_float(item, "z"),
        alpha_sw=child_int(item, "a1", 26),
        alpha_se=child_int(item, "a2", 26),
        alpha_ne=child_int(item, "a3", 26),
        alpha_nw=child_int(item, "a4", 26),
        no_stencil=child_bool(item, "NoStencil"),
    )


def _read_calming_quad(item: ET.Element) -> WaterCalmingQuad:
    return WaterCalmingQuad(
        min_x=child_int(item, "minX"),
        min_y=child_int(item, "minY"),
        max_x=child_int(item, "maxX"),
        max_y=child_int(item, "maxY"),
        dampening=child_float(item, "fDampening"),
    )


def _read_wave_quad(item: ET.Element) -> WaterWaveQuad:
    return WaterWaveQuad(
        min_x=child_int(item, "minX"),
        min_y=child_int(item, "minY"),
        max_x=child_int(item, "maxX"),
        max_y=child_int(item, "maxY"),
        amplitude=child_float(item, "Amplitude"),
        direction_x=child_float(item, "XDirection"),
        direction_y=child_float(item, "YDirection"),
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
    append_value(item, "minX", quad.min_x)
    append_value(item, "maxX", quad.max_x)
    append_value(item, "minY", quad.min_y)
    append_value(item, "maxY", quad.max_y)


def _water_quad_element(quad: WaterQuad) -> ET.Element:
    item = ET.Element("Item")
    _write_bounds(item, quad)
    append_value(item, "Type", int(quad.type))
    append_value(item, "IsInvisible", quad.is_invisible)
    append_value(item, "HasLimitedDepth", quad.has_limited_depth)
    append_value(item, "z", _float_text(quad.z))
    append_value(item, "a1", quad.alpha_sw)
    append_value(item, "a2", quad.alpha_se)
    append_value(item, "a3", quad.alpha_ne)
    append_value(item, "a4", quad.alpha_nw)
    append_value(item, "NoStencil", quad.no_stencil)
    return item


def _calming_quad_element(quad: WaterCalmingQuad) -> ET.Element:
    item = ET.Element("Item")
    _write_bounds(item, quad)
    append_value(item, "fDampening", _float_text(quad.dampening))
    return item


def _wave_quad_element(quad: WaterWaveQuad) -> ET.Element:
    item = ET.Element("Item")
    _write_bounds(item, quad)
    append_value(item, "Amplitude", _float_text(quad.amplitude))
    append_value(item, "XDirection", _float_text(quad.direction_x))
    append_value(item, "YDirection", _float_text(quad.direction_y))
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
        water.validate().raise_for_errors()
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
