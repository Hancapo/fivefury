from __future__ import annotations

import dataclasses
import math
import struct
from pathlib import Path
from typing import Mapping, Sequence

from .build_types import YdrBuild, YdrMaterialInput, YdrMeshInput, YdrModelInput, YdrTextureInput
from .defs import LOD_ORDER, VertexComponentType, VertexSemantic, YdrLod, YdrRenderMask
from .shaders import ShaderDefinition, ShaderLayoutDefinition, ShaderLibrary, ShaderParameterDefinition

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


@dataclasses.dataclass(slots=True)
class PreparedMaterial:
    index: int
    name: str
    shader_definition: ShaderDefinition
    shader_file_name: str
    render_bucket: int
    textures: dict[str, YdrTextureInput]
    parameters: dict[str, float | tuple[float, ...] | int | str]


@dataclasses.dataclass(slots=True)
class PreparedMesh:
    positions: list[tuple[float, float, float]]
    indices: list[int]
    material_index: int
    normals: list[tuple[float, float, float]]
    texcoords: list[list[tuple[float, float]]]
    tangents: list[tuple[float, float, float, float]]
    colours0: list[tuple[float, float, float, float]]
    colours1: list[tuple[float, float, float, float]]
    blend_weights: list[tuple[float, float, float, float]]
    blend_indices: list[tuple[int, int, int, int]]
    bone_ids: list[int]
    declaration_flags: int
    declaration_types: int
    vertex_stride: int
    vertex_bytes: bytes
    index_bytes: bytes
    layout: ShaderLayoutDefinition


@dataclasses.dataclass(slots=True)
class PreparedModel:
    meshes: list[PreparedMesh]
    render_mask: int = int(YdrRenderMask.STATIC_PROP)
    flags: int = 0
    skeleton_binding: int = 0


@dataclasses.dataclass(slots=True)
class ShaderParameterEntry:
    definition: ShaderParameterDefinition
    data_type: int
    data_pointer: int = 0
    inline_data: bytes = b""


PreparedLods = dict[YdrLod, list[PreparedModel]]


def coerce_texture_name(value: str | Path) -> str:
    text = str(value).strip().replace("\\", "/")
    candidate = Path(text)
    stem = candidate.stem
    return stem or candidate.name or text


def coerce_texture_input(value: str | Path | YdrTextureInput) -> YdrTextureInput:
    if isinstance(value, YdrTextureInput):
        return YdrTextureInput(name=coerce_texture_name(value.name), embedded=bool(value.embedded), source=value.source)
    return YdrTextureInput(name=coerce_texture_name(value))


def normalize_material_textures(textures: Mapping[str, str | YdrTextureInput]) -> dict[str, YdrTextureInput]:
    return {str(slot): coerce_texture_input(value) for slot, value in textures.items()}


def resolve_shader(shader_value: str, render_bucket: int, shader_library: ShaderLibrary) -> tuple[ShaderDefinition, str]:
    shader_definition = shader_library.resolve_shader(shader_name=shader_value, shader_file_name=shader_value)
    if shader_definition is None:
        raise ValueError(f"Unknown YDR shader '{shader_value}'")
    if shader_value.lower().endswith('.sps'):
        shader_file_name = shader_value
    else:
        shader_file_name = shader_definition.pick_file_name(render_bucket)
        if shader_file_name is None:
            raise ValueError(f"Shader '{shader_definition.name}' has no file for render bucket {render_bucket}")
    return shader_definition, shader_file_name


