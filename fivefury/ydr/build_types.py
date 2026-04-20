from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Sequence

from ..bounds import Bound
from ..ytd import Ytd
from .defs import YdrLod, YdrRenderMask, YdrSkeletonBinding, coerce_lod, coerce_render_mask, coerce_skeleton_binding
from .shader_enums import YdrShader

if TYPE_CHECKING:
    from .model import YdrJoints, YdrLight, YdrSkeleton


MaterialParameterValue = float | tuple[float, ...] | tuple[tuple[float, ...], ...] | int | str


@dataclasses.dataclass(slots=True)
class YdrTextureInput:
    name: str
    embedded: bool = False
    source: str | Path | bytes | None = None


TextureInputValue = str | Path | YdrTextureInput


@dataclasses.dataclass(slots=True)
class YdrMaterialInput:
    name: str = "default"
    shader: str | YdrShader = YdrShader.DEFAULT
    textures: Mapping[str, TextureInputValue] = dataclasses.field(default_factory=dict)
    parameters: Mapping[str, MaterialParameterValue] = dataclasses.field(default_factory=dict)
    render_bucket: int = 0


@dataclasses.dataclass(slots=True)
class YdrMeshInput:
    positions: Sequence[tuple[float, float, float]]
    indices: Sequence[int]
    material: str = "default"
    normals: Sequence[tuple[float, float, float]] | None = None
    texcoords: Sequence[Sequence[tuple[float, float]]] | None = None
    tangents: Sequence[tuple[float, float, float, float]] | None = None
    colours0: Sequence[tuple[float, float, float, float]] | None = None
    colours1: Sequence[tuple[float, float, float, float]] | None = None
    blend_weights: Sequence[tuple[float, float, float, float]] | None = None
    blend_indices: Sequence[tuple[int, int, int, int]] | None = None
    bone_ids: Sequence[int] | None = None
    vertex_buffer_flags: int = 0
    declaration_flags: int | None = None
    declaration_types: int | None = None


@dataclasses.dataclass(slots=True)
class YdrModelInput:
    meshes: Sequence[YdrMeshInput]
    render_mask: int | YdrRenderMask = YdrRenderMask.STATIC_PROP
    flags: int = 0
    skeleton_binding: int | YdrSkeletonBinding = dataclasses.field(default_factory=YdrSkeletonBinding)

    def __post_init__(self) -> None:
        self.render_mask = coerce_render_mask(self.render_mask)
        self.skeleton_binding = coerce_skeleton_binding(self.skeleton_binding)


def _build_model_input(
    meshes: Sequence[YdrMeshInput],
    *,
    render_mask: int | YdrRenderMask = YdrRenderMask.STATIC_PROP,
    flags: int = 0,
    skeleton_binding: int | YdrSkeletonBinding | None = None,
) -> YdrModelInput:
    return YdrModelInput(
        meshes=list(meshes),
        render_mask=render_mask,
        flags=int(flags),
        skeleton_binding=YdrSkeletonBinding() if skeleton_binding is None else coerce_skeleton_binding(skeleton_binding),
    )


def _copy_model_input(model: YdrModelInput) -> YdrModelInput:
    return _build_model_input(
        model.meshes,
        render_mask=model.render_mask,
        flags=model.flags,
        skeleton_binding=model.skeleton_binding,
    )


