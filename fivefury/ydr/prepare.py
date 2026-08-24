from __future__ import annotations

import dataclasses
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from .. import _native as _native_backend
from ..mesh_math import (
    generate_vertex_normals,
    generate_vertex_tangents,
    triangle_array,
)
from ..vector import Aabb3, Vector2, Vector3, Vector4, sphere_radius_from_points
from .build_types import (
    YdrBuild,
    YdrMaterialInput,
    YdrMeshInput,
    YdrModelInput,
    YdrTextureInput,
    _copy_model_input,
)
from .defs import (
    COMPONENT_SIZES,
    LOD_ORDER,
    VertexComponentType,
    VertexSemantic,
    YdrLod,
    YdrRenderMask,
    YdrSkeletonBinding,
    coerce_skeleton_binding,
)
from .gen9_shader_enums import YdrGen9Shader
from .shader_enums import YdrShader
from .shaders import (
    ShaderDefinition,
    ShaderLayoutDefinition,
    ShaderLibrary,
    ShaderParameterDefinition,
    resolve_shader_reference,
)
from .transforms import skeleton_absolute_transforms

if TYPE_CHECKING:
    from .gen9 import ShaderGen9Definition
    from .model import Matrix4, YdrSkeleton

T = TypeVar("T")

_DEFAULT_DECLARATION_TYPES = (
    (int(VertexComponentType.FLOAT3) << (int(VertexSemantic.POSITION) * 4))
    | (int(VertexComponentType.COLOUR) << (int(VertexSemantic.BLEND_WEIGHTS) * 4))
    | (int(VertexComponentType.COLOUR) << (int(VertexSemantic.BLEND_INDICES) * 4))
    | (int(VertexComponentType.FLOAT3) << (int(VertexSemantic.NORMAL) * 4))
    | (int(VertexComponentType.COLOUR) << (int(VertexSemantic.COLOUR0) * 4))
    | (int(VertexComponentType.COLOUR) << (int(VertexSemantic.COLOUR1) * 4))
    | (int(VertexComponentType.FLOAT2) << (int(VertexSemantic.TEXCOORD0) * 4))
    | (int(VertexComponentType.FLOAT2) << (int(VertexSemantic.TEXCOORD1) * 4))
    | (int(VertexComponentType.FLOAT2) << (int(VertexSemantic.TEXCOORD2) * 4))
    | (int(VertexComponentType.FLOAT2) << (int(VertexSemantic.TEXCOORD3) * 4))
    | (int(VertexComponentType.FLOAT2) << (int(VertexSemantic.TEXCOORD4) * 4))
    | (int(VertexComponentType.FLOAT2) << (int(VertexSemantic.TEXCOORD5) * 4))
    | (int(VertexComponentType.FLOAT2) << (int(VertexSemantic.TEXCOORD6) * 4))
    | (int(VertexComponentType.FLOAT2) << (int(VertexSemantic.TEXCOORD7) * 4))
    | (int(VertexComponentType.FLOAT4) << (int(VertexSemantic.TANGENT) * 4))
    | (int(VertexComponentType.FLOAT4) << (int(VertexSemantic.BINORMAL) * 4))
)

_SEMANTIC_ALIASES = {
    "BLENDWEIGHTS": "BLEND_WEIGHTS",
    "BLENDINDICES": "BLEND_INDICES",
}

_TEXTURE_SLOT_ALIASES = {
    "SPECULARSAMPLER": "SpecSampler",
}

_CANONICAL_COMPONENT_TYPES: dict[VertexSemantic, VertexComponentType] = {
    VertexSemantic.POSITION: VertexComponentType.FLOAT3,
    VertexSemantic.BLEND_WEIGHTS: VertexComponentType.COLOUR,
    VertexSemantic.BLEND_INDICES: VertexComponentType.COLOUR,
    VertexSemantic.NORMAL: VertexComponentType.FLOAT3,
    VertexSemantic.COLOUR0: VertexComponentType.COLOUR,
    VertexSemantic.COLOUR1: VertexComponentType.COLOUR,
    VertexSemantic.TANGENT: VertexComponentType.FLOAT4,
}


