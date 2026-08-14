from __future__ import annotations

from ..gamefile import GameFileType

CUT_MODEL_KINDS_BY_ROLE: dict[str, tuple[GameFileType, ...]] = {
    "ped": (
        GameFileType.YFT,
        GameFileType.YDD,
        GameFileType.YMT,
        GameFileType.YTD,
    ),
    "prop": (
        GameFileType.YDR,
        GameFileType.YDD,
        GameFileType.YFT,
        GameFileType.YTD,
    ),
    "vehicle": (GameFileType.YFT, GameFileType.YTD, GameFileType.YCD),
    "weapon": (
        GameFileType.YDR,
        GameFileType.YDD,
        GameFileType.YFT,
        GameFileType.YTD,
    ),
    "particle_fx": (GameFileType.YPT,),
}

CUT_DRAWABLE_KINDS_BY_ROLE: dict[str, tuple[GameFileType, ...]] = {
    role: tuple(
        kind
        for kind in kinds
        if kind in {GameFileType.YDR, GameFileType.YDD, GameFileType.YFT}
    )
    for role, kinds in CUT_MODEL_KINDS_BY_ROLE.items()
}


__all__ = ["CUT_DRAWABLE_KINDS_BY_ROLE", "CUT_MODEL_KINDS_BY_ROLE"]
