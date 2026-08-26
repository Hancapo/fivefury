from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from ..game_target import GameTarget
from .audio_profiles import CutAudioCodec

if TYPE_CHECKING:
    from ..awc import Awc, DecodedAudio


def _decoded_awc(awc: Awc) -> DecodedAudio:
    from ..awc import DecodedAudio, awc_playback_streams

    streams = awc_playback_streams(awc)
    if not streams:
        raise ValueError("AWC contains no playable stream for CUT audio")
    if awc.multi_channel_flag:
        layout = streams[0].stream_format_chunk
        if len(streams) != 1 or layout is None or not layout.channels:
            raise ValueError("AWC multichannel layout cannot be decoded for authoring")
        sample_rates = {int(channel.sample_rate) for channel in layout.channels}
        if len(sample_rates) != 1:
            raise ValueError("AWC channels must use one sample rate")
        return DecodedAudio(
            awc.pcm_bytes(),
            sample_rates.pop(),
            len(layout.channels),
        )
    if len(streams) != 1:
        raise ValueError("CUT audio authoring requires one playable AWC stream")
    return DecodedAudio(awc.pcm_bytes(), streams[0].sample_rate, 1)


def _resample_audio(source: DecodedAudio, *, sample_rate: int) -> DecodedAudio:
    from ..awc import build_pcm_wav, decode_audio

    if source.bits_per_sample != 16:
        raise ValueError("CUT audio authoring requires signed 16-bit PCM")
    if source.sample_rate <= 0 or sample_rate <= 0:
        raise ValueError("CUT audio sample rates must be positive")
    frame_size = source.channels * 2
    if source.channels <= 0 or len(source.pcm) % frame_size:
        raise ValueError("Decoded CUT audio has an invalid PCM channel layout")
    if source.sample_rate == sample_rate:
        return source
    wav = build_pcm_wav(
        source.pcm,
        sample_rate=source.sample_rate,
        channels=source.channels,
        bits_per_sample=16,
    )
    return decode_audio(
        wav,
        sample_rate=sample_rate,
        channels=source.channels,
        source_format=".wav",
    )


def _pcm_awc(name: str, source: DecodedAudio) -> Awc:
    from ..awc import Awc, AwcStream

    if source.channels == 1:
        return Awc(
            [AwcStream.from_pcm(name, source.pcm, sample_rate=source.sample_rate)]
        )
    return Awc.from_multichannel_pcm(
        name,
        source.pcm,
        sample_rate=source.sample_rate,
        channels=source.channels,
    )


def _author_cut_awc(
    name: str,
    source: Awc | DecodedAudio,
    *,
    game: GameTarget,
    codec: CutAudioCodec,
) -> Awc:
    from ..awc import Awc, AwcCodecType, DecodedAudio, awc_channel_codecs

    if isinstance(source, Awc):
        source_codecs = awc_channel_codecs(source)
        if (
            game is GameTarget.GTA5_ENHANCED
            and codec is CutAudioCodec.RETAIL
            and source_codecs
            and all(value is AwcCodecType.MP3 for value in source_codecs)
        ):
            return deepcopy(source)
        if game is GameTarget.GTA5 and codec is CutAudioCodec.RETAIL:
            return deepcopy(source)
        decoded = _decoded_awc(source)
    elif isinstance(source, DecodedAudio):
        decoded = source
    else:
        raise TypeError(f"expected Awc or DecodedAudio, got {type(source).__name__}")

    output_sample_rate = (
        48_000
        if game is GameTarget.GTA5_ENHANCED and codec is CutAudioCodec.RETAIL
        else decoded.sample_rate
    )
    decoded = _resample_audio(decoded, sample_rate=output_sample_rate)
    if game is GameTarget.GTA5_ENHANCED and codec is CutAudioCodec.RETAIL:
        return Awc.from_channel_mp3(
            name,
            list(decoded.channel_pcm),
            sample_rate=48_000,
        )
    return _pcm_awc(name, decoded)
