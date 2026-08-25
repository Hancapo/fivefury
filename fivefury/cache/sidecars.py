from __future__ import annotations

import struct
from collections.abc import Iterable, Iterator, Mapping
from functools import lru_cache
from hashlib import blake2s
from pathlib import Path

from ..common import atomic_write_bytes

_HEADER = struct.Struct("<8sQQ16sI")
_PAIR = struct.Struct("<II")
_MAX_SIDECAR_BYTES = 512 * 1024 * 1024


class UInt32MultiMap(Mapping[int, tuple[int, ...]]):
    """Read a sorted uint32 pair table without expanding it into Python objects."""

    __slots__ = ("_key_count", "_pair_count", "_payload")

    def __init__(self, payload: bytes, pair_count: int) -> None:
        self._payload = payload
        self._pair_count = int(pair_count)
        self._key_count: int | None = None

    def _key_at(self, index: int) -> int:
        return _PAIR.unpack_from(self._payload, index * _PAIR.size)[0]

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
            _PAIR.unpack_from(self._payload, index * _PAIR.size)[1]
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


@lru_cache(maxsize=16)
def _index_digest(
    path: str,
    _size: int,
    _mtime_ns: int,
    _ctime_ns: int,
) -> bytes:
    return blake2s(Path(path).read_bytes(), digest_size=16).digest()


def _index_signature(index_path: Path) -> tuple[int, int, bytes] | None:
    try:
        stat = index_path.stat()
        digest = _index_digest(
            str(index_path.resolve()),
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
        )
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns, digest


def load_sidecar_payload(
    index_path: str | Path,
    suffix: str,
    magic_value: bytes,
) -> bytes | None:
    source = Path(index_path)
    signature = _index_signature(source)
    if signature is None:
        return None
    try:
        payload = sidecar_path(source, suffix).read_bytes()
    except OSError:
        return None
    if len(payload) < _HEADER.size or len(payload) > _MAX_SIDECAR_BYTES:
        return None
    magic, index_size, index_mtime, index_digest, payload_size = _HEADER.unpack_from(
        payload
    )
    if (
        magic != magic_value
        or (index_size, index_mtime, index_digest) != signature
        or payload_size != len(payload) - _HEADER.size
    ):
        return None
    return payload[_HEADER.size :]


def save_sidecar_payload(
    index_path: str | Path,
    suffix: str,
    magic_value: bytes,
    payload: bytes,
) -> Path | None:
    source = Path(index_path)
    signature = _index_signature(source)
    if signature is None:
        return None
    if len(payload) > _MAX_SIDECAR_BYTES:
        raise ValueError("Sidecar payload exceeds the supported size")
    header = _HEADER.pack(magic_value, *signature, len(payload))
    return atomic_write_bytes(sidecar_path(source, suffix), header + payload)


def load_uint32_multimap(
    index_path: str | Path,
    suffix: str,
    magic_value: bytes,
) -> UInt32MultiMap | None:
    payload = load_sidecar_payload(index_path, suffix, magic_value)
    if payload is None or len(payload) < 4:
        return None
    pair_count = struct.unpack_from("<I", payload)[0]
    pair_payload = payload[4:]
    if len(pair_payload) != int(pair_count) * _PAIR.size:
        return None
    return UInt32MultiMap(pair_payload, pair_count)


def save_uint32_pairs(
    index_path: str | Path,
    suffix: str,
    magic_value: bytes,
    pairs: Iterable[tuple[int, int]],
) -> Path | None:
    ordered = sorted(
        {
            (int(left) & 0xFFFFFFFF, int(right) & 0xFFFFFFFF)
            for left, right in pairs
            if int(left) != 0
        }
    )
    payload = bytearray(struct.pack("<I", len(ordered)))
    for left, right in ordered:
        payload.extend(_PAIR.pack(left, right))
    return save_sidecar_payload(index_path, suffix, magic_value, bytes(payload))


__all__ = [
    "UInt32MultiMap",
    "load_sidecar_payload",
    "load_uint32_multimap",
    "save_sidecar_payload",
    "save_uint32_pairs",
    "sidecar_path",
]
