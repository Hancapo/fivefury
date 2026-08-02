from __future__ import annotations

import dataclasses

from ..ydr import YdrBone, YdrLod, YdrMesh
from ..ydr.defs import coerce_lod
from .glass import YftGlassPane
from .glass_authoring import (
    YftGlassOrthonormalTransform,
    build_yft_glass_pane_from_mesh,
)
from .physics import YftPhysicsChild, YftPhysicsGroup, YftPhysicsGroupFlag


def _group_children(group: YftPhysicsGroup, children) -> tuple[YftPhysicsChild, ...]:
    if group.children:
        return group.children
    if group.child_index == 0xFF:
        return ()
    end = int(group.child_index) + int(group.num_children)
    return tuple(children[int(group.child_index) : end])


def _first_drawable_lod(drawable) -> YdrLod:
    for lod in (YdrLod.HIGH, YdrLod.MEDIUM, YdrLod.LOW, YdrLod.VERY_LOW):
        if drawable.lods.get(lod):
            return lod
    raise ValueError("breakable glass requires render geometry in the common drawable")


def _resolve_bone(drawable, child: YftPhysicsChild) -> YdrBone:
    skeleton = drawable.skeleton
    if skeleton is None:
        raise ValueError("breakable glass requires a common drawable skeleton")
    bone = skeleton.get_bone_by_tag(int(child.bone_id))
    if bone is None and int(child.bone_id) == 0:
        bone = skeleton.get_bone_by_index(0)
    if bone is None:
        raise ValueError(
            f"glass child bone {child.bone_id} does not resolve in the common drawable"
        )
    return bone


def _skinned_binding(mesh: YdrMesh, bone: YdrBone) -> int | None:
    first_bindings = {int(value[0]) for value in mesh.blend_indices}
    if int(bone.index) in first_bindings:
        return int(bone.index)
    for palette_index, bone_id in enumerate(mesh.bone_ids):
        if (
            int(bone_id) in (int(bone.tag), int(bone.index))
            and palette_index in first_bindings
        ):
            return palette_index
    return None


def _material(drawable, mesh: YdrMesh):
    if mesh.material is not None:
        return mesh.material
    return next(
        (
            material
            for material in drawable.materials
            if int(material.index) == int(mesh.material_index)
        ),
        None,
    )


def _is_breakable_glass(drawable, mesh: YdrMesh) -> bool:
    material = _material(drawable, mesh)
    if material is None:
        return False
    shader = material.resolved_shader_file_name or material.shader_name or ""
    return shader.lower().removesuffix(".sps") == "glass_breakable"


def _resolve_mesh(
    drawable,
    bone: YdrBone,
    *,
    lod: YdrLod,
) -> tuple[YdrMesh, int | None]:
    candidates: list[tuple[YdrMesh, int | None]] = []
    for model in drawable.iter_models(lod):
        binding = None
        if model.has_skin:
            for mesh in model.meshes:
                binding = _skinned_binding(mesh, bone)
                if binding is not None:
                    candidates.append((mesh, binding))
            continue
        if int(model.bone_index) == int(bone.index):
            candidates.extend((mesh, None) for mesh in model.meshes)

    breakable = [item for item in candidates if _is_breakable_glass(drawable, item[0])]
    selected = breakable or candidates
    if not selected:
        raise ValueError(
            f"bone '{bone.name}' does not select any glass geometry in {lod.value} LOD"
        )
    if len(selected) != 1:
        raise ValueError(
            f"bone '{bone.name}' selects {len(selected)} glass meshes; "
            "use one glass_breakable.sps mesh per physics group"
        )
    return selected[0]


def _child_bound(child: YftPhysicsChild):
    entity = child.undamaged_entity
    drawable = entity.drawable if entity is not None else None
    bound = drawable.bound if drawable is not None else None
    if bound is None:
        raise ValueError("breakable glass requires an intact child drawable bound")
    return drawable, bound


def _bound_transform(drawable) -> YftGlassOrthonormalTransform:
    matrix = getattr(drawable, "fragment_matrix", None)
    if matrix is None:
        return YftGlassOrthonormalTransform()
    columns = matrix.columns
    return YftGlassOrthonormalTransform(
        x_axis=columns[0],
        y_axis=columns[1],
        z_axis=columns[2],
        translation=columns[3],
    )


def _glass_type(source, group: YftPhysicsGroup) -> int:
    if group.authored_glass_type is not None:
        return int(group.authored_glass_type)
    pane_index = int(group.glass_pane_model_info_index)
    if 0 <= pane_index < len(source.glass_panes):
        return int(source.glass_panes[pane_index].glass_type)
    return pane_index


def build_yft_glass(
    source,
    *,
    physics_lod: int | str = "high",
    drawable_lod: YdrLod | str | None = None,
) -> list[YftGlassPane]:
    if source.main_drawable is None:
        raise ValueError("breakable glass requires a common drawable")
    lod = source.physics_lod(physics_lod)
    if lod is None and physics_lod == "high":
        lod = source.best_physics_lod
    if lod is None:
        raise ValueError(f"physics LOD '{physics_lod}' does not exist")
    render_lod = (
        _first_drawable_lod(source.main_drawable)
        if drawable_lod is None
        else coerce_lod(drawable_lod)
        if not isinstance(drawable_lod, YdrLod)
        else drawable_lod
    )

    panes: list[YftGlassPane] = []
    groups: list[YftPhysicsGroup] = []
    for group in lod.groups:
        if not group.is_glass:
            groups.append(group)
            continue
        children = _group_children(group, lod.children)
        if not children:
            raise ValueError(f"glass group '{group.name}' has no physics child")
        child = children[0]
        bone = _resolve_bone(source.main_drawable, child)
        mesh, mesh_bone_index = _resolve_mesh(
            source.main_drawable,
            bone,
            lod=render_lod,
        )
        child_drawable, bound = _child_bound(child)
        pane = build_yft_glass_pane_from_mesh(
            mesh,
            bone_index=mesh_bone_index,
            glass_type=_glass_type(source, group),
            bounds_minimum=bound.box_min,
            bounds_maximum=bound.box_max,
            bounds_transform=_bound_transform(child_drawable),
        )
        pane_index = len(panes)
        panes.append(pane)
        groups.append(
            dataclasses.replace(
                group,
                glass_model_and_type=0xFF,
                glass_pane_model_info_index=pane_index,
                flags=group.flags | YftPhysicsGroupFlag.MADE_OF_GLASS,
            )
        )

    if not panes:
        raise ValueError(f"physics LOD '{lod.label}' has no breakable glass groups")
    source.glass_panes = panes
    source.physics_lod_details = [
        dataclasses.replace(item, groups=tuple(groups)) if item is lod else item
        for item in source.physics_lod_details
    ]
    return panes


def ensure_yft_glass(source) -> list[YftGlassPane]:
    glass_groups = [group for group in source.iter_physics_groups() if group.is_glass]
    if not glass_groups:
        return []
    if not source.glass_panes:
        return build_yft_glass(source)
    from .validation import validate_yft

    errors = [
        issue
        for issue in validate_yft(source)
        if issue.is_error and ("glass" in issue.path or "glass" in issue.message)
    ]
    if errors:
        raise ValueError("Invalid breakable glass: " + "; ".join(i.format() for i in errors))
    return source.glass_panes


__all__ = ["build_yft_glass", "ensure_yft_glass"]
