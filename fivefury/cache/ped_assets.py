from __future__ import annotations

import re
from collections.abc import Iterable

from .precedence import asset_source_rank
from .views import AssetRecord


def ped_asset_relevance(
    asset: AssetRecord,
    model_stem: str,
) -> tuple[int, int, str]:
    parts = asset.path.replace("\\", "/").lower().split("/")
    if model_stem in parts:
        folder_rank = 0
    elif any(part.startswith(f"{model_stem}_") for part in parts):
        folder_rank = 1
    else:
        folder_rank = 2
    source_rank, path = asset_source_rank(asset)
    return source_rank, folder_rank, path


def matching_ped_assets(
    assets: Iterable[AssetRecord],
    model_stem: str,
    pattern: re.Pattern[str],
) -> list[AssetRecord]:
    matches = []
    for asset in assets:
        parts = asset.path.replace("\\", "/").lower().split("/")
        if not any(
            part == model_stem or part.startswith(f"{model_stem}_")
            for part in parts
        ):
            continue
        if pattern.match(asset.stem.lower()):
            matches.append(asset)
    return sorted(matches, key=lambda item: ped_asset_relevance(item, model_stem))


__all__ = ["matching_ped_assets", "ped_asset_relevance"]
