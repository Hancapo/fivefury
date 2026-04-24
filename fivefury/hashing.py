from __future__ import annotations

import importlib.resources
from functools import lru_cache
from pathlib import Path
from typing import Final

from . import _native_abi3 as _ffi

_IDENTITY_LUT: Final[bytes] = bytes(range(256))


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
    data = text.encode(encoding)
    lut = _get_lut()
    if not data:
        return 0
    key = 0
    if data[:1] == b'"':
        index = 1
        while index < len(data):
            current = data[index]
            if current == 0 or current == 34:
                break
            key = (key + lut[current]) & 0xFFFFFFFF
            key = (key + ((key << 10) & 0xFFFFFFFF)) & 0xFFFFFFFF
            key ^= (key >> 6)
            key &= 0xFFFFFFFF
            index += 1
        return key
    for current in data:
        if current == 0:
            break
        key = (key + lut[current]) & 0xFFFFFFFF
        key = (key + ((key << 10) & 0xFFFFFFFF)) & 0xFFFFFFFF
        key ^= (key >> 6)
        key &= 0xFFFFFFFF
    return key


def jenk_finalize_hash(partial_hash: int) -> int:
    key = int(partial_hash) & 0xFFFFFFFF
    key = (key + ((key << 3) & 0xFFFFFFFF)) & 0xFFFFFFFF
    key ^= (key >> 11)
    key &= 0xFFFFFFFF
    key = (key + ((key << 15) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return key


def jenk_hash(value: str | bytes, *, encoding: str = "utf-8") -> int:
    text = value if isinstance(value, str) else value.decode(encoding)
    return _ffi.jenk_hash(text, _get_lut())


__all__ = [
    "jenk_hash",
    "jenk_partial_hash",
    "jenk_finalize_hash",
]
