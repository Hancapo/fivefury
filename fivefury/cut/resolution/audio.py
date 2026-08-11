from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ...gamefile import GameFileType
from ...metahash import MetaHash
from ..scene import CutScene
from .common import _load_file, _source_rank
from .models import CutsceneResolveIssue, ResolvedCutAudio
from .values import field_reference

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache


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


def _resolve_audio(
    cache: GameFileCache,
    references: tuple[str | int, ...],
    issues: list[CutsceneResolveIssue],
) -> dict[str | int, ResolvedCutAudio]:
    if not references:
        return {}
    references_by_hash: dict[int, list[str | int]] = {}
    for reference in references:
        references_by_hash.setdefault(_audio_reference_hash(reference), []).append(
            reference
        )

    candidates: dict[str | int, list[AssetRecord]] = {
        reference: [] for reference in references
    }
    for asset in cache.iter_assets(GameFileType.AWC):
        for candidate_hash in _audio_asset_reference_hashes(asset):
            for reference in references_by_hash.get(candidate_hash, ()):
                candidates[reference].append(asset)

    result: dict[str | int, ResolvedCutAudio] = {}
    for reference in references:
        matches = candidates[reference]
        if not matches:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="audio.container_unresolved",
                    message=f"No AWC container matched CUT audio cue {reference!s}",
                )
            )
            continue
        asset = min(matches, key=_source_rank)
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
        result[reference] = ResolvedCutAudio(reference, asset, game_file)
    return result
