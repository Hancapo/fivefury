from __future__ import annotations

import dataclasses
import math
import struct
from enum import Enum
from typing import Any

from ..meta.defs import meta_name
from ..vector import Aabb3, Vector3


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
    def position(self) -> Vector3:
        return Vector3(self.iCenterX / 4.0, self.iCenterY / 4.0, self.iCenterZ / 4.0)

    @property
    def size(self) -> Vector3:
        # GTA V's rasterizer expands ``iWidth`` along the local X axis and
        # ``iLength`` along local Y.  Expose the public box size as (X, Y, Z)
        # even though the packed field order is (length, width, height).
        return Vector3(self.iWidth / 4.0, self.iLength / 4.0, self.iHeight / 4.0)

    @property
    def angle_radians(self) -> float:
        return math.atan2(self.iSinZ / 16384.0, self.iCosZ / 16384.0)

    @property
    def bounds(self) -> Aabb3:
        position = self.position
        size = self.size
        half_x = size.x * 0.5
        half_y = size.y * 0.5
        radians = self.angle_radians
        extent_x = abs(math.cos(radians)) * half_x + abs(math.sin(radians)) * half_y
        extent_y = abs(math.sin(radians)) * half_x + abs(math.cos(radians)) * half_y
        return Aabb3(
            Vector3(position.x - extent_x, position.y - extent_y, position.z - size.z * 0.5),
            Vector3(position.x + extent_x, position.y + extent_y, position.z + size.z * 0.5),
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
    def from_meta(cls, value: Any) -> BoxOccluder:
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
        position: Vector3,
        size: Vector3,
        angle: float = 0.0,
        angle_mode: AngleMode = AngleMode.DEGREES,
    ) -> BoxOccluder:
        radians = (
            math.radians(angle) if angle_mode == AngleMode.DEGREES else float(angle)
        )
        return cls(
            iCenterX=round(position.x * 4),
            iCenterY=round(position.y * 4),
            iCenterZ=round(position.z * 4),
            # The runtime's BoxOccluder::CalculateVerts treats width as local
            # X and length as local Y, despite their serialized field order.
            iLength=max(1, round(abs(size.y) * 4)),
            iWidth=max(1, round(abs(size.x) * 4)),
            iHeight=max(1, round(abs(size.z) * 4)),
            # Match GTA V's BoxOccluder::SetSize exactly.  Swapping these to
            # match CodeWalker's display convention mirrors non-axis-aligned
            # boxes in the runtime and can make them occlude unrelated assets.
            iCosZ=round(math.cos(radians) * 16384),
            iSinZ=round(math.sin(radians) * 16384),
        )


_OCCLUDE_MAX_VERTICES = 256


@dataclasses.dataclass(slots=True)
class OccludeModel:
    bmin: Vector3 = dataclasses.field(default_factory=Vector3)
    bmax: Vector3 = dataclasses.field(default_factory=Vector3)
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
    def from_meta(cls, value: Any) -> OccludeModel:
        if not isinstance(value, dict):
            return cls()
        return cls(
            bmin=Vector3.from_iterable(value.get("bmin", (0.0, 0.0, 0.0))),
            bmax=Vector3.from_iterable(value.get("bmax", (0.0, 0.0, 0.0))),
            data_size=int(value.get("dataSize", 0)),
            verts=bytes(value.get("verts", b"") or b""),
            num_verts_in_bytes=int(value.get("numVertsInBytes", 0)),
            num_tris=int(value.get("numTris", 0)),
            flags=int(value.get("flags", 0)),
        )

    @property
    def bounds(self) -> Aabb3:
        return Aabb3(self.bmin, self.bmax)

    def vertices(self) -> list[Vector3]:
        count = self.num_verts_in_bytes // 12 if self.num_verts_in_bytes else 0
        return [Vector3(*value) for value in struct.iter_unpack("<fff", self.verts[: count * 12])]

    def indices(self) -> bytes:
        return self.verts[self.num_verts_in_bytes :]

    def set_geometry(
        self,
        vertices: list[Vector3],
        indices: bytes,
        *,
        flags: int | None = None,
    ) -> OccludeModel:
        vert_bytes = b"".join(struct.pack("<fff", *vertex) for vertex in vertices)
        self.verts = vert_bytes + bytes(indices)
        self.num_verts_in_bytes = len(vert_bytes)
        self.data_size = len(self.verts)
        self.num_tris = (len(indices) // 3) + 32768 if indices else 0
        if vertices:
            self.bmin = Vector3.minimum(vertices)
            self.bmax = Vector3.maximum(vertices)
        if flags is not None:
            self.flags = int(flags)
        return self

    @classmethod
    def from_geometry(
        cls,
        vertices: list[Vector3],
        indices: bytes = b"",
        *,
        flags: int = 0,
    ) -> OccludeModel:
        model = cls(flags=flags)
        return model.set_geometry(vertices, indices, flags=flags)

    @classmethod
    def from_faces(
        cls,
        vertices: list[Vector3],
        faces: list[tuple[int, ...]],
        *,
        flags: int = 0,
    ) -> list[OccludeModel]:
        triangles: list[tuple[int, int, int]] = []
        for face in faces:
            if len(face) < 3:
                continue
            for i in range(1, len(face) - 1):
                triangles.append((face[0], face[i], face[i + 1]))

        if not triangles:
            return [cls(flags=flags)]

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
        min_pos: Vector3,
        max_pos: Vector3,
        *,
        flags: int = 0,
    ) -> list[OccludeModel]:
        x0, y0, z0 = min_pos
        x1, y1, z1 = max_pos
        vertices = [
            Vector3(x0, y0, z0),
            Vector3(x1, y0, z0),
            Vector3(x1, y1, z0),
            Vector3(x0, y1, z0),
            Vector3(x0, y0, z1),
            Vector3(x1, y0, z1),
            Vector3(x1, y1, z1),
            Vector3(x0, y1, z1),
        ]
        faces = [
            (0, 1, 2, 3),
            (4, 7, 6, 5),
            (0, 4, 5, 1),
            (2, 6, 7, 3),
            (0, 3, 7, 4),
            (1, 5, 6, 2),
        ]
        return cls.from_faces(vertices, faces, flags=flags)

    @classmethod
    def from_quad(
        cls, corners: list[Vector3], *, flags: int = 0
    ) -> list[OccludeModel]:
        if len(corners) != 4:
            raise ValueError(
                f"from_quad requires exactly 4 corners, got {len(corners)}"
            )
        return cls.from_faces(list(corners), [(0, 1, 2, 3)], flags=flags)


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


__all__ = ["AngleMode", "BoxOccluder", "OccludeModel", "_coerce_occlude_model"]