@dataclasses.dataclass(slots=True)
class PreparedMaterial:
    index: int
    name: str
    shader_definition: ShaderDefinition
    shader_file_name: str
    render_bucket: int
    textures: dict[str, YdrTextureInput | None]
    parameters: dict[
        str, float | tuple[float, ...] | tuple[tuple[float, ...], ...] | int | str
    ]
    gen9_definition: ShaderGen9Definition | None = None


@dataclasses.dataclass(slots=True)
class PreparedMesh:
    positions: list[Vector3]
    indices: list[int]
    material_index: int
    normals: list[Vector3]
    texcoords: list[list[Vector2]]
    tangents: list[Vector4]
    colours0: list[tuple[float, float, float, float]]
    colours1: list[tuple[float, float, float, float]]
    blend_weights: list[tuple[float, float, float, float]]
    blend_indices: list[tuple[int, int, int, int]]
    bone_ids: list[int]
    declaration_flags: int
    declaration_types: int
    vertex_stride: int
    vertex_buffer_flags: int
    vertex_bytes: bytes
    index_bytes: bytes
    layout: ShaderLayoutDefinition


@dataclasses.dataclass(slots=True)
class PreparedModel:
    meshes: list[PreparedMesh]
    render_mask: int = int(YdrRenderMask.STATIC_PROP)
    flags: int = 0
    skeleton_binding: YdrSkeletonBinding = dataclasses.field(
        default_factory=YdrSkeletonBinding
    )


@dataclasses.dataclass(slots=True)
class ShaderParameterEntry:
    definition: ShaderParameterDefinition
    data_type: int
    data_pointer: int = 0
    inline_data: bytes = b""


PreparedLods = dict[YdrLod, list[PreparedModel]]
_MAX_MESH_UNIQUE_VERTICES = 65535


def coerce_texture_name(value: str | Path) -> str:
    text = str(value).strip().replace("\\", "/")
    candidate = Path(text)
    stem = candidate.stem
    return stem or candidate.name or text


def coerce_texture_input(
    value: str | Path | YdrTextureInput | None,
) -> YdrTextureInput | None:
    if value is None:
        return None
    if isinstance(value, YdrTextureInput):
        return YdrTextureInput(
            name=coerce_texture_name(value.name),
            embedded=bool(value.embedded),
            source=value.source,
        )
    return YdrTextureInput(name=coerce_texture_name(value))


def normalize_material_textures(
    textures: Mapping[str, str | Path | YdrTextureInput | None],
) -> dict[str, YdrTextureInput | None]:
    normalized: dict[str, YdrTextureInput | None] = {}
    for slot, value in textures.items():
        slot_name = str(slot).strip()
        slot_name = _TEXTURE_SLOT_ALIASES.get(slot_name.upper(), slot_name)
        normalized[slot_name] = coerce_texture_input(value)
    return normalized


def resolve_shader(
    shader_value: str, render_bucket: int, shader_library: ShaderLibrary
) -> tuple[ShaderDefinition, str, int]:
    return resolve_shader_reference(shader_value, render_bucket, shader_library)


def normalize_materials(
    materials: Sequence[YdrMaterialInput] | None,
    *,
    shader: str | YdrShader | YdrGen9Shader,
    material_textures: Mapping[str, str | Path | YdrTextureInput | None] | None,
) -> list[YdrMaterialInput]:
    if materials is not None and material_textures is not None:
        raise ValueError("Pass either materials= or material_textures=, not both")
    if materials is not None:
        return [
            YdrMaterialInput(
                name=material.name,
                shader=material.shader,
                layout_shader=material.layout_shader,
                textures=dict(material.textures),
                parameters=dict(material.parameters),
                render_bucket=int(material.render_bucket),
                gen9_definition=material.gen9_definition,
            )
            for material in materials
        ]

    default_textures: dict[str, str | Path | YdrTextureInput | None] = {}
    if material_textures is not None:
        default_textures.update(dict(material_textures))
    return [YdrMaterialInput(name="default", shader=shader, textures=default_textures)]


