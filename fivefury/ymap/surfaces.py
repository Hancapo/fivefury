from __future__ import annotations

import dataclasses
import math
import struct
from enum import Enum
from typing import Any

from ..hashing import jenk_hash
from ..meta import MetaFieldInfo, MetaStructInfo
from ..meta.defs import META_TYPE_NAME_ARRAYINFO, MetaDataType, meta_name


BATCH_VERT_MULTIPLIER = 0.00001525878


def _entry(
    name: str | int,
    offset: int,
    data_type: MetaDataType,
    unknown_9h: int = 0,
    ref_index: int = 0,
    ref_key: str | int = 0,
) -> MetaFieldInfo:
    name_hash = name if isinstance(name, int) else meta_name(name)
    ref_hash = meta_name(ref_key) if isinstance(ref_key, str) else ref_key
    return MetaFieldInfo(name_hash, offset, data_type, unknown_9h, ref_index, ref_hash)


def _arrayinfo(data_type: MetaDataType, *, ref_key: str | int = 0, unknown_9h: int = 0) -> MetaFieldInfo:
    ref_hash = meta_name(ref_key) if isinstance(ref_key, str) else ref_key
    return MetaFieldInfo(META_TYPE_NAME_ARRAYINFO, 0, data_type, unknown_9h, 0, ref_hash)


def _clamp_byte(value: float | int) -> int:
    return max(0, min(255, int(round(value))))


def _clamp_ushort(value: float | int) -> int:
    return max(0, min(65535, int(round(value))))


def _pack_rgbi(colour: tuple[int, int, int], intensity: int) -> int:
    r, g, b = (_clamp_byte(component) for component in colour)
    return r | (g << 8) | (b << 16) | (_clamp_byte(intensity) << 24)


def _unpack_rgbi(value: int) -> tuple[tuple[int, int, int], int]:
    return ((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF), (value >> 24) & 0xFF)


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


class AngleMode(str, Enum):
    DEGREES = "degrees"
    RADIANS = "radians"


