from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ..hashing import jenk_hash
from ..metahash import HashLike, MetaHash, coerce_meta_hash
from .audio import _build_peak_values, build_pcm_wav, decode_awc_adpcm, parse_pcm_wav
from .constants import (
    AWC_CHUNK_FIELD_MASK,
    AWC_DEFAULT_FLAGS,
    AWC_STREAM_ID_MASK,
    AwcChunkType,
    AwcCodecType,
    awc_chunk_name,
    chunk_alignment,
    chunk_sort_order,
)


def _coerce_stream_id(value: HashLike | None) -> int:
    if value is None:
        return 0
    return coerce_meta_hash(value).uint & AWC_STREAM_ID_MASK


def _hash_from_name(value: str) -> int:
    return jenk_hash(value) & AWC_STREAM_ID_MASK


@dataclass(slots=True)
class AwcChunkInfo:
    type: int | AwcChunkType
    size: int = 0
    offset: int = 0
    raw: int = 0

    @classmethod
    def from_raw(cls, raw: int) -> "AwcChunkInfo":
        chunk_type = (raw >> 56) & 0xFF
        try:
            typed: int | AwcChunkType = AwcChunkType(chunk_type)
        except ValueError:
            typed = chunk_type
        return cls(
            type=typed,
            size=int((raw >> 28) & AWC_CHUNK_FIELD_MASK),
            offset=int(raw & AWC_CHUNK_FIELD_MASK),
            raw=int(raw),
        )

    @property
    def type_value(self) -> int:
        return int(self.type) & 0xFF

    @property
    def name(self) -> str:
        return awc_chunk_name(self.type_value)

    @property
    def alignment(self) -> int:
        return chunk_alignment(self.type_value)

    @property
    def sort_order(self) -> int:
        return chunk_sort_order(self.type_value)

    def to_raw(self) -> int:
        return (
            (self.offset & AWC_CHUNK_FIELD_MASK)
            | ((self.size & AWC_CHUNK_FIELD_MASK) << 28)
            | ((self.type_value & 0xFF) << 56)
        )


@dataclass(slots=True)
class AwcFormat:
    samples: int = 0
    loop_point: int = -1
    sample_rate: int = 0
    headroom: int = 0
    loop_begin: int = 0
    loop_end: int = 0
    play_end: int = 0
    play_begin: int = 0
    codec: AwcCodecType = AwcCodecType.PCM
    peak: int | None = None

    @classmethod
    def from_bytes(cls, data: bytes, endian: str = "<") -> "AwcFormat":
        if len(data) not in {20, 24}:
            raise ValueError(f"AWC format chunk must be 20 or 24 bytes, got {len(data)}")
        values = struct.unpack_from(f"{endian}IiHhHHHBB", data, 0)
        peak = struct.unpack_from(f"{endian}I", data, 20)[0] if len(data) == 24 else None
        return cls(
            samples=int(values[0]),
            loop_point=int(values[1]),
            sample_rate=int(values[2]),
            headroom=int(values[3]),
            loop_begin=int(values[4]),
            loop_end=int(values[5]),
            play_end=int(values[6]),
            play_begin=int(values[7]),
            codec=AwcCodecType(int(values[8])),
            peak=peak,
        )

    def to_bytes(self, endian: str = "<") -> bytes:
        payload = struct.pack(
            f"{endian}IiHhHHHBB",
            int(self.samples) & 0xFFFFFFFF,
            int(self.loop_point),
            int(self.sample_rate) & 0xFFFF,
            int(self.headroom),
            int(self.loop_begin) & 0xFFFF,
            int(self.loop_end) & 0xFFFF,
            int(self.play_end) & 0xFFFF,
            int(self.play_begin) & 0xFF,
            int(self.codec) & 0xFF,
        )
        if self.peak is not None:
            payload += struct.pack(f"{endian}I", int(self.peak) & 0xFFFFFFFF)
        return payload

    @property
    def duration(self) -> float:
        return (float(self.samples) / float(self.sample_rate)) if self.sample_rate else 0.0


