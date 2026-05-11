from __future__ import annotations

import dataclasses
from typing import Any

from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta.defs import meta_name
from ..vector import aabb_center, aabb_from_center_size, aabb_size


@dataclasses.dataclass(slots=True)
class TimeCycleModifier(MetaHashFieldsMixin):
    _hash_fields = ("name",)

    name: MetaHash | HashLike = 0
    min_extents: tuple[float, float, float] = (0.0, 0.0, 0.0)
    max_extents: tuple[float, float, float] = (0.0, 0.0, 0.0)
    percentage: float = 0.0
    range: float = 0.0
    start_hour: int = 0
    end_hour: int = 0

    def to_meta(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "minExtents": self.min_extents,
            "maxExtents": self.max_extents,
            "percentage": self.percentage,
            "range": self.range,
            "startHour": self.start_hour,
            "endHour": self.end_hour,
            "_meta_name_hash": meta_name("CTimeCycleModifier"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "TimeCycleModifier":
        return cls(
            name=value.get("name", 0),
            min_extents=tuple(value.get("minExtents", (0.0, 0.0, 0.0))),
            max_extents=tuple(value.get("maxExtents", (0.0, 0.0, 0.0))),
            percentage=float(value.get("percentage", 0.0)),
            range=float(value.get("range", 0.0)),
            start_hour=int(value.get("startHour", 0)),
            end_hour=int(value.get("endHour", 0)),
        )

    @property
    def center(self) -> tuple[float, float, float]:
        """Return the center point of the modifier volume."""
        return aabb_center(self.min_extents, self.max_extents)

    @property
    def size(self) -> tuple[float, float, float]:
        """Return the full size (width, depth, height) of the modifier volume."""
        return aabb_size(self.min_extents, self.max_extents)

    @property
    def hours(self) -> tuple[int, int]:
        """Return (start_hour, end_hour) as a tuple."""
        return (self.start_hour, self.end_hour)

    @hours.setter
    def hours(self, value: tuple[int, int]) -> None:
        self.start_hour = int(value[0])
        self.end_hour = int(value[1])

    @classmethod
    def create(
        cls,
        name: HashLike,
        position: tuple[float, float, float],
        size: tuple[float, float, float],
        *,
        percentage: float = 100.0,
        range: float = 50.0,
        hours: tuple[int, int] = (0, 24),
    ) -> "TimeCycleModifier":
        """Create a TimeCycleModifier from center position and size."""
        min_extents, max_extents = aabb_from_center_size(position, size)
        return cls(
            name=name,
            min_extents=min_extents,
            max_extents=max_extents,
            percentage=float(percentage),
            range=float(range),
            start_hour=int(hours[0]),
            end_hour=int(hours[1]),
        )

    @classmethod
    def from_bounds(
        cls,
        name: HashLike,
        min_pos: tuple[float, float, float],
        max_pos: tuple[float, float, float],
        *,
        percentage: float = 100.0,
        range: float = 50.0,
        hours: tuple[int, int] = (0, 24),
    ) -> "TimeCycleModifier":
        """Create a TimeCycleModifier from min/max AABB corners."""
        return cls(
            name=name,
            min_extents=min_pos,
            max_extents=max_pos,
            percentage=float(percentage),
            range=float(range),
            start_hour=int(hours[0]),
            end_hour=int(hours[1]),
        )


__all__ = ["TimeCycleModifier"]
