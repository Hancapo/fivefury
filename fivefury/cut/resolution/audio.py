from __future__ import annotations

from typing import TYPE_CHECKING

from ...gamefile import GameFileType
from ..audio_references import (
    cut_audio_asset_reference_hashes,
    cut_audio_hint_rank,
    cut_audio_reference_hash,
)
from .common import _load_file, _source_rank
from .models import CutsceneResolveIssue, ResolvedCutAudio
from .runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache


def _resolve_audio(
    cache: GameFileCache,
    references: tuple[str | int, ...],
    issues: list[CutsceneResolveIssue],
    *,
    container_hints: dict[str | int, tuple[str, ...]] | None = None,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> dict[str | int, ResolvedCutAudio]:
    if not references:
        return {}
    references_by_hash: dict[int, list[str | int]] = {}
    for reference in references:
        references_by_hash.setdefault(cut_audio_reference_hash(reference), []).append(
            reference
        )

    candidates: dict[str | int, dict[int, tuple[AssetRecord, int]]] = {
        reference: {} for reference in references
    }
    hints_by_reference = container_hints or {}
    for asset in cache.iter_assets(GameFileType.AWC):
        check_cutscene_resolution_cancelled(cancellation)
        for candidate_hash in cut_audio_asset_reference_hashes(asset):
            for reference in references_by_hash.get(candidate_hash, ()):
                candidates[reference][asset.id] = (asset, 0)
        for reference, hints in hints_by_reference.items():
            hint_rank = cut_audio_hint_rank(asset, hints)
            if hint_rank is not None:
                current = candidates[reference].get(asset.id)
                if current is None or hint_rank < current[1]:
                    candidates[reference][asset.id] = (asset, hint_rank)

    result: dict[str | int, ResolvedCutAudio] = {}
    for reference in references:
        check_cutscene_resolution_cancelled(cancellation)
        matches = tuple(candidates[reference].values())
        if not matches:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="audio.container_unresolved",
                    message=f"No AWC container matched CUT audio cue {reference!s}",
                )
            )
            continue
        asset, _hint_rank = min(
            matches,
            key=lambda item: (
                _source_rank(item[0])[0],
                item[1],
                _source_rank(item[0])[1],
            ),
        )
        game_file = _load_file(cache, asset, issues)
        awc = game_file.parsed if game_file is not None else None
        if awc is None or not hasattr(awc, "wav_bytes"):
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="audio.container_invalid",
                    message=f"Asset is not a decoded AWC: {asset.path}",
                    asset_path=asset.path,
                )
            )
            continue
        hints = hints_by_reference.get(reference, ())
        result[reference] = ResolvedCutAudio(
            reference,
            asset,
            game_file,
            container_reference=hints[0] if hints else None,
        )
    return result
