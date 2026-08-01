from __future__ import annotations

import dataclasses

from ..game_target import GameTarget, coerce_game_target

YED_VERSION = 25


@dataclasses.dataclass(frozen=True, slots=True)
class YedRuntimeProfile:
    game: GameTarget
    dictionary_vft: int
    expression_vft: int


LEGACY_YED_RUNTIME_PROFILE = YedRuntimeProfile(
    game=GameTarget.GTA5,
    dictionary_vft=0x40573540,
    expression_vft=0x405A3548,
)
GEN9_YED_RUNTIME_PROFILE = YedRuntimeProfile(
    game=GameTarget.GTA5_ENHANCED,
    dictionary_vft=0x4068E748,
    expression_vft=0x406DAD90,
)

GEN9_YED_DICTIONARY_VFTS = frozenset(
    {
        GEN9_YED_RUNTIME_PROFILE.dictionary_vft,
        0x405F5228,
    }
)


def get_yed_runtime_profile(game: str | GameTarget) -> YedRuntimeProfile:
    target = coerce_game_target(game)
    return GEN9_YED_RUNTIME_PROFILE if target is GameTarget.GTA5_ENHANCED else LEGACY_YED_RUNTIME_PROFILE


def infer_yed_game(dictionary_vft: int) -> GameTarget:
    if int(dictionary_vft) in GEN9_YED_DICTIONARY_VFTS:
        return GameTarget.GTA5_ENHANCED
    return GameTarget.GTA5


__all__ = [
    "GEN9_YED_DICTIONARY_VFTS",
    "GEN9_YED_RUNTIME_PROFILE",
    "LEGACY_YED_RUNTIME_PROFILE",
    "YED_VERSION",
    "YedRuntimeProfile",
    "get_yed_runtime_profile",
    "infer_yed_game",
]
