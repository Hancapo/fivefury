from __future__ import annotations

from typing import TYPE_CHECKING

from ...authoring import DiagnosticSeverity
from ..payloads import CutVehicleVariationPayload
from .models import CutsceneResolveIssue, ResolvedCutBinding
from .runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)

if TYPE_CHECKING:
    from ...cache import GameFileCache
    from ..scene import CutScene


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