@dataclass(slots=True)
class AwcStreamFormat:
    id: int = 0
    samples: int = 0
    headroom: int = 0
    sample_rate: int = 0
    codec: AwcCodecType = AwcCodecType.ADPCM
    unused1: int = 0
    unused2: int = 0

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0, endian: str = "<") -> "AwcStreamFormat":
        values = struct.unpack_from(f"{endian}IIhHBBH", data, offset)
        return cls(
            id=int(values[0]),
            samples=int(values[1]),
            headroom=int(values[2]),
            sample_rate=int(values[3]),
            codec=AwcCodecType(int(values[4])),
            unused1=int(values[5]),
            unused2=int(values[6]),
        )

    def to_bytes(self, endian: str = "<") -> bytes:
        return struct.pack(
            f"{endian}IIhHBBH",
            int(self.id) & 0xFFFFFFFF,
            int(self.samples) & 0xFFFFFFFF,
            int(self.headroom),
            int(self.sample_rate) & 0xFFFF,
            int(self.codec) & 0xFF,
            int(self.unused1) & 0xFF,
            int(self.unused2) & 0xFFFF,
        )


@dataclass(slots=True)
class AwcStreamFormatChunk:
    block_count: int = 0
    block_size: int = 0
    channels: list[AwcStreamFormat] = field(default_factory=list)

    @classmethod
    def from_bytes(cls, data: bytes, endian: str = "<") -> "AwcStreamFormatChunk":
        if len(data) < 12:
            raise ValueError("AWC streamformat chunk is truncated")
        block_count, block_size, channel_count = struct.unpack_from(f"{endian}III", data, 0)
        expected = 12 + int(channel_count) * 16
        if len(data) < expected:
            raise ValueError("AWC streamformat channel table is truncated")
        channels = [AwcStreamFormat.from_bytes(data, 12 + (index * 16), endian) for index in range(int(channel_count))]
        return cls(int(block_count), int(block_size), channels)

    def to_bytes(self, endian: str = "<") -> bytes:
        payload = struct.pack(f"{endian}III", int(self.block_count), int(self.block_size), len(self.channels))
        payload += b"".join(channel.to_bytes(endian) for channel in self.channels)
        return payload


@dataclass(slots=True)
class AwcChunk:
    type: int | AwcChunkType
    data: bytes = b""
    info: AwcChunkInfo | None = None
    format: AwcFormat | None = None
    stream_format: AwcStreamFormatChunk | None = None
    peaks: list[int] | None = None
    seek_table: list[int] | None = None

    @classmethod
    def from_info(cls, info: AwcChunkInfo, source: bytes, endian: str = "<") -> "AwcChunk":
        start = info.offset
        end = start + info.size
        if start < 0 or end > len(source):
            raise ValueError(f"AWC chunk {info.name} points outside the file")
        data = bytes(source[start:end])
        chunk = cls(info.type, data, info=info)
        if info.type_value == int(AwcChunkType.FORMAT):
            chunk.format = AwcFormat.from_bytes(data, endian)
        elif info.type_value == int(AwcChunkType.STREAM_FORMAT):
            chunk.stream_format = AwcStreamFormatChunk.from_bytes(data, endian)
        elif info.type_value == int(AwcChunkType.PEAK):
            if len(data) % 2:
                raise ValueError("AWC peak chunk size must be even")
            chunk.peaks = list(struct.unpack(f"{endian}{len(data) // 2}H", data)) if data else []
        elif info.type_value == int(AwcChunkType.SEEK_TABLE):
            if len(data) % 4:
                raise ValueError("AWC seektable chunk size must be divisible by 4")
            chunk.seek_table = list(struct.unpack(f"{endian}{len(data) // 4}I", data)) if data else []
        return chunk

    @property
    def type_value(self) -> int:
        return int(self.type) & 0xFF

    @property
    def name(self) -> str:
        return awc_chunk_name(self.type_value)

    @property
    def payload_size(self) -> int:
        return len(self.to_payload())

    @property
    def alignment(self) -> int:
        return chunk_alignment(self.type_value)

    @property
    def sort_order(self) -> int:
        return chunk_sort_order(self.type_value)

    def to_payload(self, endian: str = "<") -> bytes:
        if self.type_value == int(AwcChunkType.FORMAT) and self.format is not None:
            return self.format.to_bytes(endian)
        if self.type_value == int(AwcChunkType.STREAM_FORMAT) and self.stream_format is not None:
            return self.stream_format.to_bytes(endian)
        if self.type_value == int(AwcChunkType.PEAK) and self.peaks is not None:
            return struct.pack(f"{endian}{len(self.peaks)}H", *[int(value) & 0xFFFF for value in self.peaks]) if self.peaks else b""
        if self.type_value == int(AwcChunkType.SEEK_TABLE) and self.seek_table is not None:
            return struct.pack(f"{endian}{len(self.seek_table)}I", *[int(value) & 0xFFFFFFFF for value in self.seek_table]) if self.seek_table else b""
        return bytes(self.data)


