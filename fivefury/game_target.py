from __future__ import annotations

from enum import StrEnum


class GameTarget(StrEnum):
    GTA5 = "gta5"
    GTA5_ENHANCED = "gta5_enhanced"


def coerce_game_target(value: str | GameTarget) -> GameTarget:
    if isinstance(value, GameTarget):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"gta5", "legacy"}:
        return GameTarget.GTA5
    if normalized in {"gta5_enhanced", "enhanced", "gen9"}:
        return GameTarget.GTA5_ENHANCED
    raise ValueError(f"Unsupported target game: {value}")


__all__ = [
    "GameTarget",
    "coerce_game_target",
]
