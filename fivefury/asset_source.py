from enum import IntEnum


class AssetSourceTier(IntEnum):
    """Semantic provenance, independent of cache sorting priorities."""

    MODS = 0
    DLC = 1
    UPDATE = 2
    BASE = 3
    OVERLAY = 4


def source_tier_from_path(path: str) -> AssetSourceTier:
    path = path.replace("\\", "/").lower()
    if path.startswith("mods/"):
        return AssetSourceTier.MODS
    if "/dlcpacks/" in path:
        return AssetSourceTier.DLC
    if path.startswith("update/"):
        return AssetSourceTier.UPDATE
    return AssetSourceTier.BASE


__all__ = ["AssetSourceTier"]
