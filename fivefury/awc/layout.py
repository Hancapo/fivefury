from __future__ import annotations

from enum import IntEnum


class AwcSpeaker(IntEnum):
    FRONT_LEFT = 1
    FRONT_RIGHT = 2
    FRONT_CENTER = 4
    LFE = 8
    REAR_LEFT = 16
    REAR_RIGHT = 32


def default_awc_speakers(count: int) -> tuple[AwcSpeaker, ...]:
    layouts = {
        1: (AwcSpeaker.FRONT_CENTER,),
        2: (AwcSpeaker.FRONT_LEFT, AwcSpeaker.FRONT_RIGHT),
        3: (
            AwcSpeaker.FRONT_CENTER,
            AwcSpeaker.FRONT_LEFT,
            AwcSpeaker.FRONT_RIGHT,
        ),
        4: (
            AwcSpeaker.FRONT_CENTER,
            AwcSpeaker.FRONT_LEFT,
            AwcSpeaker.FRONT_RIGHT,
            AwcSpeaker.LFE,
        ),
        5: (
            AwcSpeaker.FRONT_CENTER,
            AwcSpeaker.FRONT_LEFT,
            AwcSpeaker.REAR_LEFT,
            AwcSpeaker.FRONT_RIGHT,
            AwcSpeaker.REAR_RIGHT,
        ),
        6: (
            AwcSpeaker.FRONT_CENTER,
            AwcSpeaker.FRONT_LEFT,
            AwcSpeaker.REAR_LEFT,
            AwcSpeaker.FRONT_RIGHT,
            AwcSpeaker.REAR_RIGHT,
            AwcSpeaker.LFE,
        ),
    }
    try:
        return layouts[int(count)]
    except KeyError as exc:
        raise ValueError("AWC speaker layouts support one through six channels") from exc


__all__ = ["AwcSpeaker", "default_awc_speakers"]
