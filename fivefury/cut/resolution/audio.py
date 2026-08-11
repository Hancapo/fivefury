from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ...gamefile import GameFileType
from ...metahash import MetaHash
from ..scene import CutScene
from .common import _load_file, _source_rank
from .models import CutsceneResolveIssue, ResolvedCutAudio
from .runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)
from .values import field_reference

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache


_AUDIO_CONTAINER_VARIANTS = (
    "_edited",
    "_mastered",
    "_mastered_only",
    "_mastered_replay",
    "_mastered_replay_only",
    "_mastered_trimmed",
)


def _event_references(scene: CutScene, names: set[str]) -> tuple[str | int, ...]:
    values: list[str | int] = []
    seen: set[str | int] = set()
    for event in scene.timeline:
        if event.event_name not in names:
            continue
        value = field_reference(event.payload.get("cName"))
        if value is not None and value not in seen:
            seen.add(value)
            values.append(value)
    return tuple(values)


def _audio_reference_hash(reference: str | int) -> int:
    if isinstance(reference, str):
        stem = PurePosixPath(reference.replace("\\", "/")).stem.casefold()
        return MetaHash(stem).uint
    return int(reference) & 0xFFFFFFFF


def _audio_asset_reference_hashes(asset: AssetRecord) -> tuple[int, ...]:
    stem = asset.stem.casefold()
    names = [stem]
    for suffix in ("_mastered_only", "_seq_mastered_only"):
        if stem.endswith(suffix):
            names.append(stem[: -len(suffix)])
    return tuple(dict.fromkeys(MetaHash(name).uint for name in names if name))


def _normalize_audio_container_hint(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = PurePosixPath(value.strip().replace("\\", "/"))
    name = path.name.casefold()
    if name.endswith((".wa", ".awc")):
        name = name.rsplit(".", 1)[0]
    return name or None


def _audio_container_hints(
    scene: CutScene,
    references: tuple[str | int, ...],
) -> dict[str | int, tuple[str, ...]]:
    wanted = set(references)
    bindings = {binding.object_id: binding for binding in scene.bindings}
    hints: dict[str | int, list[str]] = {reference: [] for reference in references}
    for event in scene.timeline:
        if event.event_name not in {"load_audio", "play_audio"}:
            continue
        reference = field_reference(event.payload.get("cName"))
        if reference not in wanted:
            continue
        binding = bindings.get(event.target_id)
        values = (
            event.target_name,
            getattr(binding, "name", None),
            getattr(binding, "fields", {}).get("cName") if binding is not None else None,
        )
        for value in values:
            hint = _normalize_audio_container_hint(value)
            if hint is not None and hint not in hints[reference]:
                hints[reference].append(hint)
    return {reference: tuple(values) for reference, values in hints.items()}


def _audio_hint_rank(asset: AssetRecord, hints: tuple[str, ...]) -> int | None:
    stem = asset.stem.casefold()
    for hint in hints:
        if stem == hint:
            return 0
        if not stem.startswith(f"{hint}_"):
            continue
        remainder = stem[len(hint) :]
        if remainder.endswith(_AUDIO_CONTAINER_VARIANTS):
            return 1
    return None


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
        references_by_hash.setdefault(_audio_reference_hash(reference), []).append(
            reference
        )

    candidates: dict[str | int, dict[int, tuple[AssetRecord, int]]] = {
        reference: {} for reference in references
    }
    hints_by_reference = container_hints or {}
    for asset in cache.iter_assets(GameFileType.AWC):
        check_cutscene_resolution_cancelled(cancellation)
        for candidate_hash in _audio_asset_reference_hashes(asset):
            for reference in references_by_hash.get(candidate_hash, ()):
                candidates[reference][asset.id] = (asset, 0)
        for reference, hints in hints_by_reference.items():
            hint_rank = _audio_hint_rank(asset, hints)
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
