from __future__ import annotations

from enum import IntEnum

AWC_MAGIC_LE = 0x54414441
AWC_MAGIC_BE = 0x41444154
AWC_MAGIC_BYTES = b"ADAT"
AWC_DEFAULT_FLAGS = 0xFF00
AWC_STREAM_ID_MASK = 0x1FFFFFFF
AWC_CHUNK_FIELD_MASK = 0x0FFFFFFF
AWC_RSXXTEA_CONSTANT = 0x7B3A207F
AWC_RSXXTEA_DELTA = 0x9E3779B9


class AwcCodecType(IntEnum):
    PCM = 0
    ADPCM = 4


class AwcChunkType(IntEnum):
    DATA = 0x55
    FORMAT = 0xFA
    ANIMATION = 0x5C
    PEAK = 0x36
    MID = 0x68
    GESTURE = 0x2B
    GRANULAR_GRAINS = 0x5A
    GRANULAR_LOOPS = 0xD9
    MARKERS = 0xBD
    STREAM_FORMAT = 0x48
    SEEK_TABLE = 0xA3


_CHUNK_XML_NAMES = {
    AwcChunkType.DATA: "data",
    AwcChunkType.FORMAT: "format",
    AwcChunkType.ANIMATION: "animation",
    AwcChunkType.PEAK: "peak",
    AwcChunkType.MID: "mid",
    AwcChunkType.GESTURE: "gesture",
    AwcChunkType.GRANULAR_GRAINS: "granulargrains",
    AwcChunkType.GRANULAR_LOOPS: "granularloops",
    AwcChunkType.MARKERS: "markers",
    AwcChunkType.STREAM_FORMAT: "streamformat",
    AwcChunkType.SEEK_TABLE: "seektable",
}


def awc_chunk_name(value: int | AwcChunkType) -> str:
    try:
        return _CHUNK_XML_NAMES[AwcChunkType(int(value))]
    except Exception:
        return f"unknown_0x{int(value) & 0xFF:02X}"


def chunk_sort_order(chunk_type: int | AwcChunkType) -> int:
    try:
        kind = AwcChunkType(int(chunk_type))
    except Exception:
        return 0
    if kind in {AwcChunkType.DATA, AwcChunkType.MID}:
        return 3
    if kind in {
        AwcChunkType.MARKERS,
        AwcChunkType.GRANULAR_GRAINS,
        AwcChunkType.GRANULAR_LOOPS,
        AwcChunkType.ANIMATION,
        AwcChunkType.GESTURE,
    }:
        return 2
    if kind is AwcChunkType.SEEK_TABLE:
        return 1
    return 0


def chunk_alignment(chunk_type: int | AwcChunkType) -> int:
    try:
        kind = AwcChunkType(int(chunk_type))
    except Exception:
        return 0
    if kind in {AwcChunkType.DATA, AwcChunkType.MID}:
        return 16
    if kind in {AwcChunkType.MARKERS, AwcChunkType.GRANULAR_GRAINS, AwcChunkType.GRANULAR_LOOPS}:
        return 4
    return 0


__all__ = [
    "AWC_CHUNK_FIELD_MASK",
    "AWC_DEFAULT_FLAGS",
    "AWC_MAGIC_BE",
    "AWC_MAGIC_BYTES",
    "AWC_MAGIC_LE",
    "AWC_RSXXTEA_CONSTANT",
    "AWC_RSXXTEA_DELTA",
    "AWC_STREAM_ID_MASK",
    "AwcChunkType",
    "AwcCodecType",
    "awc_chunk_name",
    "chunk_alignment",
    "chunk_sort_order",
]
