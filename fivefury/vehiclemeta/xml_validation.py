from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..authoring import ValidationReport
from .enums import (
    VehicleClass,
    VehicleDashboardType,
    VehiclePlateType,
    VehicleSwankness,
    VehicleType,
    VehicleWheelType,
    parse_vehicle_model_flags,
)
from .handling_flags import HandlingFlagValue, handling_flag_problem

_FLOAT = re.compile(r"[-+]?(?:\d+\.\d{6})")
_COLOR32 = re.compile(r"0x[0-9A-F]{8}")
_ROOTS = {
    "CVehicleModelInfo__InitDataList",
    "CHandlingDataMgr",
    "CVehicleModelInfoVariation",
    "CVehicleModelInfoVarGlobal",
}
_VEHICLE_ENUMS = {
    "type": VehicleType,
    "plateType": VehiclePlateType,
    "vehicleClass": VehicleClass,
    "wheelType": VehicleWheelType,
    "dashboardType": VehicleDashboardType,
    "swankness": VehicleSwankness,
}


def _root(source: bytes | str | Path | ET.Element) -> ET.Element:
    if isinstance(source, ET.Element):
        return source
    if isinstance(source, Path):
        return ET.fromstring(source.read_bytes())
    if isinstance(source, bytes):
        return ET.fromstring(source)
    text = str(source)
    path = Path(text)
    if "<" not in text and path.is_file():
        return ET.fromstring(path.read_bytes())
    return ET.fromstring(text)


def _issue(
    report: ValidationReport,
    code: str,
    message: str,
    path: str,
) -> None:
    report.issue(code, message, path=path)


def _validate_float_array(
    report: ValidationReport,
    element: ET.Element | None,
    path: str,
) -> None:
    if element is None:
        _issue(report, "vehicle.xml.array.required", "Missing float array", path)
        return
    if element.attrib != {"content": "float_array"}:
        _issue(
            report,
            "vehicle.xml.array.float.invalid",
            'Float arrays require only content="float_array"',
            path,
        )
    if list(element):
        _issue(
            report,
            "vehicle.xml.array.items.invalid",
            "Retail float arrays contain text, not Item elements",
            path,
        )
    for index, token in enumerate((element.text or "").split()):
        if _FLOAT.fullmatch(token) is None:
            _issue(
                report,
                "vehicle.xml.float.lexical.invalid",
                f"Float {token!r} must use six decimal places",
                f"{path}[{index}]",
            )


def _validate_enum(
    report: ValidationReport,
    element: ET.Element | None,
    enum_type: type,
    path: str,
) -> None:
    if element is None:
        return
    if "value" in element.attrib or list(element):
        _issue(
            report,
            "vehicle.xml.enum.shape.invalid",
            "Vehicle enums must be token text",
            path,
        )
        return
    token = (element.text or "").strip()
    if enum_type.from_token(token) is None:
        _issue(
            report,
            "vehicle.xml.enum.token.invalid",
            f"Unknown {enum_type.__name__} token {token!r}",
            path,
        )


def _validate_color32(
    report: ValidationReport,
    element: ET.Element | None,
    path: str,
) -> None:
    if element is None:
        return
    value = element.attrib.get("value", "")
    if set(element.attrib) != {"value"} or _COLOR32.fullmatch(value) is None:
        _issue(
            report,
            "vehicle.xml.color32.invalid",
            "Color32 values require uppercase 0xAARRGGBB notation",
            path,
        )