def _semantic_enum(name: str) -> VertexSemantic:
    key = name.upper()
    return VertexSemantic[_SEMANTIC_ALIASES.get(key, key)]


def _component_size(component_type: VertexComponentType) -> int:
    size = COMPONENT_SIZES.get(int(component_type))
    if size is None:
        raise ValueError(f"Unsupported vertex component type: {component_type}")
    if size <= 0 and component_type is not VertexComponentType.NOTHING:
        raise ValueError(
            f"Unsupported zero-sized vertex component type: {component_type}"
        )
    return size


def _canonical_component_type(
    semantic: VertexSemantic,
    component_type: VertexComponentType | None = None,
) -> VertexComponentType:
    if component_type is None:
        mapped = _CANONICAL_COMPONENT_TYPES.get(semantic)
        if mapped is None:
            raise ValueError(f"Unsupported vertex semantic: {semantic}")
        return mapped
    if (
        semantic is VertexSemantic.BLEND_INDICES
        and component_type is VertexComponentType.UBYTE4
    ):
        return VertexComponentType.COLOUR
    return component_type


def _semantics_from_flags_types(
    flags: int, types_value: int
) -> list[tuple[VertexSemantic, VertexComponentType]]:
    semantics: list[tuple[VertexSemantic, VertexComponentType]] = []
    for semantic_index in range(16):
        if ((int(flags) >> semantic_index) & 0x1) == 0:
            continue
        component_type = VertexComponentType(
            (int(types_value) >> (semantic_index * 4)) & 0xF
        )
        semantics.append((VertexSemantic(semantic_index), component_type))
    return semantics


def _stride_from_flags_types(flags: int, types_value: int) -> int:
    return sum(
        _component_size(component_type)
        for _semantic, component_type in _semantics_from_flags_types(flags, types_value)
    )


def _select_layout(
    shader_definition: ShaderDefinition,
    *,
    used_uv_indices: set[int],
    skinned: bool = False,
) -> ShaderLayoutDefinition:
    for layout in shader_definition.layouts:
        semantics = {semantic.lower() for semantic in layout.semantics}
        has_blend = "blendweights" in semantics or "blendindices" in semantics
        if skinned and not has_blend:
            continue
        if not skinned and has_blend:
            continue
        if any(f"texcoord{uv_index}" not in semantics for uv_index in used_uv_indices):
            continue
        return layout
    kind = "skinned" if skinned else "static"
    raise ValueError(
        f"No supported {kind} layout found for shader '{shader_definition.name}'"
    )


def select_layout(
    shader_definition: ShaderDefinition,
    *,
    used_uv_indices: set[int],
    skinned: bool = False,
) -> ShaderLayoutDefinition:
    return _select_layout(
        shader_definition, used_uv_indices=used_uv_indices, skinned=skinned
    )


def _encode_vertex_bytes(
    semantics: Sequence[tuple[VertexSemantic, VertexComponentType]],
    positions: Sequence[Vector3],
    normals: Sequence[Vector3],
    texcoords: Sequence[Sequence[Vector2]],
    tangents: Sequence[Vector4],
    colours0: Sequence[tuple[float, float, float, float]],
    colours1: Sequence[tuple[float, float, float, float]],
    blend_weights: Sequence[tuple[float, float, float, float]] | None = None,
    blend_indices: Sequence[tuple[int, int, int, int]] | None = None,
) -> tuple[int, int, int, bytes]:
    flags = 0
    types_value = _DEFAULT_DECLARATION_TYPES
    for semantic, component_type in semantics:
        flags |= 1 << int(semantic)
        shift = int(semantic) * 4
        types_value = (types_value & ~(0xF << shift)) | (int(component_type) << shift)
    stride = _stride_from_flags_types(flags, types_value)
    component_types = dict(semantics)

    def expand(values, semantic: VertexSemantic, *, fill: float = 0.0):
        component_type = component_types.get(semantic)
        if component_type is None:
            return values
        match component_type:
            case VertexComponentType.FLOAT:
                arity = 1
            case VertexComponentType.FLOAT2 | VertexComponentType.HALF2:
                arity = 2
            case VertexComponentType.FLOAT3:
                arity = 3
            case _:
                arity = 4
        expanded = []
        for value in values:
            components = tuple(value)
            expanded.append(
                components[:arity] + (fill,) * max(0, arity - len(components))
            )
        return expanded

    positions = expand(positions, VertexSemantic.POSITION, fill=1.0)
    normals = expand(normals, VertexSemantic.NORMAL)
    tangents = expand(tangents, VertexSemantic.TANGENT)
    colours0 = expand(colours0, VertexSemantic.COLOUR0, fill=1.0)
    colours1 = expand(colours1, VertexSemantic.COLOUR1, fill=1.0)
    texcoords = [
        expand(
            channel,
            VertexSemantic(int(VertexSemantic.TEXCOORD0) + channel_index),
        )
        for channel_index, channel in enumerate(texcoords)
    ]

    packed = _native_backend._ydr_pack_vertex_buffer(
        [
            (int(semantic), int(component_type))
            for semantic, component_type in semantics
        ],
        positions,
        normals,
        texcoords,
        tangents,
        colours0,
        colours1,
        blend_weights if blend_weights else None,
        blend_indices if blend_indices else None,
    )
    return flags, types_value, stride, packed


