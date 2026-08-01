from __future__ import annotations

import struct
import zlib

import pytest

from fivefury.resource import (
    RSC7_MAGIC,
    decompress_resource_stream,
    get_resource_flags_from_size,
    parse_rsc7,
)


def _compress_with_zero_history(data: bytes) -> bytes:
    compressor = zlib.compressobj(
        level=9,
        wbits=-15,
        zdict=b"\0" * 32768,
    )
    return compressor.compress(data) + compressor.flush()


def test_resource_stream_accepts_zero_initialized_deflate_history():
    compressed = _compress_with_zero_history(b"\0" * 32)
    flags = get_resource_flags_from_size(8192, 5)
    raw = struct.pack("<4I", RSC7_MAGIC, 5, flags, 0) + compressed

    header, payload = parse_rsc7(raw)

    assert header.version == 5
    assert header.total_size == 8192
    assert payload == b"\0" * 32


def test_resource_stream_rejects_trailing_data():
    compressed = zlib.compress(b"payload", level=9, wbits=-15)

    with pytest.raises(ValueError, match="trailing data"):
        decompress_resource_stream(compressed + b"extra")
