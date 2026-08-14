from __future__ import annotations

import struct

import pytest

from fivefury import (
    Awc,
    AwcChunk,
    AwcChunkType,
    AwcStream,
    AwcStreamFormat,
    AwcStreamFormatChunk,
    _native_abi3,
    resolve_awc_playback_stream,
)
from fivefury.awc.audio import (
    _build_peak_values,
    _extract_multichannel_blocks,
    build_pcm_wav,
    decode_awc_adpcm,
    interleave_pcm16,
    parse_pcm_wav,
    split_interleaved_pcm16,
)
from fivefury.awc.crypto import decrypt_awc_rsxxtea, encrypt_awc_rsxxtea


def test_multichannel_validation_rejects_missing_channel_stream() -> None:
    source = AwcStream(
        "dialogue",
        [
            AwcChunk(
                AwcChunkType.STREAM_FORMAT,
                stream_format=AwcStreamFormatChunk(
                    block_count=1,
                    block_size=2048,
                    channels=[
                        AwcStreamFormat(id=1, samples=16, sample_rate=48000),
                        AwcStreamFormat(id=2, samples=16, sample_rate=48000),
                    ],
                ),
            ),
            AwcChunk(AwcChunkType.DATA, data=b"audio"),
        ],
    )
    awc = Awc([source, AwcStream(1)], flags=4)

    codes = {issue.code for issue in awc.validate()}

    assert "awc.stream.channel.missing" in codes


def test_multichannel_channel_hash_selects_owning_stream() -> None:
    source = AwcStream(
        "dialogue",
        [
            AwcChunk(
                AwcChunkType.STREAM_FORMAT,
                stream_format=AwcStreamFormatChunk(
                    1,
                    2048,
                    [
                        AwcStreamFormat(id=7, samples=16, sample_rate=48000),
                        AwcStreamFormat(id=8, samples=16, sample_rate=48000),
                    ],
                ),
            ),
            AwcChunk(AwcChunkType.DATA, data=b"audio"),
        ],
    )
    awc = Awc([source, AwcStream(7), AwcStream(8)], flags=4)

    assert resolve_awc_playback_stream(awc, stream_hash=7) is source


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


def test_native_rsxxtea_binding_accepts_nonempty_byte_buffers() -> None:
    source = bytes(range(64))
    key = (0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00)

    encrypted = _native_abi3.awc_rsxxtea(source, key, False)

    assert len(encrypted) == len(source)
    assert _native_abi3.awc_rsxxtea(encrypted, key, True) == source


def test_native_pcm_wav_roundtrip_and_padding() -> None:
    wav = build_pcm_wav(b"\x7f", sample_rate=22050, channels=1, bits_per_sample=8)

    assert len(wav) % 2 == 0
    assert parse_pcm_wav(wav) == (b"\x7f", 22050, 1, 8)


def test_native_multichannel_block_extraction() -> None:
    left = b"left"
    right = b"right!"
    block = bytearray()
    block += struct.pack("<6i", 0, 1, 0, 2, 0, len(left))
    block += struct.pack("<6i", 1, 1, 0, 3, 0, len(right))
    block += struct.pack("<2i", 0, 0)
    block += b"\x00" * ((-len(block)) % 0x800)
    block += left
    block += right

    assert _extract_multichannel_blocks(
        bytes(block), block_count=1, block_size=len(block), channel_count=2
    ) == [[(2, left)], [(3, right)]]


def test_native_multichannel_block_extraction_accepts_compact_final_block() -> None:
    payload = b"final"
    block = bytearray()
    block += struct.pack("<6i", 0, 1, 0, 2, 0, len(payload))
    block += struct.pack("<i", 0)
    block += b"\x00" * ((-len(block)) % 0x800)
    block += payload

    assert _extract_multichannel_blocks(
        bytes(block), block_count=1, block_size=8192, channel_count=1
    ) == [[(2, payload)]]


