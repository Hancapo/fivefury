from __future__ import annotations

import dataclasses
from typing import Any

from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta.defs import meta_name


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


@dataclasses.dataclass(slots=True)
class CarGen(MetaHashFieldsMixin):
    _hash_fields = ("car_model", "pop_group")

    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orient_x: float = 0.0
    orient_y: float = 0.0
    perpendicular_length: float = 0.0
    car_model: MetaHash | HashLike = 0
    flags: int = 0
    body_color_remap1: int = -1
    body_color_remap2: int = -1
    body_color_remap3: int = -1
    body_color_remap4: int = -1
    pop_group: MetaHash | HashLike = 0
    livery: int = -1

    def to_meta(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "orientX": self.orient_x,
            "orientY": self.orient_y,
            "perpendicularLength": self.perpendicular_length,
            "carModel": self.car_model,
            "flags": self.flags,
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
            flags=int(value.get("flags", 0)),
            body_color_remap1=int(value.get("bodyColorRemap1", -1)),
            body_color_remap2=int(value.get("bodyColorRemap2", -1)),
            body_color_remap3=int(value.get("bodyColorRemap3", -1)),
            body_color_remap4=int(value.get("bodyColorRemap4", -1)),
            pop_group=value.get("popGroup", 0),
            livery=int(value.get("livery", -1)),
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
