from __future__ import annotations

from dataclasses import dataclass
from math import ceil

MP3_RETAIL_SAMPLE_RATE = 48_000
MP3_SAMPLES_PER_FRAME = 1_152
MP3_STREAMING_PACKET_SIZE = 2_048

_MPEG1_LAYER3_BIT_RATES = (
    0,
    32,
    40,
    48,
    56,
    64,
    80,
    96,
    112,
    128,
    160,
    192,
    224,
    256,
    320,
)
_MPEG1_SAMPLE_RATES = (44_100, 48_000, 32_000)


@dataclass(frozen=True, slots=True)
class Mp3Frame:
    offset: int
    size: int
    sample_rate: int
    samples: int = MP3_SAMPLES_PER_FRAME


@dataclass(frozen=True, slots=True)
class EncodedMp3Channel:
    data: bytes
    frame_sizes: tuple[int, ...]
    sample_rate: int
    sample_count: int

    @property
    def frame_count(self) -> int:
        return len(self.frame_sizes)

    @property
    def seek_table_entry_size(self) -> int:
        return 2

    @property
    def seek_table_bytes(self) -> bytes:
        return b"".join(size.to_bytes(2, "little") for size in self.frame_sizes)


def _load_av():
    try:
        import av
    except ImportError as exc:  # pragma: no cover - dependency is declared.
        raise RuntimeError("MP3 authoring requires the 'av' package") from exc
    return av


def parse_mp3_frames(
    data: bytes | bytearray | memoryview,
    *,
    require_independent: bool = False,
    sample_rate: int | None = None,
) -> tuple[Mp3Frame, ...]:
    source = bytes(data)
    frames: list[Mp3Frame] = []
    offset = 0
    while offset < len(source):
        if offset + 4 > len(source):
            raise ValueError("MP3 frame header is truncated")
        header = int.from_bytes(source[offset : offset + 4], "big")
        if header >> 21 != 0x7FF:
            raise ValueError(f"MP3 frame sync is invalid at byte {offset}")
        version = (header >> 19) & 0x3
        layer = (header >> 17) & 0x3
        bit_rate_index = (header >> 12) & 0xF
        sample_rate_index = (header >> 10) & 0x3
        padding = (header >> 9) & 0x1
        channel_mode = (header >> 6) & 0x3
        if version != 0x3 or layer != 0x1:
            raise ValueError("Retail AWC MP3 requires MPEG-1 Layer III frames")
        if bit_rate_index not in range(1, 15) or sample_rate_index == 0x3:
            raise ValueError("MP3 frame has an invalid bit rate or sample rate")
        frame_sample_rate = _MPEG1_SAMPLE_RATES[sample_rate_index]
        if sample_rate is not None and frame_sample_rate != int(sample_rate):
            raise ValueError("MP3 frame sample rate does not match its stream metadata")
        if channel_mode != 0x3:
            raise ValueError("Retail AWC stores each MP3 channel as a mono stream")
        frame_size = (
            144_000 * _MPEG1_LAYER3_BIT_RATES[bit_rate_index]
        ) // frame_sample_rate + padding
        if frame_size > 0xFFFF:
            raise ValueError("MP3 frame size exceeds the uint16 seek-table field")
        if offset + frame_size > len(source):
            raise ValueError("MP3 frame payload is truncated")
        if require_independent:
            crc_size = 2 if ((header >> 16) & 0x1) == 0 else 0
            side_info = offset + 4 + crc_size
            if side_info + 2 > offset + frame_size:
                raise ValueError("MP3 side information is truncated")
            main_data_begin = (source[side_info] << 1) | (source[side_info + 1] >> 7)
            if main_data_begin:
                raise ValueError(
                    "MP3 bit reservoir is enabled; AWC streaming frames must be independent"
                )
        frames.append(Mp3Frame(offset, frame_size, frame_sample_rate))
        offset += frame_size
    if not frames:
        raise ValueError("MP3 channel contains no frames")
    return tuple(frames)


def encode_mp3_channel(
    pcm: bytes | bytearray | memoryview,
    *,
    sample_rate: int = MP3_RETAIL_SAMPLE_RATE,
    bit_rate: int = 128_000,
) -> EncodedMp3Channel:
    source = bytes(pcm)
    if len(source) % 2:
        raise ValueError("PCM16 channel byte length must be even")
    if int(sample_rate) != MP3_RETAIL_SAMPLE_RATE:
        raise ValueError("Retail AWC MP3 authoring requires 48000 Hz PCM")
    if int(bit_rate) <= 0:
        raise ValueError("MP3 bit rate must be positive")
    sample_count = len(source) // 2
    if sample_count <= 0:
        raise ValueError("MP3 authoring requires at least one PCM sample")

    av = _load_av()
    encoder = av.CodecContext.create("libmp3lame", "w")
    encoder.sample_rate = MP3_RETAIL_SAMPLE_RATE
    encoder.layout = "mono"
    encoder.format = "s16p"
    encoder.bit_rate = int(bit_rate)
    encoder.options = {"reservoir": "0", "write_xing": "0"}
    encoder.open()
    if encoder.frame_size != MP3_SAMPLES_PER_FRAME:
        raise RuntimeError(
            f"libmp3lame selected an unsupported frame size of {encoder.frame_size} samples"
        )

    output = bytearray()
    frame_bytes = MP3_SAMPLES_PER_FRAME * 2
    for start in range(0, len(source), frame_bytes):
        payload = source[start : start + frame_bytes]
        payload += bytes(frame_bytes - len(payload))
        frame = av.AudioFrame(
            format="s16p",
            layout="mono",
            samples=MP3_SAMPLES_PER_FRAME,
        )
        frame.sample_rate = MP3_RETAIL_SAMPLE_RATE
        frame.planes[0].update(payload)
        for packet in encoder.encode(frame):
            output.extend(bytes(packet))
    for packet in encoder.encode(None):
        output.extend(bytes(packet))

    encoded = bytes(output)
    frames = parse_mp3_frames(
        encoded,
        require_independent=True,
        sample_rate=MP3_RETAIL_SAMPLE_RATE,
    )
    expected_frames = ceil(sample_count / MP3_SAMPLES_PER_FRAME)
    if len(frames) != expected_frames + 1:
        raise RuntimeError(
            "libmp3lame produced an unexpected encoder-delay frame layout"
        )
    encoded = encoded[frames[0].size :]
    frames = parse_mp3_frames(
        encoded,
        require_independent=True,
        sample_rate=MP3_RETAIL_SAMPLE_RATE,
    )
    if len(frames) != expected_frames:
        raise RuntimeError("MP3 frame count does not cover the source PCM duration")
    return EncodedMp3Channel(
        data=encoded,
        frame_sizes=tuple(frame.size for frame in frames),
        sample_rate=MP3_RETAIL_SAMPLE_RATE,
        sample_count=sample_count,
    )


__all__ = [
    "MP3_RETAIL_SAMPLE_RATE",
    "MP3_SAMPLES_PER_FRAME",
    "MP3_STREAMING_PACKET_SIZE",
    "EncodedMp3Channel",
    "Mp3Frame",
    "encode_mp3_channel",
    "parse_mp3_frames",
]
