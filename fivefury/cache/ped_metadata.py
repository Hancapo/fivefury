from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..gamefile import GameFile, GameFileType
from ..ymt.ped_metadata import YmtPedMetadata

if TYPE_CHECKING:
    from .core import GameFileCache
    from .views import AssetRecord


def ped_metadata_assets(cache: GameFileCache) -> list[AssetRecord]:
    return [
        *cache.find_assets("peds.ymt", kind=GameFileType.YMT),
        *cache.iter_assets(GameFileType.PEDS),
    ]


def ped_metadata_from_file(game_file: GameFile | None) -> YmtPedMetadata | None:
    parsed = getattr(game_file, "parsed", None)
    return (
        parsed
        if isinstance(parsed, YmtPedMetadata)
        else getattr(parsed, "ped_metadata", None)
    )


def ped_metadata_index_path(cache: GameFileCache) -> Path | None:
    scan = getattr(cache, "last_scan", None)
    if scan is None or not (scan.used_index_cache or scan.saved_index_cache):
        return None
    return cache.get_index_cache_path()
