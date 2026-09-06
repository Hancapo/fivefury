from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from ..build_types import YdrBuild, YdrModelInput, _copy_model_input
from ..defs import (
    LOD_ORDER,
    YdrLod,
    YdrRenderMask,
    YdrSkeletonBinding,
    coerce_skeleton_binding,
)
from ..model.skeleton import YdrSkeleton
from ..shaders import ShaderLibrary, resolve_shader_reference
from .material import MaterialPreparer, PreparedMaterial, normalize_material_textures
from .mesh import PreparedMesh, prepare_meshes


@dataclasses.dataclass(slots=True)
class PreparedModel:
    meshes: list[PreparedMesh]
    render_mask: int = int(YdrRenderMask.STATIC_PROP)
    flags: int = 0
    skeleton_binding: YdrSkeletonBinding = dataclasses.field(
        default_factory=YdrSkeletonBinding
    )


PreparedLods = dict[YdrLod, list[PreparedModel]]


def _normalize_skinned_model_palette(
    model: PreparedModel, skeleton: YdrSkeleton | None
) -> None:
    if skeleton is None or not skeleton.bones:
        return
    bone_count = len(skeleton.bones)
    if bone_count > 255:
        raise ValueError(
            "Skinned YDR models currently support at most 255 bones per skeleton"
        )

    model_has_skin = False
    for mesh in model.meshes:
        if not mesh.blend_weights:
            continue
        model_has_skin = True

    if model_has_skin:
        model.skeleton_binding = YdrSkeletonBinding.skinned(
            bone_index=model.skeleton_binding.bone_index,
            unknown_1=bone_count,
            unknown_2=model.skeleton_binding.unknown_2,
        )


def normalize_lods(source: YdrBuild) -> dict[YdrLod, list[YdrModelInput]]:
    normalized: dict[YdrLod, list[YdrModelInput]] = {}
    for lod_name in YdrLod:
        models = source.lods.get(lod_name)
        if not models:
            continue
        normalized[lod_name] = [_copy_model_input(model) for model in models]
    return normalized


def default_root_render_mask_flags(
    models: Sequence[PreparedModel],
    materials: Sequence[PreparedMaterial] = (),
) -> int:
    render_mask = 0
    base_bucket_mask = 0
    material_buckets = {
        int(material.index): int(material.render_bucket) for material in materials
    }
    for model in models:
        render_mask |= int(model.render_mask) & 0xFF
        for mesh in model.meshes:
            render_bucket = material_buckets.get(int(mesh.material_index))
            if render_bucket is None:
                continue
            if not 0 <= render_bucket < 8:
                raise ValueError(
                    f"YDR render bucket must be between 0 and 7, got {render_bucket}"
                )
            base_bucket_mask |= 1 << render_bucket
    return ((render_mask & 0xFF) << 8) | (base_bucket_mask & 0xFF)


def drawable_name(source_name: str) -> str:
    base = source_name.strip() or "drawable"
    return base if base.lower().endswith(".#dr") else f"{base}.#dr"


def prepare_build(
    source: YdrBuild,
    shader_library: ShaderLibrary,
    *,
    prepare_materials: MaterialPreparer,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
) -> tuple[list[PreparedMaterial], PreparedLods]:
    prepared_materials, material_lookup = prepare_materials(
        source.materials,
        shader_library,
        prepared_material_cls=PreparedMaterial,
        normalize_material_textures=normalize_material_textures,
        resolve_shader=resolve_shader_reference,
    )
    prepared_lods: PreparedLods = {}
    normalized = normalize_lods(source)
    for lod_name in LOD_ORDER:
        normalized_models = normalized.get(lod_name)
        if not normalized_models:
            continue
        prepared_models: list[PreparedModel] = []
        for model in normalized_models:
            prepared_meshes = prepare_meshes(
                model.meshes,
                prepared_materials,
                material_lookup,
                generate_normals=generate_normals,
                generate_tangents=generate_tangents,
                fill_vertex_colours=fill_vertex_colours,
                skeleton=source.skeleton,
            )
            effective_flags = int(model.flags)
            if any(mesh.blend_weights for mesh in prepared_meshes):
                effective_flags |= 0x1
            prepared_models.append(
                PreparedModel(
                    meshes=prepared_meshes,
                    render_mask=int(model.render_mask),
                    flags=effective_flags,
                    skeleton_binding=coerce_skeleton_binding(model.skeleton_binding),
                )
            )
            _normalize_skinned_model_palette(prepared_models[-1], source.skeleton)
        prepared_lods[lod_name] = prepared_models
    return prepared_materials, prepared_lods
