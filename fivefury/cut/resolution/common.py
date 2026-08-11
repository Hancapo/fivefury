from __future__ import annotations

from typing import TYPE_CHECKING

from ...gamefile import GameFile, GameFileType
from .models import CutsceneResolveIssue

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache


def _source_rank(asset: AssetRecord) -> tuple[int, str]:
    path = asset.path.replace("\\", "/").lower()
    if path.startswith("mods/"):
        tier = 0
    elif path.startswith("update/x64/dlcpacks/"):
        tier = 1
    elif path.startswith("update/"):
        tier = 2
    else:
        tier = 3
    return tier, path


def _preferred_asset(
    cache: GameFileCache, value: int, kind: GameFileType
) -> AssetRecord | None:
    matches = cache.find_hash(value, kind=kind)
    return min(matches, key=_source_rank) if matches else None


def _load_file(
    cache: GameFileCache,
    asset: AssetRecord,
    issues: list[CutsceneResolveIssue],
    *,
    object_id: int | None = None,
) -> GameFile | None:
    try:
        result = cache.load_asset(asset)
    except Exception as exc:  # noqa: BLE001 - dependency failures become structured issues
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
