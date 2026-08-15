from __future__ import annotations

from typing import TYPE_CHECKING

from ...authoring import DiagnosticSeverity
from ...gamefile import GameFileType
from ..payloads import CutVehicleVariationPayload
from .common import _load_file, _source_rank
from .models import CutsceneResolveIssue, ResolvedCutBinding
from .runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache
    from ...gamefile import GameFile
    from ..scene import CutScene


def _resolve_vehicle_high_detail_models(
    cache: GameFileCache,
    bindings: dict[int, ResolvedCutBinding],
    issues: list[CutsceneResolveIssue],
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> None:
    assets_by_stem: dict[str, AssetRecord | None] = {}
    files_by_asset: dict[int, GameFile | None] = {}
    for object_id, resolved in bindings.items():
        check_cutscene_resolution_cancelled(cancellation)
        if resolved.binding.role != "vehicle":
            continue
        base_asset = resolved.assets.get(GameFileType.YFT)
        if base_asset is None:
            continue
        companion_stem = f"{base_asset.stem.casefold()}_hi"
        if companion_stem not in assets_by_stem:
            candidates = (
                asset
                for asset in cache.find_assets(
                    companion_stem,
                    kind=GameFileType.YFT,
                )
                if asset.stem.casefold() == companion_stem
            )
            assets_by_stem[companion_stem] = min(
                candidates,
                key=_source_rank,
                default=None,
            )
        asset = assets_by_stem[companion_stem]
        if asset is None:
            continue
        if asset.id not in files_by_asset:
            files_by_asset[asset.id] = _load_file(
                cache,
                asset,
                issues,
                object_id=object_id,
                issue_code="binding.vehicle_high_detail_invalid",
            )
        game_file = files_by_asset[asset.id]
        if game_file is None:
            continue
        resolved.high_detail_model_asset = asset
        resolved.high_detail_model_file = game_file


def _vehicle_variations(scene: CutScene) -> dict[int, CutVehicleVariationPayload]:
    result: dict[int, CutVehicleVariationPayload] = {}
    for event in scene.timeline:
        if event.event_name != "set_variation":
            continue
        fields = event.payload
        object_id = fields.get("iObjectId", event.target_id)
        if not isinstance(object_id, int) or object_id in result:
            continue
        binding = scene.get_binding(object_id)
        if binding is None or binding.role != "vehicle":
            continue
        result[object_id] = CutVehicleVariationPayload(
            object_id=object_id,
            main_body_colour=int(fields.get("iMainBodyColour", 0)),
            second_body_colour=int(fields.get("iSecondBodyColour", 0)),
            specular_colour=int(fields.get("iSpecularColour", 0)),
            wheel_trim_colour=int(fields.get("iWheelTrimColour", 0)),
            body_colour_5=int(fields.get("iBodyColour5", 0)),
            livery=int(fields.get("iLivery", 0)),
            livery_2=int(fields.get("iLivery2", 0)),
            dirt_level=float(fields.get("fDirtLevel", 0.0)),
        )
    return result


def _resolve_vehicle_appearances(
    cache: GameFileCache,
    scene: CutScene,
    bindings: dict[int, ResolvedCutBinding],
    issues: list[CutsceneResolveIssue],
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> None:
    variations = _vehicle_variations(scene)
    for object_id, resolved in bindings.items():
        check_cutscene_resolution_cancelled(cancellation)
        if resolved.binding.role != "vehicle" or resolved.reference_hash is None:
            continue
        appearance = cache.resolve_vehicle_appearance(
            resolved,
            variation=variations.get(object_id),
        )
        resolved.vehicle_appearance = appearance
        for diagnostic in appearance.diagnostics:
            issues.append(
                CutsceneResolveIssue(
                    severity=(
                        "error"
                        if diagnostic.severity >= DiagnosticSeverity.ERROR
                        else "warning"
                        if diagnostic.severity >= DiagnosticSeverity.WARNING
                        else "info"
                    ),
                    code=diagnostic.code,
                    message=diagnostic.message,
                    asset_path=diagnostic.asset,
                    object_id=object_id,
                )
            )


__all__ = []
