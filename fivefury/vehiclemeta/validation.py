from __future__ import annotations

import dataclasses
from enum import IntEnum
from typing import Any

from ..authoring import BuildContext, DiagnosticSeverity, ValidationReport
from ..game_target import GameTarget
from ..metahash import MetaHash
from .carcols import (
    VehicleCarCols,
    VehicleLightSettings,
    VehicleModelColor,
    VehicleModKit,
    VehicleSirenSettings,
)
from .enums import (
    VehicleClass,
    VehicleDashboardType,
    VehicleDoor,
    VehicleModCameraPosition,
    VehicleModelFlags,
    VehicleModKitType,
    VehicleModType,
    VehiclePlateType,
    VehicleSwankness,
    VehicleType,
    VehicleWheelType,
    VehicleWindow,
    vehicle_extra_flag_text,
    vehicle_model_flag_text,
)
from .handling import HandlingData, HandlingDataManager
from .variations import (
    LicensePlateProbability,
    VehicleColorIndices,
    VehicleModelInfoVariation,
    VehicleVariation,
)
from .vehicles import VehicleInitData, VehicleInitDataList, VehicleVfxExtra

_ENUM_FIELDS = {
    "vehicle_type": VehicleType,
    "plate_type": VehiclePlateType,
    "vehicle_class": VehicleClass,
    "dashboard_type": VehicleDashboardType,
    "wheel_type": VehicleWheelType,
    "swankness": VehicleSwankness,
    "door": VehicleDoor,
    "convertible_roof_windows": VehicleWindow,
    "closed_collision_doors": VehicleDoor,
    "driveable_doors": VehicleDoor,
    "mod_type": VehicleModType,
    "camera_position": VehicleModCameraPosition,
    "kit_type": VehicleModKitType,
    "slot": VehicleModType,
}


def _identifier(
    report: ValidationReport,
    value: str | MetaHash,
    *,
    code: str,
    path: str,
) -> None:
    if not str(value).strip():
        report.issue(code, "A required vehicle identifier is empty", path=path)


def _enum_value(
    report: ValidationReport,
    value: Any,
    enum_type: type[IntEnum],
    *,
    path: str,
) -> None:
    values = value if isinstance(value, list) else (value,)
    for index, item in enumerate(values):
        try:
            enum_type(int(item))
        except (TypeError, ValueError):
            suffix = f"[{index}]" if isinstance(value, list) else ""
            report.issue(
                "vehicle.enum.invalid",
                f"{item!r} is not a valid {enum_type.__name__}",
                path=f"{path}{suffix}",
            )


def _validate_children(
    report: ValidationReport,
    model: Any,
    *,
    context: BuildContext | None,
) -> None:
    if not dataclasses.is_dataclass(model):
        return
    for model_field in dataclasses.fields(model):
        name = model_field.name
        if name == "raw":
            continue
        value = getattr(model, name)
        enum_type = _ENUM_FIELDS.get(name)
        if enum_type is not None:
            _enum_value(report, value, enum_type, path=name)
        if dataclasses.is_dataclass(value):
            report.extend(
                validate_vehicle_meta_model(value, context=context),
                path=name,
            )
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if dataclasses.is_dataclass(child):
                    report.extend(
                        validate_vehicle_meta_model(child, context=context),
                        path=f"{name}[{index}]",
                    )


def _duplicate_identifiers(
    report: ValidationReport,
    values: list[str],
    *,
    code: str,
    path: str,
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
) -> None:
    seen: dict[str, int] = {}
    for index, value in enumerate(values):
        key = value.casefold()
        if not key:
            continue
        if key in seen:
            report.issue(
                code,
                f"Duplicate vehicle identifier: {value}",
                path=f"{path}[{index}]",
                severity=severity,
            )
        else:
            seen[key] = index


def _asset_documents(
    context: BuildContext | None, document_type: type[Any]
) -> tuple[Any, ...]:
    if context is None:
        return ()
    documents: list[Any] = []
    for asset in context.assets.values():
        target = getattr(asset, "parsed", asset)
        content = getattr(target, "content", target)
        if isinstance(content, document_type):
            documents.append(content)
    return tuple(documents)


