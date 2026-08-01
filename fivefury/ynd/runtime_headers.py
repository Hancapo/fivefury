from __future__ import annotations

import dataclasses

from ..game_target import GameTarget, coerce_game_target

YND_VERSION = 1


@dataclasses.dataclass(frozen=True, slots=True)
class YndRuntimeProfile:
    game: GameTarget
    file_vft: int


LEGACY_YND_RUNTIME_PROFILE = YndRuntimeProfile(
    game=GameTarget.GTA5,
    file_vft=0x406203D0,
)
GEN9_YND_RUNTIME_PROFILE = YndRuntimeProfile(
    game=GameTarget.GTA5_ENHANCED,
    file_vft=0x406D2A40,
)


def get_ynd_runtime_profile(game: str | GameTarget) -> YndRuntimeProfile:
    target = coerce_game_target(game)
    return GEN9_YND_RUNTIME_PROFILE if target is GameTarget.GTA5_ENHANCED else LEGACY_YND_RUNTIME_PROFILE


def infer_ynd_game(file_vft: int) -> GameTarget:
    if int(file_vft) == GEN9_YND_RUNTIME_PROFILE.file_vft:
        return GameTarget.GTA5_ENHANCED
    return GameTarget.GTA5


__all__ = [
    "GEN9_YND_RUNTIME_PROFILE",
    "LEGACY_YND_RUNTIME_PROFILE",
    "YND_VERSION",
    "YndRuntimeProfile",
    "get_ynd_runtime_profile",
    "infer_ynd_game",
]
