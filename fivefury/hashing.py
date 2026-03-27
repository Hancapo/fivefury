from __future__ import annotations

import importlib.resources
from functools import lru_cache
from pathlib import Path
from typing import Final

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


def jenk_hash(value: str | bytes, *, encoding: str = "utf-8") -> int:
    data = value.encode(encoding) if isinstance(value, str) else bytes(value)
    lut = _get_lut()
    result = 0
    for byte in data:
        temp = (1025 * (lut[byte] + result)) & 0xFFFFFFFF
        result = ((temp >> 6) ^ temp) & 0xFFFFFFFF
    tail = (9 * result) & 0xFFFFFFFF
    return (32769 * (((tail >> 11) ^ tail) & 0xFFFFFFFF)) & 0xFFFFFFFF


__all__ = [
    "jenk_hash",
]
