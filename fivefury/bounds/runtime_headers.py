from __future__ import annotations

from collections.abc import Callable, Mapping

from ..game_target import GameTarget, coerce_game_target
from .model import Bound, BoundType

LEGACY_BOUND_FILE_VFTS: Mapping[BoundType, int] = {
    BoundType.SPHERE: 0x4062E108,
    BoundType.CAPSULE: 0x4062BE78,
    BoundType.BOX: 0x4062DD58,
    BoundType.DISC: 0x40630048,
    BoundType.CYLINDER: 0x40629678,
    BoundType.GEOMETRY: 0x4062F268,
    BoundType.GEOMETRY_BVH: 0x4062FAB8,
    BoundType.COMPOSITE: 0x4062BAA8,
}

GEN9_BOUND_FILE_VFTS: Mapping[BoundType, int] = {
    BoundType.SPHERE: 0x406B2328,
    BoundType.CAPSULE: 0x406B1868,
    BoundType.BOX: 0x406B1F48,
    BoundType.DISC: 0x406B24E8,
    BoundType.CYLINDER: 0x406B2400,
    BoundType.GEOMETRY: 0x406B2020,
    BoundType.GEOMETRY_BVH: 0x406B2130,
    BoundType.COMPOSITE: 0x406B1940,
}


def _bound_file_vft(bound: Bound, mapping: Mapping[BoundType, int], target: GameTarget) -> int:
    try:
        return mapping[bound.bound_type]
    except KeyError as exc:
        raise ValueError(
            f"{target.value} does not define a runtime header for {bound.bound_type.name}"
        ) from exc


def legacy_bound_file_vft(bound: Bound) -> int:
    return _bound_file_vft(bound, LEGACY_BOUND_FILE_VFTS, GameTarget.GTA5)


def gen9_bound_file_vft(bound: Bound) -> int:
    return _bound_file_vft(bound, GEN9_BOUND_FILE_VFTS, GameTarget.GTA5_ENHANCED)


def get_bound_file_vft_resolver(game: str | GameTarget) -> Callable[[Bound], int]:
    target = coerce_game_target(game)
    return gen9_bound_file_vft if target is GameTarget.GTA5_ENHANCED else legacy_bound_file_vft


def infer_bound_game(file_vft: int) -> GameTarget:
    if int(file_vft) in GEN9_BOUND_FILE_VFTS.values():
        return GameTarget.GTA5_ENHANCED
    return GameTarget.GTA5


__all__ = [
    "GEN9_BOUND_FILE_VFTS",
    "LEGACY_BOUND_FILE_VFTS",
    "gen9_bound_file_vft",
    "get_bound_file_vft_resolver",
    "infer_bound_game",
    "legacy_bound_file_vft",
]
