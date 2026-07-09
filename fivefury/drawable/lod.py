from __future__ import annotations

import enum


class DrawableLod(enum.StrEnum):
    HIGH = "high"
    MEDIUM = "med"
    LOW = "low"
    VERY_LOW = "vlow"


DRAWABLE_LOD_ORDER = (
    DrawableLod.HIGH,
    DrawableLod.MEDIUM,
    DrawableLod.LOW,
    DrawableLod.VERY_LOW,
)

_LOD_ALIASES = {
    "high": DrawableLod.HIGH,
    "med": DrawableLod.MEDIUM,
    "medium": DrawableLod.MEDIUM,
    "low": DrawableLod.LOW,
    "vlow": DrawableLod.VERY_LOW,
    "very_low": DrawableLod.VERY_LOW,
    "verylow": DrawableLod.VERY_LOW,
}


def coerce_drawable_lod(value: DrawableLod | str) -> DrawableLod:
    if isinstance(value, DrawableLod):
        return value
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return _LOD_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown drawable LOD '{value}'") from exc


__all__ = ["DRAWABLE_LOD_ORDER", "DrawableLod", "coerce_drawable_lod"]
