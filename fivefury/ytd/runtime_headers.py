from __future__ import annotations

import dataclasses

from ..game_target import GameTarget


@dataclasses.dataclass(frozen=True, slots=True)
class Gen9TextureRuntimeProfile:
    game: GameTarget
    texture_vft: int
    descriptor_flags: int
    tile_mode: int
    image_flags: int
    usage_class: int
    srv_vft: int
    srv_dimension: int


GEN9_TEXTURE_RUNTIME_PROFILE = Gen9TextureRuntimeProfile(
    game=GameTarget.GTA5_ENHANCED,
    texture_vft=0x00000001406B7940,
    descriptor_flags=0x00260208,
    tile_mode=0xFF,
    image_flags=0,
    usage_class=2,
    srv_vft=0x00000001406B77D8,
    srv_dimension=0x41,
)


__all__ = [
    "GEN9_TEXTURE_RUNTIME_PROFILE",
    "Gen9TextureRuntimeProfile",
]