@dataclass(slots=True)
class AwcStream:
    id: int = 0
    chunks: list[AwcChunk] = field(default_factory=list)
    name: str | None = None

    def __init__(
        self,
        id: HashLike | None = 0,
        chunks: Iterable[AwcChunk] | None = None,
        *,
        name: str | None = None,
    ) -> None:
        self.id = _hash_from_name(name) if name and id in (None, 0, "") else _coerce_stream_id(id)
        self.chunks = list(chunks or [])
        self.name = name

    @staticmethod
    def from_pcm(name: HashLike | str, pcm: bytes, *, sample_rate: int) -> "AwcStream":
        return _awc_stream_from_pcm(name, pcm, sample_rate=sample_rate)

    @property
    def hash(self) -> int:
        return self.id & AWC_STREAM_ID_MASK

    @property
    def format_chunk(self) -> AwcFormat | None:
        for chunk in self.chunks:
            if chunk.format is not None:
                return chunk.format
        return None

    @property
    def stream_format_chunk(self) -> AwcStreamFormatChunk | None:
        for chunk in self.chunks:
            if chunk.stream_format is not None:
                return chunk.stream_format
        return None

    @property
    def data_chunk(self) -> AwcChunk | None:
        for chunk in self.chunks:
            if chunk.type_value == int(AwcChunkType.DATA):
                return chunk
        return None

    @property
    def codec(self) -> AwcCodecType | None:
        fmt = self.format_chunk
        return fmt.codec if fmt is not None else None

    @property
    def sample_rate(self) -> int:
        fmt = self.format_chunk
        return int(fmt.sample_rate) if fmt is not None else 0

    @property
    def sample_count(self) -> int:
        fmt = self.format_chunk
        return int(fmt.samples) if fmt is not None else 0

    @property
    def duration(self) -> float:
        fmt = self.format_chunk
        return fmt.duration if fmt is not None else 0.0

    @property
    def raw_audio_bytes(self) -> bytes:
        chunk = self.data_chunk
        return chunk.to_payload() if chunk is not None else b""

    def pcm_bytes(self) -> bytes:
        data = self.raw_audio_bytes
        codec = self.codec or AwcCodecType.PCM
        if codec is AwcCodecType.ADPCM:
            return decode_awc_adpcm(data, self.sample_count)
        return data

    def wav_bytes(self) -> bytes:
        return build_pcm_wav(self.pcm_bytes(), sample_rate=self.sample_rate, channels=1, bits_per_sample=16)


