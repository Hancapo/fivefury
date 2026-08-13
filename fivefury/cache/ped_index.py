from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .sidecars import (
    UInt32MultiMap,
    load_uint32_multimap,
    save_uint32_pairs,
    sidecar_path,
)

_MAGIC = b"FFPED001"


def ped_init_index_path(index_path: str | Path) -> Path:
    return sidecar_path(index_path, "ped")


def load_ped_init_index(index_path: str | Path) -> UInt32MultiMap | None:
    return load_uint32_multimap(index_path, "ped", _MAGIC)


def save_ped_init_index(
    index_path: str | Path,
    values: Mapping[int, tuple[int, ...]],
) -> Path | None:
    return save_uint32_pairs(
        index_path,
        "ped",
        _MAGIC,
        (
            (ped_hash, asset_id)
            for ped_hash, asset_ids in values.items()
            for asset_id in asset_ids
        ),
    )


__all__ = ["load_ped_init_index", "ped_init_index_path", "save_ped_init_index"]
