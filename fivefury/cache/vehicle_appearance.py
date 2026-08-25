from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from ..authoring import Diagnostic, DiagnosticSeverity
from ..colors import parse_css_rgba, srgb_rgba_to_linear
from ..gamefile import GameFileType
from ..hashing import jenk_hash
from ..metahash import MetaHash
from ..vehiclemeta.appearance import (
    ResolvedVehicleAppearance,
    ResolvedVehicleColor,
    VehicleAppearanceSource,
    VehicleAppearanceSourceTier,
)
from ..vehiclemeta.carcols import VehicleModelColor
from ..vehiclemeta.resource import VehicleMeta
from ..vehiclemeta.variations import VehicleVariation
from .precedence import asset_source_rank

if TYPE_CHECKING:
    from ..cut.payloads import CutVehicleVariationPayload
    from .core import GameFileCache
    from .views import AssetRecord


@dataclass(frozen=True, slots=True)
class _VehicleAppearanceIndex:
    variations: dict[int, tuple[VehicleVariation, VehicleAppearanceSource]]
    colors: dict[int, tuple[VehicleModelColor, VehicleAppearanceSource]]
    diagnostics: tuple[Diagnostic, ...]


def _source(asset: AssetRecord) -> VehicleAppearanceSource:
    tier, _path = asset_source_rank(asset)
    return VehicleAppearanceSource(
        path=asset.path,
        kind=asset.kind,
        tier=VehicleAppearanceSourceTier(tier),
    )


def _build_index(
    cache: GameFileCache,
    cancellation: Any | None = None,
) -> _VehicleAppearanceIndex:
    from ..cut.resolution.runtime import check_cutscene_resolution_cancelled

    variations: dict[int, tuple[VehicleVariation, VehicleAppearanceSource]] = {}
    colors: dict[int, tuple[VehicleModelColor, VehicleAppearanceSource]] = {}
    diagnostics: list[Diagnostic] = []
    assets = [
        *cache.iter_assets(GameFileType.CAR_VARIATIONS),
        *cache.iter_assets(GameFileType.CAR_COLS),
    ]
    for asset in sorted(assets, key=asset_source_rank, reverse=True):
        check_cutscene_resolution_cancelled(cancellation)
        try:
            game_file = cache.load_asset(asset)
        except (OSError, ValueError) as exc:
            diagnostics.append(
                Diagnostic(
                    code="vehicle.appearance.metadata_invalid",
                    message=str(exc),
                    severity=DiagnosticSeverity.WARNING,
                    asset=asset.path,
                )
            )
            continue
        metadata = game_file.parsed if game_file is not None else None
        if not isinstance(metadata, VehicleMeta):
            diagnostics.append(
                Diagnostic(
                    code="vehicle.appearance.metadata_unreadable",
                    message="Vehicle metadata could not be decoded",
                    severity=DiagnosticSeverity.WARNING,
                    asset=asset.path,
                )
            )
            continue
        source = _source(asset)
        expected_content = (
            metadata.variations
            if asset.kind is GameFileType.CAR_VARIATIONS
            else metadata.carcols
        )
        if expected_content is None:
            diagnostics.append(
                Diagnostic(
                    code="vehicle.appearance.metadata_content_mismatch",
                    message=(
                        "Vehicle metadata root does not match its indexed asset type"
                    ),
                    severity=DiagnosticSeverity.WARNING,
                    asset=asset.path,
                )
            )
            continue
        if metadata.variations is not None:
            for variation in metadata.variations.vehicles:
                name = variation.model_name.strip()
                if name:
                    variations[jenk_hash(name.casefold())] = (variation, source)
        if metadata.carcols is not None:
            for index, color in enumerate(metadata.carcols.colors):
                colors[index] = (color, source)
    return _VehicleAppearanceIndex(variations, colors, tuple(diagnostics))


def _index(cache: GameFileCache) -> _VehicleAppearanceIndex:
    cached = cache._vehicle_appearance_index
    if cached is None:
        prepare_vehicle_appearance_index(cache)
        cached = cache._vehicle_appearance_index
    return cached


def prepare_vehicle_appearance_index(
    cache: GameFileCache,
    *,
    cancellation: Any | None = None,
) -> tuple[Any, tuple[Diagnostic, ...]]:
    from .cutscene_preparation import CutsceneIndexPreparationStatus
    from .vehicle_appearance_index import (
        load_vehicle_appearance_index,
        save_vehicle_appearance_index,
    )

    if cache._vehicle_appearance_index is not None:
        return (
            CutsceneIndexPreparationStatus.READY,
            cache._vehicle_appearance_index.diagnostics,
        )
    cached = load_vehicle_appearance_index(cache.get_index_cache_path())
    if cached is not None:
        cache._vehicle_appearance_index = cached
        return CutsceneIndexPreparationStatus.LOADED, cached.diagnostics
    index = _build_index(cache, cancellation)
    save_vehicle_appearance_index(cache.get_index_cache_path(), index)
    cache._vehicle_appearance_index = index
    return CutsceneIndexPreparationStatus.REBUILT, index.diagnostics


