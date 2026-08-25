from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from .._native import extract_ytyp_texture_relationships
from ..gamefile import GameFileType
from ..resource import parse_rsc7
from .precedence import asset_source_rank

if TYPE_CHECKING:
    from ..cut.resolution.runtime import CutsceneResolutionCancellation
    from .core import GameFileCache


def build_asset_texture_relationships(
    cache: GameFileCache,
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
    progress: Callable[[str], None] | None = None,
) -> Mapping[int, tuple[int, ...]]:
    from ..cut.resolution.runtime import check_cutscene_resolution_cancelled

    archetypes: dict[int, tuple[int, int]] = {}
    assets = sorted(
        cache.iter_assets(GameFileType.YTYP),
        key=asset_source_rank,
        reverse=True,
    )
    for asset in assets:
        check_cutscene_resolution_cancelled(cancellation)
        if progress is not None:
            progress(asset.path)
        payload = cache.read_bytes(asset, logical=True)
        if payload is None:
            continue
        if payload[:4] == b"RSC7":
            try:
                _header, payload = parse_rsc7(payload)
            except (ValueError, OSError):
                continue
        try:
            records = extract_ytyp_texture_relationships(payload)
        except ValueError:
            continue
        for name_hash, texture_hash, asset_hash in records:
            if name_hash:
                archetypes[name_hash] = (texture_hash, asset_hash)

    relationships: dict[int, set[int]] = {}
    for name_hash, (texture_hash, asset_hash) in archetypes.items():
        if not texture_hash:
            continue
        relationships.setdefault(name_hash, set()).add(texture_hash)
        if asset_hash:
            relationships.setdefault(asset_hash, set()).add(texture_hash)
    return {
        key: tuple(sorted(values))
        for key, values in relationships.items()
    }


__all__ = ["build_asset_texture_relationships"]
