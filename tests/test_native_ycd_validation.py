import struct

import pytest

from fivefury import _native_abi3 as native


@pytest.mark.parametrize("kind", [-1, 0, 1, 2, 6, 7, 8, 255])
def test_frame_codecs_reject_non_frame_channel_types(kind):
    with pytest.raises(ValueError, match="channel type"):
        native.ycd_decode_frame_channels(bytes(4), 1, 0, 4, [(kind, 0, 32, 1.0, 0.0)])
    with pytest.raises(ValueError, match="channel type"):
        native.ycd_encode_frame_channels(1, [(kind, 32, [0])])


@pytest.mark.parametrize("kind,bits", [(3, 0), (3, 16), (4, -1), (5, 33)])
def test_frame_codecs_reject_invalid_width(kind, bits):
    with pytest.raises(ValueError, match="bit width"):
        native.ycd_decode_frame_channels(bytes(4), 1, 0, 4, [(kind, 0, bits, 1.0, 0.0)])
    with pytest.raises(ValueError, match="bit width"):
        native.ycd_encode_frame_channels(1, [(kind, bits, [0])])


def test_frame_decode_rejects_truncation_and_releases_buffer():
    data = bytearray(4)
    with pytest.raises(ValueError, match="truncated"):
        native.ycd_decode_frame_channels(data, 2, 0, 4, [(3, 0, 32, 0.0, 0.0)])
    data.extend(b"not pinned")
    with pytest.raises(ValueError, match="beyond"):
        native.ycd_decode_frame_channels(bytes(4), 1, 0, 4, [(3, 1, 32, 0.0, 0.0)])


def test_all_frame_channel_types_roundtrip():
    data, length = native.ycd_encode_frame_channels(
        2, [(3, 32, [1.25, -2.5]), (4, 8, [3, 7]), (5, 4, [2, 9])]
    )
    assert native.ycd_decode_frame_channels(
        data,
        2,
        0,
        length,
        [(3, 0, 32, 0.0, 0.0), (4, 32, 8, 0.5, -1.0), (5, 40, 4, 0.0, 0.0)],
    ) == [[1.25, -2.5], [0.5, 2.5], [2, 9]]
    assert data[:4] == struct.pack("<f", 1.25)