def normalize_materials(
    materials: Sequence[YdrMaterialInput] | None,
    *,
    shader: str,
    textures: Mapping[str, str | YdrTextureInput] | None,
    texture: str | YdrTextureInput | None,
) -> list[YdrMaterialInput]:
    if materials is not None and (textures is not None or texture is not None):
        raise ValueError('Pass either materials= or textures=/texture=, not both')
    if materials is not None:
        return [
            YdrMaterialInput(
                name=material.name,
                shader=material.shader,
                textures=dict(material.textures),
                parameters=dict(material.parameters),
                render_bucket=int(material.render_bucket),
            )
            for material in materials
        ]

    default_textures: dict[str, str | YdrTextureInput] = {}
    if textures is not None:
        default_textures.update(dict(textures))
    if texture is not None:
        default_textures.setdefault('DiffuseSampler', texture)
    return [YdrMaterialInput(name='default', shader=shader, textures=default_textures)]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _subtract(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _normalize3(value: tuple[float, float, float], fallback: tuple[float, float, float] = (0.0, 0.0, 1.0)) -> tuple[float, float, float]:
    length = math.sqrt(value[0] * value[0] + value[1] * value[1] + value[2] * value[2])
    if length <= 1e-8:
        return fallback
    return (value[0] / length, value[1] / length, value[2] / length)


def _dot3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _generate_normals(positions: Sequence[tuple[float, float, float]], indices: Sequence[int]) -> list[tuple[float, float, float]]:
    accum = [[0.0, 0.0, 0.0] for _ in positions]
    for base in range(0, len(indices), 3):
        i0, i1, i2 = indices[base : base + 3]
        if i0 >= len(positions) or i1 >= len(positions) or i2 >= len(positions):
            continue
        normal = _cross(_subtract(positions[i1], positions[i0]), _subtract(positions[i2], positions[i0]))
        for index in (i0, i1, i2):
            accum[index][0] += normal[0]
            accum[index][1] += normal[1]
            accum[index][2] += normal[2]
    return [_normalize3((value[0], value[1], value[2])) for value in accum]


def _generate_tangents(
    positions: Sequence[tuple[float, float, float]],
    normals: Sequence[tuple[float, float, float]],
    texcoords: Sequence[tuple[float, float]],
    indices: Sequence[int],
) -> list[tuple[float, float, float, float]]:
    tan1 = [[0.0, 0.0, 0.0] for _ in positions]
    tan2 = [[0.0, 0.0, 0.0] for _ in positions]
    for base in range(0, len(indices), 3):
        i0, i1, i2 = indices[base : base + 3]
        if max(i0, i1, i2) >= len(positions) or max(i0, i1, i2) >= len(texcoords):
            continue
        p0, p1, p2 = positions[i0], positions[i1], positions[i2]
        uv0, uv1, uv2 = texcoords[i0], texcoords[i1], texcoords[i2]
        x1, y1, z1 = _subtract(p1, p0)
        x2, y2, z2 = _subtract(p2, p0)
        s1 = uv1[0] - uv0[0]
        t1 = uv1[1] - uv0[1]
        s2 = uv2[0] - uv0[0]
        t2 = uv2[1] - uv0[1]
        determinant = (s1 * t2) - (s2 * t1)
        if abs(determinant) <= 1e-8:
            continue
        r = 1.0 / determinant
        tangent = ((t2 * x1 - t1 * x2) * r, (t2 * y1 - t1 * y2) * r, (t2 * z1 - t1 * z2) * r)
        bitangent = ((s1 * x2 - s2 * x1) * r, (s1 * y2 - s2 * y1) * r, (s1 * z2 - s2 * z1) * r)
        for index in (i0, i1, i2):
            tan1[index][0] += tangent[0]
            tan1[index][1] += tangent[1]
            tan1[index][2] += tangent[2]
            tan2[index][0] += bitangent[0]
            tan2[index][1] += bitangent[1]
            tan2[index][2] += bitangent[2]

    tangents: list[tuple[float, float, float, float]] = []
    for index, normal in enumerate(normals):
        t = (tan1[index][0], tan1[index][1], tan1[index][2])
        projected = (
            t[0] - normal[0] * _dot3(normal, t),
            t[1] - normal[1] * _dot3(normal, t),
            t[2] - normal[2] * _dot3(normal, t),
        )
        tangent3 = _normalize3(projected, fallback=(1.0, 0.0, 0.0))
        handedness = 1.0 if _dot3(_cross(normal, tangent3), (tan2[index][0], tan2[index][1], tan2[index][2])) >= 0.0 else -1.0
        tangents.append((tangent3[0], tangent3[1], tangent3[2], handedness))
    return tangents


def _clamp_byte(value: float) -> int:
    return max(0, min(255, int(round(float(value) * 255.0))))


def _encode_colour(value: tuple[float, float, float, float]) -> bytes:
    return bytes((_clamp_byte(value[0]), _clamp_byte(value[1]), _clamp_byte(value[2]), _clamp_byte(value[3])))


def _semantic_enum(name: str) -> VertexSemantic:
    key = name.upper()
    return VertexSemantic[_SEMANTIC_ALIASES.get(key, key)]


def _select_layout(shader_definition: ShaderDefinition, *, used_uv_indices: set[int], skinned: bool = False) -> ShaderLayoutDefinition:
    for layout in shader_definition.layouts:
        semantics = {semantic.lower() for semantic in layout.semantics}
        has_blend = 'blendweights' in semantics or 'blendindices' in semantics
        if skinned and not has_blend:
            continue
        if not skinned and has_blend:
            continue
        if any(f'texcoord{uv_index}' not in semantics for uv_index in used_uv_indices):
            continue
        return layout
    kind = 'skinned' if skinned else 'static'
    raise ValueError(f"No supported {kind} layout found for shader '{shader_definition.name}'")


def select_layout(shader_definition: ShaderDefinition, *, used_uv_indices: set[int], skinned: bool = False) -> ShaderLayoutDefinition:
    return _select_layout(shader_definition, used_uv_indices=used_uv_indices, skinned=skinned)


def _encode_vertex_bytes(
    layout: ShaderLayoutDefinition,
    positions: Sequence[tuple[float, float, float]],
    normals: Sequence[tuple[float, float, float]],
    texcoords: Sequence[Sequence[tuple[float, float]]],
    tangents: Sequence[tuple[float, float, float, float]],
    colours0: Sequence[tuple[float, float, float, float]],
    colours1: Sequence[tuple[float, float, float, float]],
    blend_weights: Sequence[tuple[float, float, float, float]] | None = None,
    blend_indices: Sequence[tuple[int, int, int, int]] | None = None,
) -> tuple[int, int, int, bytes]:
    component_by_semantic: dict[VertexSemantic, VertexComponentType] = {
        VertexSemantic.POSITION: VertexComponentType.FLOAT3,
        VertexSemantic.NORMAL: VertexComponentType.FLOAT3,
        VertexSemantic.COLOUR0: VertexComponentType.COLOUR,
        VertexSemantic.COLOUR1: VertexComponentType.COLOUR,
        VertexSemantic.TANGENT: VertexComponentType.FLOAT4,
    }
    if blend_weights:
        component_by_semantic[VertexSemantic.BLEND_WEIGHTS] = VertexComponentType.COLOUR
    if blend_indices:
        component_by_semantic[VertexSemantic.BLEND_INDICES] = VertexComponentType.UBYTE4
    for channel_index in range(min(8, len(texcoords))):
        if texcoords[channel_index]:
            component_by_semantic[VertexSemantic(int(VertexSemantic.TEXCOORD0) + channel_index)] = VertexComponentType.FLOAT2

    semantics: list[tuple[VertexSemantic, VertexComponentType]] = []
    for semantic_name in layout.semantics:
        semantic = _semantic_enum(semantic_name)
        component_type = component_by_semantic.get(semantic)
        if component_type is None:
            raise ValueError(f"Unsupported layout semantic '{semantic_name}' for YDR builder")
        semantics.append((semantic, component_type))
    semantics.sort(key=lambda item: int(item[0]))

    flags = 0
    types_value = _DEFAULT_DECLARATION_TYPES
    stride = 0
    for semantic, component_type in semantics:
        flags |= 1 << int(semantic)
        shift = int(semantic) * 4
        types_value = (types_value & ~(0xF << shift)) | (int(component_type) << shift)
        if component_type is VertexComponentType.FLOAT3:
            stride += 12
        elif component_type is VertexComponentType.FLOAT2:
            stride += 8
        elif component_type is VertexComponentType.FLOAT4:
            stride += 16
        elif component_type in (VertexComponentType.COLOUR, VertexComponentType.UBYTE4):
            stride += 4
        else:
            raise ValueError(f"Unsupported vertex component type: {component_type}")

    chunks = bytearray()
    for vertex_index in range(len(positions)):
        for semantic, _component_type in semantics:
            if semantic is VertexSemantic.POSITION:
                chunks.extend(struct.pack('<3f', *positions[vertex_index]))
            elif semantic is VertexSemantic.BLEND_WEIGHTS and blend_weights:
                w = blend_weights[vertex_index]
                chunks.extend(bytes((_clamp_byte(w[0]), _clamp_byte(w[1]), _clamp_byte(w[2]), _clamp_byte(w[3]))))
            elif semantic is VertexSemantic.BLEND_INDICES and blend_indices:
                bi = blend_indices[vertex_index]
                chunks.extend(bytes((bi[0] & 0xFF, bi[1] & 0xFF, bi[2] & 0xFF, bi[3] & 0xFF)))
            elif semantic is VertexSemantic.NORMAL:
                chunks.extend(struct.pack('<3f', *normals[vertex_index]))
            elif semantic is VertexSemantic.COLOUR0:
                chunks.extend(_encode_colour(colours0[vertex_index]))
            elif semantic is VertexSemantic.COLOUR1:
                chunks.extend(_encode_colour(colours1[vertex_index]))
            elif VertexSemantic.TEXCOORD0 <= semantic <= VertexSemantic.TEXCOORD7:
                channel_index = int(semantic) - int(VertexSemantic.TEXCOORD0)
                chunks.extend(struct.pack('<2f', *texcoords[channel_index][vertex_index]))
            elif semantic is VertexSemantic.TANGENT:
                chunks.extend(struct.pack('<4f', *tangents[vertex_index]))
    return flags, types_value, stride, bytes(chunks)


def compute_bounds(positions: Sequence[tuple[float, float, float]]) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]:
    if not positions:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    zs = [p[2] for p in positions]
    bb_min = (min(xs), min(ys), min(zs))
    bb_max = (max(xs), max(ys), max(zs))
    centre = ((bb_min[0] + bb_max[0]) * 0.5, (bb_min[1] + bb_max[1]) * 0.5, (bb_min[2] + bb_max[2]) * 0.5)
    radius = max(math.dist(centre, p) for p in positions)
    return centre, bb_min, bb_max, radius


