from __future__ import annotations

import struct

from .._native import (
    _awc_build_peak_values,
    _awc_decode_adpcm,
    _awc_interleave_pcm16,
    _awc_split_interleaved_pcm16,
)


def _build_peak_values(
    pcm: bytes, sample_count: int, *, block_size: int = 4096
) -> list[int]:
    return _awc_build_peak_values(bytes(pcm), int(sample_count), int(block_size))


def split_interleaved_pcm16(pcm: bytes, channels: int) -> list[bytes]:
    return _awc_split_interleaved_pcm16(bytes(pcm), int(channels))


def interleave_pcm16(
    channels: list[bytes], *, sample_count: int | None = None
) -> bytes:
    return _awc_interleave_pcm16([bytes(channel) for channel in channels], sample_count)


def parse_pcm_wav(data: bytes) -> tuple[bytes, int, int, int]:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Expected a RIFF/WAVE file")
    offset = 12
    fmt: tuple[int, int, int, int] | None = None
    pcm: bytes | None = None
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        payload_start = offset + 8
        payload_end = payload_start + chunk_size
        if payload_end > len(data):
            raise ValueError("WAV chunk points outside the file")
        payload = data[payload_start:payload_end]
        if chunk_id == b"fmt ":
            if len(payload) < 16:
                raise ValueError("WAV fmt chunk is truncated")
            (
                audio_format,
                channels,
                sample_rate,
                _byte_rate,
                _block_align,
                bits_per_sample,
            ) = struct.unpack_from("<HHIIHH", payload, 0)
            fmt = (
                int(audio_format),
                int(channels),
                int(sample_rate),
                int(bits_per_sample),
            )
        elif chunk_id == b"data":
            pcm = bytes(payload)
        offset = payload_end + (chunk_size & 1)
    if fmt is None:
        raise ValueError("WAV fmt chunk not found")
    if pcm is None:
        raise ValueError("WAV data chunk not found")
    audio_format, channels, sample_rate, bits_per_sample = fmt
    if audio_format != 1:
        raise ValueError("Only PCM WAV files are supported")
    return pcm, sample_rate, channels, bits_per_sample


def build_pcm_wav(
    pcm: bytes, *, sample_rate: int, channels: int = 1, bits_per_sample: int = 16
) -> bytes:
    block_align = channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    data_size = len(pcm)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack(
            "<IHHIIHH",
            16,
            1,
            channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
        )
        + b"data"
        + struct.pack("<I", data_size)
        + bytes(pcm)
    )


def decode_awc_adpcm(data: bytes, sample_count: int) -> bytes:
    return _awc_decode_adpcm(bytes(data), int(sample_count))


__all__ = [
    "_build_peak_values",
    "build_pcm_wav",
    "decode_awc_adpcm",
    "interleave_pcm16",
    "parse_pcm_wav",
    "split_interleaved_pcm16",
]
