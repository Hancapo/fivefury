from __future__ import annotations

import math
import struct

import pytest

from fivefury import (
    Awc,
    AwcChunkType,
    AwcCodecType,
    encode_mp3_channel,
    inspect_mp3_streaming_data,
    parse_mp3_frames,
    read_awc,
)


def _sine_pcm(samples: int, *, frequency: float = 440.0) -> bytes:
    return b"".join(
        struct.pack(
            "<h",
            int(12_000 * math.sin(2.0 * math.pi * frequency * index / 48_000)),
        )
        for index in range(samples)
    )


@pytest.mark.parametrize("channel_count", (1, 2, 3, 5))
def test_mp3_multichannel_authoring_round_trips(channel_count: int) -> None:
    sample_count = 4_800
    channels = [
        _sine_pcm(sample_count, frequency=220.0 + index * 110.0)
        for index in range(channel_count)
    ]

    authored = Awc.from_channel_mp3("master", channels)
    source = authored.streams[0]
    assert [chunk.type for chunk in source.chunks] == [
        AwcChunkType.STREAM_FORMAT,
        AwcChunkType.DATA,
        AwcChunkType.SEEK_TABLE,
    ]

    encoded = authored.to_bytes()
    assert source.chunks[2].info is not None
    assert source.chunks[1].info is not None
    assert source.chunks[2].info.offset < source.chunks[1].info.offset

    rebuilt = read_awc(encoded)
    source = rebuilt.streams[0]
    layout = source.stream_format_chunk

    assert layout is not None
    assert [channel.codec for channel in layout.channels] == [
        AwcCodecType.MP3
    ] * channel_count
    assert [channel.sample_rate for channel in layout.channels] == [
        48_000
    ] * channel_count
    assert [channel.samples for channel in layout.channels] == [
        sample_count
    ] * channel_count
    assert len(rebuilt.pcm_bytes()) == sample_count * channel_count * 2
    assert any(rebuilt.pcm_bytes())
    assert not rebuilt.validate().errors

    blocks = inspect_mp3_streaming_data(
        source.data_chunk.data,
        block_count=layout.block_count,
        block_size=layout.block_size,
        channel_count=channel_count,
        sample_rate=48_000,
    )
    assert source.chunks[2].seek_table == [
        block.first_packet_sample_offset for block in blocks
    ]
    assert source.chunks[2].seek_table_entry_size == 4


def test_long_stereo_mp3_uses_retail_block_seek_offsets() -> None:
    sample_count = 1_830_400
    awc = Awc.from_channel_mp3(
        "bobei_mastered_only",
        [bytes(sample_count * 2), bytes(sample_count * 2)],
    )
    source = awc.streams[0]

    assert source.stream_format_chunk is not None
    assert source.stream_format_chunk.block_count == 3
    assert source.chunks[2].seek_table == [0, 783_360, 1_566_720]


def test_mp3_frame_table_is_uint16_and_deterministic() -> None:
    pcm = _sine_pcm(9_600)

    first = encode_mp3_channel(pcm)
    second = encode_mp3_channel(pcm)

    assert first == second
    assert first.seek_table_entry_size == 2
    assert len(first.seek_table_bytes) == first.frame_count * 2
    assert sum(first.frame_sizes) == len(first.data)
    assert all(0 < size <= 0xFFFF for size in first.frame_sizes)


def test_mp3_streaming_packet_offsets_are_global_and_in_range() -> None:
    awc = Awc.from_channel_mp3("master", [_sine_pcm(480_000)] * 3)
    source = awc.streams[0]
    layout = source.stream_format_chunk
    assert layout is not None and source.data_chunk is not None

    blocks = inspect_mp3_streaming_data(
        source.data_chunk.data,
        block_count=layout.block_count,
        block_size=layout.block_size,
        channel_count=3,
        sample_rate=48_000,
    )
    offsets = [
        offset for block in blocks for offset in block.channels[0].packet_offsets
    ]

    assert offsets == sorted(offsets)
    assert len(offsets) == len(set(offsets))
    assert offsets[0] == 0
    assert offsets[-1] < 480_000


def test_mp3_parser_rejects_bit_reservoir_dependencies() -> None:
    encoded = encode_mp3_channel(_sine_pcm(4_800)).data
    corrupted = bytearray(encoded)
    corrupted[4] = 1

    with pytest.raises(ValueError, match="reservoir"):
        parse_mp3_frames(corrupted, require_independent=True, sample_rate=48_000)


def test_long_stereo_mp3_is_materially_smaller_than_pcm() -> None:
    pcm = bytes(38 * 48_000 * 2)
    awc = Awc.from_channel_mp3("master", [pcm, pcm])

    assert len(awc.to_bytes()) < len(pcm) * 2 // 2
