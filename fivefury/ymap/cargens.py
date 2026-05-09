from __future__ import annotations

import dataclasses
import math
from typing import Any

from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta.defs import meta_name
from .enums import YmapCarGenFlags, coerce_ymap_cargen_flags


@dataclasses.dataclass(slots=True)
class CarGen(MetaHashFieldsMixin):
    _hash_fields = ("car_model", "pop_group")

    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orient_x: float = 0.0
    orient_y: float = 0.0
    perpendicular_length: float = 0.0
    car_model: MetaHash | HashLike = 0
    flags: YmapCarGenFlags | int = YmapCarGenFlags.NONE
    body_color_remap1: int = -1
    body_color_remap2: int = -1
    body_color_remap3: int = -1
    body_color_remap4: int = -1
    pop_group: MetaHash | HashLike = 0
    livery: int = -1

    def __post_init__(self) -> None:
        self.flags = coerce_ymap_cargen_flags(self.flags)

    def to_meta(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "orientX": self.orient_x,
            "orientY": self.orient_y,
            "perpendicularLength": self.perpendicular_length,
            "carModel": self.car_model,
            "flags": int(self.flags),
            "bodyColorRemap1": self.body_color_remap1,
            "bodyColorRemap2": self.body_color_remap2,
            "bodyColorRemap3": self.body_color_remap3,
            "bodyColorRemap4": self.body_color_remap4,
            "popGroup": self.pop_group,
            "livery": self.livery,
            "_meta_name_hash": meta_name("CCarGen"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "CarGen":
        return cls(
            position=tuple(value.get("position", (0.0, 0.0, 0.0))),
            orient_x=float(value.get("orientX", 0.0)),
            orient_y=float(value.get("orientY", 0.0)),
            perpendicular_length=float(value.get("perpendicularLength", 0.0)),
            car_model=value.get("carModel", 0),
            flags=coerce_ymap_cargen_flags(int(value.get("flags", 0))),
            body_color_remap1=int(value.get("bodyColorRemap1", -1)),
            body_color_remap2=int(value.get("bodyColorRemap2", -1)),
            body_color_remap3=int(value.get("bodyColorRemap3", -1)),
            body_color_remap4=int(value.get("bodyColorRemap4", -1)),
            pop_group=value.get("popGroup", 0),
            livery=int(value.get("livery", -1)),
        )

    @property
    def heading(self) -> float:
        """Return the heading angle in degrees (0-360)."""
        return math.degrees(math.atan2(self.orient_x, self.orient_y)) % 360.0

    @heading.setter
    def heading(self, degrees: float) -> None:
        """Set the heading from an angle in degrees."""
        radians = math.radians(degrees)
        self.orient_x = math.sin(radians)
        self.orient_y = math.cos(radians)

    @property
    def body_colors(self) -> tuple[int, int, int, int]:
        """Return all four body color remap values (-1 = random)."""
        return (self.body_color_remap1, self.body_color_remap2, self.body_color_remap3, self.body_color_remap4)

    @body_colors.setter
    def body_colors(self, colors: tuple[int, ...]) -> None:
        """Set body color remaps. Pad with -1 if fewer than 4 values given."""
        padded = (tuple(colors) + (-1, -1, -1, -1))[:4]
        self.body_color_remap1 = int(padded[0])
        self.body_color_remap2 = int(padded[1])
        self.body_color_remap3 = int(padded[2])
        self.body_color_remap4 = int(padded[3])

    @classmethod
    def create(
        cls,
        car_model: HashLike,
        position: tuple[float, float, float],
        heading: float = 0.0,
        *,
        perpendicular_length: float = 2.6,
        flags: YmapCarGenFlags | int = YmapCarGenFlags.NONE,
        body_colors: tuple[int, ...] = (-1, -1, -1, -1),
        pop_group: HashLike = 0,
        livery: int = -1,
    ) -> "CarGen":
        """Create a CarGen from human-readable parameters."""
        radians = math.radians(heading)
        padded = (tuple(body_colors) + (-1, -1, -1, -1))[:4]
        return cls(
            position=position,
            orient_x=math.sin(radians),
            orient_y=math.cos(radians),
            perpendicular_length=float(perpendicular_length),
            car_model=car_model,
            flags=flags,
            body_color_remap1=int(padded[0]),
            body_color_remap2=int(padded[1]),
            body_color_remap3=int(padded[2]),
            body_color_remap4=int(padded[3]),
            pop_group=pop_group,
            livery=livery,
        )


CarGenerator = CarGen

__all__ = ["CarGen", "CarGenerator"]
