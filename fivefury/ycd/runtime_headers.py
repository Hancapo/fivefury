from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType

from ..game_target import GameTarget, coerce_game_target

YCD_VERSION = 46


@dataclasses.dataclass(frozen=True, slots=True)
class YcdRuntimeProfile:
    game: GameTarget
    file_vft: int
    animation_map_vft: int
    animation_vft: int
    clip_animation_vft: int
    clip_animation_list_vft: int
    clip_property_vft: int
    clip_tag_vft: int
    attribute_vfts: Mapping[int, int]

    def attribute_vft(self, attribute_type: int) -> int:
        try:
            return self.attribute_vfts[int(attribute_type)]
        except KeyError as exc:
            raise ValueError(
                f"YCD attribute type {int(attribute_type)} has no verified runtime header for {self.game.value}"
            ) from exc


LEGACY_YCD_RUNTIME_PROFILE = YcdRuntimeProfile(
    game=GameTarget.GTA5,
    file_vft=0x405702E8,
    animation_map_vft=0x405A7C08,
    animation_vft=0x405A58F0,
    clip_animation_vft=0x405A4088,
    clip_animation_list_vft=0x405A3FF8,
    clip_property_vft=0x406110F8,
    clip_tag_vft=0x40614FA0,
    attribute_vfts=MappingProxyType(
        {
            1: 0x40615078,
            2: 0x406150E8,
            3: 0x40615158,
            6: 0x40615218,
            8: 0x40615318,
            12: 0x40615498,
        }
    ),
)

GEN9_YCD_RUNTIME_PROFILE = YcdRuntimeProfile(
    game=GameTarget.GTA5_ENHANCED,
    file_vft=0x4068E340,
    animation_map_vft=0x406AF610,
    animation_vft=0x406AEB48,
    clip_animation_vft=0x406DA038,
    clip_animation_list_vft=0x406DA0E0,
    clip_property_vft=0x406BD5B8,
    clip_tag_vft=0x406BDEA0,
    attribute_vfts=MappingProxyType(
        {
            1: 0x406BD658,
            2: 0x406BD6A0,
            3: 0x406BD6E8,
            6: 0x406BD7C0,
            8: 0x406BD850,
            12: 0x406BD970,
        }
    ),
)


def get_ycd_runtime_profile(game: str | GameTarget) -> YcdRuntimeProfile:
    target = coerce_game_target(game)
    return GEN9_YCD_RUNTIME_PROFILE if target is GameTarget.GTA5_ENHANCED else LEGACY_YCD_RUNTIME_PROFILE


def infer_ycd_game(file_vft: int) -> GameTarget:
    if int(file_vft) == GEN9_YCD_RUNTIME_PROFILE.file_vft:
        return GameTarget.GTA5_ENHANCED
    return GameTarget.GTA5


__all__ = [
    "GEN9_YCD_RUNTIME_PROFILE",
    "LEGACY_YCD_RUNTIME_PROFILE",
    "YCD_VERSION",
    "YcdRuntimeProfile",
    "get_ycd_runtime_profile",
    "infer_ycd_game",
]