def _encode_vertex_bytes_from_layout(
    layout: ShaderLayoutDefinition,
    positions: Sequence[Vector3],
    normals: Sequence[Vector3],
    texcoords: Sequence[Sequence[Vector2]],
    tangents: Sequence[Vector4],
    colours0: Sequence[tuple[float, float, float, float]],
    colours1: Sequence[tuple[float, float, float, float]],
    *,
    blend_weights: Sequence[tuple[float, float, float, float]] | None = None,
    blend_indices: Sequence[tuple[int, int, int, int]] | None = None,
) -> tuple[int, int, int, bytes]:
    component_by_semantic: dict[VertexSemantic, VertexComponentType] = {
        semantic: component_type
        for semantic, component_type in _CANONICAL_COMPONENT_TYPES.items()
    }
    if blend_weights:
        component_by_semantic[VertexSemantic.BLEND_WEIGHTS] = _canonical_component_type(
            VertexSemantic.BLEND_WEIGHTS
        )
    if blend_indices:
        component_by_semantic[VertexSemantic.BLEND_INDICES] = _canonical_component_type(
            VertexSemantic.BLEND_INDICES
        )
    for channel_index in range(min(8, len(texcoords))):
        if texcoords[channel_index]:
            component_by_semantic[
                VertexSemantic(int(VertexSemantic.TEXCOORD0) + channel_index)
            ] = VertexComponentType.FLOAT2

    semantics: list[tuple[VertexSemantic, VertexComponentType]] = []
    for semantic_name in layout.semantics:
        semantic = _semantic_enum(semantic_name)
        component_type = component_by_semantic.get(semantic)
        if component_type is None:
            raise ValueError(
                f"Unsupported layout semantic '{semantic_name}' for YDR builder"
            )
        semantics.append((semantic, component_type))
    semantics.sort(key=lambda item: int(item[0]))
    return _encode_vertex_bytes(
        semantics,
        positions,
        normals,
        texcoords,
        tangents,
        colours0,
        colours1,
        blend_weights=blend_weights,
        blend_indices=blend_indices,
    )


def _encode_vertex_bytes_from_declaration(
    flags: int,
    types_value: int,
    positions: Sequence[Vector3],
    normals: Sequence[Vector3],
    texcoords: Sequence[Sequence[Vector2]],
    tangents: Sequence[Vector4],
    colours0: Sequence[tuple[float, float, float, float]],
    colours1: Sequence[tuple[float, float, float, float]],
    *,
    blend_weights: Sequence[tuple[float, float, float, float]] | None = None,
    blend_indices: Sequence[tuple[int, int, int, int]] | None = None,
) -> tuple[int, int, int, bytes]:
    semantics = [
        (semantic, _canonical_component_type(semantic, component_type))
        for semantic, component_type in _semantics_from_flags_types(flags, types_value)
    ]
    return _encode_vertex_bytes(
        semantics,
        positions,
        normals,
        texcoords,
        tangents,
        colours0,
        colours1,
        blend_weights=blend_weights,
        blend_indices=blend_indices,
    )


