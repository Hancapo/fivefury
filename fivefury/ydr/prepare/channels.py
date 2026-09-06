from __future__ import annotations

import dataclasses

from ...mesh_math import (
    generate_vertex_normals,
    generate_vertex_tangents,
    triangle_array,
)
from ...vector import Vector3
from ..build_types import YdrMeshInput
from ..model.skeleton import YdrSkeleton
from ..shaders import ShaderLayoutDefinition
from .layout import _semantics_from_flags_types, select_layout
from .material import PreparedMaterial
from .skinning import normalize_skin_channels


def prepare_channels(
    mesh: YdrMeshInput,
    material: PreparedMaterial,
    *,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
    skeleton: YdrSkeleton | None,
) -> tuple[YdrMeshInput, ShaderLayoutDefinition]:
    # Validate source channels before generation or remapping can hide mismatches.
    channels = [
        (name, getattr(mesh, name))
        for name in (
            "normals",
            "tangents",
            "colours0",
            "colours1",
            "blend_weights",
            "blend_indices",
        )
    ]
    channels.extend(
        (f"UV channel {index}", channel)
        for index, channel in enumerate(
            mesh.texcoords if mesh.texcoords is not None else ()
        )
    )
    for name, channel in channels:
        if channel is not None and len(channel) not in (0, len(mesh.positions)):
            raise ValueError(f"Mesh {name} length must match positions length")

    positions = list(mesh.positions)
    indices = triangle_array(mesh.indices, len(positions)).reshape(-1).tolist()
    normals = list(mesh.normals) if mesh.normals is not None else []
    texcoords = [list(channel) for channel in (mesh.texcoords or [])]
    tangents = list(mesh.tangents) if mesh.tangents is not None else []
    colours0 = (
        [tuple(map(float, colour)) for colour in mesh.colours0]
        if mesh.colours0 is not None
        else []
    )
    colours1 = (
        [tuple(map(float, colour)) for colour in mesh.colours1]
        if mesh.colours1 is not None
        else []
    )
    blend_weights = (
        [tuple(map(float, w)) for w in mesh.blend_weights]
        if mesh.blend_weights is not None
        else []
    )
    blend_indices = (
        [tuple(map(int, bi)) for bi in mesh.blend_indices]
        if mesh.blend_indices is not None
        else []
    )
    bone_ids = [int(b) for b in mesh.bone_ids] if mesh.bone_ids is not None else []
    skinned = bool(blend_weights)

    blend_indices, bone_ids = normalize_skin_channels(
        blend_weights, blend_indices, bone_ids, skeleton
    )

    if not normals:
        normals = (
            generate_vertex_normals(positions, indices)
            if generate_normals
            else [Vector3(0.0, 0.0, 1.0)] * len(positions)
        )

    material_texture_slots = {
        slot.lower()
        for slot, texture in material.textures.items()
        if texture is not None
    }
    used_uv_indices = {
        int(parameter.uv_index or 0)
        for parameter in material.shader_definition.texture_parameters
        if parameter.name.lower() in material_texture_slots
    }
    layout = select_layout(
        material.shader_definition,
        used_uv_indices=used_uv_indices,
        skinned=skinned,
    )
    expected_semantics = {semantic.lower() for semantic in layout.semantics}
    if mesh.declaration_flags is not None and mesh.declaration_types is not None:
        expected_semantics.update(
            semantic.name.lower()
            for semantic, _component_type in _semantics_from_flags_types(
                int(mesh.declaration_flags), int(mesh.declaration_types)
            )
        )

    if fill_vertex_colours and not colours0 and "colour0" in expected_semantics:
        colours0 = [(1.0, 1.0, 1.0, 1.0)] * len(positions)
    if fill_vertex_colours and not colours1 and "colour1" in expected_semantics:
        colours1 = [(1.0, 1.0, 1.0, 1.0)] * len(positions)

    for parameter in material.shader_definition.texture_parameters:
        if parameter.name.lower() not in material_texture_slots:
            continue
        uv_index = int(parameter.uv_index or 0)
        semantic_name = f"texcoord{uv_index}"
        if semantic_name not in expected_semantics:
            raise ValueError(
                f"Shader layout for material '{material.name}' does not expose {semantic_name} required by slot '{parameter.name}'"
            )
        if uv_index >= len(texcoords) or not texcoords[uv_index]:
            raise ValueError(
                f"Mesh for material '{material.name}' is missing UV channel {uv_index} required by slot '{parameter.name}'"
            )

    if "tangent" in expected_semantics:
        if not tangents and generate_tangents:
            if not texcoords or not texcoords[0]:
                raise ValueError(
                    f"Material '{material.name}' requires tangents but mesh has no UV0 to generate them"
                )
            tangents = generate_vertex_tangents(
                positions, normals, texcoords[0], indices
            )
        if len(tangents) != len(positions):
            raise ValueError("Mesh tangents length must match positions length")
    else:
        tangents = []

    if "colour0" not in expected_semantics:
        colours0 = []
    if "colour1" not in expected_semantics:
        colours1 = []

    # Derive channels on the full topology so duplicated split vertices agree.
    normalized = dataclasses.replace(
        mesh,
        positions=positions,
        indices=indices,
        normals=normals,
        texcoords=texcoords,
        tangents=tangents,
        colours0=colours0,
        colours1=colours1,
        blend_weights=blend_weights,
        blend_indices=blend_indices,
        bone_ids=bone_ids,
    )
    return normalized, layout
