from __future__ import annotations

from typing import TYPE_CHECKING

from ...awc.structures import Awc
from ...awc.validation import validate_awc_stream
from ...gamefile import GameFileType
from ..audio_references import (
    cut_audio_asset_reference_hashes,
    cut_audio_hint_names,
    cut_audio_hint_rank,
    cut_audio_reference_hash,
    resolve_cut_audio_sound_graph,
)
from .common import _load_file, _source_rank
from .models import CutsceneResolveIssue, ResolvedCutAudio
from .runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache
    from ...rel import RelSoundGraph, RelSoundIndex


def _audio_candidates(
    cache: GameFileCache,
    references: tuple[str | int, ...],
    hints_by_reference: dict[str | int, tuple[str, ...]],
    cancellation: CutsceneResolutionCancellation | None,
) -> dict[str | int, dict[int, tuple[AssetRecord, int]]]:
    candidates: dict[str | int, dict[int, tuple[AssetRecord, int]]] = {
        reference: {} for reference in references
    }
    find_hashes = getattr(cache, "find_hashes", None)
    find_names = getattr(cache, "find_names", None)
    if callable(find_hashes) and callable(find_names):
        references_by_hash: dict[int, list[str | int]] = {}
        for reference in references:
            references_by_hash.setdefault(
                cut_audio_reference_hash(reference), []
            ).append(reference)
        for hash_value, assets in find_hashes(
            tuple(references_by_hash),
            kind=GameFileType.AWC,
        ).items():
            for reference in references_by_hash.get(hash_value, ()):
                for asset in assets:
                    candidates[reference][asset.id] = (asset, 0)
        names = tuple(
            dict.fromkeys(
                name
                for hints in hints_by_reference.values()
                for name in cut_audio_hint_names(hints)
            )
        )
        assets_by_name = find_names(names, kind=GameFileType.AWC) if names else {}
        for reference, hints in hints_by_reference.items():
            for name in cut_audio_hint_names(hints):
                for asset in assets_by_name.get(name, ()):
                    rank = cut_audio_hint_rank(asset, hints)
                    if rank is None:
                        continue
                    current = candidates[reference].get(asset.id)
                    if current is None or rank < current[1]:
                        candidates[reference][asset.id] = (asset, rank)
        return candidates

    references_by_hash: dict[int, list[str | int]] = {}
    for reference in references:
        references_by_hash.setdefault(cut_audio_reference_hash(reference), []).append(
            reference
        )
    for asset in cache.iter_assets(GameFileType.AWC):
        check_cutscene_resolution_cancelled(cancellation)
        for candidate_hash in cut_audio_asset_reference_hashes(asset):
            for reference in references_by_hash.get(candidate_hash, ()):
                candidates[reference][asset.id] = (asset, 0)
        for reference, hints in hints_by_reference.items():
            rank = cut_audio_hint_rank(asset, hints)
            if rank is None:
                continue
            current = candidates[reference].get(asset.id)
            if current is None or rank < current[1]:
                candidates[reference][asset.id] = (asset, rank)
    return candidates


def _rel_sound_index(cache: GameFileCache) -> RelSoundIndex | None:
    ensure = getattr(cache, "ensure_rel_sound_index", None)
    if not callable(ensure):
        return None
    return ensure()


def _endpoint_assets(
    cache: GameFileCache,
    graph: RelSoundGraph,
) -> tuple[AssetRecord, ...]:
    find_hash = getattr(cache, "find_hash", None)
    if callable(find_hash):
        matches = [
            asset
            for endpoint in graph.endpoints
            for asset in find_hash(endpoint.container_hash, kind=GameFileType.AWC)
        ]
    else:
        matches = [
            asset
            for asset in cache.iter_assets(GameFileType.AWC)
            if any(
                endpoint.container_hash in cut_audio_asset_reference_hashes(asset)
                for endpoint in graph.endpoints
            )
        ]
    return tuple({asset.id: asset for asset in matches}.values())


