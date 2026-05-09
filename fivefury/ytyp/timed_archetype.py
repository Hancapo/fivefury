from __future__ import annotations

import dataclasses
from typing import Any

from ..meta.defs import meta_name
from .base_archetype import BaseArchetypeDef
from .flags import TimeArchetypeFlags


def coerce_time_archetype_flags(value: int | TimeArchetypeFlags) -> TimeArchetypeFlags:
    return value if isinstance(value, TimeArchetypeFlags) else TimeArchetypeFlags(int(value))


@dataclasses.dataclass(slots=True)
class TimeArchetypeDef(BaseArchetypeDef):
    time_flags: TimeArchetypeFlags | int = TimeArchetypeFlags.NONE

    def __post_init__(self) -> None:
        super().__post_init__()
        self.time_flags = coerce_time_archetype_flags(self.time_flags)

    @property
    def flip_while_visible(self) -> bool:
        return bool(self.time_flags & TimeArchetypeFlags.FLIP_WHILE_VISIBLE)

    @flip_while_visible.setter
    def flip_while_visible(self, value: bool) -> None:
        if value:
            self.time_flags |= TimeArchetypeFlags.FLIP_WHILE_VISIBLE
        else:
            self.time_flags &= ~TimeArchetypeFlags.FLIP_WHILE_VISIBLE

    @property
    def hour_flags(self) -> TimeArchetypeFlags:
        return self.time_flags & TimeArchetypeFlags.ALL_HOURS

    def to_meta(self) -> dict[str, Any]:
        data = super().to_meta()
        data.update({"timeFlags": int(self.time_flags), "_meta_name_hash": meta_name("CTimeArchetypeDef")})
        return data

    @classmethod
    def from_meta(cls, value: Any) -> "TimeArchetypeDef":
        base = BaseArchetypeDef.from_meta(value)
        return cls(**dataclasses.asdict(base), time_flags=coerce_time_archetype_flags(int(value.get("timeFlags", 0))))


TimeArchetype = TimeArchetypeDef


__all__ = ["TimeArchetype", "TimeArchetypeDef", "coerce_time_archetype_flags"]