def test_native_multichannel_block_extraction_accepts_compact_three_channel_final_block() -> None:
    payloads = [b"A" * 1872, b"B" * 1920, b"C" * 1920]
    block = bytearray()
    for channel, payload in enumerate(payloads):
        block += struct.pack("<6i", channel, 1, 0, 7744, 0, len(payload))
    block += struct.pack("<3i", 0, 0, 0)
    block += b"\x00" * ((-len(block)) % 0x800)
    block += b"".join(payloads)

    assert len(block) == 7760
    assert _extract_multichannel_blocks(
        bytes(block), block_count=1, block_size=524288, channel_count=3
    ) == [[(7744, payload)] for payload in payloads]


def test_native_multichannel_block_extraction_uses_compact_strides_before_padding() -> None:
    payloads = [b"\xff\xfbA", b"\xff\xfbBBBB", b"\xff\xfbCCCCC"]
    block = bytearray()
    for channel, payload in enumerate(payloads):
        block += struct.pack("<6i", channel, 1, 0, 1152, 0, len(payload))
    block += struct.pack("<3i", 0, 0, 0)
    block += b"\x00" * ((-len(block)) % 0x800)
    block += b"".join(payloads)
    block += b"padding" * 800

    assert len(block) < 8192
    block += b"\x00" * (8192 - len(block))
    assert _extract_multichannel_blocks(
        bytes(block), block_count=1, block_size=8192, channel_count=3
    ) == [[(1152, payload)] for payload in payloads]


def test_native_multichannel_block_extraction_falls_back_to_padded_stride() -> None:
    payloads = [b"L" * 2048, b"R" * 2048]
    block = bytearray()
    for channel in range(2):
        block += struct.pack("<6i", channel, 1, 0, 1024, 0, 0)
    block += struct.pack("<2i", 0, 0)
    block += b"\x00" * ((-len(block)) % 0x800)
    block += b"".join(payloads)

    assert _extract_multichannel_blocks(
        bytes(block), block_count=1, block_size=len(block), channel_count=2
    ) == [[(1024, payloads[0])], [(1024, payloads[1])]]


def test_native_multichannel_block_validation_rejects_compact_size_sum() -> None:
    block = bytearray()
    block += struct.pack("<6i", 0, 1, 0, 2, 0, 5)
    block += struct.pack("<6i", 1, 1, 0, 2, 0, 5)
    block += struct.pack("<2i", 0, 0)
    block += b"\x00" * ((-len(block)) % 0x800)
    block += b"123456789"

    with pytest.raises(ValueError, match="payload is truncated"):
        _extract_multichannel_blocks(
            bytes(block), block_count=1, block_size=8192, channel_count=2
        )


def test_native_multichannel_block_validation_rejects_truncated_padded_payload() -> None:
    block = bytearray(struct.pack("<6i", 0, 1, 0, 2, 0, 0))
    block += struct.pack("<i", 0)
    block += b"\x00" * ((-len(block)) % 0x800)
    block += b"short"

    with pytest.raises(ValueError, match="payload is truncated"):
        _extract_multichannel_blocks(
            bytes(block), block_count=1, block_size=8192, channel_count=1
        )


@pytest.mark.parametrize(
    ("small_block_count", "sample_count", "encoded_size"),
    [(-1, 2, 0), (1, -1, 0), (1, 2, -1)],
    ids=["small-block-count", "sample-count", "encoded-size"],
)
def test_native_multichannel_block_validation_rejects_negative_sizes(
    small_block_count: int,
    sample_count: int,
    encoded_size: int,
) -> None:
    block = bytearray(
        struct.pack(
            "<6i",
            0,
            small_block_count,
            0,
            sample_count,
            0,
            encoded_size,
        )
    )

    with pytest.raises(ValueError, match="negative size"):
        _extract_multichannel_blocks(
            bytes(block), block_count=1, block_size=len(block), channel_count=1
        )


def test_native_multichannel_block_validation_rejects_truncation() -> None:
    with pytest.raises(ValueError, match="alignment is invalid"):
        _extract_multichannel_blocks(
            b"\x00" * 24, block_count=1, block_size=24, channel_count=1
        )