def _identity(cache: GameFileCache, value: Any) -> tuple[str | None, int]:
    reference_hash = getattr(value, "reference_hash", None)
    assets = getattr(value, "assets", None)
    if isinstance(assets, dict):
        for kind in (GameFileType.YFT, GameFileType.YDR, GameFileType.YDD):
            asset = assets.get(kind)
            if asset is not None:
                name = asset.stem
                return name, int(reference_hash or jenk_hash(name.casefold()))
    if reference_hash is not None:
        resolved = (
            cache.resolver.resolve(int(reference_hash))
            if cache.resolver is not None
            else None
        )
        name = (
            resolved
            if isinstance(resolved, str) and not resolved.startswith("0x")
            else None
        )
        return name, int(reference_hash)
    if isinstance(value, (int, MetaHash)):
        model_hash = int(value)
        resolved = (
            cache.resolver.resolve(model_hash) if cache.resolver is not None else None
        )
        name = (
            resolved
            if isinstance(resolved, str) and not resolved.startswith("0x")
            else None
        )
        return name, model_hash
    text = str(value).replace("\\", "/")
    name = PurePosixPath(text).stem
    return name, jenk_hash(name.casefold())


def resolve_vehicle_appearance(
    cache: GameFileCache,
    binding_or_model: Any,
    *,
    variation: CutVehicleVariationPayload | None = None,
) -> ResolvedVehicleAppearance:
    model_name, model_hash = _identity(cache, binding_or_model)
    index = _index(cache)
    diagnostics = list(index.diagnostics)
    selected = index.variations.get(model_hash)
    selected_variation = selected[0] if selected is not None else None
    selected_source = selected[1] if selected is not None else None
    if selected_variation is None:
        diagnostics.append(
            Diagnostic(
                code="vehicle.appearance.variation_missing",
                message=f"No carvariations entry matches 0x{model_hash:08X}",
                severity=DiagnosticSeverity.WARNING,
            )
        )
        default_indices: list[int] = []
    else:
        model_name = selected_variation.model_name
        default_indices = (
            list(selected_variation.colors[0].indices)
            if selected_variation.colors
            else []
        )
        if not default_indices:
            diagnostics.append(
                Diagnostic(
                    code="vehicle.appearance.default_colors_missing",
                    message="The selected carvariations entry has no default color set",
                    severity=DiagnosticSeverity.WARNING,
                    asset=selected_source.path if selected_source is not None else None,
                )
            )

    slots: list[int | None] = [
        int(default_indices[position]) if position < len(default_indices) else None
        for position in range(6)
    ]
    livery_index: int | None = None
    secondary_livery_index: int | None = None
    dirt_level: float | None = None
    if variation is not None:
        slots[:5] = [
            int(variation.main_body_colour),
            int(variation.second_body_colour),
            int(variation.specular_colour),
            int(variation.wheel_trim_colour),
            int(variation.body_colour_5),
        ]
        livery_index = int(variation.livery)
        secondary_livery_index = int(variation.livery_2)
        dirt_level = float(variation.dirt_level)

    used_sources: dict[str, VehicleAppearanceSource] = {}
    if selected_source is not None:
        used_sources[selected_source.path] = selected_source

    def resolve_color(
        slot_name: str, color_index: int | None
    ) -> ResolvedVehicleColor | None:
        if color_index is None:
            return None
        entry = index.colors.get(color_index)
        if entry is None:
            diagnostics.append(
                Diagnostic(
                    code="vehicle.appearance.color_index_invalid",
                    message=(
                        f"{slot_name} color index {color_index} is not present in carcols"
                    ),
                    path=slot_name,
                )
            )
            return None
        definition, source = entry
        used_sources[source.path] = source
        srgb = parse_css_rgba(definition.color)
        return ResolvedVehicleColor(
            index=color_index,
            packed_argb=int(definition.color),
            srgb=srgb,
            linear=srgb_rgba_to_linear(srgb),
            metallic_id=int(definition.metallic_id),
            name=definition.name,
            source=source,
            definition=definition,
        )

    resolved_colors = tuple(
        resolve_color(name, color_index)
        for name, color_index in zip(
            ("primary", "secondary", "specular", "wheel_trim", "body_5", "body_6"),
            slots,
            strict=True,
        )
    )
    return ResolvedVehicleAppearance(
        game=cache.game,
        model_name=model_name,
        model_hash=model_hash,
        primary_index=slots[0],
        secondary_index=slots[1],
        specular_index=slots[2],
        wheel_trim_index=slots[3],
        body_5_index=slots[4],
        body_6_index=slots[5],
        primary=resolved_colors[0],
        secondary=resolved_colors[1],
        specular=resolved_colors[2],
        wheel_trim=resolved_colors[3],
        body_5=resolved_colors[4],
        body_6=resolved_colors[5],
        livery_index=livery_index,
        secondary_livery_index=secondary_livery_index,
        dirt_level=dirt_level,
        variation=selected_variation,
        sources=tuple(
            sorted(used_sources.values(), key=lambda item: (item.tier, item.path))
        ),
        diagnostics=tuple(diagnostics),
    )


__all__ = ["resolve_vehicle_appearance"]
