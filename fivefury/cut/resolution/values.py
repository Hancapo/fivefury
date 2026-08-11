from __future__ import annotations

from typing import Any

from ...metahash import MetaHash
from ..model import CutHashedString


def field_hash(value: Any) -> int | None:
    if isinstance(value, CutHashedString):
        return int(value.hash) & 0xFFFFFFFF if value.hash else None
    uint = getattr(value, "uint", None)
    if uint is not None:
        return int(uint) & 0xFFFFFFFF if int(uint) else None
    if isinstance(value, int) and value:
        return int(value) & 0xFFFFFFFF
    return None


def field_reference(value: Any) -> str | int | None:
    if isinstance(value, CutHashedString):
        return value.text or (int(value.hash) & 0xFFFFFFFF if value.hash else None)
    if isinstance(value, str):
        return value or None
    return field_hash(value)


def subtitle_hash(value: Any) -> int | None:
    value_hash = field_hash(value)
    if value_hash is not None:
        return value_hash
    if isinstance(value, str) and value:
        return MetaHash(value).uint
    return None


__all__ = ["field_hash", "field_reference", "subtitle_hash"]
