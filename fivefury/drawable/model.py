from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Generic, TypeVar

from .lod import DRAWABLE_LOD_ORDER, DrawableLod, coerce_drawable_lod

NumericParameterValue = float | tuple[float, ...] | tuple[tuple[float, ...], ...]

ParameterT = TypeVar("ParameterT", bound="DrawableParameter")
MaterialT = TypeVar("MaterialT", bound="DrawableMaterial")
MeshT = TypeVar("MeshT", bound="DrawableMesh")
ModelT = TypeVar("ModelT", bound="DrawableModel")


def find_parameter(parameters: Iterable[ParameterT], value: str | int) -> ParameterT | None:
    if isinstance(value, str):
        lowered = value.lower()
        return next((parameter for parameter in parameters if parameter.name.lower() == lowered), None)
    target_hash = int(value)
    return next((parameter for parameter in parameters if int(parameter.name_hash) == target_hash), None)


def find_material(materials: Iterable[MaterialT], value: str | int) -> MaterialT | None:
    if isinstance(value, str):
        lowered = value.lower()
        return next(
            (
                material
                for material in materials
                if material.name.lower() == lowered or (material.shader_name or "").lower() == lowered
            ),
            None,
        )
    target_index = int(value)
    return next((material for material in materials if int(material.index) == target_index), None)


class DrawableParameter:
    __slots__ = ()

    name: str
    name_hash: int
    value: NumericParameterValue | None
    texture_name: str | None

    @property
    def is_texture(self) -> bool:
        return self.texture_name is not None

    @property
    def is_numeric(self) -> bool:
        return not self.is_texture

    @property
    def is_bound(self) -> bool:
        return self.texture_name is not None if self.is_texture else self.value is not None


class DrawableMaterial(Generic[ParameterT]):
    __slots__ = ()

    index: int
    name: str
    shader_name: str | None
    parameters: list[ParameterT]

    @property
    def texture_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        candidates = (
            *(parameter.texture_name for parameter in self.parameters),
            *(texture.name for texture in getattr(self, "textures", ())),
        )
        for name in candidates:
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)
        return names

    @property
    def primary_texture_name(self) -> str | None:
        names = self.texture_names
        return names[0] if names else None

    def get_parameter(self, value: str | int) -> ParameterT | None:
        return find_parameter(self.parameters, value)

    def get_numeric_parameter(self, value: str | int) -> NumericParameterValue | None:
        parameter = self.get_parameter(value)
        if parameter is None or not parameter.is_numeric:
            return None
        return parameter.value


class DrawableMesh(Generic[MaterialT]):
    __slots__ = ()

    material_index: int
    material: MaterialT | None
    indices: list[int]
    positions: list[tuple[float, float, float]]
    blend_weights: list[tuple[float, float, float, float]]
    blend_indices: list[tuple[int, int, int, int]]
    bone_ids: list[int]

    @property
    def texture_names(self) -> list[str]:
        return self.material.texture_names if self.material is not None else []

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    @property
    def index_count(self) -> int:
        return len(self.indices)

    @property
    def is_skinned(self) -> bool:
        return bool(self.blend_weights or self.blend_indices or self.bone_ids)


class DrawableModel(Generic[MeshT, MaterialT]):
    __slots__ = ()

    lod: DrawableLod
    index: int
    meshes: list[MeshT]

    @property
    def mesh_count(self) -> int:
        return len(self.meshes)

    @property
    def material_indices(self) -> list[int]:
        indices: list[int] = []
        seen: set[int] = set()
        for mesh in self.meshes:
            index = int(mesh.material_index)
            if index < 0 or index in seen:
                continue
            seen.add(index)
            indices.append(index)
        return indices

    @property
    def materials(self) -> list[MaterialT]:
        materials: list[MaterialT] = []
        seen: set[int] = set()
        for mesh in self.meshes:
            material = mesh.material
            if material is None or int(material.index) in seen:
                continue
            seen.add(int(material.index))
            materials.append(material)
        return materials

    @property
    def material_count(self) -> int:
        return len(self.materials)

    @property
    def slot_indices(self) -> list[int]:
        return self.material_indices

    def iter_materials(self) -> Iterator[MaterialT]:
        yield from self.materials

    def get_material(self, value: str | int) -> MaterialT | None:
        return find_material(self.materials, value)


class DrawableAsset(Generic[MaterialT, ModelT, MeshT]):
    __slots__ = ()

    path: str
    materials: list[MaterialT]
    lods: dict[DrawableLod, list[ModelT]]
    lod_distances: dict[DrawableLod, float]

    def __post_init__(self) -> None:
        self.lods = {coerce_drawable_lod(lod): list(models) for lod, models in self.lods.items()}
        self.lod_distances = {
            coerce_drawable_lod(lod): float(distance)
            for lod, distance in self.lod_distances.items()
        }

    @property
    def name(self) -> str:
        return Path(self.path).stem if self.path else "drawable"

    def get_lod(self, lod: DrawableLod | str) -> list[ModelT]:
        return self.lods.get(coerce_drawable_lod(lod), [])

    def iter_models(self, lod: DrawableLod | str | None = None) -> Iterator[ModelT]:
        if lod is not None:
            yield from self.get_lod(lod)
            return
        for lod_name in DRAWABLE_LOD_ORDER:
            yield from self.lods.get(lod_name, ())

    def iter_meshes(self, lod: DrawableLod | str | None = None) -> Iterator[MeshT]:
        for model in self.iter_models(lod):
            yield from model.meshes

    @property
    def models(self) -> list[ModelT]:
        return list(self.iter_models())

    @property
    def model_count(self) -> int:
        return sum(len(self.lods.get(lod, ())) for lod in DRAWABLE_LOD_ORDER)

    def get_model(self, index: int, *, lod: DrawableLod | str | None = None) -> ModelT | None:
        target = int(index)
        if target < 0:
            return None
        return next((model for model_index, model in enumerate(self.iter_models(lod)) if model_index == target), None)

    @property
    def meshes(self) -> list[MeshT]:
        return list(self.iter_meshes())

    def get_lod_meshes(self, lod: DrawableLod | str) -> list[MeshT]:
        return list(self.iter_meshes(lod))

    @property
    def primary_lod(self) -> DrawableLod | None:
        return next((lod for lod in DRAWABLE_LOD_ORDER if self.lods.get(lod)), None)

    @property
    def primary_meshes(self) -> list[MeshT]:
        lod = self.primary_lod
        return self.get_lod_meshes(lod) if lod is not None else []

    @property
    def texture_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for material in self.materials:
            for name in material.texture_names:
                lowered = name.lower()
                if lowered not in seen:
                    seen.add(lowered)
                    names.append(name)
        return names

    def get_material(self, value: str | int) -> MaterialT | None:
        return find_material(self.materials, value)

    @property
    def slot_indices(self) -> list[int]:
        return [int(material.index) for material in self.materials]


__all__ = [
    "DrawableAsset",
    "DrawableMaterial",
    "DrawableMesh",
    "DrawableModel",
    "DrawableParameter",
    "NumericParameterValue",
    "find_material",
    "find_parameter",
]
