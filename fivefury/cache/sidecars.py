from __future__ import annotations

import struct
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

from ..common import atomic_write_bytes

_HEADER = struct.Struct("<8sQQI")
_PAIR = struct.Struct("<II")


class UInt32MultiMap(Mapping[int, tuple[int, ...]]):
    """Read a sorted uint32 pair table without expanding it into Python objects."""

    __slots__ = ("_key_count", "_pair_count", "_payload")

    def __init__(self, payload: bytes, pair_count: int) -> None:
        self._payload = payload
        self._pair_count = int(pair_count)
        self._key_count: int | None = None

    def _key_at(self, index: int) -> int:
        return _PAIR.unpack_from(self._payload, _HEADER.size + (index * _PAIR.size))[0]

    def _lower_bound(self, key: int) -> int:
        lower = 0
        upper = self._pair_count
        while lower < upper:
            middle = (lower + upper) // 2
            if self._key_at(middle) < key:
                lower = middle + 1
            else:
                upper = middle
        return lower

    def get(
        self,
        key: int,
        default: tuple[int, ...] | None = None,
    ) -> tuple[int, ...] | None:
        value = int(key) & 0xFFFFFFFF
        first = self._lower_bound(value)
        if first == self._pair_count or self._key_at(first) != value:
            return default
        last = first + 1
        while last < self._pair_count and self._key_at(last) == value:
            last += 1
        return tuple(
            _PAIR.unpack_from(self._payload, _HEADER.size + (index * _PAIR.size))[1]
            for index in range(first, last)
        )

    def __getitem__(self, key: int) -> tuple[int, ...]:
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result

    def __iter__(self) -> Iterator[int]:
        previous: int | None = None
        for index in range(self._pair_count):
            key = self._key_at(index)
            if key != previous:
                previous = key
                yield key

    def __len__(self) -> int:
        if self._key_count is None:
            self._key_count = sum(1 for _ in self)
        return self._key_count


def sidecar_path(index_path: str | Path, suffix: str) -> Path:
    source = Path(index_path)
    return source.with_suffix(f"{source.suffix}.{suffix}")


def _index_signature(index_path: Path) -> tuple[int, int] | None:
    try:
        stat = index_path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def load_uint32_multimap(
    index_path: str | Path,
    suffix: str,
    magic_value: bytes,
) -> UInt32MultiMap | None:
    source = Path(index_path)
    signature = _index_signature(source)
    if signature is None:
        return None
    try:
        payload = sidecar_path(source, suffix).read_bytes()
    except OSError:
        return None
    if len(payload) < _HEADER.size:
        return None
    magic, index_size, index_mtime, pair_count = _HEADER.unpack_from(payload)
    if (
        magic != magic_value
        or (index_size, index_mtime) != signature
        or len(payload) != _HEADER.size + (int(pair_count) * _PAIR.size)
    ):
        return None
    return UInt32MultiMap(payload, pair_count)


def save_uint32_pairs(
    index_path: str | Path,
    suffix: str,
    magic_value: bytes,
    pairs: Iterable[tuple[int, int]],
) -> Path | None:
    source = Path(index_path)
    signature = _index_signature(source)
    if signature is None:
        return None
    ordered = sorted(
        {
            (int(left) & 0xFFFFFFFF, int(right) & 0xFFFFFFFF)
            for left, right in pairs
            if int(left) != 0
        }
    )
    payload = bytearray(_HEADER.pack(magic_value, *signature, len(ordered)))
    for left, right in ordered:
        payload.extend(_PAIR.pack(left, right))
    return atomic_write_bytes(sidecar_path(source, suffix), bytes(payload))


__all__ = [
    "UInt32MultiMap",
    "load_uint32_multimap",
    "save_uint32_pairs",
    "sidecar_path",
]