@dataclass(slots=True)
class Awc:
    streams: list[AwcStream] = field(default_factory=list)
    version: int = 1
    flags: int = AWC_DEFAULT_FLAGS
    path: str | None = None
    endian: str = "<"
    whole_file_encrypted: bool = False

    def __init__(
        self,
        streams: Iterable[AwcStream] | None = None,
        *,
        version: int = 1,
        flags: int = AWC_DEFAULT_FLAGS,
        path: str | Path | None = None,
        endian: str = "<",
        whole_file_encrypted: bool = False,
    ) -> None:
        self.streams = list(streams or [])
        self.version = int(version)
        self.flags = int(flags)
        self.path = str(path) if path is not None else None
        self.endian = endian
        self.whole_file_encrypted = bool(whole_file_encrypted)

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, *, path: str | Path | None = None) -> "Awc":
        from .io import read_awc

        return read_awc(data, path=path)

    @classmethod
    def from_file(cls, path: str | Path) -> "Awc":
        from .io import read_awc

        return read_awc(path)

    @classmethod
    def from_wav(cls, name: HashLike | str, wav: bytes | bytearray | memoryview | str | Path) -> "Awc":
        wav_data = Path(wav).read_bytes() if isinstance(wav, (str, Path)) else bytes(wav)
        pcm, sample_rate, channels, bits_per_sample = parse_pcm_wav(wav_data)
        if channels != 1:
            raise ValueError("AWC WAV import currently supports mono PCM only")
        if bits_per_sample != 16:
            raise ValueError("AWC WAV import currently supports 16-bit PCM only")
        stream = AwcStream.from_pcm(name, pcm, sample_rate=sample_rate)
        return cls([stream])

    @property
    def stream_count(self) -> int:
        return len(self.streams)

    @property
    def chunk_indices_flag(self) -> bool:
        return bool(self.flags & 1)

    @chunk_indices_flag.setter
    def chunk_indices_flag(self, value: bool) -> None:
        self.flags = (self.flags | 1) if value else (self.flags & ~1)

    @property
    def single_channel_encrypt_flag(self) -> bool:
        return bool(self.flags & 2)

    @single_channel_encrypt_flag.setter
    def single_channel_encrypt_flag(self, value: bool) -> None:
        self.flags = (self.flags | 2) if value else (self.flags & ~2)

    @property
    def multi_channel_flag(self) -> bool:
        return bool(self.flags & 4)

    @multi_channel_flag.setter
    def multi_channel_flag(self, value: bool) -> None:
        self.flags = (self.flags | 4) if value else (self.flags & ~4)

    @property
    def multi_channel_encrypt_flag(self) -> bool:
        return bool(self.flags & 8)

    @multi_channel_encrypt_flag.setter
    def multi_channel_encrypt_flag(self, value: bool) -> None:
        self.flags = (self.flags | 8) if value else (self.flags & ~8)

    def stream(self, value: int | str | MetaHash) -> AwcStream | None:
        target = _hash_from_name(value) if isinstance(value, str) else (int(value) & AWC_STREAM_ID_MASK)
        for stream in self.streams:
            if stream.hash == target:
                return stream
        return None

    def to_bytes(self) -> bytes:
        from .io import build_awc_bytes

        return build_awc_bytes(self)

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())


def _awc_stream_from_pcm(name: HashLike | str, pcm: bytes, *, sample_rate: int) -> AwcStream:
    sample_count = len(pcm) // 2
    fmt = AwcFormat(
        samples=sample_count,
        loop_point=-1,
        sample_rate=int(sample_rate),
        headroom=0,
        play_begin=0,
        play_end=min(sample_count, 0xFFFF),
        codec=AwcCodecType.PCM,
    )
    peaks = _build_peak_values(pcm, sample_count)
    if peaks:
        fmt.peak = peaks[0]
        peak_chunk_values = peaks[1:]
    else:
        peak_chunk_values = []
    chunks = [
        AwcChunk(AwcChunkType.FORMAT, format=fmt),
        AwcChunk(AwcChunkType.DATA, data=bytes(pcm)),
    ]
    if peak_chunk_values:
        chunks.insert(1, AwcChunk(AwcChunkType.PEAK, peaks=peak_chunk_values))
    text_name = str(name) if isinstance(name, str) else None
    return AwcStream(name if not isinstance(name, str) else None, chunks, name=text_name)


__all__ = [
    "Awc",
    "AwcChunk",
    "AwcChunkInfo",
    "AwcFormat",
    "AwcStream",
    "AwcStreamFormat",
    "AwcStreamFormatChunk",
]
