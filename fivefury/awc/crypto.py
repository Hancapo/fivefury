from __future__ import annotations

import struct

from .._native import _awc_rsxxtea


def coerce_awc_key(
    key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None,
) -> tuple[int, int, int, int]:
    if key is None:
        from ..crypto import ensure_game_crypto

        crypto = ensure_game_crypto()
        if crypto.awc_key is None:
            raise ValueError(
                "AWC encryption key is unavailable; load a full GTA V magic.dat first"
            )
        return crypto.awc_key
    if isinstance(key, (bytes, bytearray, memoryview)):
        key_bytes = bytes(key)
        if len(key_bytes) != 16:
            raise ValueError("AWC encryption key bytes must be exactly 16 bytes")
        return tuple(int(value) for value in struct.unpack("<4I", key_bytes))
    if len(key) != 4:
        raise ValueError("AWC encryption key must contain four uint32 values")
    return tuple(int(value) & 0xFFFFFFFF for value in key)


def decrypt_awc_rsxxtea(
    data: bytes | bytearray | memoryview,
    key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None = None,
) -> bytes:
    return _awc_rsxxtea(bytes(data), coerce_awc_key(key), decrypt=True)


def encrypt_awc_rsxxtea(
    data: bytes | bytearray | memoryview,
    key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None = None,
) -> bytes:
    return _awc_rsxxtea(bytes(data), coerce_awc_key(key), decrypt=False)


__all__ = [
    "coerce_awc_key",
    "decrypt_awc_rsxxtea",
    "encrypt_awc_rsxxtea",
]