def _validate_vehicle_references(
    report: ValidationReport,
    document: VehicleInitDataList,
    context: BuildContext | None,
) -> None:
    managers = _asset_documents(context, HandlingDataManager)
    variations = _asset_documents(context, VehicleModelInfoVariation)
    handling_names = {
        str(entry.name).casefold()
        for manager in managers
        for entry in manager.entries
        if str(entry.name)
    }
    variation_names = {
        entry.model_name.casefold()
        for variation in variations
        for entry in variation.vehicles
    }
    for index, vehicle in enumerate(document.vehicles):
        if managers and vehicle.handling_id.casefold() not in handling_names:
            report.issue(
                "vehicle.handling.unresolved",
                f"Handling entry {vehicle.handling_id!r} is not present in the authoring context",
                path=f"vehicles[{index}].handling_id",
            )
        if variations and vehicle.model_name.casefold() not in variation_names:
            report.issue(
                "vehicle.variation.unresolved",
                f"Variation entry for {vehicle.model_name!r} is not present in the authoring context",
                path=f"vehicles[{index}].model_name",
            )


def _validate_variation_references(
    report: ValidationReport,
    document: VehicleModelInfoVariation,
    context: BuildContext | None,
) -> None:
    carcols_documents = _asset_documents(context, VehicleCarCols)
    if not carcols_documents:
        return
    color_count = max(len(document.colors) for document in carcols_documents)
    for vehicle_index, vehicle in enumerate(document.vehicles):
        for group_index, group in enumerate(vehicle.colors):
            for slot_index, color_index in enumerate(group.indices):
                if not 0 <= color_index < color_count:
                    report.issue(
                        "vehicle.color.reference.unresolved",
                        f"Color index {color_index} is not present in carcols",
                        path=(
                            f"vehicles[{vehicle_index}].colors[{group_index}]"
                            f".indices[{slot_index}]"
                        ),
                    )


