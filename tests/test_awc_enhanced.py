from __future__ import annotations

import struct

from fivefury import (
    Awc,
    AwcChunk,
    AwcChunkType,
    AwcCodecType,
    AwcFormat,
    AwcStream,
    AwcStreamFormat,
    AwcStreamFormatChunk,
    DecodedAudio,
)


def test_enhanced_mp3_codec_is_decoded_to_pcm(monkeypatch) -> None:
    stream = AwcStream(
        1,
        [
            AwcChunk(
                AwcChunkType.FORMAT,
                format=AwcFormat(samples=3, sample_rate=48000, codec=AwcCodecType.MP3),
            ),
            AwcChunk(AwcChunkType.DATA, data=b"encoded-mp3"),
        ],
    )
    calls = []

    def decode(source, **kwargs):
        calls.append((source, kwargs))
        return DecodedAudio(b"\x01\x00\x02\x00\x03\x00", 48000, 1)

    monkeypatch.setattr("fivefury.awc.conversion.decode_audio", decode)

    assert stream.pcm_bytes() == b"\x01\x00\x02\x00\x03\x00"
    assert calls == [
        (
            b"encoded-mp3",
            {"sample_rate": 48000, "channels": 1, "source_format": ".mp3"},
        )
    ]


def test_enhanced_multichannel_block_uses_encoded_size_and_sample_count(
    monkeypatch,
) -> None:
    encoded = b"mp3data"
    header = struct.pack("<6i", -1, 1, 0, 3, 0, len(encoded))
    offsets = struct.pack("<i", 0)
    data = header + offsets
    data += b"\x00" * ((-len(data)) % 0x800)
    data += encoded + b"padding"
    channel = AwcStreamFormat(
        id=2,
        samples=3,
        sample_rate=48000,
        codec=AwcCodecType.MP3,
    )
    source = AwcStream(
        0,
        [
            AwcChunk(
                AwcChunkType.STREAM_FORMAT,
                stream_format=AwcStreamFormatChunk(
                    block_count=1,
                    block_size=len(data),
                    channels=[channel],
                ),
            ),
            AwcChunk(AwcChunkType.DATA, data=data),
        ],
    )
    awc = Awc([source, AwcStream(2, stream_format=channel)], flags=4)

    def decode(payload, **_kwargs):
        assert payload == encoded
        return DecodedAudio(b"\x01\x00\x02\x00\x03\x00\x04\x00", 48000, 1)

    monkeypatch.setattr("fivefury.awc.conversion.decode_audio", decode)

    assert awc.pcm_bytes() == b"\x01\x00\x02\x00\x03\x00"