def compute_bounds(
    positions: Sequence[Vector3],
) -> tuple[Vector3, Vector3, Vector3, float]:
    if not positions:
        zero = Vector3()
        return zero, zero, zero, 0.0
    bounds = Aabb3.from_points(positions)
    centre = bounds.center
    radius = sphere_radius_from_points(centre, positions)
    return centre, bounds.minimum, bounds.maximum, radius


def compute_model_collection_bounds(
    models: Sequence[PreparedModel],
    *,
    skeleton: YdrSkeleton | None = None,
) -> tuple[Vector3, Vector3, Vector3, float]:
    absolute_transforms = skeleton_absolute_transforms(skeleton)
    position_groups = []
    for model in models:
        transform = None
        binding = model.skeleton_binding
        if (
            absolute_transforms
            and not binding.is_skinned
            and 0 <= int(binding.bone_index) < len(absolute_transforms)
        ):
            transform = absolute_transforms[int(binding.bone_index)]
        for mesh in model.meshes:
            if not mesh.positions:
                continue
            position_groups.append(
                mesh.positions
                if transform is None
                else [
                    _transform_position(position, transform)
                    for position in mesh.positions
                ]
            )
    if not position_groups:
        return compute_bounds(())
    mesh_bounds = [Aabb3.from_points(positions) for positions in position_groups]
    bounds = mesh_bounds[0]
    for mesh_bounds_value in mesh_bounds[1:]:
        bounds = bounds.merged(mesh_bounds_value)
    bb_min = bounds.minimum
    bb_max = bounds.maximum
    centre = bounds.center
    radius = max(
        sphere_radius_from_points(centre, positions) for positions in position_groups
    )
    return centre, bb_min, bb_max, radius


def _transform_position(
    position: Vector3,
    matrix: Matrix4,
) -> Vector3:
    return Vector3(
        position.x * matrix[0][0] + position.y * matrix[1][0] + position.z * matrix[2][0] + matrix[3][0],
        position.x * matrix[0][1] + position.y * matrix[1][1] + position.z * matrix[2][1] + matrix[3][1],
        position.x * matrix[0][2] + position.y * matrix[1][2] + position.z * matrix[2][2] + matrix[3][2],
    )


def _copy_vertex_channel(
    channel: Sequence[T] | None, vertex_indices: Sequence[int]
) -> list[T] | None:
    if channel is None:
        return None
    return [channel[index] for index in vertex_indices]


def _copy_texcoord_channels(
    channels: Sequence[Sequence[Vector2]] | None,
    vertex_indices: Sequence[int],
) -> list[list[Vector2]] | None:
    if channels is None:
        return None
    return [[channel[index] for index in vertex_indices] for channel in channels]


def _build_split_mesh(
    mesh: YdrMeshInput, vertex_indices: Sequence[int], remapped_indices: Sequence[int]
) -> YdrMeshInput:
    return YdrMeshInput(
        positions=[mesh.positions[index] for index in vertex_indices],
        indices=list(remapped_indices),
        material=mesh.material,
        normals=_copy_vertex_channel(mesh.normals, vertex_indices),
        texcoords=_copy_texcoord_channels(mesh.texcoords, vertex_indices),
        tangents=_copy_vertex_channel(mesh.tangents, vertex_indices),
        colours0=_copy_vertex_channel(mesh.colours0, vertex_indices),
        colours1=_copy_vertex_channel(mesh.colours1, vertex_indices),
        blend_weights=_copy_vertex_channel(mesh.blend_weights, vertex_indices),
        blend_indices=_copy_vertex_channel(mesh.blend_indices, vertex_indices),
        bone_ids=list(mesh.bone_ids) if mesh.bone_ids is not None else None,
        vertex_buffer_flags=int(mesh.vertex_buffer_flags),
        declaration_flags=mesh.declaration_flags,
        declaration_types=mesh.declaration_types,
    )


