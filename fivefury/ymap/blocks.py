from __future__ import annotations

import dataclasses
import math
from typing import Any

from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta.defs import meta_name
from .enums import YmapCarGenFlags, coerce_ymap_cargen_flags


@dataclasses.dataclass(slots=True)
class BlockDesc:
    version: int = 0
    flags: int = 0
    name: str = ""
    exported_by: str = ""
    owner: str = ""
    time: str = ""

    def to_meta(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "flags": self.flags,
            "name": self.name,
            "exportedBy": self.exported_by,
            "owner": self.owner,
            "time": self.time,
            "_meta_name_hash": meta_name("CBlockDesc"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "BlockDesc":
        if not isinstance(value, dict):
            return cls()
        return cls(
            version=int(value.get("version", 0)),
            flags=int(value.get("flags", 0)),
            name=str(value.get("name", "")),
            exported_by=str(value.get("exportedBy", "")),
            owner=str(value.get("owner", "")),
            time=str(value.get("time", "")),
        )


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
        return (
            (self.min_extents[0] + self.max_extents[0]) * 0.5,
            (self.min_extents[1] + self.max_extents[1]) * 0.5,
            (self.min_extents[2] + self.max_extents[2]) * 0.5,
        )

    @property
    def size(self) -> tuple[float, float, float]:
        """Return the full size (width, depth, height) of the modifier volume."""
        return (
            self.max_extents[0] - self.min_extents[0],
            self.max_extents[1] - self.min_extents[1],
            self.max_extents[2] - self.min_extents[2],
        )

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
        """Create a TimeCycleModifier from center position and size.

        Args:
            name: Timecycle modifier name or hash.
            position: Center of the volume (x, y, z).
            size: Full dimensions (width, depth, height).
            percentage: Effect strength (0-100, default 100).
            range: Fade distance at volume edges (default 50).
            hours: Active time range as (start, end) in 24h format (default all day).
        """
        half = (size[0] * 0.5, size[1] * 0.5, size[2] * 0.5)
        return cls(
            name=name,
            min_extents=(position[0] - half[0], position[1] - half[1], position[2] - half[2]),
            max_extents=(position[0] + half[0], position[1] + half[1], position[2] + half[2]),
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
        """Create a CarGen from human-readable parameters.

        Args:
            car_model: Vehicle model name or hash (e.g. "sultan", "adder").
            position: World-space (x, y, z) coordinates.
            heading: Direction the car faces in degrees (0 = north, 90 = east).
            perpendicular_length: Width of the parking space (default 2.6).
            flags: CCarGen flags.
            body_colors: Up to 4 body color remap indices (-1 = random).
            pop_group: Population group name or hash.
            livery: Livery index (-1 = default/random).
        """
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


@dataclasses.dataclass(slots=True)
class ContainerLodDef(MetaHashFieldsMixin):
    """rage__fwContainerLodDef: 8 bytes (name hash + parentIndex)."""

    _hash_fields = ("name",)

    name: MetaHash | HashLike = 0
    parent_index: int = 0

    def to_meta(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parentIndex": self.parent_index,
            "_meta_name_hash": meta_name("rage__fwContainerLodDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "ContainerLodDef":
        if not isinstance(value, dict):
            return cls()
        return cls(
            name=value.get("name", 0),
            parent_index=int(value.get("parentIndex", 0)),
        )