def validate_vehicle_meta_model(
    model: Any,
    *,
    context: BuildContext | None = None,
) -> ValidationReport:
    report = ValidationReport()
    if isinstance(model, VehicleInitData):
        _identifier(
            report,
            model.model_name,
            code="vehicle.model_name.required",
            path="model_name",
        )
        _identifier(
            report, model.txd_name, code="vehicle.txd_name.required", path="txd_name"
        )
        _identifier(
            report,
            model.handling_id,
            code="vehicle.handling_id.required",
            path="handling_id",
        )
        if len(model.lod_distances) > 8:
            report.issue(
                "vehicle.lod_distances.limit",
                "Vehicle LOD distance arrays cannot contain more than 8 entries",
                path="lod_distances",
            )
        try:
            vehicle_model_flag_text(model.flags)
        except (TypeError, ValueError) as exc:
            report.issue(
                "vehicle.flags.invalid",
                str(exc),
                path="flags",
            )
        if isinstance(model.flags, VehicleModelFlags):
            for index, token in enumerate(model.flags.unknown_tokens):
                report.issue(
                    "vehicle.flags.token.unknown",
                    f"Preserving unknown vehicle flag token {token!r}",
                    path=f"flags[{index}]",
                    severity=DiagnosticSeverity.WARNING,
                )
        extras = [("required_extras", model.required_extras)]
        extras.extend(
            (f"extra_includes[{index}]", value)
            for index, value in enumerate(model.extra_includes)
        )
        for path, value in extras:
            try:
                vehicle_extra_flag_text(value)
            except (TypeError, ValueError) as exc:
                report.issue("vehicle.extras.invalid", str(exc), path=path)
    elif isinstance(model, VehicleVfxExtra):
        try:
            vehicle_extra_flag_text(model.extras)
        except (TypeError, ValueError) as exc:
            report.issue("vehicle.extras.invalid", str(exc), path="extras")
    elif isinstance(model, HandlingData):
        _identifier(
            report, model.name, code="vehicle.handling_name.required", path="name"
        )
        if model.mass <= 0.0:
            report.issue(
                "vehicle.handling.mass.invalid",
                "Vehicle mass must be greater than zero",
                path="mass",
            )
    elif isinstance(model, VehicleVariation):
        _identifier(
            report,
            model.model_name,
            code="vehicle.variation.model_name.required",
            path="model_name",
        )
    elif isinstance(model, VehicleColorIndices):
        maximum = 6 if context is not None and context.game is GameTarget.GTA5 else 7
        if len(model.indices) > maximum:
            report.issue(
                "vehicle.color.indices.limit",
                f"A vehicle color set cannot contain more than {maximum} indices",
                path="indices",
            )
        for index, color_index in enumerate(model.indices):
            if not 0 <= color_index <= 0xFF:
                report.issue(
                    "vehicle.color.index.out_of_range",
                    "Vehicle color indices must fit an unsigned byte",
                    path=f"indices[{index}]",
                )
    elif isinstance(model, LicensePlateProbability) and model.weight < 0:
        report.issue(
            "vehicle.plate_probability.weight.invalid",
            "License plate probability weights cannot be negative",
            path="weight",
        )
    elif isinstance(model, VehicleModelColor):
        if not 0 <= model.color <= 0xFFFFFFFF:
            report.issue(
                "vehicle.color.value.out_of_range",
                "Packed vehicle colors must fit ARGB8",
                path="color",
            )
        if not -1 <= model.metallic_id <= 0xFF:
            report.issue(
                "vehicle.color.metallic_id.out_of_range",
                "Vehicle metallic IDs must be -1 or fit an unsigned byte",
                path="metallic_id",
            )
    elif isinstance(model, VehicleLightSettings) and not 0 <= model.id <= 0xFF:
        report.issue(
            "vehicle.light.id.out_of_range",
            "Light setting IDs must fit an unsigned byte",
            path="id",
        )
    elif isinstance(model, VehicleSirenSettings) and not 0 <= model.id <= 0xFF:
        report.issue(
            "vehicle.siren.id.out_of_range",
            "Siren setting IDs must fit an unsigned byte",
            path="id",
        )
    elif isinstance(model, VehicleModKit) and not 0 <= model.id <= 0xFFFF:
        report.issue(
            "vehicle.mod_kit.id.out_of_range",
            "Mod kit IDs must fit an unsigned short",
            path="id",
        )

    if isinstance(model, VehicleInitDataList):
        _duplicate_identifiers(
            report,
            [vehicle.model_name for vehicle in model.vehicles],
            code="vehicle.model_name.duplicate",
            path="vehicles",
        )
        _validate_vehicle_references(report, model, context)
    elif isinstance(model, HandlingDataManager):
        _duplicate_identifiers(
            report,
            [str(entry.name) for entry in model.entries],
            code="vehicle.handling_name.duplicate",
            path="entries",
        )
    elif isinstance(model, VehicleModelInfoVariation):
        _duplicate_identifiers(
            report,
            [vehicle.model_name for vehicle in model.vehicles],
            code="vehicle.variation.model_name.duplicate",
            path="vehicles",
            severity=DiagnosticSeverity.WARNING,
        )
        _validate_variation_references(report, model, context)
    elif isinstance(model, VehicleCarCols):
        if len(model.colors) > 0x100:
            report.issue(
                "vehicle.colors.limit",
                "Vehicle color tables cannot contain more than 256 entries",
                path="colors",
            )
        seen_colors: dict[int, int] = {}
        for index, color in enumerate(model.colors):
            previous = seen_colors.get(color.color)
            if previous is not None:
                report.issue(
                    "vehicle.color.duplicate",
                    f"Packed color duplicates colors[{previous}]",
                    path=f"colors[{index}]",
                    severity=DiagnosticSeverity.ERROR,
                )
            else:
                seen_colors[color.color] = index

    _validate_children(report, model, context=context)
    return report


__all__ = ["validate_vehicle_meta_model"]
