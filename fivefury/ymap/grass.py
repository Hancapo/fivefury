from __future__ import annotations

import dataclasses
import math
from typing import Any

from ..colors import CssColor, parse_css_rgb
from ..meta import MetaStructInfo
from ..meta.defs import MetaDataType, meta_name
from ..meta.utils import meta_array_info as _arrayinfo, meta_field_entry as _entry
from .packing import clamp_byte, clamp_ushort


BATCH_VERT_MULTIPLIER = 0.00001525878


@dataclasses.dataclass(slots=True)
class Aabb:
    minimum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    maximum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    minimum_w: float = 0.0
    maximum_w: float = 0.0

    def to_meta(self) -> dict[str, Any]:
        return {
            "min": (*self.minimum, self.minimum_w),
            "max": (*self.maximum, self.maximum_w),
            "_meta_name_hash": meta_name("rage__spdAABB"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "Aabb":
        if not isinstance(value, dict):
            return cls()
        minimum = tuple(value.get("min", (0.0, 0.0, 0.0, 0.0)))
        maximum = tuple(value.get("max", (0.0, 0.0, 0.0, 0.0)))
        return cls(
            minimum=(float(minimum[0]), float(minimum[1]), float(minimum[2])),
            maximum=(float(maximum[0]), float(maximum[1]), float(maximum[2])),
            minimum_w=float(minimum[3]) if len(minimum) > 3 else 0.0,
            maximum_w=float(maximum[3]) if len(maximum) > 3 else 0.0,
        )

    @property
    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        return self.minimum, self.maximum

    def size(self) -> tuple[float, float, float]:
        return (
            self.maximum[0] - self.minimum[0],
            self.maximum[1] - self.minimum[1],
            self.maximum[2] - self.minimum[2],
        )


@dataclasses.dataclass(slots=True)
class GrassInstance:
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    color: tuple[int, int, int] | CssColor = (255, 255, 255)
    scale: int = 255
    ao: int = 255
    pad: tuple[int, int, int] = (0, 0, 0)

    def __post_init__(self) -> None:
        self.color = parse_css_rgb(self.color)

    @classmethod
    def from_meta(cls, value: Any, batch_aabb: Aabb) -> "GrassInstance":
        if not isinstance(value, dict):
            return cls()
        packed_position = tuple(value.get("Position", (0, 0, 0)))
        size = batch_aabb.size()
        world_position = tuple(
            batch_aabb.minimum[index] + size[index] * (float(packed_position[index]) * BATCH_VERT_MULTIPLIER)
            for index in range(3)
        )
        normal_x = (int(value.get("NormalX", 127)) / 255.0) * 2.0 - 1.0
        normal_y = (int(value.get("NormalY", 127)) / 255.0) * 2.0 - 1.0
        normal_z = math.sqrt(max(0.0, 1.0 - min(1.0, normal_x * normal_x + normal_y * normal_y)))
        return cls(
            position=world_position,
            normal=(normal_x, normal_y, normal_z),
            color=parse_css_rgb(value.get("Color", (255, 255, 255))),
            scale=int(value.get("Scale", 255)),
            ao=int(value.get("Ao", 255)),
            pad=tuple(value.get("Pad", (0, 0, 0))),
        )

    def to_meta(self, batch_aabb: Aabb) -> dict[str, Any]:
        size = batch_aabb.size()
        packed_position = []
        for index in range(3):
            axis_size = size[index] if abs(size[index]) > 1e-6 else 1.0
            rel = (self.position[index] - batch_aabb.minimum[index]) / axis_size
            packed_position.append(clamp_ushort(rel / BATCH_VERT_MULTIPLIER))
        return {
            "Position": tuple(packed_position),
            "NormalX": clamp_byte((self.normal[0] + 1.0) * 0.5 * 255.0),
            "NormalY": clamp_byte((self.normal[1] + 1.0) * 0.5 * 255.0),
            "Color": tuple(clamp_byte(component) for component in self.color),
            "Scale": clamp_byte(self.scale),
            "Ao": clamp_byte(self.ao),
            "Pad": tuple(clamp_byte(component) for component in self.pad),
            "_meta_name_hash": meta_name("rage__fwGrassInstanceListDef__InstanceData"),
        }


@dataclasses.dataclass(slots=True)
class GrassInstanceBatch:
    batch_aabb: Aabb = dataclasses.field(default_factory=Aabb)
    scale_range: tuple[float, float, float] = (1.0, 1.0, 1.0)
    archetype_name: int | str = 0
    lod_dist: int = 0
    lod_fade_start_dist: float = 0.0
    lod_inst_fade_range: float = 0.0
    orient_to_terrain: float = 0.0
    instances: list[GrassInstance] = dataclasses.field(default_factory=list)

    def to_meta(self) -> dict[str, Any]:
        return {
            "BatchAABB": self.batch_aabb.to_meta(),
            "ScaleRange": self.scale_range,
            "archetypeName": self.archetype_name,
            "lodDist": int(self.lod_dist),
            "LodFadeStartDist": self.lod_fade_start_dist,
            "LodInstFadeRange": self.lod_inst_fade_range,
            "OrientToTerrain": self.orient_to_terrain,
            "InstanceList": [instance.to_meta(self.batch_aabb) for instance in self.instances],
            "_meta_name_hash": meta_name("rage__fwGrassInstanceListDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "GrassInstanceBatch":
        if not isinstance(value, dict):
            return cls()
        batch_aabb = Aabb.from_meta(value.get("BatchAABB"))
        return cls(
            batch_aabb=batch_aabb,
            scale_range=tuple(value.get("ScaleRange", (1.0, 1.0, 1.0))),
            archetype_name=value.get("archetypeName", 0),
            lod_dist=int(value.get("lodDist", 0)),
            lod_fade_start_dist=float(value.get("LodFadeStartDist", 0.0)),
            lod_inst_fade_range=float(value.get("LodInstFadeRange", 0.0)),
            orient_to_terrain=float(value.get("OrientToTerrain", 0.0)),
            instances=[GrassInstance.from_meta(item, batch_aabb) for item in value.get("InstanceList", []) or []],
        )

    @property
    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        return self.batch_aabb.bounds

    def add_instance(self, instance: GrassInstance) -> GrassInstance:
        self.instances.append(instance)
        return instance


@dataclasses.dataclass(slots=True)
class InstancedMapData:
    imap_link: int | str = 0
    prop_instance_list: list[Any] = dataclasses.field(default_factory=list)
    grass_instance_list: list[GrassInstanceBatch] = dataclasses.field(default_factory=list)

    def to_meta(self) -> dict[str, Any]:
        return {
            "ImapLink": self.imap_link,
            "PropInstanceList": self.prop_instance_list,
            "GrassInstanceList": [batch.to_meta() if hasattr(batch, "to_meta") else batch for batch in self.grass_instance_list],
            "_meta_name_hash": meta_name("rage__fwInstancedMapData"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "InstancedMapData":
        if not isinstance(value, dict):
            return cls()
        return cls(
            imap_link=value.get("ImapLink", 0),
            prop_instance_list=list(value.get("PropInstanceList", []) or []),
            grass_instance_list=[
                GrassInstanceBatch.from_meta(item) if isinstance(item, dict) else item
                for item in value.get("GrassInstanceList", []) or []
            ],
        )

    def add_grass_batch(self, batch: GrassInstanceBatch) -> GrassInstanceBatch:
        self.grass_instance_list.append(batch)
        return batch


YMAP_GRASS_STRUCT_INFOS = [
    MetaStructInfo(
        name_hash=meta_name("rage__spdAABB"),
        key=1158138379,
        unknown=1024,
        structure_size=32,
        entries=[
            _entry("min", 0, MetaDataType.FLOAT_XYZW),
            _entry("max", 16, MetaDataType.FLOAT_XYZW),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("rage__fwInstancedMapData"),
        key=1836780118,
        unknown=1024,
        structure_size=48,
        entries=[
            _entry("ImapLink", 8, MetaDataType.HASH),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="rage__fwPropInstanceListDef"),
            _entry("PropInstanceList", 16, MetaDataType.ARRAY, ref_index=1),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="rage__fwGrassInstanceListDef"),
            _entry("GrassInstanceList", 32, MetaDataType.ARRAY, ref_index=3),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("rage__fwGrassInstanceListDef"),
        key=941808164,
        unknown=1024,
        structure_size=96,
        entries=[
            _entry("BatchAABB", 0, MetaDataType.STRUCTURE, ref_key="rage__spdAABB"),
            _entry("ScaleRange", 32, MetaDataType.FLOAT_XYZ),
            _entry("archetypeName", 48, MetaDataType.HASH),
            _entry("lodDist", 52, MetaDataType.UNSIGNED_INT),
            _entry("LodFadeStartDist", 56, MetaDataType.FLOAT),
            _entry("LodInstFadeRange", 60, MetaDataType.FLOAT),
            _entry("OrientToTerrain", 64, MetaDataType.FLOAT),
            _arrayinfo(MetaDataType.STRUCTURE, ref_key="rage__fwGrassInstanceListDef__InstanceData"),
            _entry("InstanceList", 72, MetaDataType.ARRAY, ref_index=7),
        ],
    ),
    MetaStructInfo(
        name_hash=meta_name("rage__fwGrassInstanceListDef__InstanceData"),
        key=2740378365,
        unknown=1024,
        structure_size=16,
        entries=[
            _arrayinfo(MetaDataType.UNSIGNED_SHORT),
            _entry("Position", 0, MetaDataType.ARRAY_OF_BYTES, ref_index=0, ref_key=3),
            _entry("NormalX", 6, MetaDataType.UNSIGNED_BYTE),
            _entry("NormalY", 7, MetaDataType.UNSIGNED_BYTE),
            _arrayinfo(MetaDataType.UNSIGNED_BYTE),
            _entry("Color", 8, MetaDataType.ARRAY_OF_BYTES, ref_index=4, ref_key=3),
            _entry("Scale", 11, MetaDataType.UNSIGNED_BYTE),
            _entry("Ao", 12, MetaDataType.UNSIGNED_BYTE),
            _arrayinfo(MetaDataType.UNSIGNED_BYTE),
            _entry("Pad", 13, MetaDataType.ARRAY_OF_BYTES, ref_index=8, ref_key=3),
        ],
    ),
]


GrassBatch = GrassInstanceBatch
InstancedData = InstancedMapData


__all__ = [
    "Aabb",
    "BATCH_VERT_MULTIPLIER",
    "GrassBatch",
    "GrassInstance",
    "GrassInstanceBatch",
    "InstancedData",
    "InstancedMapData",
    "YMAP_GRASS_STRUCT_INFOS",
]
