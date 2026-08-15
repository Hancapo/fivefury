from __future__ import annotations

from collections.abc import Iterator

from ..ydr import (
    YdrBone,
    YdrMaterial,
    YdrMaterialInput,
    YdrMesh,
    YdrMeshInput,
    YdrModel,
    YdrModelInput,
)
from ..ydr.defs import YdrSkeletonBinding, coerce_skeleton_binding

GlassMaterial = YdrMaterial | YdrMaterialInput
GlassMesh = YdrMesh | YdrMeshInput
GlassModel = YdrModel | YdrModelInput


def model_binding(model: GlassModel) -> YdrSkeletonBinding:
    return coerce_skeleton_binding(model.skeleton_binding)


def skinned_binding(mesh: GlassMesh, bone: YdrBone) -> int | None:
    first_bindings = {
        int(value[0]) for value in (mesh.blend_indices or ()) if value
    }
    if int(bone.index) in first_bindings:
        return int(bone.index)
    for palette_index, bone_id in enumerate(mesh.bone_ids or ()):
        if (
            int(bone_id) in (int(bone.tag), int(bone.index))
            and palette_index in first_bindings
        ):
            return palette_index
    return None


def iter_bone_meshes(
    model: GlassModel,
    bone: YdrBone,
) -> Iterator[tuple[GlassMesh, int | None]]:
    binding = model_binding(model)
    if binding.is_skinned:
        for mesh in model.meshes:
            mesh_binding = skinned_binding(mesh, bone)
            if mesh_binding is not None:
                yield mesh, mesh_binding
        return
    if int(binding.bone_index) == int(bone.index):
        yield from ((mesh, None) for mesh in model.meshes)


def mesh_material(drawable: object, mesh: GlassMesh) -> GlassMaterial | None:
    material = mesh.material
    if material is not None and not isinstance(material, str):
        return material
    materials = getattr(drawable, "materials", ())
    if isinstance(material, str):
        name = material.casefold()
        return next(
            (
                candidate
                for candidate in materials
                if candidate.name.casefold() == name
            ),
            None,
        )
    material_index = getattr(mesh, "material_index", None)
    if material_index is None:
        return None
    return next(
        (
            candidate
            for candidate in materials
            if int(getattr(candidate, "index", -1)) == int(material_index)
        ),
        None,
    )


def mesh_material_index(
    drawable: object,
    mesh: GlassMesh,
    material: GlassMaterial,
) -> int | None:
    material_index = getattr(mesh, "material_index", None)
    if material_index is not None and int(material_index) >= 0:
        return int(material_index)
    return next(
        (
            index
            for index, candidate in enumerate(getattr(drawable, "materials", ()))
            if candidate is material
        ),
        None,
    )


def material_shader_name(material: GlassMaterial) -> str:
    for field in (
        "resolved_shader_file_name",
        "shader_file_name",
        "shader_name",
        "shader",
    ):
        value = getattr(material, field, None)
        if value is None:
            continue
        value = getattr(value, "value", value)
        if value:
            return str(value)
    return ""


def is_breakable_glass(drawable: object, mesh: GlassMesh) -> bool:
    material = mesh_material(drawable, mesh)
    if material is None:
        return False
    shader = material_shader_name(material)
    return shader.lower().removesuffix(".sps") == "glass_breakable"
