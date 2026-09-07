import bisect
import struct

import pytest

from fivefury import Awc, AwcStream, read_awc


@pytest.mark.parametrize("indexed", [False, True])
@pytest.mark.parametrize("encrypted", [False, True])
def test_ordinary_bank_table_supports_native_binary_search(indexed, encrypted):
    streams = [
        AwcStream.from_pcm(value, bytes([value, 0]) * 8, sample_rate=48000)
        for value in (30, 10, 20)
    ]
    awc = Awc(streams)
    awc.chunk_indices_flag = indexed
    awc.single_channel_encrypt_flag = encrypted
    data = awc.to_bytes()
    start = 16 + (2 * len(streams) if indexed else 0)
    hashes = [value & 0x1FFFFFFF for value in struct.unpack_from("<3I", data, start)]
    assert hashes == [10, 20, 30]
    for value in (30, 10, 20):
        assert hashes[bisect.bisect_left(hashes, value)] == value
    loaded = read_awc(data)
    for stream in streams:
        assert loaded.stream(stream.hash).pcm_bytes() == stream.pcm_bytes()
    assert [stream.hash for stream in awc.streams] == [30, 10, 20]