@dataclasses.dataclass(slots=True)
class BoxOccluder:
    iCenterX: int = 0
    iCenterY: int = 0
    iCenterZ: int = 0
    iCosZ: int = 0
    iLength: int = 0
    iWidth: int = 0
    iHeight: int = 0
    iSinZ: int = 0

    @property
    def position(self) -> tuple[float, float, float]:
        return (self.iCenterX / 4.0, self.iCenterY / 4.0, self.iCenterZ / 4.0)

    @property
    def size(self) -> tuple[float, float, float]:
        return (self.iLength / 4.0, self.iWidth / 4.0, self.iHeight / 4.0)

    @property
    def angle_radians(self) -> float:
        return math.atan2(self.iCosZ / 32767.0, self.iSinZ / 32767.0)

    @property
    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        px, py, pz = self.position
        sx, sy, sz = self.size
        return (
            (px - sx * 0.5, py - sy * 0.5, pz - sz * 0.5),
            (px + sx * 0.5, py + sy * 0.5, pz + sz * 0.5),
        )

    def to_meta(self) -> dict[str, Any]:
        return {
            "iCenterX": int(self.iCenterX),
            "iCenterY": int(self.iCenterY),
            "iCenterZ": int(self.iCenterZ),
            "iCosZ": int(self.iCosZ),
            "iLength": int(self.iLength),
            "iWidth": int(self.iWidth),
            "iHeight": int(self.iHeight),
            "iSinZ": int(self.iSinZ),
            "_meta_name_hash": meta_name("BoxOccluder"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "BoxOccluder":
        if not isinstance(value, dict):
            return cls()
        return cls(
            iCenterX=int(value.get("iCenterX", 0)),
            iCenterY=int(value.get("iCenterY", 0)),
            iCenterZ=int(value.get("iCenterZ", 0)),
            iCosZ=int(value.get("iCosZ", 0)),
            iLength=int(value.get("iLength", 0)),
            iWidth=int(value.get("iWidth", 0)),
            iHeight=int(value.get("iHeight", 0)),
            iSinZ=int(value.get("iSinZ", 0)),
        )

    @classmethod
    def from_box(
        cls,
        position: tuple[float, float, float],
        size: tuple[float, float, float],
        angle: float = 0.0,
        angle_mode: AngleMode = AngleMode.DEGREES,
    ) -> "BoxOccluder":
        """Create a BoxOccluder from world-space position, size and rotation angle."""
        radians = math.radians(angle) if angle_mode == AngleMode.DEGREES else float(angle)
        return cls(
            iCenterX=round(position[0] * 4),
            iCenterY=round(position[1] * 4),
            iCenterZ=round(position[2] * 4),
            iLength=round(size[0] * 4),
            iWidth=round(size[1] * 4),
            iHeight=round(size[2] * 4),
            iCosZ=round(math.cos(radians) * 32767),
            iSinZ=round(math.sin(radians) * 32767),
        )


_OCCLUDE_MAX_VERTICES = 256


@dataclasses.dataclass(slots=True)
class OccludeModel:
    bmin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bmax: tuple[float, float, float] = (0.0, 0.0, 0.0)
    data_size: int = 0
    verts: bytes = b""
    num_verts_in_bytes: int = 0
    num_tris: int = 0
    flags: int = 0

    def to_meta(self) -> dict[str, Any]:
        payload = self.verts or b""
        return {
            "bmin": self.bmin,
            "bmax": self.bmax,
            "dataSize": self.data_size or len(payload),
            "verts": payload,
            "numVertsInBytes": self.num_verts_in_bytes,
            "numTris": self.num_tris,
            "flags": self.flags,
            "_meta_name_hash": meta_name("OccludeModel"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "OccludeModel":
        if not isinstance(value, dict):
            return cls()
        return cls(
            bmin=tuple(value.get("bmin", (0.0, 0.0, 0.0))),
            bmax=tuple(value.get("bmax", (0.0, 0.0, 0.0))),
            data_size=int(value.get("dataSize", 0)),
            verts=bytes(value.get("verts", b"") or b""),
            num_verts_in_bytes=int(value.get("numVertsInBytes", 0)),
            num_tris=int(value.get("numTris", 0)),
            flags=int(value.get("flags", 0)),
        )

    @property
    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        return self.bmin, self.bmax

    def vertices(self) -> list[tuple[float, float, float]]:
        count = self.num_verts_in_bytes // 12 if self.num_verts_in_bytes else 0
        return [value for value in struct.iter_unpack("<fff", self.verts[: count * 12])]

    def indices(self) -> bytes:
        return self.verts[self.num_verts_in_bytes :]

    def set_geometry(self, vertices: list[tuple[float, float, float]], indices: bytes, *, flags: int | None = None) -> "OccludeModel":
        vert_bytes = b"".join(struct.pack("<fff", *vertex) for vertex in vertices)
        self.verts = vert_bytes + bytes(indices)
        self.num_verts_in_bytes = len(vert_bytes)
        self.data_size = len(self.verts)
        self.num_tris = (len(indices) // 3) + 32768 if indices else 0
        if vertices:
            xs = [vertex[0] for vertex in vertices]
            ys = [vertex[1] for vertex in vertices]
            zs = [vertex[2] for vertex in vertices]
            self.bmin = (min(xs), min(ys), min(zs))
            self.bmax = (max(xs), max(ys), max(zs))
        if flags is not None:
            self.flags = int(flags)
        return self

    @classmethod
    def from_geometry(cls, vertices: list[tuple[float, float, float]], indices: bytes = b"", *, flags: int = 0) -> "OccludeModel":
        model = cls(flags=flags)
        return model.set_geometry(vertices, indices, flags=flags)

    @classmethod
    def from_faces(
        cls,
        vertices: list[tuple[float, float, float]],
        faces: list[tuple[int, ...]],
        *,
        flags: int = 0,
    ) -> list["OccludeModel"]:
        """Create OccludeModel(s) from vertices and face index tuples.

        Faces with more than 3 vertices are triangulated as a fan.
        If the geometry exceeds 256 vertices, it is automatically split
        into multiple OccludeModel instances.
        """
        triangles: list[tuple[int, int, int]] = []
        for face in faces:
            if len(face) < 3:
                continue
            for i in range(1, len(face) - 1):
                triangles.append((face[0], face[i], face[i + 1]))

        if not triangles:
            return [cls(flags=flags)]

        # Group triangles into chunks that fit within 256 unique vertices
        chunks: list[list[tuple[int, int, int]]] = []
        current_chunk: list[tuple[int, int, int]] = []
        current_verts: set[int] = set()

        for tri in triangles:
            new_verts = {v for v in tri if v not in current_verts}
            if len(current_verts) + len(new_verts) > _OCCLUDE_MAX_VERTICES:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = [tri]
                current_verts = set(tri)
            else:
                current_chunk.append(tri)
                current_verts.update(tri)

        if current_chunk:
            chunks.append(current_chunk)

        models: list[OccludeModel] = []
        for chunk in chunks:
            used_indices = sorted({v for tri in chunk for v in tri})
            remap = {old: new for new, old in enumerate(used_indices)}
            chunk_verts = [vertices[i] for i in used_indices]
            index_bytes = bytes(remap[v] for tri in chunk for v in tri)
            models.append(cls.from_geometry(chunk_verts, index_bytes, flags=flags))

        return models

    @classmethod
    def from_box(
        cls,
        min_pos: tuple[float, float, float],
        max_pos: tuple[float, float, float],
        *,
        flags: int = 0,
    ) -> list["OccludeModel"]:
        """Create an OccludeModel box from min/max AABB corners."""
        x0, y0, z0 = min_pos
        x1, y1, z1 = max_pos
        vertices = [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ]
        faces = [
            (0, 1, 2, 3),  # bottom
            (4, 7, 6, 5),  # top
            (0, 4, 5, 1),  # front
            (2, 6, 7, 3),  # back
            (0, 3, 7, 4),  # left
            (1, 5, 6, 2),  # right
        ]
        return cls.from_faces(vertices, faces, flags=flags)

    @classmethod
    def from_quad(
        cls,
        corners: list[tuple[float, float, float]],
        *,
        flags: int = 0,
    ) -> list["OccludeModel"]:
        """Create an OccludeModel plane from 4 corner vertices."""
        if len(corners) != 4:
            raise ValueError(f"from_quad requires exactly 4 corners, got {len(corners)}")
        return cls.from_faces(list(corners), [(0, 1, 2, 3)], flags=flags)


@dataclasses.dataclass(slots=True)
class GrassInstance:
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    color: tuple[int, int, int] = (255, 255, 255)
    scale: int = 255
    ao: int = 255
    pad: tuple[int, int, int] = (0, 0, 0)

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
            color=tuple(value.get("Color", (255, 255, 255))),
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
            packed_position.append(_clamp_ushort(rel / BATCH_VERT_MULTIPLIER))
        return {
            "Position": tuple(packed_position),
            "NormalX": _clamp_byte((self.normal[0] + 1.0) * 0.5 * 255.0),
            "NormalY": _clamp_byte((self.normal[1] + 1.0) * 0.5 * 255.0),
            "Color": tuple(_clamp_byte(component) for component in self.color),
            "Scale": _clamp_byte(self.scale),
            "Ao": _clamp_byte(self.ao),
            "Pad": tuple(_clamp_byte(component) for component in self.pad),
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
            grass_instance_list=[GrassInstanceBatch.from_meta(item) if isinstance(item, dict) else item for item in value.get("GrassInstanceList", []) or []],
        )

    def add_grass_batch(self, batch: GrassInstanceBatch) -> GrassInstanceBatch:
        self.grass_instance_list.append(batch)
        return batch


@dataclasses.dataclass(slots=True)
class LodLight:
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    direction: tuple[float, float, float] = (0.0, 0.0, -1.0)
    falloff: float = 1.0
    falloff_exponent: float = 1.0
    time_and_state_flags: int = 0
    hash: int | str = 0
    cone_inner_angle: int = 0
    cone_outer_angle_or_cap_ext: int = 0
    corona_intensity: int = 0
    rgbi: int = 0

    @property
    def light_type(self) -> int:
        return (self.time_and_state_flags >> 26) & 7

    @property
    def time_flags(self) -> int:
        return self.time_and_state_flags & 0xFFFFFF

    @property
    def state_flags_1(self) -> int:
        return (self.time_and_state_flags >> 24) & 3

    @property
    def state_flags_2(self) -> int:
        return (self.time_and_state_flags >> 29) & 7

    @property
    def colour(self) -> tuple[int, int, int]:
        return _unpack_rgbi(self.rgbi)[0]

    @property
    def intensity(self) -> int:
        return _unpack_rgbi(self.rgbi)[1]


@dataclasses.dataclass(slots=True)
class LodLightsSoa:
    direction: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    falloff: list[float] = dataclasses.field(default_factory=list)
    falloff_exponent: list[float] = dataclasses.field(default_factory=list)
    time_and_state_flags: list[int] = dataclasses.field(default_factory=list)
    hash: list[int | str] = dataclasses.field(default_factory=list)
    cone_inner_angle: list[int] = dataclasses.field(default_factory=list)
    cone_outer_angle_or_cap_ext: list[int] = dataclasses.field(default_factory=list)
    corona_intensity: list[int] = dataclasses.field(default_factory=list)

    def __len__(self) -> int:
        return len(self.direction)

    def to_meta(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "falloff": self.falloff,
            "falloffExponent": self.falloff_exponent,
            "timeAndStateFlags": [int(value) for value in self.time_and_state_flags],
            "hash": [jenk_hash(value) if isinstance(value, str) else int(value) for value in self.hash],
            "coneInnerAngle": [int(value) for value in self.cone_inner_angle],
            "coneOuterAngleOrCapExt": [int(value) for value in self.cone_outer_angle_or_cap_ext],
            "coronaIntensity": [int(value) for value in self.corona_intensity],
            "_meta_name_hash": meta_name("CLODLight"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "LodLightsSoa":
        if not isinstance(value, dict):
            return cls()
        return cls(
            direction=[tuple(item) for item in value.get("direction", []) or []],
            falloff=[float(item) for item in value.get("falloff", []) or []],
            falloff_exponent=[float(item) for item in value.get("falloffExponent", []) or []],
            time_and_state_flags=[int(item) for item in value.get("timeAndStateFlags", []) or []],
            hash=list(value.get("hash", []) or []),
            cone_inner_angle=[int(item) for item in value.get("coneInnerAngle", []) or []],
            cone_outer_angle_or_cap_ext=[int(item) for item in value.get("coneOuterAngleOrCapExt", []) or []],
            corona_intensity=[int(item) for item in value.get("coronaIntensity", []) or []],
        )

    def append(self, light: LodLight) -> LodLight:
        self.direction.append(tuple(light.direction))
        self.falloff.append(float(light.falloff))
        self.falloff_exponent.append(float(light.falloff_exponent))
        self.time_and_state_flags.append(int(light.time_and_state_flags))
        self.hash.append(light.hash)
        self.cone_inner_angle.append(_clamp_byte(light.cone_inner_angle))
        self.cone_outer_angle_or_cap_ext.append(_clamp_byte(light.cone_outer_angle_or_cap_ext))
        self.corona_intensity.append(_clamp_byte(light.corona_intensity))
        return light


@dataclasses.dataclass(slots=True)
class DistantLodLightsSoa:
    position: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    RGBI: list[int] = dataclasses.field(default_factory=list)
    num_street_lights: int = 0
    category: int = 0

    def __len__(self) -> int:
        return len(self.position)

    def to_meta(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "RGBI": [int(value) for value in self.RGBI],
            "numStreetLights": int(self.num_street_lights),
            "category": int(self.category),
            "_meta_name_hash": meta_name("CDistantLODLight"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "DistantLodLightsSoa":
        if not isinstance(value, dict):
            return cls()
        return cls(
            position=[tuple(item) for item in value.get("position", []) or []],
            RGBI=[int(item) for item in value.get("RGBI", []) or []],
            num_street_lights=int(value.get("numStreetLights", 0)),
            category=int(value.get("category", 0)),
        )

    def append(self, position: tuple[float, float, float], rgbi: int) -> None:
        self.position.append(tuple(position))
        self.RGBI.append(int(rgbi))


YMAP_SURFACE_STRUCT_INFOS = [
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


def _coerce_occlude_model(**kwargs: Any) -> OccludeModel:
    if "vertices" in kwargs:
        vertices = kwargs.pop("vertices")
        indices = bytes(kwargs.pop("indices", b""))
        flags = int(kwargs.pop("flags", 0))
        return OccludeModel.from_geometry(vertices, indices, flags=flags)
    if "dataSize" in kwargs:
        kwargs["data_size"] = kwargs.pop("dataSize")
    if "numVertsInBytes" in kwargs:
        kwargs["num_verts_in_bytes"] = kwargs.pop("numVertsInBytes")
    if "numTris" in kwargs:
        kwargs["num_tris"] = kwargs.pop("numTris")
    return OccludeModel(**kwargs)


def _coerce_lod_lights(**kwargs: Any) -> LodLightsSoa:
    if "falloffExponent" in kwargs:
        kwargs["falloff_exponent"] = kwargs.pop("falloffExponent")
    if "timeAndStateFlags" in kwargs:
        kwargs["time_and_state_flags"] = kwargs.pop("timeAndStateFlags")
    if "coneInnerAngle" in kwargs:
        kwargs["cone_inner_angle"] = kwargs.pop("coneInnerAngle")
    if "coneOuterAngleOrCapExt" in kwargs:
        kwargs["cone_outer_angle_or_cap_ext"] = kwargs.pop("coneOuterAngleOrCapExt")
    if "coronaIntensity" in kwargs:
        kwargs["corona_intensity"] = kwargs.pop("coronaIntensity")
    return LodLightsSoa(**kwargs)


def _coerce_lod_light(**kwargs: Any) -> LodLight | LodLightsSoa:
    if isinstance(kwargs.get("direction"), list) or isinstance(kwargs.get("falloff"), list):
        return _coerce_lod_lights(**kwargs)
    if "timeAndStateFlags" in kwargs:
        kwargs["time_and_state_flags"] = kwargs.pop("timeAndStateFlags")
    if "coneInnerAngle" in kwargs:
        kwargs["cone_inner_angle"] = kwargs.pop("coneInnerAngle")
    if "coneOuterAngleOrCapExt" in kwargs:
        kwargs["cone_outer_angle_or_cap_ext"] = kwargs.pop("coneOuterAngleOrCapExt")
    if "coronaIntensity" in kwargs:
        kwargs["corona_intensity"] = kwargs.pop("coronaIntensity")
    return LodLight(**kwargs)


GrassBatch = GrassInstanceBatch
InstancedData = InstancedMapData
LodLights = LodLightsSoa
DistantLodLights = DistantLodLightsSoa


__all__ = [
    "Aabb",
    "BATCH_VERT_MULTIPLIER",
    "BoxOccluder",
    "DistantLodLights",
    "DistantLodLightsSoa",
    "GrassBatch",
    "GrassInstance",
    "GrassInstanceBatch",
    "InstancedData",
    "InstancedMapData",
    "LodLight",
    "LodLights",
    "LodLightsSoa",
    "OccludeModel",
    "YMAP_SURFACE_STRUCT_INFOS",
]





