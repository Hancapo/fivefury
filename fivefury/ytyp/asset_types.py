from __future__ import annotations

import enum


class ArchetypeAssetType(enum.IntEnum):
    UNINITIALIZED = 0
    FRAGMENT = 1
    DRAWABLE = 2
    DRAWABLE_DICTIONARY = 3
    ASSETLESS = 4

    DRAWABLEDICTIONARY = DRAWABLE_DICTIONARY


def coerce_archetype_asset_type(value: int | ArchetypeAssetType) -> ArchetypeAssetType:
    return value if isinstance(value, ArchetypeAssetType) else ArchetypeAssetType(int(value))


__all__ = ["ArchetypeAssetType", "coerce_archetype_asset_type"]
