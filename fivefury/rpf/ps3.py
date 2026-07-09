from __future__ import annotations

from ..crypto import PS3_AES_ENCRYPTION

GTA5_PS3_AES_KEY = bytes(
    (
        0x85,
        0x13,
        0x6E,
        0x1E,
        0x37,
        0xFC,
        0xBC,
        0x45,
        0x94,
        0xE7,
        0xF7,
        0xBC,
        0x5F,
        0x18,
        0x52,
        0x00,
        0xB3,
        0x2A,
        0x67,
        0x30,
        0x8C,
        0xC1,
        0xB8,
        0x33,
        0xB3,
        0x2A,
        0x67,
        0x30,
        0x8C,
        0xC1,
        0xB8,
        0x33,
    )
)


def normalize_ps3_entries(entries_data: bytes) -> bytes:
    data = bytearray(entries_data)
    for offset in range(0, len(data), 16):
        block = data[offset : offset + 16]
        if len(block) < 16:
            break
        data[offset : offset + 8] = reversed(block[:8])
        data[offset + 8 : offset + 12] = reversed(block[8:12])
        data[offset + 12 : offset + 16] = reversed(block[12:16])
    return bytes(data)


__all__ = [
    "GTA5_PS3_AES_KEY",
    "PS3_AES_ENCRYPTION",
    "normalize_ps3_entries",
]
