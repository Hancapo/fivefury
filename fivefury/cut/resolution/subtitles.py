from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ...gamefile import GameFile, GameFileType
from ..scene import CutScene
from .common import _source_rank
from .models import CutsceneResolveIssue, ResolvedCutSubtitleDictionary
from .runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)
from .values import field_reference, subtitle_hash

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache


def _subtitle_requests(scene: CutScene) -> dict[str | int, set[int]]:
    requests: dict[str | int, set[int]] = {}
    active: list[str | int] = []
    for event in scene.timeline:
        if event.event_name == "load_subtitles":
            reference = field_reference(event.payload.get("cName"))
            if reference is not None:
                requests.setdefault(reference, set())
                if reference not in active:
                    active.append(reference)
        elif event.event_name == "unload_subtitles":
            reference = field_reference(event.payload.get("cName"))
            if reference in active:
                active.remove(reference)
        elif event.event_name == "show_subtitle":
            key_hash = subtitle_hash(event.payload.get("cName"))
            if key_hash is not None:
                for reference in active:
                    requests.setdefault(reference, set()).add(key_hash)
    return requests


def _subtitle_asset_language(asset: AssetRecord) -> str | None:
    path = asset.path.replace("\\", "/").lower()
    match = re.search(r"/data/lang/([^/]+)\.rpf/", path)
    if match is None:
        return None
    archive_name = match.group(1)
    if archive_name.endswith("_rel"):
        return archive_name[:-4]
    if archive_name.endswith("dlc"):
        return archive_name[:-3]
    return archive_name


def _subtitle_candidates(
    cache: GameFileCache,
    reference: str | int,
    *,
    language: str,
) -> list[AssetRecord]:
    if isinstance(reference, int):
        candidates = cache.find_hash(reference, kind=GameFileType.GXT2)
    else:
        reference_stem = PurePosixPath(reference.replace("\\", "/")).stem.casefold()
        candidates = cache.find_stem_prefix(reference_stem, kind=GameFileType.GXT2)
        candidates = [
            asset
            for asset in candidates
            if asset.stem.casefold().startswith(reference_stem)
        ]
    requested_language = language.casefold()
    matching_language = [
        asset
        for asset in candidates
        if _subtitle_asset_language(asset) == requested_language
    ]
    if matching_language:
        neutral = [
            asset for asset in candidates if _subtitle_asset_language(asset) is None
        ]
        candidates = [*matching_language, *neutral]
    unique: dict[str, AssetRecord] = {}
    for asset in candidates:
        unique.setdefault(asset.path.casefold(), asset)
    return list(unique.values())


def _resolve_subtitle_dictionaries(
    cache: GameFileCache,
    scene: CutScene,
    issues: list[CutsceneResolveIssue],
    *,
    language: str,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> dict[str | int, ResolvedCutSubtitleDictionary]:
    result: dict[str | int, ResolvedCutSubtitleDictionary] = {}
    for reference, expected_hashes in _subtitle_requests(scene).items():
        check_cutscene_resolution_cancelled(cancellation)
        candidates = _subtitle_candidates(cache, reference, language=language)
        if not candidates:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="subtitle.dictionary_unresolved",
                    message=(
                        f"No {language} GXT2 dictionary matched subtitle block "
                        f"{reference!s}"
                    ),
                )
            )
            continue

        loaded: dict[int, GameFile] = {}
        groups: dict[str, list[AssetRecord]] = {}
        for asset in candidates:
            check_cutscene_resolution_cancelled(cancellation)
            try:
                game_file = cache.load_asset(asset)
            except Exception as exc:
                game_file = None
                _ = exc
            if game_file is None or game_file.parsed is None:
                continue
            loaded[asset.id] = game_file
            groups.setdefault(asset.stem.casefold(), []).append(asset)

        if not groups:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="subtitle.dictionary_unresolved",
                    message=f"Unable to decode subtitle block {reference!s}",
                )
            )
            continue

        reference_stem = (
            PurePosixPath(reference.replace("\\", "/")).stem.casefold()
            if isinstance(reference, str)
            else ""
        )

        def group_rank(
            item: tuple[str, list[AssetRecord]],
            *,
            expected: frozenset[int] = frozenset(expected_hashes),
            decoded: dict[int, GameFile] = loaded,
            requested_stem: str = reference_stem,
        ) -> tuple[int, int, int, str]:
            stem, assets = item
            coverage = len(
                {
                    key_hash
                    for asset in assets
                    for key_hash in expected
                    if decoded[asset.id].parsed.get(key_hash) is not None
                }
            )
            exact_rank = 0 if stem == requested_stem else 1
            suffix_length = max(0, len(stem) - len(requested_stem))
            return -coverage, exact_rank, suffix_length, stem

        _, selected_assets = min(groups.items(), key=group_rank)
        selected_assets.sort(key=_source_rank)
        selected_files = tuple(loaded[asset.id] for asset in selected_assets)
        dictionary = ResolvedCutSubtitleDictionary(
            reference=reference,
            language=language,
            assets=tuple(selected_assets),
            files=selected_files,
        )
        result[reference] = dictionary
        for key_hash in sorted(expected_hashes):
            if dictionary.get(key_hash) is None:
                issues.append(
                    CutsceneResolveIssue(
                        severity="warning",
                        code="subtitle.label_unresolved",
                        message=(
                            f"Subtitle 0x{key_hash:08X} is absent from "
                            f"{selected_assets[0].stem} ({language})"
                        ),
                        asset_path=selected_assets[0].path,
                    )
                )
    return result
