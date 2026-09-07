import struct

import pytest

from fivefury import Awc, encode_mp3_channel, inspect_mp3_streaming_data, read_awc
from fivefury.awc.audio import _extract_multichannel_blocks
from fivefury.awc.streaming import build_mp3_streaming_data


@pytest.mark.parametrize("rate", [32000, 44100, 48000])
def test_mp3_channels_use_independently_aligned_payloads(rate):
    channel = encode_mp3_channel(bytes((rate // 10) * 2), sample_rate=rate)
    result = build_mp3_streaming_data((channel, channel), block_size=8192)
    block = result.data
    packet_count = struct.unpack_from("<I", block, 4)[0]
    start = ((48 + 8 * packet_count + 2047) // 2048) * 2048
    size = struct.unpack_from("<I", block, 20)[0]
    second = start + (size + 15) // 16 * 16
    assert block[start : start + size] == channel.data
    assert block[second : second + size] == channel.data
    assert block[start + size : second] == bytes(second - start - size)
    blocks = inspect_mp3_streaming_data(
        block, block_count=1, block_size=8192, channel_count=2, sample_rate=rate
    )
    assert blocks[0].channels[1].encoded_size == len(channel.data)
    extracted = _extract_multichannel_blocks(
        block, block_count=1, block_size=8192, channel_count=2
    )
    assert extracted == [[(channel.sample_count, 0, channel.data)]] * 2


def test_pcm_extended_headers_and_absolute_packet_offsets():
    pcm = struct.pack("<h", 1234) * 400000
    awc = Awc.from_channel_pcm("pcm", [pcm, pcm], sample_rate=48000)
    owner = awc.streams[0]
    layout = owner.stream_format_chunk
    for index in range(layout.block_count):
        block = owner.data_chunk.data[
            index * layout.block_size : (index + 1) * layout.block_size
        ]
        assert struct.unpack_from("<i", block)[0] == -1
        assert struct.unpack_from("<i", block, 24)[0] == -1
        first_packet_sample = struct.unpack_from("<I", block, 48)[0]
        assert first_packet_sample == owner.seek_table_chunk.seek_table[index]
    assert len(owner.data_chunk.data) < layout.block_size * layout.block_count
    assert (
        read_awc(awc.to_bytes()).pcm_bytes() == struct.pack("<hh", 1234, 1234) * 400000
    )


def test_native_extraction_exposes_skipped_samples():
    payload = struct.pack("<4h", 100, 200, 300, 400)
    block = struct.pack("<6iI", -1, 1, 2, 4, 0, len(payload), 0)
    block += bytes(2048 - len(block)) + payload
    assert _extract_multichannel_blocks(
        block, block_count=1, block_size=4096, channel_count=1
    ) == [[(4, 2, payload)]]


def test_pcm_decode_discards_overlap_prefix():
    awc = Awc.from_channel_pcm(
        "overlap", [struct.pack("<4h", 1, 2, 3, 4)] * 2, sample_rate=48000
    )
    owner = awc.streams[0]
    data = bytearray(owner.data_chunk.data)
    struct.pack_into("<i", data, 8, 2)
    struct.pack_into("<i", data, 32, 2)
    owner.data_chunk.data = bytes(data)
    for channel in owner.stream_format_chunk.channels:
        channel.samples = 2
    assert awc.pcm_bytes() == struct.pack("<4h", 3, 3, 4, 4)