def compute_model_collection_bounds(models: Sequence[PreparedModel]) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]:
    positions = [vertex for model in models for mesh in model.meshes for vertex in mesh.positions]
    return compute_bounds(positions)


def _prepare_meshes(
    meshes: Sequence[YdrMeshInput],
    prepared_materials: Sequence[PreparedMaterial],
    material_lookup: Mapping[str, int],
    *,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
) -> list[PreparedMesh]:
    prepared: list[PreparedMesh] = []
    for mesh in meshes:
        if len(mesh.indices) % 3 != 0:
            raise ValueError('YDR writer currently requires triangle list indices')
        if max(mesh.indices, default=-1) >= len(mesh.positions):
            raise ValueError('Mesh indices reference a vertex outside positions')
        material_key = mesh.material.lower()
        if material_key not in material_lookup:
            raise ValueError(f"Mesh references unknown material '{mesh.material}'")
        material = prepared_materials[material_lookup[material_key]]

        positions = [tuple(map(float, position)) for position in mesh.positions]
        indices = [int(index) for index in mesh.indices]
        normals = [tuple(map(float, normal)) for normal in mesh.normals] if mesh.normals is not None else []
        texcoords = [[(float(u), float(v)) for u, v in channel] for channel in (mesh.texcoords or [])]
        tangents = [tuple(map(float, tangent)) for tangent in mesh.tangents] if mesh.tangents is not None else []
        colours0 = [tuple(map(float, colour)) for colour in mesh.colours0] if mesh.colours0 is not None else []
        colours1 = [tuple(map(float, colour)) for colour in mesh.colours1] if mesh.colours1 is not None else []
        blend_weights = [tuple(map(float, w)) for w in mesh.blend_weights] if mesh.blend_weights is not None else []
        blend_indices = [tuple(map(int, bi)) for bi in mesh.blend_indices] if mesh.blend_indices is not None else []
        bone_ids = [int(b) for b in mesh.bone_ids] if mesh.bone_ids is not None else []
        skinned = bool(blend_weights)

        if skinned:
            if not blend_indices:
                raise ValueError('Mesh has blend_weights but no blend_indices')
            if len(blend_weights) != len(positions):
                raise ValueError('Mesh blend_weights length must match positions length')
            if len(blend_indices) != len(positions):
                raise ValueError('Mesh blend_indices length must match positions length')

        if not normals:
            normals = _generate_normals(positions, indices) if generate_normals else [(0.0, 0.0, 1.0)] * len(positions)
        if len(normals) != len(positions):
            raise ValueError('Mesh normals length must match positions length')

        material_texture_slots = {slot.lower() for slot in material.textures}
        used_uv_indices = {
            int(parameter.uv_index or 0)
            for parameter in material.shader_definition.texture_parameters
            if parameter.name.lower() in material_texture_slots
        }
        layout = _select_layout(material.shader_definition, used_uv_indices=used_uv_indices, skinned=skinned)
        expected_semantics = {semantic.lower() for semantic in layout.semantics}

        if fill_vertex_colours and not colours0 and 'colour0' in expected_semantics:
            colours0 = [(1.0, 1.0, 1.0, 1.0)] * len(positions)
        if fill_vertex_colours and not colours1 and 'colour1' in expected_semantics:
            colours1 = [(1.0, 1.0, 1.0, 1.0)] * len(positions)
        if colours0 and len(colours0) != len(positions):
            raise ValueError('Mesh colours0 length must match positions length')
        if colours1 and len(colours1) != len(positions):
            raise ValueError('Mesh colours1 length must match positions length')

        for parameter in material.shader_definition.texture_parameters:
            if parameter.name.lower() not in material_texture_slots:
                continue
            uv_index = int(parameter.uv_index or 0)
            semantic_name = f'texcoord{uv_index}'
            if semantic_name not in expected_semantics:
                raise ValueError(
                    f"Shader layout for material '{material.name}' does not expose {semantic_name} required by slot '{parameter.name}'"
                )
            if uv_index >= len(texcoords) or not texcoords[uv_index]:
                raise ValueError(
                    f"Mesh for material '{material.name}' is missing UV channel {uv_index} required by slot '{parameter.name}'"
                )
            if len(texcoords[uv_index]) != len(positions):
                raise ValueError(f'Mesh UV channel {uv_index} length must match positions length')

        for channel_index, channel in enumerate(texcoords):
            if channel and len(channel) != len(positions):
                raise ValueError(f'Mesh UV channel {channel_index} length must match positions length')

        if 'tangent' in expected_semantics:
            if not tangents and generate_tangents:
                if not texcoords or not texcoords[0]:
                    raise ValueError(f"Material '{material.name}' requires tangents but mesh has no UV0 to generate them")
                tangents = _generate_tangents(positions, normals, texcoords[0], indices)
            if len(tangents) != len(positions):
                raise ValueError('Mesh tangents length must match positions length')
        else:
            tangents = []

        if 'colour0' not in expected_semantics:
            colours0 = []
        if 'colour1' not in expected_semantics:
            colours1 = []

        flags, types_value, stride, vertex_bytes = _encode_vertex_bytes(
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
        if max(indices, default=0) > 0xFFFF:
            raise ValueError('YDR writer currently supports at most 65535 unique vertices per mesh')
        index_bytes = struct.pack(f'<{len(indices)}H', *indices) if indices else b''

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
                vertex_bytes=vertex_bytes,
                index_bytes=index_bytes,
                layout=layout,
            )
        )
    return prepared


