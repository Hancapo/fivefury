from __future__ import annotations

import importlib.resources
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Final

from . import _native_abi3 as _ffi

_IDENTITY_LUT: Final[bytes] = bytes(range(256))
_UINT32_MASK: Final[int] = 0xFFFFFFFF


def _read_lut_bytes() -> bytes:
    resource = importlib.resources.files("fivefury").joinpath("data", "lut.dat")
    if resource.is_file():
        data = resource.read_bytes()
        if len(data) == 256:
            return data
    fallback = Path(__file__).resolve().parent / "data" / "lut.dat"
    if fallback.is_file():
        data = fallback.read_bytes()
        if len(data) == 256:
            return data
    return _IDENTITY_LUT


@lru_cache(maxsize=1)
def _get_lut() -> bytes:
    return _read_lut_bytes()


def jenk_partial_hash(value: str | bytes, *, encoding: str = "utf-8") -> int:
    text = value if isinstance(value, str) else value.decode(encoding)
    return _ffi.jenk_partial_hash(text, _get_lut())


def jenk_finalize_hash(partial_hash: int) -> int:
    return _ffi.jenk_finalize_hash(int(partial_hash) & 0xFFFFFFFF)


def jenk_hash(value: str | bytes, *, encoding: str = "utf-8") -> int:
    text = value if isinstance(value, str) else value.decode(encoding)
    return _ffi.jenk_hash(text, _get_lut())


def jenk_hash_many(
    values: Iterable[str | bytes],
    *,
    encoding: str = "utf-8",
) -> list[int]:
    texts = [value if isinstance(value, str) else value.decode(encoding) for value in values]
    return _ffi.jenk_hash_many(texts, _get_lut())


def _rotate_left_32(value: int, amount: int) -> int:
    value &= _UINT32_MASK
    return ((value << amount) | (value >> (32 - amount))) & _UINT32_MASK


def _lookup3_mix(a: int, b: int, c: int) -> tuple[int, int, int]:
    a = ((a - c) ^ _rotate_left_32(c, 4)) & _UINT32_MASK
    c = (c + b) & _UINT32_MASK
    b = ((b - a) ^ _rotate_left_32(a, 6)) & _UINT32_MASK
    a = (a + c) & _UINT32_MASK
    c = ((c - b) ^ _rotate_left_32(b, 8)) & _UINT32_MASK
    b = (b + a) & _UINT32_MASK
    a = ((a - c) ^ _rotate_left_32(c, 16)) & _UINT32_MASK
    c = (c + b) & _UINT32_MASK
    b = ((b - a) ^ _rotate_left_32(a, 19)) & _UINT32_MASK
    a = (a + c) & _UINT32_MASK
    c = ((c - b) ^ _rotate_left_32(b, 4)) & _UINT32_MASK
    b = (b + a) & _UINT32_MASK
    return a, b, c


def _lookup3_final(a: int, b: int, c: int) -> tuple[int, int, int]:
    c = ((c ^ b) - _rotate_left_32(b, 14)) & _UINT32_MASK
    a = ((a ^ c) - _rotate_left_32(c, 11)) & _UINT32_MASK
    b = ((b ^ a) - _rotate_left_32(a, 25)) & _UINT32_MASK
    c = ((c ^ b) - _rotate_left_32(b, 16)) & _UINT32_MASK
    a = ((a ^ c) - _rotate_left_32(c, 4)) & _UINT32_MASK
    b = ((b ^ a) - _rotate_left_32(a, 14)) & _UINT32_MASK
    c = ((c ^ b) - _rotate_left_32(b, 24)) & _UINT32_MASK
    return a, b, c


def jenkins_hash_words(words: Iterable[int], *, initial_value: int = 0) -> int:
    key = [int(word) & _UINT32_MASK for word in words]
    remaining = len(key)
    a = b = c = (
        0xDEADBEEF + (remaining << 2) + (int(initial_value) & _UINT32_MASK)
    ) & _UINT32_MASK
    offset = 0

    while remaining > 3:
        a = (a + key[offset]) & _UINT32_MASK
        b = (b + key[offset + 1]) & _UINT32_MASK
        c = (c + key[offset + 2]) & _UINT32_MASK
        a, b, c = _lookup3_mix(a, b, c)
        remaining -= 3
        offset += 3

    if remaining == 3:
        c = (c + key[offset + 2]) & _UINT32_MASK
    if remaining >= 2:
        b = (b + key[offset + 1]) & _UINT32_MASK
    if remaining >= 1:
        a = (a + key[offset]) & _UINT32_MASK
        _, _, c = _lookup3_final(a, b, c)
    return c


__all__ = [
    "jenk_finalize_hash",
    "jenk_hash",
    "jenk_hash_many",
    "jenk_partial_hash",
    "jenkins_hash_words",
]
