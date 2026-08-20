from __future__ import annotations

import dataclasses
import math
from typing import Any

from ..colors import CssColor, parse_css_rgb
from ..meta import MetaStructInfo
from ..meta.defs import MetaDataType, meta_name
from ..meta.utils import meta_array_info as _arrayinfo
from ..meta.utils import meta_field_entry as _entry
from ..vector import Aabb3, Vector3
from .packing import clamp_byte, clamp_ushort

BATCH_VERT_MULTIPLIER = 0.00001525878


@dataclasses.dataclass(slots=True)
class Aabb:
    minimum: Vector3 = dataclasses.field(default_factory=Vector3)
    maximum: Vector3 = dataclasses.field(default_factory=Vector3)
    minimum_w: float = 0.0
    maximum_w: float = 0.0

    def to_meta(self) -> dict[str, Any]:
        return {
            "min": (*self.minimum, self.minimum_w),
            "max": (*self.maximum, self.maximum_w),
            "_meta_name_hash": meta_name("rage__spdAABB"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> Aabb:
        if not isinstance(value, dict):
            return cls()
        minimum = tuple(value.get("min", (0.0, 0.0, 0.0, 0.0)))
        maximum = tuple(value.get("max", (0.0, 0.0, 0.0, 0.0)))
        minimum = minimum + (0.0,) * max(0, 4 - len(minimum))
        maximum = maximum + (0.0,) * max(0, 4 - len(maximum))
        minimum_x, minimum_y, minimum_z, minimum_w = minimum[:4]
        maximum_x, maximum_y, maximum_z, maximum_w = maximum[:4]
        return cls(
            minimum=Vector3(minimum_x, minimum_y, minimum_z),
            maximum=Vector3(maximum_x, maximum_y, maximum_z),
            minimum_w=float(minimum_w),
            maximum_w=float(maximum_w),
        )

    @property
    def bounds(self) -> Aabb3:
        return Aabb3(self.minimum, self.maximum)

    def size(self) -> Vector3:
        return self.maximum - self.minimum


@dataclasses.dataclass(slots=True)
class GrassInstance:
    position: Vector3 = dataclasses.field(default_factory=Vector3)
    normal: Vector3 = Vector3(0.0, 0.0, 1.0)
    color: tuple[int, int, int] | CssColor = (255, 255, 255)
    scale: int = 255
    ao: int = 255
    pad: tuple[int, int, int] = (0, 0, 0)

    def __post_init__(self) -> None:
        if not isinstance(self.position, Vector3) or not isinstance(self.normal, Vector3):
            raise TypeError("Grass instance position and normal must be Vector3 instances")
        self.color = parse_css_rgb(self.color)

    @classmethod
    def from_meta(cls, value: Any, batch_aabb: Aabb) -> GrassInstance:
        if not isinstance(value, dict):
            return cls()
        packed_position = tuple(value.get("Position", (0, 0, 0)))
        size = batch_aabb.size()
        world_position = Vector3(
            batch_aabb.minimum.x + size.x * (float(packed_position[0]) * BATCH_VERT_MULTIPLIER),
            batch_aabb.minimum.y + size.y * (float(packed_position[1]) * BATCH_VERT_MULTIPLIER),
            batch_aabb.minimum.z + size.z * (float(packed_position[2]) * BATCH_VERT_MULTIPLIER),
        )
        normal_x = (int(value.get("NormalX", 127)) / 255.0) * 2.0 - 1.0
        normal_y = (int(value.get("NormalY", 127)) / 255.0) * 2.0 - 1.0
        normal_z = math.sqrt(max(0.0, 1.0 - min(1.0, normal_x * normal_x + normal_y * normal_y)))
        return cls(
            position=world_position,
            normal=Vector3(normal_x, normal_y, normal_z),
            color=parse_css_rgb(value.get("Color", (255, 255, 255))),
            scale=int(value.get("Scale", 255)),
            ao=int(value.get("Ao", 255)),
            pad=tuple(value.get("Pad", (0, 0, 0))),
        )

    def to_meta(self, batch_aabb: Aabb) -> dict[str, Any]:
        size = batch_aabb.size()
        packed_position = []
        for position, minimum, extent in zip(self.position, batch_aabb.minimum, size, strict=True):
            axis_size = extent if abs(extent) > 1e-6 else 1.0
            rel = (position - minimum) / axis_size
            packed_position.append(clamp_ushort(rel / BATCH_VERT_MULTIPLIER))
        return {
            "Position": tuple(packed_position),
            "NormalX": clamp_byte((self.normal.x + 1.0) * 0.5 * 255.0),
            "NormalY": clamp_byte((self.normal.y + 1.0) * 0.5 * 255.0),
            "Color": tuple(clamp_byte(component) for component in self.color),
            "Scale": clamp_byte(self.scale),
            "Ao": clamp_byte(self.ao),
            "Pad": tuple(clamp_byte(component) for component in self.pad),
            "_meta_name_hash": meta_name("rage__fwGrassInstanceListDef__InstanceData"),
        }


@dataclasses.dataclass(slots=True)
class GrassInstanceBatch:
    batch_aabb: Aabb = dataclasses.field(default_factory=Aabb)
    scale_range: Vector3 = Vector3(1.0, 1.0, 1.0)
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
    def from_meta(cls, value: Any) -> GrassInstanceBatch:
        if not isinstance(value, dict):
            return cls()
        batch_aabb = Aabb.from_meta(value.get("BatchAABB"))
        return cls(
            batch_aabb=batch_aabb,
            scale_range=Vector3.from_iterable(value.get("ScaleRange", (1.0, 1.0, 1.0))),
            archetype_name=value.get("archetypeName", 0),
            lod_dist=int(value.get("lodDist", 0)),
            lod_fade_start_dist=float(value.get("LodFadeStartDist", 0.0)),
            lod_inst_fade_range=float(value.get("LodInstFadeRange", 0.0)),
            orient_to_terrain=float(value.get("OrientToTerrain", 0.0)),
            instances=[GrassInstance.from_meta(item, batch_aabb) for item in value.get("InstanceList", []) or []],
        )

    @property
    def bounds(self) -> Aabb3:
        return self.batch_aabb.bounds



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
    def from_meta(cls, value: Any) -> InstancedMapData:
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
    "BATCH_VERT_MULTIPLIER",
    "YMAP_GRASS_STRUCT_INFOS",
    "Aabb",
    "GrassBatch",
    "GrassInstance",
    "GrassInstanceBatch",
    "InstancedData",
    "InstancedMapData",
]
