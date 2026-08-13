from __future__ import annotations

from typing import TYPE_CHECKING

from ...cache.precedence import asset_source_rank, preferred_asset
from ...gamefile import GameFile, GameFileType
from .models import CutsceneResolveIssue

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache


def _source_rank(asset: AssetRecord) -> tuple[int, str]:
    return asset_source_rank(asset)


def _preferred_asset(
    cache: GameFileCache, value: int, kind: GameFileType
) -> AssetRecord | None:
    return preferred_asset(cache, value, kind)


def _load_file(
    cache: GameFileCache,
    asset: AssetRecord,
    issues: list[CutsceneResolveIssue],
    *,
    object_id: int | None = None,
) -> GameFile | None:
    try:
        result = cache.load_asset(asset)
    except Exception as exc:
        issues.append(
            CutsceneResolveIssue(
                severity="warning",
                code="asset.load_failed",
                message=f"Unable to load {asset.path}: {type(exc).__name__}: {exc}",
                asset_path=asset.path,
                object_id=object_id,
            )
        )
        return None
    if result is None:
        issues.append(
            CutsceneResolveIssue(
                severity="warning",
                code="asset.load_failed",
                message=f"Unable to load {asset.path}",
                asset_path=asset.path,
                object_id=object_id,
            )
        )
    return result
