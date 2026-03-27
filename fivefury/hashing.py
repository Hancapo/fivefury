from __future__ import annotations


def jenk_hash(value: str | bytes, *, encoding: str = "utf-8") -> int:
    if isinstance(value, str):
        data = value.encode(encoding)
    else:
        data = value
    h = 0
    for byte in data:
        h = (h + byte) & 0xFFFFFFFF
        h = (h + ((h << 10) & 0xFFFFFFFF)) & 0xFFFFFFFF
        h ^= (h >> 6)
    h = (h + ((h << 3) & 0xFFFFFFFF)) & 0xFFFFFFFF
    h ^= (h >> 11)
    h = (h + ((h << 15) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return h & 0xFFFFFFFF