@dataclasses.dataclass(slots=True)
class YdrBuild:
    materials: list[YdrMaterialInput]
    lods: dict[YdrLod, list[YdrModelInput]] = dataclasses.field(default_factory=dict)
    name: str = ""
    version: int = 165
    skeleton: YdrSkeleton | None = None
    joints: YdrJoints | None = None
    lights: list[YdrLight] = dataclasses.field(default_factory=list)
    embedded_textures: Ytd | None = None
    bound: Bound | None = None
    lod_distances: dict[YdrLod, float] = dataclasses.field(default_factory=dict)
    render_mask_flags: dict[YdrLod, int] = dataclasses.field(default_factory=dict)
    unknown_98: int = 0
    unknown_9c: int = 0

    def __post_init__(self) -> None:
        self.lods = {coerce_lod(lod): list(models) for lod, models in self.lods.items()}
        self.lod_distances = {coerce_lod(lod): float(distance) for lod, distance in self.lod_distances.items()}
        self.render_mask_flags = {coerce_lod(lod): int(mask) for lod, mask in self.render_mask_flags.items()}

    @classmethod
    def from_meshes(
        cls,
        *,
        meshes: Sequence[YdrMeshInput],
        materials: Sequence[YdrMaterialInput] | None = None,
        shader: str | YdrShader = YdrShader.DEFAULT,
        material_textures: Mapping[str, TextureInputValue] | None = None,
        skeleton: YdrSkeleton | None = None,
        joints: YdrJoints | None = None,
        lights: Sequence[YdrLight] | None = None,
        embedded_textures: Ytd | None = None,
        bound: Bound | None = None,
        name: str = "",
        lod: YdrLod | str = YdrLod.HIGH,
        lod_distance: float = 9998.0,
        render_mask: int | YdrRenderMask = YdrRenderMask.STATIC_PROP,
        flags: int = 0,
        skeleton_binding: int | YdrSkeletonBinding | None = None,
        version: int = 165,
    ) -> "YdrBuild":
        from .prepare import normalize_materials

        normalized_lod = coerce_lod(lod)
        build = cls(
            materials=normalize_materials(materials, shader=shader, material_textures=material_textures),
            name=name,
            version=int(version),
            skeleton=skeleton,
            joints=joints,
            lights=list(lights or []),
            embedded_textures=embedded_textures,
            bound=bound,
        )
        build.add_model(
            meshes,
            lod=normalized_lod,
            render_mask=render_mask,
            flags=flags,
            skeleton_binding=skeleton_binding,
            lod_distance=lod_distance,
        )
        return build

    def add_model(
        self,
        meshes: Sequence[YdrMeshInput],
        *,
        lod: YdrLod | str = YdrLod.HIGH,
        render_mask: int | YdrRenderMask = YdrRenderMask.STATIC_PROP,
        flags: int = 0,
        skeleton_binding: int | YdrSkeletonBinding | None = None,
        lod_distance: float | None = None,
    ) -> YdrModelInput:
        normalized_lod = coerce_lod(lod)
        model = _build_model_input(
            meshes,
            render_mask=render_mask,
            flags=flags,
            skeleton_binding=skeleton_binding,
        )
        self.lods.setdefault(normalized_lod, []).append(model)
        if lod_distance is not None:
            self.lod_distances[normalized_lod] = float(lod_distance)
        return model

    def add_light(
        self,
        light: YdrLight,
    ) -> YdrLight:
        self.lights.append(light)
        return light

    def clear_lights(self) -> "YdrBuild":
        self.lights.clear()
        return self

    def get_lod(self, lod: YdrLod | str) -> list[YdrModelInput]:
        return self.lods.get(coerce_lod(lod), [])

    def iter_models(self, lod: YdrLod | str | None = None):
        if lod is not None:
            yield from self.get_lod(lod)
            return
        for lod_name in YdrLod:
            yield from self.lods.get(lod_name, [])

    @property
    def model_count(self) -> int:
        return sum(len(models) for models in self.lods.values())

    def to_bytes(self, *, shader_library=None, recalculate_skeleton_hashes: bool = False) -> bytes:
        from .builder import build_ydr_bytes

        return build_ydr_bytes(
            self,
            shader_library=shader_library,
            recalculate_skeleton_hashes=recalculate_skeleton_hashes,
        )

    def save(self, destination: str | Path, *, shader_library=None, recalculate_skeleton_hashes: bool = False) -> Path:
        from .builder import save_ydr

        return save_ydr(
            self,
            destination,
            shader_library=shader_library,
            recalculate_skeleton_hashes=recalculate_skeleton_hashes,
        )


def create_ydr(
    *,
    meshes: Sequence[YdrMeshInput],
    materials: Sequence[YdrMaterialInput] | None = None,
    shader: str | YdrShader = YdrShader.DEFAULT,
    material_textures: Mapping[str, TextureInputValue] | None = None,
    skeleton: YdrSkeleton | None = None,
    joints: YdrJoints | None = None,
    lights: Sequence[YdrLight] | None = None,
    embedded_textures: Ytd | None = None,
    bound: Bound | None = None,
    name: str = "",
    lod: YdrLod | str = YdrLod.HIGH,
    lod_distance: float = 9998.0,
    render_mask: int | YdrRenderMask = YdrRenderMask.STATIC_PROP,
    flags: int = 0,
    skeleton_binding: int | YdrSkeletonBinding | None = None,
    version: int = 165,
) -> YdrBuild:
    return YdrBuild.from_meshes(
        meshes=meshes,
        materials=materials,
        shader=shader,
        material_textures=material_textures,
        skeleton=skeleton,
        joints=joints,
        lights=lights,
        embedded_textures=embedded_textures,
        bound=bound,
        name=name,
        lod=lod,
        lod_distance=lod_distance,
        render_mask=render_mask,
        flags=flags,
        skeleton_binding=skeleton_binding,
        version=version,
    )


__all__ = [
    "YdrBuild",
    "YdrMaterialInput",
    "YdrMeshInput",
    "YdrModelInput",
    "YdrTextureInput",
    "create_ydr",
]
