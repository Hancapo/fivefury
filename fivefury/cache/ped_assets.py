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


def ped_assets_for_model(
    assets: Iterable[AssetRecord],
    model_stem: str,
) -> tuple[AssetRecord, ...]:
    """Filter and rank a ped asset set once before repeated stem matching."""
    prefix = f"{model_stem}_"
    matches = []
    for asset in assets:
        parts = asset.path.replace("\\", "/").lower().split("/")
        if any(part == model_stem or part.startswith(prefix) for part in parts):
            matches.append(asset)
    return tuple(
        sorted(matches, key=lambda item: ped_asset_relevance(item, model_stem))
    )


def first_matching_ped_asset(
    assets: Iterable[AssetRecord],
    pattern: re.Pattern[str],
) -> AssetRecord | None:
    return next((asset for asset in assets if pattern.match(asset.stem.lower())), None)


__all__ = [
    "first_matching_ped_asset",
    "matching_ped_assets",
    "ped_asset_relevance",
    "ped_assets_for_model",
]
