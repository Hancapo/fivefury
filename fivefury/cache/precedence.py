from __future__ import annotations

from typing import TYPE_CHECKING

from ..asset_source import source_tier_from_path

if TYPE_CHECKING:
    from ..gamefile import GameFileType
    from .core import GameFileCache
    from .views import AssetRecord


def asset_source_rank(asset: AssetRecord) -> tuple[int, str]:
    path = asset.path.replace("\\", "/").lower()
    priority = getattr(asset, "source_priority", None)
    if priority is not None:
        return priority, path
    return int(source_tier_from_path(path)), path


def preferred_asset(
    cache: GameFileCache,
    value: int,
    kind: GameFileType,
) -> AssetRecord | None:
    matches = cache.find_hash(value, kind=kind)
    return min(matches, key=asset_source_rank) if matches else None


__all__ = ["asset_source_rank", "preferred_asset"]
