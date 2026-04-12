from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Sequence

from ..bounds import Bound
from ..ytd import Ytd
from .defs import YdrLod, YdrRenderMask, YdrSkeletonBinding, coerce_lod, coerce_render_mask, coerce_skeleton_binding

if TYPE_CHECKING:
    from .model import YdrJoints, YdrLight, YdrSkeleton


@dataclasses.dataclass(slots=True)
class YdrTextureInput:
    name: str
    embedded: bool = False
    source: str | Path | bytes | None = None


@dataclasses.dataclass(slots=True)
class YdrMaterialInput:
    name: str = "default"
    shader: str = "default.sps"
    textures: Mapping[str, str | YdrTextureInput] = dataclasses.field(default_factory=dict)
    parameters: Mapping[str, float | tuple[float, ...] | tuple[tuple[float, ...], ...] | int | str] = dataclasses.field(default_factory=dict)
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

    def to_bytes(self, *, shader_library=None) -> bytes:
        from .builder import build_ydr_bytes

        return build_ydr_bytes(self, shader_library=shader_library)

    def save(self, destination: str | Path, *, shader_library=None) -> Path:
        from .builder import save_ydr

        return save_ydr(self, destination, shader_library=shader_library)


def create_ydr(
    *,
    meshes: Sequence[YdrMeshInput],
    materials: Sequence[YdrMaterialInput] | None = None,
    shader: str = "default.sps",
    textures: Mapping[str, str | YdrTextureInput] | None = None,
    texture: str | YdrTextureInput | None = None,
    skeleton: YdrSkeleton | None = None,
    joints: YdrJoints | None = None,
    lights: Sequence[YdrLight] | None = None,
    embedded_textures: Ytd | None = None,
    bound: Bound | None = None,
    name: str = "",
    lod: YdrLod | str = YdrLod.HIGH,
    render_mask: int | YdrRenderMask = YdrRenderMask.STATIC_PROP,
    version: int = 165,
) -> YdrBuild:
    from .prepare import normalize_materials

    normalized_materials = normalize_materials(materials, shader=shader, textures=textures, texture=texture)
    normalized_lod = coerce_lod(lod)
    return YdrBuild(
        materials=normalized_materials,
        lods={normalized_lod: [YdrModelInput(meshes=list(meshes), render_mask=render_mask)]},
        name=name,
        version=int(version),
        skeleton=skeleton,
        joints=joints,
        lights=list(lights or []),
        embedded_textures=embedded_textures,
        bound=bound,
        lod_distances={normalized_lod: 9998.0},
    )


__all__ = [
    "YdrBuild",
    "YdrMaterialInput",
    "YdrMeshInput",
    "YdrModelInput",
    "YdrTextureInput",
    "create_ydr",
]
