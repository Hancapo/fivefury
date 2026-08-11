from __future__ import annotations

import struct

import pytest

from fivefury.awc.audio import (
    _build_peak_values,
    decode_awc_adpcm,
    interleave_pcm16,
    split_interleaved_pcm16,
)
from fivefury.awc.crypto import decrypt_awc_rsxxtea, encrypt_awc_rsxxtea


def test_native_pcm_channel_split_and_interleave_roundtrip() -> None:
    left = struct.pack("<3h", -32768, 0, 32767)
    right = struct.pack("<3h", 120, -240, 360)

    interleaved = interleave_pcm16([left, right])

    assert split_interleaved_pcm16(interleaved, 2) == [left, right]
    assert interleave_pcm16([left, right], sample_count=2) == interleaved[:8]


def test_native_pcm_helpers_validate_binary_alignment() -> None:
    with pytest.raises(ValueError, match="channels must be greater than zero"):
        split_interleaved_pcm16(b"", 0)
    with pytest.raises(ValueError, match="aligned"):
        split_interleaved_pcm16(b"\x00\x01", 2)
    with pytest.raises(ValueError, match="16-bit aligned"):
        interleave_pcm16([b"\x00"])


def test_native_peak_builder_matches_awc_saturation_contract() -> None:
    pcm = struct.pack("<4h", -32768, -100, 50, 32767)

    assert _build_peak_values(pcm, 4, block_size=2) == [65535, 65534]


def test_native_adpcm_decoder_matches_known_nibbles_and_zero_padding() -> None:
    block = bytes((0, 0, 0, 0, 0x11))

    assert decode_awc_adpcm(block, 2) == struct.pack("<2h", 2, 4)
    assert decode_awc_adpcm(block, 4) == struct.pack("<4h", 2, 4, 0, 0)


def test_native_rsxxtea_roundtrip_and_size_validation() -> None:
    source = bytes(range(64))
    key = (0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00)

    encrypted = encrypt_awc_rsxxtea(source, key)

    assert encrypted != source
    assert decrypt_awc_rsxxtea(encrypted, key) == source
    with pytest.raises(ValueError, match="divisible by 4"):
        encrypt_awc_rsxxtea(b"unaligned", key)
