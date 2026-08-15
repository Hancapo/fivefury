from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..gamefile import GameFileType
    from .core import GameFileCache
    from .views import AssetRecord


def asset_source_rank(asset: AssetRecord) -> tuple[int, str]:
    path = asset.path.replace("\\", "/").lower()
    if path.startswith("mods/"):
        tier = 0
    elif "/dlcpacks/" in path:
        tier = 1
    elif path.startswith("update/"):
        tier = 2
    else:
        tier = 3
    return tier, path


def preferred_asset(
    cache: GameFileCache,
    value: int,
    kind: GameFileType,
) -> AssetRecord | None:
    matches = cache.find_hash(value, kind=kind)
    return min(matches, key=asset_source_rank) if matches else None


__all__ = ["asset_source_rank", "preferred_asset"]
