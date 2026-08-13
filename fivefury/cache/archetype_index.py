from __future__ import annotations

import struct
from collections.abc import Mapping
from pathlib import Path

from ..common import atomic_write_bytes

_MAGIC = b"FFATX001"
_TEXTURE_PARENT_MAGIC = b"FFTXP001"
_HEADER = struct.Struct("<8sQQI")
_PAIR = struct.Struct("<II")


def asset_texture_index_path(index_path: str | Path) -> Path:
    source = Path(index_path)
    return source.with_suffix(f"{source.suffix}.atx")


def texture_parent_index_path(index_path: str | Path) -> Path:
    source = Path(index_path)
    return source.with_suffix(f"{source.suffix}.txp")


def _index_signature(index_path: Path) -> tuple[int, int] | None:
    try:
        stat = index_path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def load_asset_texture_index(
    index_path: str | Path,
) -> dict[int, tuple[int, ...]] | None:
    source = Path(index_path)
    signature = _index_signature(source)
    if signature is None:
        return None
    try:
        payload = asset_texture_index_path(source).read_bytes()
    except OSError:
        return None
    if len(payload) < _HEADER.size:
        return None
    magic, index_size, index_mtime, pair_count = _HEADER.unpack_from(payload)
    expected_size = _HEADER.size + (int(pair_count) * _PAIR.size)
    if (
        magic != _MAGIC
        or (index_size, index_mtime) != signature
        or len(payload) != expected_size
    ):
        return None
    values: dict[int, list[int]] = {}
    for asset_hash, texture_hash in struct.iter_unpack(
        "<II", payload[_HEADER.size :]
    ):
        values.setdefault(asset_hash, []).append(texture_hash)
    return {key: tuple(items) for key, items in values.items()}


def save_asset_texture_index(
    index_path: str | Path,
    values: Mapping[int, tuple[int, ...]],
) -> Path | None:
    source = Path(index_path)
    signature = _index_signature(source)
    if signature is None:
        return None
    pairs = sorted(
        {
            (int(asset_hash) & 0xFFFFFFFF, int(texture_hash) & 0xFFFFFFFF)
            for asset_hash, texture_hashes in values.items()
            for texture_hash in texture_hashes
            if int(asset_hash) != 0 and int(texture_hash) != 0
        }
    )
    payload = bytearray(_HEADER.pack(_MAGIC, *signature, len(pairs)))
    for asset_hash, texture_hash in pairs:
        payload.extend(_PAIR.pack(asset_hash, texture_hash))
    return atomic_write_bytes(asset_texture_index_path(source), bytes(payload))


def _load_pair_index(
    index_path: str | Path,
    sidecar_path: Path,
    magic_value: bytes,
) -> tuple[tuple[int, int], ...] | None:
    source = Path(index_path)
    signature = _index_signature(source)
    if signature is None:
        return None
    try:
        payload = sidecar_path.read_bytes()
    except OSError:
        return None
    if len(payload) < _HEADER.size:
        return None
    magic, index_size, index_mtime, pair_count = _HEADER.unpack_from(payload)
    expected_size = _HEADER.size + (int(pair_count) * _PAIR.size)
    if (
        magic != magic_value
        or (index_size, index_mtime) != signature
        or len(payload) != expected_size
    ):
        return None
    return tuple(struct.iter_unpack("<II", payload[_HEADER.size :]))


def _save_pair_index(
    index_path: str | Path,
    sidecar_path: Path,
    magic_value: bytes,
    pairs: set[tuple[int, int]],
) -> Path | None:
    source = Path(index_path)
    signature = _index_signature(source)
    if signature is None:
        return None
    ordered = sorted(pairs)
    payload = bytearray(_HEADER.pack(magic_value, *signature, len(ordered)))
    for left, right in ordered:
        payload.extend(_PAIR.pack(left, right))
    return atomic_write_bytes(sidecar_path, bytes(payload))


def load_texture_parent_index(index_path: str | Path) -> dict[int, int] | None:
    pairs = _load_pair_index(
        index_path,
        texture_parent_index_path(index_path),
        _TEXTURE_PARENT_MAGIC,
    )
    return None if pairs is None else dict(pairs)


def save_texture_parent_index(
    index_path: str | Path,
    values: Mapping[int, int],
) -> Path | None:
    pairs = {
        (int(child) & 0xFFFFFFFF, int(parent) & 0xFFFFFFFF)
        for child, parent in values.items()
        if int(child) != 0 and int(parent) != 0
    }
    return _save_pair_index(
        index_path,
        texture_parent_index_path(index_path),
        _TEXTURE_PARENT_MAGIC,
        pairs,
    )


__all__ = [
    "asset_texture_index_path",
    "load_asset_texture_index",
    "load_texture_parent_index",
    "save_asset_texture_index",
    "save_texture_parent_index",
    "texture_parent_index_path",
]
