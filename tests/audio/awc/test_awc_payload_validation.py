import copy
import struct

import pytest

from fivefury import Awc, AwcChunk, AwcChunkType, AwcCodecType, AwcFormat, AwcStream


@pytest.fixture
def mp3():
    return Awc.from_channel_mp3("probe", [bytes(9600), bytes(9600)])


@pytest.mark.parametrize("field,value", [(8, 2147483647), (12, 4800000), (48, 1152)])
def test_mp3_rejects_impossible_skip_duration_or_origin(mp3, field, value):
    owner = mp3.streams[0]
    data = bytearray(owner.data_chunk.data)
    struct.pack_into("<i", data, field, value)
    owner.data_chunk.data = bytes(data)
    assert not mp3.validate().valid


def test_mp3_rejects_matching_but_impossible_total_duration(mp3):
    owner = mp3.streams[0]
    data = bytearray(owner.data_chunk.data)
    for index, channel in enumerate(owner.stream_format_chunk.channels):
        struct.pack_into("<i", data, 24 * index + 12, 4800000)
        channel.samples = 4800000
    owner.data_chunk.data = bytes(data)
    assert "awc.stream.mp3.layout.invalid" in {d.code for d in mp3.validate()}


def test_trimmed_mp3_packet_may_retain_original_frame_counter(mp3):
    owner = mp3.streams[0]
    data = bytearray(owner.data_chunk.data)
    count = struct.unpack_from("<i", data, 16)[0]
    struct.pack_into("<i", data, 16, count + 1)
    owner.data_chunk.data = bytes(data)
    assert mp3.validate().valid


@pytest.mark.parametrize("mutation", ["payload", "marker", "seek", "packet", "samples"])
def test_fixed_stream_rejects_incoherent_binary_contract(mutation):
    awc = Awc.from_channel_pcm("pcm", [bytes(9600)] * 2, sample_rate=48000)
    owner = awc.streams[0]
    if mutation == "seek":
        owner.seek_table_chunk.seek_table[0] = 1
    else:
        data = bytearray(owner.data_chunk.data)
        if mutation == "payload":
            data = bytearray(b"x")
        else:
            offset, value = {
                "marker": (0, 0),
                "packet": (48, 1),
                "samples": (12, 999999),
            }[mutation]
            struct.pack_into("<i", data, offset, value)
        owner.data_chunk.data = bytes(data)
    assert "awc.stream.payload.invalid" in {d.code for d in awc.validate()}


def test_validation_is_read_only(mp3):
    previous = copy.deepcopy(mp3)
    assert mp3.validate().valid
    assert mp3 == previous


def test_adpcm_capacity_and_step_index():
    fmt = AwcFormat(samples=4088, sample_rate=48000, codec=AwcCodecType.ADPCM)
    data = AwcChunk(AwcChunkType.DATA, data=bytes(2048))
    awc = Awc([AwcStream(1, [AwcChunk(AwcChunkType.FORMAT, format=fmt), data])])
    assert awc.validate().valid
    data.data = bytes([89]) + bytes(2047)
    assert not awc.validate().valid
    data.data = bytes(2047)
    assert not awc.validate().valid


def test_mono_pcm_cannot_claim_more_samples_than_data():
    awc = Awc([AwcStream.from_pcm("mono", bytes(200), sample_rate=48000)])
    awc.streams[0].format_chunk.samples = 101
    assert not awc.validate().valid