def _validate_vehicles(report: ValidationReport, root: ET.Element) -> None:
    init_data = root.find("InitDatas")
    if init_data is None:
        _issue(
            report,
            "vehicle.xml.vehicles.items.required",
            "vehicles.meta requires InitDatas",
            "InitDatas",
        )
        return
    for index, item in enumerate(init_data.findall("Item")):
        path = f"InitDatas[{index}]"
        _validate_float_array(report, item.find("lodDistances"), f"{path}.lodDistances")
        for wrong, expected in (
            ("visibleSpawnDistanceScale", "visibleSpawnDistScale"),
            ("weaponForceMultiplier", "weaponForceMult"),
        ):
            if item.find(wrong) is not None:
                _issue(
                    report,
                    "vehicle.xml.element.alias.invalid",
                    f"Use {expected}, not {wrong}",
                    f"{path}.{wrong}",
                )
        for tag in ("visibleSpawnDistScale", "weaponForceMult"):
            if item.find(tag) is None:
                _issue(
                    report,
                    "vehicle.xml.element.required",
                    f"vehicles.meta requires {tag}",
                    f"{path}.{tag}",
                )
        flags = item.find("flags")
        if flags is None:
            _issue(
                report,
                "vehicle.xml.flags.required",
                "vehicles.meta requires flags",
                f"{path}.flags",
            )
        elif flags.attrib or list(flags):
            _issue(
                report,
                "vehicle.xml.flags.shape.invalid",
                "Vehicle flags must be space-separated text",
                f"{path}.flags",
            )
        else:
            try:
                parse_vehicle_model_flags(flags.text or "")
            except ValueError as exc:
                _issue(
                    report,
                    "vehicle.xml.flags.token.invalid",
                    str(exc),
                    f"{path}.flags",
                )
        for tag, enum_type in _VEHICLE_ENUMS.items():
            _validate_enum(report, item.find(tag), enum_type, f"{path}.{tag}")
        _validate_color32(report, item.find("diffuseTint"), f"{path}.diffuseTint")


def _validate_handling(report: ValidationReport, root: ET.Element) -> None:
    handling = root.find("HandlingData")
    if handling is None:
        _issue(
            report,
            "vehicle.xml.handling.items.required",
            "handling.meta requires HandlingData",
            "HandlingData",
        )
        return
    for index, item in enumerate(handling.findall("Item")):
        path = f"HandlingData[{index}]"
        if item.attrib.get("type") != "CHandlingData":
            _issue(
                report,
                "vehicle.xml.handling.type.invalid",
                'Handling entries require type="CHandlingData"',
                path,
            )
        for tag in ("strModelFlags", "strHandlingFlags", "strDamageFlags"):
            element = item.find(tag)
            if element is None:
                continue
            flag_path = f"{path}.{tag}"
            if element.attrib or list(element):
                _issue(
                    report,
                    "vehicle.xml.handling.flags.shape.invalid",
                    "Handling flags require hexadecimal text without XML attributes",
                    flag_path,
                )
                continue
            problem = handling_flag_problem(HandlingFlagValue(element.text or ""))
            if problem is not None:
                suffix, message = problem
                _issue(
                    report,
                    f"vehicle.xml.handling.flags.{suffix}",
                    message,
                    flag_path,
                )
        sub_data = item.find("SubHandlingData")
        if sub_data is None:
            continue
        for sub_index, sub_item in enumerate(sub_data.findall("Item")):
            sub_path = f"{path}.SubHandlingData[{sub_index}]"
            type_name = sub_item.attrib.get("type", "")
            if not type_name:
                _issue(
                    report,
                    "vehicle.xml.handling.subtype.required",
                    "Subhandling entries require a type",
                    sub_path,
                )
            elif type_name == "NULL" and (
                len(sub_item.attrib) != 1
                or list(sub_item)
                or (sub_item.text or "").strip()
            ):
                _issue(
                    report,
                    "vehicle.xml.handling.null.invalid",
                    "NULL subhandling slots cannot contain data",
                    sub_path,
                )


