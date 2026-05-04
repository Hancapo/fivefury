from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .structures import Awc


SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".mp3", ".ogg", ".oga", ".flac")


@dataclass(frozen=True, slots=True)
class DecodedAudio:
    pcm: bytes
    sample_rate: int
    channels: int
    bits_per_sample: int = 16

    @property
    def frame_count(self) -> int:
        frame_size = self.channels * (self.bits_per_sample // 8)
        return len(self.pcm) // frame_size if frame_size else 0

    @property
    def duration(self) -> float:
        return (self.frame_count / self.sample_rate) if self.sample_rate else 0.0


def _load_miniaudio() -> Any:
    try:
        import miniaudio
    except ImportError as exc:  # pragma: no cover - dependency is declared, this is for broken installs.
        raise RuntimeError("Audio conversion requires the 'miniaudio' package to be installed") from exc
    return miniaudio


def _normalize_source_format(source_format: str | None, path: Path | None = None) -> str | None:
    value = source_format or (path.suffix if path is not None else None)
    if not value:
        return None
    value = value.lower()
    return value if value.startswith(".") else f".{value}"


def _info_from_bytes(miniaudio: Any, data: bytes, source_format: str | None) -> Any | None:
    suffix = _normalize_source_format(source_format)
    if suffix in {".ogg", ".oga"}:
        return miniaudio.vorbis_get_info(data)
    if suffix == ".flac":
        return miniaudio.flac_get_info(data)
    if suffix == ".mp3":
        return miniaudio.mp3_get_info(data)
    if suffix == ".wav":
        return miniaudio.wav_get_info(data)
    return None


def decode_audio(
    source: bytes | bytearray | memoryview | str | Path,
    *,
    sample_rate: int | None = None,
    channels: int | None = None,
    source_format: str | None = None,
) -> DecodedAudio:
    """Decode a popular audio format to signed 16-bit PCM with miniaudio.

    File input preserves the source sample rate unless ``sample_rate`` is provided.
    Byte input can also preserve the rate when ``source_format`` is supplied.
    """

    if channels is not None and channels <= 0:
        raise ValueError("channels must be greater than zero")

    miniaudio = _load_miniaudio()
    output_format = miniaudio.SampleFormat.SIGNED16

    if isinstance(source, (str, Path)):
        path = Path(source)
        info = miniaudio.get_file_info(str(path))
        output_rate = int(sample_rate or info.sample_rate)
        output_channels = int(channels or info.nchannels)
        decoded = miniaudio.decode_file(str(path), output_format=output_format, nchannels=output_channels, sample_rate=output_rate)
    else:
        data = bytes(source)
        info = _info_from_bytes(miniaudio, data, source_format)
        output_rate = int(sample_rate or (info.sample_rate if info is not None else 44100))
        output_channels = int(channels or (info.nchannels if info is not None else 2))
        decoded = miniaudio.decode(data, output_format=output_format, nchannels=output_channels, sample_rate=output_rate)

    return DecodedAudio(
        pcm=decoded.samples.tobytes(),
        sample_rate=int(decoded.sample_rate),
        channels=int(decoded.nchannels),
        bits_per_sample=16,
    )


def convert_audio_to_awc(
    source: bytes | bytearray | memoryview | str | Path,
    target: str | Path,
    *,
    stream_name: str | None = None,
    sample_rate: int | None = None,
    channels: int | None = None,
    source_format: str | None = None,
) -> "Awc":
    from .structures import Awc

    awc = Awc.from_audio(stream_name or _default_stream_name(source), source, sample_rate=sample_rate, channels=channels, source_format=source_format)
    awc.save(target)
    return awc


def _default_stream_name(source: bytes | bytearray | memoryview | str | Path) -> str:
    if isinstance(source, (str, Path)):
        return Path(source).stem
    return "audio_stream"


__all__ = [
    "DecodedAudio",
    "SUPPORTED_AUDIO_EXTENSIONS",
    "convert_audio_to_awc",
    "decode_audio",
]
