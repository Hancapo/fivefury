from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Iterator

from ..ytd import Ytd
from .defs import LOD_ORDER
from .shaders import ShaderDefinition

if TYPE_CHECKING:
    from .materials import YdrMaterialDescriptor


@dataclasses.dataclass(slots=True)
class YdrTextureRef:
    name: str
    parameter_hash: int = 0
    parameter_name: str | None = None
    name_hash: int = 0
    uv_index: int | None = None
    parameter_type: str | None = None
    hidden: bool = False

    @property
    def slot_name(self) -> str | None:
        return self.parameter_name


@dataclasses.dataclass(slots=True)
class YdrMaterial:
    index: int
    shader_name_hash: int = 0
    shader_name: str | None = None
    shader_file_hash: int = 0
    shader_file_name: str | None = None
    render_bucket: int = 0
    textures: list[YdrTextureRef] = dataclasses.field(default_factory=list)
    shader_definition: ShaderDefinition | None = None

    @property
    def texture_names(self) -> list[str]:
        return [texture.name for texture in self.textures if texture.name]

    @property
    def primary_texture_name(self) -> str | None:
        names = self.texture_names
        return names[0] if names else None

    @property
    def resolved_shader_file_name(self) -> str | None:
        if self.shader_file_name:
            return self.shader_file_name
        if self.shader_definition is None:
            return None
        return self.shader_definition.pick_file_name(self.render_bucket)

    @property
    def texture_slots(self) -> dict[str, YdrTextureRef]:
        slots: dict[str, YdrTextureRef] = {}
        for texture in self.textures:
            if texture.parameter_name:
                slots[texture.parameter_name] = texture
        return slots

    @property
    def material_descriptor(self) -> YdrMaterialDescriptor:
        from .materials import build_material_descriptor

        return build_material_descriptor(self)

    def get_texture(self, value: str | int) -> YdrTextureRef | None:
        if isinstance(value, str):
            lowered = value.lower()
            for texture in self.textures:
                if (texture.parameter_name or "").lower() == lowered:
                    return texture
            return None
        hash_value = int(value)
        for texture in self.textures:
            if texture.parameter_hash == hash_value:
                return texture
        return None


@dataclasses.dataclass(slots=True)
class YdrMesh:
    material_index: int = -1
    material: YdrMaterial | None = None
    indices: list[int] = dataclasses.field(default_factory=list)
    positions: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    normals: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    tangents: list[tuple[float, float, float, float]] = dataclasses.field(default_factory=list)
    texcoords: list[list[tuple[float, float]]] = dataclasses.field(default_factory=list)
    colours0: list[tuple[float, float, float, float]] = dataclasses.field(default_factory=list)
    colours1: list[tuple[float, float, float, float]] = dataclasses.field(default_factory=list)
    blend_weights: list[tuple[float, float, float, float]] = dataclasses.field(default_factory=list)
    blend_indices: list[tuple[int, int, int, int]] = dataclasses.field(default_factory=list)
    bone_ids: list[int] = dataclasses.field(default_factory=list)
    vertex_stride: int = 0
    declaration_flags: int = 0
    declaration_types: int = 0
    render_mask: int = 0
    flags: int = 0

    @property
    def texture_names(self) -> list[str]:
        return self.material.texture_names if self.material is not None else []


@dataclasses.dataclass(slots=True)
class YdrModel:
    lod: str
    meshes: list[YdrMesh] = dataclasses.field(default_factory=list)
    render_mask: int = 0
    flags: int = 0
    skeleton_binding: int = 0

    @property
    def has_skin(self) -> bool:
        return bool((self.skeleton_binding >> 8) & 0xFF)

    @property
    def bone_index(self) -> int:
        return (self.skeleton_binding >> 24) & 0xFF


@dataclasses.dataclass(slots=True)
class Ydr:
    version: int
    path: str = ""
    materials: list[YdrMaterial] = dataclasses.field(default_factory=list)
    lods: dict[str, list[YdrModel]] = dataclasses.field(default_factory=dict)
    bounding_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounding_sphere_radius: float = 0.0
    bounding_box_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounding_box_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    embedded_textures: Ytd | None = None

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, *, path: str = "") -> "Ydr":
        from . import read_ydr

        return read_ydr(data, path=path)

    def get_lod(self, name: str) -> list[YdrModel]:
        return self.lods.get(str(name).lower(), [])

    def iter_models(self, lod: str | None = None) -> Iterator[YdrModel]:
        if lod is not None:
            yield from self.get_lod(lod)
            return
        for name in LOD_ORDER:
            yield from self.lods.get(name, [])

    def iter_meshes(self, lod: str | None = None) -> Iterator[YdrMesh]:
        for model in self.iter_models(lod=lod):
            yield from model.meshes

    @property
    def meshes(self) -> list[YdrMesh]:
        for lod in LOD_ORDER:
            models = self.lods.get(lod)
            if models:
                meshes: list[YdrMesh] = []
                for model in models:
                    meshes.extend(model.meshes)
                return meshes
        return []

    @property
    def texture_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for material in self.materials:
            for name in material.texture_names:
                lowered = name.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                names.append(name)
        return names


__all__ = [
    "Ydr",
    "YdrMaterial",
    "YdrMesh",
    "YdrModel",
    "YdrTextureRef",
]