def _validate_variations(report: ValidationReport, root: ET.Element) -> None:
    variations = root.find("variationData")
    if variations is None:
        _issue(
            report,
            "vehicle.xml.variations.items.required",
            "carvariations.meta requires variationData",
            "variationData",
        )
        return
    for vehicle_index, vehicle in enumerate(variations.findall("Item")):
        colors = vehicle.find("colors")
        if colors is None:
            continue
        for color_index, color in enumerate(colors.findall("Item")):
            indices = color.find("indices")
            path = f"variationData[{vehicle_index}].colors[{color_index}].indices"
            if indices is None or indices.attrib != {"content": "char_array"}:
                _issue(
                    report,
                    "vehicle.xml.array.char.invalid",
                    'Color indices require content="char_array"',
                    path,
                )
                continue
            if list(indices):
                _issue(
                    report,
                    "vehicle.xml.array.items.invalid",
                    "Retail char arrays contain text, not Item elements",
                    path,
                )
            for index, token in enumerate((indices.text or "").split()):
                try:
                    value = int(token)
                except ValueError:
                    value = -1
                if not 0 <= value <= 0xFF:
                    _issue(
                        report,
                        "vehicle.xml.array.char.value.invalid",
                        f"Character array value {token!r} does not fit a byte",
                        f"{path}[{index}]",
                    )
            liveries = color.find("liveries")
            if liveries is not None:
                for index, item in enumerate(liveries.findall("Item")):
                    if set(item.attrib) != {"value"} or item.attrib.get(
                        "value"
                    ) not in {"true", "false"}:
                        _issue(
                            report,
                            "vehicle.xml.array.boolean.invalid",
                            'Boolean arrays require Item value="true|false"',
                            f"{path.rsplit('.', 1)[0]}.liveries[{index}]",
                        )


def _validate_carcols(report: ValidationReport, root: ET.Element) -> None:
    if root.find("./VehiclePlates/textures") is not None:
        _issue(
            report,
            "vehicle.xml.element.alias.invalid",
            "Use Textures, not textures",
            "VehiclePlates.textures",
        )
    color_tags = {
        "FontColor",
        "FontOutlineColor",
        "color",
        "xenonLightColor",
        "xenonCoronaColor",
        "lightColor",
        "coronaColor",
    }
    for element in root.iter():
        if element.tag in color_tags:
            _validate_color32(report, element, element.tag)
    corona_tags = {
        "rearIndicatorCorona",
        "frontIndicatorCorona",
        "tailLightCorona",
        "tailLightMiddleCorona",
        "headLightCorona",
        "reversingLightCorona",
    }
    wrong_fields = {
        "farSize": "size_far",
        "farIntensity": "intensity_far",
        "count": "numCoronas",
        "spacing": "distBetweenCoronas",
        "farSpacing": "distBetweenCoronas_far",
    }
    for corona in (item for item in root.iter() if item.tag in corona_tags):
        for wrong, expected in wrong_fields.items():
            if corona.find(wrong) is not None:
                _issue(
                    report,
                    "vehicle.xml.element.alias.invalid",
                    f"Use {expected}, not {wrong}",
                    f"{corona.tag}.{wrong}",
                )


def validate_vehicle_meta_xml(
    source: bytes | str | Path | ET.Element,
    *,
    expected_root: str | None = None,
) -> ValidationReport:
    report = ValidationReport()
    try:
        root = _root(source)
    except (ET.ParseError, OSError, ValueError) as exc:
        report.issue("vehicle.xml.invalid", str(exc), path="xml")
        return report
    if expected_root is not None and root.tag != expected_root:
        _issue(
            report,
            "vehicle.xml.root.mismatch",
            f"Expected {expected_root}, got {root.tag}",
            "xml",
        )
    if root.tag not in _ROOTS:
        _issue(
            report,
            "vehicle.xml.root.unsupported",
            f"Unsupported vehicle metadata root {root.tag!r}",
            "xml",
        )
        return report
    if root.tag == "CVehicleModelInfo__InitDataList":
        _validate_vehicles(report, root)
    elif root.tag == "CHandlingDataMgr":
        _validate_handling(report, root)
    elif root.tag == "CVehicleModelInfoVariation":
        _validate_variations(report, root)
    elif root.tag == "CVehicleModelInfoVarGlobal":
        _validate_carcols(report, root)
    return report


__all__ = ["validate_vehicle_meta_xml"]
