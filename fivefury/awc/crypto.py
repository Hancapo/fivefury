from __future__ import annotations

import struct

from .constants import AWC_RSXXTEA_CONSTANT, AWC_RSXXTEA_DELTA


def coerce_awc_key(key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None) -> tuple[int, int, int, int]:
    if key is None:
        from ..crypto import ensure_game_crypto

        crypto = ensure_game_crypto()
        if crypto.awc_key is None:
            raise ValueError("AWC encryption key is unavailable; load a full GTA V magic.dat first")
        return crypto.awc_key
    if isinstance(key, (bytes, bytearray, memoryview)):
        key_bytes = bytes(key)
        if len(key_bytes) != 16:
            raise ValueError("AWC encryption key bytes must be exactly 16 bytes")
        return tuple(int(value) for value in struct.unpack("<4I", key_bytes))
    if len(key) != 4:
        raise ValueError("AWC encryption key must contain four uint32 values")
    return tuple(int(value) & 0xFFFFFFFF for value in key)


def _rsxxtea_mx(left: int, right: int, total: int, key_value: int) -> int:
    mixed_a = ((left >> 5) ^ ((right << 2) & 0xFFFFFFFF)) & 0xFFFFFFFF
    mixed_b = ((right >> 3) ^ ((left << 4) & 0xFFFFFFFF)) & 0xFFFFFFFF
    mixed_c = ((total ^ right) + ((key_value ^ left ^ AWC_RSXXTEA_CONSTANT) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return (((mixed_a + mixed_b) & 0xFFFFFFFF) ^ mixed_c) & 0xFFFFFFFF


def decrypt_awc_rsxxtea(
    data: bytes | bytearray | memoryview,
    key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None = None,
) -> bytes:
    source = bytes(data)
    if len(source) % 4:
        raise ValueError("AWC RSXXTEA data size must be divisible by 4")
    if len(source) < 8:
        return source
    awc_key = coerce_awc_key(key)
    blocks = list(struct.unpack(f"<{len(source) // 4}I", source))
    block_count = len(blocks)
    total = (AWC_RSXXTEA_DELTA * (6 + (52 // block_count))) & 0xFFFFFFFF
    right = blocks[0]
    while total:
        for block_index in range(block_count - 1, -1, -1):
            left = blocks[(block_index if block_index > 0 else block_count) - 1]
            key_index = (block_index & 3) ^ ((total >> 2) & 3)
            value = (blocks[block_index] - _rsxxtea_mx(left, right, total, awc_key[key_index])) & 0xFFFFFFFF
            blocks[block_index] = value
            right = value
        total = (total - AWC_RSXXTEA_DELTA) & 0xFFFFFFFF
    return struct.pack(f"<{block_count}I", *blocks)


def encrypt_awc_rsxxtea(
    data: bytes | bytearray | memoryview,
    key: tuple[int, int, int, int] | bytes | bytearray | memoryview | None = None,
) -> bytes:
    source = bytes(data)
    if len(source) % 4:
        raise ValueError("AWC RSXXTEA data size must be divisible by 4")
    if len(source) < 8:
        return source
    awc_key = coerce_awc_key(key)
    blocks = list(struct.unpack(f"<{len(source) // 4}I", source))
    block_count = len(blocks)
    rounds = 6 + (52 // block_count)
    total = 0
    left = blocks[-1]
    while rounds:
        total = (total + AWC_RSXXTEA_DELTA) & 0xFFFFFFFF
        e = (total >> 2) & 3
        for block_index in range(block_count):
            right = blocks[(block_index + 1) % block_count]
            key_index = (block_index & 3) ^ e
            value = (blocks[block_index] + _rsxxtea_mx(left, right, total, awc_key[key_index])) & 0xFFFFFFFF
            blocks[block_index] = value
            left = value
        rounds -= 1
    return struct.pack(f"<{block_count}I", *blocks)


__all__ = [
    "coerce_awc_key",
    "decrypt_awc_rsxxtea",
    "encrypt_awc_rsxxtea",
]
