from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..awc.layout import AwcSpeaker
from ..game_target import GameTarget, coerce_game_target
from ..rel import RelSoundHeader


class CutAudioCodec(StrEnum):
    RETAIL = "retail"
    ANALYSIS_PCM = "analysis_pcm"


@dataclass(frozen=True, slots=True)
class CutAudioRoute:
    channel: AwcSpeaker
    flags: int
    pan: int = 0
    speaker_mask: int = 0

    def header(self) -> RelSoundHeader:
        return RelSoundHeader(
            flags=self.flags,
            pan=self.pan,
            speaker_mask=self.speaker_mask,
        )


@dataclass(frozen=True, slots=True)
class CutAudioProfile:
    game: GameTarget
    multichannel_flags: int

    @classmethod
    def retail(cls, game: str | GameTarget) -> CutAudioProfile:
        target = coerce_game_target(game)
        return cls(
            game=target,
            multichannel_flags=(
                0xFF0C if target is GameTarget.GTA5_ENHANCED else 0xFF05
            ),
        )

    def streaming_header(self) -> RelSoundHeader:
        return RelSoundHeader(
            flags=0x0080A001,
            flags2=0xAA91AAAA,
            release_time=300,
            category=0x7F01B626,
            speaker_mask=0,
        )

    def routes(
        self,
        channels: tuple[AwcSpeaker, ...],
    ) -> tuple[CutAudioRoute, ...]:
        del self
        if len(channels) in {2, 3}:
            return tuple(_stereo_route(channel) for channel in channels)
        return tuple(
            CutAudioRoute(
                channel=channel,
                flags=0x00800000,
                speaker_mask=int(channel),
            )
            for channel in channels
        )


def _stereo_route(channel: AwcSpeaker) -> CutAudioRoute:
    if channel is AwcSpeaker.FRONT_LEFT:
        return CutAudioRoute(channel, flags=0x00800040, pan=307)
    if channel is AwcSpeaker.FRONT_RIGHT:
        return CutAudioRoute(channel, flags=0x00800040, pan=53)
    return CutAudioRoute(
        channel,
        flags=0x00800000,
        speaker_mask=int(channel),
    )


__all__ = [
    "CutAudioCodec",
    "CutAudioProfile",
    "CutAudioRoute",
]
