from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .sidecars import (
    UInt32MultiMap,
    load_uint32_multimap,
    save_uint32_pairs,
    sidecar_path,
)

_MAGIC = b"FFATX001"
_TEXTURE_PARENT_MAGIC = b"FFTXP001"


def asset_texture_index_path(index_path: str | Path) -> Path:
    return sidecar_path(index_path, "atx")


def texture_parent_index_path(index_path: str | Path) -> Path:
    return sidecar_path(index_path, "txp")


def load_asset_texture_index(
    index_path: str | Path,
) -> UInt32MultiMap | None:
    return load_uint32_multimap(index_path, "atx", _MAGIC)


def save_asset_texture_index(
    index_path: str | Path,
    values: Mapping[int, tuple[int, ...]],
) -> Path | None:
    return save_uint32_pairs(
        index_path,
        "atx",
        _MAGIC,
        (
            (asset_hash, texture_hash)
            for asset_hash, texture_hashes in values.items()
            for texture_hash in texture_hashes
            if int(asset_hash) != 0 and int(texture_hash) != 0
        ),
    )


def load_texture_parent_index(index_path: str | Path) -> dict[int, int] | None:
    values = load_uint32_multimap(index_path, "txp", _TEXTURE_PARENT_MAGIC)
    return None if values is None else {key: values[key][0] for key in values}


def save_texture_parent_index(
    index_path: str | Path,
    values: Mapping[int, int],
) -> Path | None:
    return save_uint32_pairs(
        index_path,
        "txp",
        _TEXTURE_PARENT_MAGIC,
        (
            (child, parent)
            for child, parent in values.items()
            if int(child) != 0 and int(parent) != 0
        ),
    )


__all__ = [
    "asset_texture_index_path",
    "load_asset_texture_index",
    "load_texture_parent_index",
    "save_asset_texture_index",
    "save_texture_parent_index",
    "texture_parent_index_path",
]
