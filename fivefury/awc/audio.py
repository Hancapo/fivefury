from __future__ import annotations

from .._native import (
    _awc_build_pcm_wav,
    _awc_build_peak_values,
    _awc_decode_adpcm,
    _awc_extract_multichannel_blocks,
    _awc_interleave_pcm16,
    _awc_parse_pcm_wav,
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
    return _awc_parse_pcm_wav(bytes(data))


def build_pcm_wav(
    pcm: bytes, *, sample_rate: int, channels: int = 1, bits_per_sample: int = 16
) -> bytes:
    return _awc_build_pcm_wav(
        bytes(pcm), int(sample_rate), int(channels), int(bits_per_sample)
    )


def _extract_multichannel_blocks(
    data: bytes, *, block_count: int, block_size: int, channel_count: int
) -> list[list[tuple[int, bytes]]]:
    return _awc_extract_multichannel_blocks(
        bytes(data), int(block_count), int(block_size), int(channel_count)
    )


def decode_awc_adpcm(data: bytes, sample_count: int) -> bytes:
    return _awc_decode_adpcm(bytes(data), int(sample_count))


__all__ = [
    "_build_peak_values",
    "_extract_multichannel_blocks",
    "build_pcm_wav",
    "decode_awc_adpcm",
    "interleave_pcm16",
    "parse_pcm_wav",
    "split_interleaved_pcm16",
]