def _split_mesh_by_vertex_limit(
    mesh: YdrMeshInput, *, max_vertices: int = _MAX_MESH_UNIQUE_VERTICES
) -> list[YdrMeshInput]:
    indices = triangle_array(mesh.indices, len(mesh.positions)).reshape(-1).tolist()
    normalized = dataclasses.replace(mesh, indices=indices)
    if not indices:
        return [normalized]
    chunks = _native_backend._ydr_split_mesh_indices(
        indices,
        len(mesh.positions),
        max_vertices,
    )
    if chunks is None:
        return [normalized]
    return [
        _build_split_mesh(normalized, vertex_indices, remapped_indices)
        for vertex_indices, remapped_indices in chunks
    ]


def _prepare_meshes(
    meshes: Sequence[YdrMeshInput],
    prepared_materials: Sequence[PreparedMaterial],
    material_lookup: Mapping[str, int],
    *,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
    skeleton=None,
) -> list[PreparedMesh]:
    prepared: list[PreparedMesh] = []
    for source_mesh in meshes:
        for mesh in _split_mesh_by_vertex_limit(source_mesh):
            material_key = mesh.material.lower()
            if material_key not in material_lookup:
                raise ValueError(f"Mesh references unknown material '{mesh.material}'")
            material = prepared_materials[material_lookup[material_key]]

            positions = list(mesh.positions)
            indices = [int(index) for index in mesh.indices]
            normals = (
                list(mesh.normals)
                if mesh.normals is not None
                else []
            )
            texcoords = [
                list(channel)
                for channel in (mesh.texcoords or [])
            ]
            tangents = (
                list(mesh.tangents)
                if mesh.tangents is not None
                else []
            )
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
            bone_ids = (
                [int(b) for b in mesh.bone_ids] if mesh.bone_ids is not None else []
            )
            skinned = bool(blend_weights)

            if skinned:
                if not blend_indices:
                    raise ValueError("Mesh has blend_weights but no blend_indices")
                if len(blend_weights) != len(positions):
                    raise ValueError(
                        "Mesh blend_weights length must match positions length"
                    )
                if len(blend_indices) != len(positions):
                    raise ValueError(
                        "Mesh blend_indices length must match positions length"
                    )
                if skeleton is not None and getattr(skeleton, "bones", None):
                    bone_count = len(skeleton.bones)
                    if bone_count > 255:
                        raise ValueError(
                            "Skinned YDR models currently support at most 255 bones per skeleton"
                        )
                    source_palette = (
                        list(bone_ids) if bone_ids else list(range(bone_count))
                    )
                    resolved_palette = [
                        _resolve_palette_bone_index(bone_id, skeleton)
                        for bone_id in source_palette
                    ]
                    remapped_indices: list[tuple[int, int, int, int]] = []
                    for vertex_indices, vertex_weights in zip(
                        blend_indices, blend_weights, strict=True
                    ):
                        remapped: list[int] = []
                        for palette_index, weight in zip(
                            vertex_indices, vertex_weights, strict=True
                        ):
                            index = int(palette_index)
                            if float(weight) <= 0.0:
                                remapped.append(0)
                                continue
                            if index < 0 or index >= len(resolved_palette):
                                raise ValueError(
                                    f"Vertex blend index {index} is outside the mesh bone palette"
                                )
                            remapped.append(int(resolved_palette[index]))
                        remapped_indices.append(
                            (remapped[0], remapped[1], remapped[2], remapped[3])
                        )
                    blend_indices = remapped_indices
                    bone_ids = list(range(bone_count))

            if not normals:
                normals = (
                    generate_vertex_normals(positions, indices)
                    if generate_normals
                    else [Vector3(0.0, 0.0, 1.0)] * len(positions)
                )
            if len(normals) != len(positions):
                raise ValueError("Mesh normals length must match positions length")

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
            layout = _select_layout(
                material.shader_definition,
                used_uv_indices=used_uv_indices,
                skinned=skinned,
            )
            expected_semantics = {semantic.lower() for semantic in layout.semantics}
            if (
                mesh.declaration_flags is not None
                and mesh.declaration_types is not None
            ):
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
            if colours0 and len(colours0) != len(positions):
                raise ValueError("Mesh colours0 length must match positions length")
            if colours1 and len(colours1) != len(positions):
                raise ValueError("Mesh colours1 length must match positions length")

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
                if len(texcoords[uv_index]) != len(positions):
                    raise ValueError(
                        f"Mesh UV channel {uv_index} length must match positions length"
                    )

            for channel_index, channel in enumerate(texcoords):
                if channel and len(channel) != len(positions):
                    raise ValueError(
                        f"Mesh UV channel {channel_index} length must match positions length"
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

            if (
                mesh.declaration_flags is not None
                and mesh.declaration_types is not None
            ):
                flags, types_value, stride, vertex_bytes = (
                    _encode_vertex_bytes_from_declaration(
                        int(mesh.declaration_flags),
                        int(mesh.declaration_types),
                        positions,
                        normals,
                        texcoords,
                        tangents,
                        colours0,
                        colours1,
                        blend_weights=blend_weights or None,
                        blend_indices=blend_indices or None,
                    )
                )
            else:
                flags, types_value, stride, vertex_bytes = (
                    _encode_vertex_bytes_from_layout(
                        layout,
                        positions,
                        normals,
                        texcoords,
                        tangents,
                        colours0,
                        colours1,
                        blend_weights=blend_weights or None,
                        blend_indices=blend_indices or None,
                    )
                )
            if max(indices, default=0) > 0xFFFF:
                raise ValueError(
                    "YDR writer currently supports at most 65535 unique vertices per mesh"
                )
            index_bytes = struct.pack(f"<{len(indices)}H", *indices) if indices else b""

            prepared.append(
                PreparedMesh(
                    positions=positions,
                    indices=indices,
                    material_index=material.index,
                    normals=normals,
                    texcoords=texcoords,
                    tangents=tangents,
                    colours0=colours0,
                    colours1=colours1,
                    blend_weights=blend_weights,
                    blend_indices=blend_indices,
                    bone_ids=bone_ids,
                    declaration_flags=flags,
                    declaration_types=types_value,
                    vertex_stride=stride,
                    vertex_buffer_flags=int(mesh.vertex_buffer_flags),
                    vertex_bytes=vertex_bytes,
                    index_bytes=index_bytes,
                    layout=layout,
                )
            )
    return prepared


def prepare_meshes(*args, **kwargs):
    return _prepare_meshes(*args, **kwargs)


def _resolve_palette_bone_index(raw_bone_id: int, skeleton) -> int:
    bone_id = int(raw_bone_id)
    bone_count = len(skeleton.bones)
    if 0 <= bone_id < bone_count:
        return bone_id
    bone = skeleton.get_bone_by_tag(bone_id)
    if bone is None:
        raise ValueError(f"Mesh skin references unknown skeleton bone id/tag {bone_id}")
    return int(bone.index)


def _normalize_skinned_model_palette(model: PreparedModel, skeleton) -> None:
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
    prepare_materials,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
) -> tuple[list[PreparedMaterial], PreparedLods]:
    prepared_materials, material_lookup = prepare_materials(
        source.materials,
        shader_library,
        prepared_material_cls=PreparedMaterial,
        normalize_material_textures=normalize_material_textures,
        resolve_shader=resolve_shader,
    )
    prepared_lods: PreparedLods = {}
    normalized = normalize_lods(source)
    for lod_name in LOD_ORDER:
        normalized_models = normalized.get(lod_name)
        if not normalized_models:
            continue
        prepared_models: list[PreparedModel] = []
        for model in normalized_models:
            prepared_meshes = _prepare_meshes(
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


__all__ = [
    "PreparedLods",
    "PreparedMaterial",
    "PreparedMesh",
    "PreparedModel",
    "ShaderParameterEntry",
    "compute_bounds",
    "compute_model_collection_bounds",
    "default_root_render_mask_flags",
    "drawable_name",
    "normalize_lods",
    "normalize_material_textures",
    "normalize_materials",
    "prepare_build",
    "prepare_meshes",
    "resolve_shader",
    "select_layout",
]
