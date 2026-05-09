from __future__ import annotations

import dataclasses
import math
import struct
from enum import Enum
from typing import Any

from ..meta.defs import meta_name


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

    def set_geometry(
        self,
        vertices: list[tuple[float, float, float]],
        indices: bytes,
        *,
        flags: int | None = None,
    ) -> "OccludeModel":
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
    def from_geometry(
        cls,
        vertices: list[tuple[float, float, float]],
        indices: bytes = b"",
        *,
        flags: int = 0,
    ) -> "OccludeModel":
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
        min_pos: tuple[float, float, float],
        max_pos: tuple[float, float, float],
        *,
        flags: int = 0,
    ) -> list["OccludeModel"]:
        x0, y0, z0 = min_pos
        x1, y1, z1 = max_pos
        vertices = [
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1),
        ]
        faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (2, 6, 7, 3), (0, 3, 7, 4), (1, 5, 6, 2)]
        return cls.from_faces(vertices, faces, flags=flags)

    @classmethod
    def from_quad(cls, corners: list[tuple[float, float, float]], *, flags: int = 0) -> list["OccludeModel"]:
        if len(corners) != 4:
            raise ValueError(f"from_quad requires exactly 4 corners, got {len(corners)}")
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
