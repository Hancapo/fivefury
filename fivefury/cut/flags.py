from __future__ import annotations

from enum import IntFlag
from typing import Iterable, Sequence


class CutSceneFlags(IntFlag):
    NONE = 0
    FADE_IN_GAME = 1 << 0
    FADE_OUT_GAME = 1 << 1
    FADE_IN_CUTSCENE = 1 << 2
    FADE_OUT_CUTSCENE = 1 << 3
    SHORT_FADE_OUT = 1 << 4
    LONG_FADE_OUT = 1 << 5
    FADE_BETWEEN_SECTIONS = 1 << 6
    NO_AMBIENT_LIGHTS = 1 << 7
    NO_VEHICLE_LIGHTS = 1 << 8
    USE_ONE_AUDIO = 1 << 9
    MUTE_MUSIC_PLAYER = 1 << 10
    LEAK_RADIO = 1 << 11
    TRANSLATE_BONE_IDS = 1 << 12
    INTERP_CAMERA = 1 << 13
    IS_SECTIONED = 1 << 14
    SECTION_BY_CAMERA_CUTS = 1 << 15
    SECTION_BY_DURATION = 1 << 16
    SECTION_BY_SPLIT = 1 << 17
    USE_PARENT_SCALE = 1 << 18
    USE_ONE_SCENE_ORIENTATION = 1 << 19
    ENABLE_DEPTH_OF_FIELD = 1 << 20
    STREAM_PROCESSED = 1 << 21
    USE_STORY_MODE = 1 << 22
    USE_IN_GAME_DOF_START = 1 << 23
    USE_IN_GAME_DOF_END = 1 << 24
    USE_CATCHUP_CAMERA = 1 << 25
    USE_BLENDOUT_CAMERA = 1 << 26
    PART = 1 << 27
    INTERNAL_CONCAT = 1 << 28
    EXTERNAL_CONCAT = 1 << 29
    USE_AUDIO_EVENTS_CONCAT = 1 << 30
    USE_IN_GAME_DOF_START_SECOND_CUT = 1 << 31


DEFAULT_PLAYABLE_CUTSCENE_FLAGS = (
    CutSceneFlags.USE_ONE_AUDIO
    | CutSceneFlags.IS_SECTIONED
    | CutSceneFlags.USE_STORY_MODE
    | CutSceneFlags.USE_IN_GAME_DOF_START
    | CutSceneFlags.INTERNAL_CONCAT
)


def pack_cutscene_flags(value: CutSceneFlags | int | Sequence[int] | None) -> list[int]:
    if value is None:
        packed = int(DEFAULT_PLAYABLE_CUTSCENE_FLAGS)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [int(item) & 0xFFFFFFFF for item in list(value)[:4]] + [0] * max(0, 4 - len(value))
    else:
        packed = int(value)
    return [packed & 0xFFFFFFFF, 0, 0, 0]


def unpack_cutscene_flags(value: Iterable[int] | int | None) -> CutSceneFlags:
    if value is None:
        return CutSceneFlags.NONE
    if isinstance(value, int):
        return CutSceneFlags(value & 0xFFFFFFFF)
    values = list(value)
    return CutSceneFlags((int(values[0]) if values else 0) & 0xFFFFFFFF)


__all__ = [
    "CutSceneFlags",
    "DEFAULT_PLAYABLE_CUTSCENE_FLAGS",
    "pack_cutscene_flags",
    "unpack_cutscene_flags",
]
