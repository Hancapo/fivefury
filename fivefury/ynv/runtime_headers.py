from __future__ import annotations

import dataclasses

from ..game_target import GameTarget, coerce_game_target

YNV_VERSION = 2


@dataclasses.dataclass(frozen=True, slots=True)
class YnvRuntimeProfile:
    game: GameTarget
    file_vft: int
    vertices_vft: int
    indices_vft: int
    edges_vft: int
    polys_vft: int


LEGACY_YNV_RUNTIME_PROFILE = YnvRuntimeProfile(
    game=GameTarget.GTA5,
    file_vft=0x4061E7E8,
    vertices_vft=0x4061E8F8,
    indices_vft=0x4061E8D8,
    edges_vft=0x4061E8E8,
    polys_vft=0x4061E8C8,
)
GEN9_YNV_RUNTIME_PROFILE = YnvRuntimeProfile(
    game=GameTarget.GTA5_ENHANCED,
    file_vft=0x406D2160,
    vertices_vft=0x406D21A8,
    indices_vft=0x406D21A8,
    edges_vft=0x406D21A8,
    polys_vft=0x406D21A8,
)


def get_ynv_runtime_profile(game: str | GameTarget) -> YnvRuntimeProfile:
    target = coerce_game_target(game)
    return GEN9_YNV_RUNTIME_PROFILE if target is GameTarget.GTA5_ENHANCED else LEGACY_YNV_RUNTIME_PROFILE


def infer_ynv_game(file_vft: int) -> GameTarget:
    if int(file_vft) == GEN9_YNV_RUNTIME_PROFILE.file_vft:
        return GameTarget.GTA5_ENHANCED
    return GameTarget.GTA5


__all__ = [
    "GEN9_YNV_RUNTIME_PROFILE",
    "LEGACY_YNV_RUNTIME_PROFILE",
    "YNV_VERSION",
    "YnvRuntimeProfile",
    "get_ynv_runtime_profile",
    "infer_ynv_game",
]