def _resolved_audio(
    cache: GameFileCache,
    reference: str | int,
    asset: AssetRecord,
    issues: list[CutsceneResolveIssue],
    *,
    container_reference: str | None = None,
    sound_hashes: tuple[int, ...] = (),
    stream_hashes: tuple[int, ...] = (),
) -> ResolvedCutAudio | None:
    game_file = _load_file(cache, asset, issues)
    awc = game_file.parsed if game_file is not None else None
    if not isinstance(awc, Awc):
        issues.append(
            CutsceneResolveIssue(
                severity="warning",
                code="audio.container_invalid",
                message=f"Asset is not a decoded AWC: {asset.path}",
                asset_path=asset.path,
            )
        )
        return None
    resolved = ResolvedCutAudio(
        reference,
        asset,
        game_file,
        container_reference=container_reference,
        sound_hashes=tuple(int(value) & 0xFFFFFFFF for value in sound_hashes),
        stream_hashes=tuple(int(value) & 0xFFFFFFFF for value in stream_hashes),
    )
    unresolved_stream_hashes = resolved.unresolved_stream_hashes
    for stream_hash in unresolved_stream_hashes:
        issues.append(
            CutsceneResolveIssue(
                severity="warning",
                code="audio.stream_unresolved",
                message=f"AWC {asset.path} has no stream 0x{stream_hash:08X}",
                asset_path=asset.path,
            )
        )
    stream = resolved.stream
    if stream is None:
        if unresolved_stream_hashes and len(unresolved_stream_hashes) == len(
            resolved.stream_hashes
        ):
            return resolved
        candidates = ", ".join(
            f"0x{value:08X}" for value in resolved.stream_ambiguity
        )
        issues.append(
            CutsceneResolveIssue(
                severity="warning",
                code="audio.stream_unresolved",
                message=(
                    f"AWC {asset.path} has no unambiguous stream for cue {reference!s}"
                    + (f": {candidates}" if candidates else "")
                ),
                asset_path=asset.path,
            )
        )
        return resolved
    for diagnostic in validate_awc_stream(awc, stream):
        issues.append(
            CutsceneResolveIssue(
                severity="warning",
                code=f"audio.{diagnostic.code}",
                message=diagnostic.message,
                asset_path=asset.path,
            )
        )
    return resolved


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
    hints_by_reference = container_hints or {}
    direct_candidates = _audio_candidates(
        cache,
        references,
        hints_by_reference,
        cancellation,
    )
    sound_index = _rel_sound_index(cache)
    result: dict[str | int, ResolvedCutAudio] = {}
    for reference in references:
        check_cutscene_resolution_cancelled(cancellation)
        graph = (
            resolve_cut_audio_sound_graph(sound_index, reference)
            if sound_index is not None
            else None
        )
        if graph is not None:
            for unresolved_hash in graph.unresolved_hashes:
                issues.append(
                    CutsceneResolveIssue(
                        severity="warning",
                        code="audio.sound_child_unresolved",
                        message=f"REL sound graph references missing sound 0x{unresolved_hash:08X}",
                    )
                )
            if not graph.endpoints:
                issues.append(
                    CutsceneResolveIssue(
                        severity="warning",
                        code="audio.sound_no_stream",
                        message=f"REL sound for CUT audio cue {reference!s} resolves to no AWC stream",
                    )
                )

        matches = tuple(direct_candidates[reference].values())
        if not matches and graph is not None:
            matches = tuple((asset, 2) for asset in _endpoint_assets(cache, graph))
        if not matches:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="audio.container_unresolved",
                    message=f"No AWC container matched CUT audio cue {reference!s}",
                )
            )
            continue
        asset, _rank = min(
            matches,
            key=lambda item: (
                _source_rank(item[0])[0],
                item[1],
                _source_rank(item[0])[1],
            ),
        )
        hints = hints_by_reference.get(reference, ())
        resolved = _resolved_audio(
            cache,
            reference,
            asset,
            issues,
            container_reference=hints[0] if hints else None,
            sound_hashes=graph.sound_hashes if graph is not None else (),
            stream_hashes=graph.stream_hashes if graph is not None else (),
        )
        if resolved is not None:
            result[reference] = resolved
    return result
