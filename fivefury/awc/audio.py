from __future__ import annotations

import struct


def _build_peak_values(pcm: bytes, sample_count: int, *, block_size: int = 4096) -> list[int]:
    def sample_peak(index: int) -> int:
        offset = index * 2
        if offset + 2 > len(pcm):
            return 0
        sample = struct.unpack_from("<h", pcm, offset)[0]
        return min(abs(int(sample)) * 2, 65535)

    if sample_count <= 0:
        return []
    block_count = max(1, ((sample_count - 1) // block_size) + 1)
    values: list[int] = []
    for block_index in range(block_count):
        start = block_index * block_size
        end = min(start + block_size, sample_count)
        values.append(max((sample_peak(index) for index in range(start, end)), default=0))
    return values


def split_interleaved_pcm16(pcm: bytes, channels: int) -> list[bytes]:
    if channels <= 0:
        raise ValueError("channels must be greater than zero")
    frame_size = channels * 2
    if len(pcm) % frame_size:
        raise ValueError("PCM byte length is not aligned to the channel count")
    outputs = [bytearray() for _ in range(channels)]
    for frame_offset in range(0, len(pcm), frame_size):
        for channel_index in range(channels):
            sample_offset = frame_offset + (channel_index * 2)
            outputs[channel_index].extend(pcm[sample_offset : sample_offset + 2])
    return [bytes(output) for output in outputs]


def interleave_pcm16(channels: list[bytes], *, sample_count: int | None = None) -> bytes:
    if not channels:
        return b""
    if any(len(channel) % 2 for channel in channels):
        raise ValueError("PCM channel byte length must be 16-bit aligned")
    frame_count = min(len(channel) // 2 for channel in channels)
    if sample_count is not None:
        frame_count = min(frame_count, int(sample_count))
    out = bytearray()
    for frame_index in range(frame_count):
        offset = frame_index * 2
        for channel in channels:
            out.extend(channel[offset : offset + 2])
    return bytes(out)


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
            audio_format, channels, sample_rate, _byte_rate, _block_align, bits_per_sample = struct.unpack_from("<HHIIHH", payload, 0)
            fmt = (int(audio_format), int(channels), int(sample_rate), int(bits_per_sample))
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


def build_pcm_wav(pcm: bytes, *, sample_rate: int, channels: int = 1, bits_per_sample: int = 16) -> bytes:
    block_align = channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    data_size = len(pcm)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample)
        + b"data"
        + struct.pack("<I", data_size)
        + bytes(pcm)
    )


_IMA_INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)
_IMA_STEP_TABLE = (
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    16,
    17,
    19,
    21,
    23,
    25,
    28,
    31,
    34,
    37,
    41,
    45,
    50,
    55,
    60,
    66,
    73,
    80,
    88,
    97,
    107,
    118,
    130,
    143,
    157,
    173,
    190,
    209,
    230,
    253,
    279,
    307,
    337,
    371,
    408,
    449,
    494,
    544,
    598,
    658,
    724,
    796,
    876,
    963,
    1060,
    1166,
    1282,
    1411,
    1552,
    1707,
    1878,
    2066,
    2272,
    2499,
    2749,
    3024,
    3327,
    3660,
    4026,
    4428,
    4871,
    5358,
    5894,
    6484,
    7132,
    7845,
    8630,
    9493,
    10442,
    11487,
    12635,
    13899,
    15289,
    16818,
    18500,
    20350,
    22385,
    24623,
    27086,
    29794,
    32767,
)


def _clip(value: int, low: int, high: int) -> int:
    return low if value < low else high if value > high else value


def decode_awc_adpcm(data: bytes, sample_count: int) -> bytes:
    predictor = 0
    step_index = 0
    reading_offset = 0
    bytes_in_block = 0
    out = bytearray()
    remaining = int(sample_count)

    def parse_nibble(nibble: int) -> None:
        nonlocal predictor, step_index
        step = _IMA_STEP_TABLE[step_index]
        diff = ((((nibble & 7) << 1) + 1) * step) >> 3
        if nibble & 8:
            diff = -diff
        predictor = _clip(predictor + diff, -32768, 32767)
        step_index = _clip(step_index + _IMA_INDEX_TABLE[nibble & 0xF], 0, 88)
        out.extend(struct.pack("<h", predictor))

    while reading_offset < len(data) and remaining > 0:
        if bytes_in_block == 0:
            if reading_offset + 4 > len(data):
                break
            step_index = _clip(data[reading_offset], 0, 88)
            predictor = struct.unpack_from("<h", data, reading_offset + 2)[0]
            bytes_in_block = 2044
            reading_offset += 4
        else:
            value = data[reading_offset]
            parse_nibble(value & 0x0F)
            remaining -= 1
            if remaining > 0:
                parse_nibble((value >> 4) & 0x0F)
                remaining -= 1
            bytes_in_block -= 1
            reading_offset += 1
    target_size = max(0, int(sample_count)) * 2
    if len(out) < target_size:
        out.extend(b"\x00" * (target_size - len(out)))
    return bytes(out[:target_size])


__all__ = [
    "_build_peak_values",
    "build_pcm_wav",
    "decode_awc_adpcm",
    "interleave_pcm16",
    "parse_pcm_wav",
    "split_interleaved_pcm16",
]