def prepare_meshes(*args, **kwargs):
    return _prepare_meshes(*args, **kwargs)


def normalize_lods(source: YdrBuild) -> dict[YdrLod, list[YdrModelInput]]:
    normalized: dict[YdrLod, list[YdrModelInput]] = {}
    for lod_name in YdrLod:
        models = source.lods.get(lod_name)
        if not models:
            continue
        normalized[lod_name] = [
            YdrModelInput(
                meshes=list(model.meshes),
                render_mask=int(model.render_mask),
                flags=int(model.flags),
                skeleton_binding=int(model.skeleton_binding),
            )
            for model in models
        ]
    return normalized


def default_root_render_mask_flags(models: Sequence[PreparedModel]) -> int:
    render_mask = 0
    flags = 0
    for model in models:
        render_mask |= int(model.render_mask) & 0xFF
        flags |= int(model.flags) & 0xFF
    return ((render_mask & 0xFF) << 8) | (flags & 0xFF)


def drawable_name(source_name: str) -> str:
    base = source_name.strip() or 'drawable'
    return base if base.lower().endswith('.#dr') else f'{base}.#dr'


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
        prepared_lods[lod_name] = [
            PreparedModel(
                meshes=_prepare_meshes(
                    model.meshes,
                    prepared_materials,
                    material_lookup,
                    generate_normals=generate_normals,
                    generate_tangents=generate_tangents,
                    fill_vertex_colours=fill_vertex_colours,
                ),
                render_mask=int(model.render_mask),
                flags=int(model.flags),
                skeleton_binding=int(model.skeleton_binding),
            )
            for model in normalized_models
        ]
    return prepared_materials, prepared_lods


__all__ = [
    'PreparedLods',
    'PreparedMaterial',
    'PreparedMesh',
    'PreparedModel',
    'ShaderParameterEntry',
    'compute_bounds',
    'compute_model_collection_bounds',
    'default_root_render_mask_flags',
    'drawable_name',
    'normalize_lods',
    'normalize_material_textures',
    'normalize_materials',
    'prepare_build',
    'prepare_meshes',
    'resolve_shader',
    'select_layout',
]
