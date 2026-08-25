from __future__ import annotations

from pathlib import Path
from typing import Any

from ..authoring import Diagnostic, DiagnosticSeverity
from ..gamefile import GameFileType
from ..metahash import MetaHash
from ..vehiclemeta.appearance import (
    VehicleAppearanceSource,
    VehicleAppearanceSourceTier,
)
from ..vehiclemeta.carcols import VehicleModelColor
from ..vehiclemeta.variations import (
    LicensePlateProbability,
    VehicleColorIndices,
    VehicleVariation,
)
from .sidecar_binary import SidecarReader, SidecarWriter
from .sidecars import load_sidecar_payload, save_sidecar_payload, sidecar_path

_MAGIC = b"FFVEH001"
_MAX_ENTRIES = 1_000_000
_MAX_ITEMS = 4096


def vehicle_appearance_index_path(index_path: str | Path) -> Path:
    return sidecar_path(index_path, "veh")


def _write_hash(writer: SidecarWriter, value: MetaHash) -> None:
    raw = value.raw
    if isinstance(raw, str):
        writer.u8(1)
        writer.text(raw)
    else:
        writer.u8(0)
        writer.u32(raw)


def _read_hash(reader: SidecarReader) -> MetaHash:
    kind = reader.u8()
    if kind == 0:
        return MetaHash(reader.u32())
    if kind == 1:
        return MetaHash(reader.text())
    raise ValueError("Invalid vehicle sidecar hash encoding")


def _write_source(writer: SidecarWriter, source: VehicleAppearanceSource) -> None:
    writer.text(source.path)
    writer.i32(int(source.kind))
    writer.u8(int(source.tier))


def _read_source(reader: SidecarReader) -> VehicleAppearanceSource:
    return VehicleAppearanceSource(
        path=reader.text(),
        kind=GameFileType(reader.i32()),
        tier=VehicleAppearanceSourceTier(reader.u8()),
    )


def _write_variation(writer: SidecarWriter, variation: VehicleVariation) -> None:
    writer.text(variation.model_name)
    writer.count(len(variation.colors), _MAX_ITEMS)
    for color in variation.colors:
        writer.count(len(color.indices), _MAX_ITEMS)
        for value in color.indices:
            writer.i32(value)
        writer.count(len(color.liveries), _MAX_ITEMS)
        for value in color.liveries:
            writer.u8(value)
    for values in (variation.kits, variation.windows_with_exposed_edges):
        writer.count(len(values), _MAX_ITEMS)
        for value in values:
            _write_hash(writer, value)
    writer.count(len(variation.plate_probabilities), _MAX_ITEMS)
    for probability in variation.plate_probabilities:
        _write_hash(writer, probability.name)
        writer.i32(probability.weight)
    writer.i32(variation.light_settings)
    writer.i32(variation.siren_settings)


def _read_variation(reader: SidecarReader) -> VehicleVariation:
    colors = []
    model_name = reader.text()
    for _ in range(reader.count(_MAX_ITEMS)):
        indices = [reader.i32() for _ in range(reader.count(_MAX_ITEMS))]
        liveries = [bool(reader.u8()) for _ in range(reader.count(_MAX_ITEMS))]
        colors.append(VehicleColorIndices(indices, liveries))
    kits = [_read_hash(reader) for _ in range(reader.count(_MAX_ITEMS))]
    windows = [_read_hash(reader) for _ in range(reader.count(_MAX_ITEMS))]
    probabilities = [
        LicensePlateProbability(_read_hash(reader), reader.i32())
        for _ in range(reader.count(_MAX_ITEMS))
    ]
    return VehicleVariation(
        model_name=model_name,
        colors=colors,
        kits=kits,
        windows_with_exposed_edges=windows,
        plate_probabilities=probabilities,
        light_settings=reader.i32(),
        siren_settings=reader.i32(),
    )


def _write_color(writer: SidecarWriter, color: VehicleModelColor) -> None:
    writer.u32(color.color)
    writer.i32(color.metallic_id)
    writer.i32(color.audio_color)
    writer.i32(color.audio_prefix)
    writer.u32(color.audio_color_hash)
    writer.u32(color.audio_prefix_hash)
    writer.text(color.name)


def _read_color(reader: SidecarReader) -> VehicleModelColor:
    return VehicleModelColor(
        color=reader.u32(),
        metallic_id=reader.i32(),
        audio_color=reader.i32(),
        audio_prefix=reader.i32(),
        audio_color_hash=reader.u32(),
        audio_prefix_hash=reader.u32(),
        name=reader.text(),
    )


def _write_optional_text(writer: SidecarWriter, value: str | None) -> None:
    writer.u8(value is not None)
    if value is not None:
        writer.text(value)


def _read_optional_text(reader: SidecarReader) -> str | None:
    present = reader.u8()
    if present not in (0, 1):
        raise ValueError("Invalid optional string marker")
    return reader.text() if present else None


def load_vehicle_appearance_index(index_path: str | Path) -> Any | None:
    payload = load_sidecar_payload(index_path, "veh", _MAGIC)
    if payload is None:
        return None
    reader = SidecarReader(payload)
    try:
        variations = {}
        for _ in range(reader.count(_MAX_ENTRIES)):
            model_hash = reader.u32()
            variations[model_hash] = (_read_variation(reader), _read_source(reader))
        colors = {}
        for _ in range(reader.count(_MAX_ENTRIES)):
            color_index = reader.i32()
            colors[color_index] = (_read_color(reader), _read_source(reader))
        diagnostics = tuple(
            Diagnostic(
                code=reader.text(),
                message=reader.text(),
                severity=DiagnosticSeverity(reader.u8()),
                asset=_read_optional_text(reader),
                path=_read_optional_text(reader),
            )
            for _ in range(reader.count(_MAX_ENTRIES))
        )
        reader.finish()
    except (ValueError, OverflowError):
        return None
    from .vehicle_appearance import _VehicleAppearanceIndex

    return _VehicleAppearanceIndex(variations, colors, diagnostics)


def save_vehicle_appearance_index(index_path: str | Path, index: Any) -> Path | None:
    writer = SidecarWriter()
    writer.count(len(index.variations), _MAX_ENTRIES)
    for model_hash, (variation, source) in sorted(index.variations.items()):
        writer.u32(model_hash)
        _write_variation(writer, variation)
        _write_source(writer, source)
    writer.count(len(index.colors), _MAX_ENTRIES)
    for color_index, (color, source) in sorted(index.colors.items()):
        writer.i32(color_index)
        _write_color(writer, color)
        _write_source(writer, source)
    writer.count(len(index.diagnostics), _MAX_ENTRIES)
    for diagnostic in index.diagnostics:
        writer.text(diagnostic.code)
        writer.text(diagnostic.message)
        writer.u8(int(diagnostic.severity))
        _write_optional_text(writer, diagnostic.asset)
        _write_optional_text(writer, diagnostic.path)
    return save_sidecar_payload(index_path, "veh", _MAGIC, writer.to_bytes())


__all__ = [
    "load_vehicle_appearance_index",
    "save_vehicle_appearance_index",
    "vehicle_appearance_index_path",
]
