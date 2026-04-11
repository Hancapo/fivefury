from __future__ import annotations

import dataclasses
import math
import struct
from pathlib import Path
from typing import Mapping, Sequence

from ..bounds import Bound, write_bound_resource
from ..binary import align
from ..resource import ResourceWriter, build_rsc7, split_rsc7_sections
from ..ytd import Ytd
from .defs import (
    DAT_PHYSICAL_BASE,
    DAT_VIRTUAL_BASE,
    LOD_POINTER_OFFSETS,
    VertexComponentType,
    VertexSemantic,
    YdrLod,
    YdrRenderMask,
    coerce_lod,
    coerce_render_mask,
)
from .model import YdrLight, YdrSkeleton
from .shaders import ShaderDefinition, ShaderLibrary, ShaderLayoutDefinition, ShaderParameterDefinition, load_shader_library
from .write_lights import write_lights
from .write_materials import prepare_materials, write_shader_blocks
from .write_skeleton import write_skeleton


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

_DRAWABLE_FILE_VFT = 0x40570C38
_SHADER_GROUP_VFT = 0x406138E0
_TEXTURE_BASE_VFT = 0x4061A8C8
_DRAWABLE_MODEL_VFT = 0x40610A78
_DRAWABLE_GEOMETRY_VFT = 0x40618868
_VERTEX_BUFFER_VFT = 0x4061D3E8
_INDEX_BUFFER_VFT = 0x406131D8
_UNKNOWN_FLOAT_SENTINEL = 0x7F800001
_ROOT_SIZE = 0xD0
_PAGES_INFO_OFFSET = 0xD0
_ENHANCED_YDR_VERSIONS = frozenset({154, 159, 171})


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
    parameters: Mapping[str, float | tuple[float, ...] | int | str] = dataclasses.field(default_factory=dict)
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


@dataclasses.dataclass(slots=True)
class YdrModelInput:
    meshes: Sequence[YdrMeshInput]
    render_mask: int | YdrRenderMask = YdrRenderMask.STATIC_PROP
    flags: int = 0
    skeleton_binding: int = 0

    def __post_init__(self) -> None:
        self.render_mask = coerce_render_mask(self.render_mask)


@dataclasses.dataclass(slots=True)
class YdrBuild:
    models: list[YdrModelInput]
    materials: list[YdrMaterialInput]
    name: str = ""
    lod: YdrLod = YdrLod.HIGH
    version: int = 165
    skeleton: YdrSkeleton | None = None
    lights: list[YdrLight] = dataclasses.field(default_factory=list)
    embedded_textures: Ytd | None = None
    bound: Bound | None = None

    def __post_init__(self) -> None:
        self.lod = coerce_lod(self.lod)

    def to_bytes(self, *, shader_library: ShaderLibrary | None = None) -> bytes:
        return build_ydr_bytes(self, shader_library=shader_library)

    def save(self, destination: str | Path, *, shader_library: ShaderLibrary | None = None) -> Path:
        return save_ydr(self, destination, shader_library=shader_library)


@dataclasses.dataclass(slots=True)
class _PreparedMaterial:
    index: int
    name: str
    shader_definition: ShaderDefinition
    shader_file_name: str
    render_bucket: int
    textures: dict[str, YdrTextureInput]
    parameters: dict[str, float | tuple[float, ...] | int | str]


@dataclasses.dataclass(slots=True)
class _PreparedMesh:
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
class _PreparedModel:
    meshes: list[_PreparedMesh]
    render_mask: int = int(YdrRenderMask.STATIC_PROP)
    flags: int = 0
    skeleton_binding: int = 0


@dataclasses.dataclass(slots=True)
class _MeshBlock:
    material_index: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    geometry_bytes: bytes


@dataclasses.dataclass(slots=True)
class _ShaderParameterEntry:
    definition: ShaderParameterDefinition
    data_type: int
    data_pointer: int = 0
    inline_data: bytes = b""


class _GraphicsWriter:
    def __init__(self):
        self.data = bytearray()

    def alloc(self, value: bytes, alignment: int = 16) -> int:
        offset = align(len(self.data), alignment)
        if offset > len(self.data):
            self.data.extend(b"\x00" * (offset - len(self.data)))
        self.data.extend(value)
        return offset

    def finish(self) -> bytes:
        return bytes(self.data)


def _virtual(offset: int) -> int:
    return DAT_VIRTUAL_BASE + int(offset)


def _physical(offset: int) -> int:
    return DAT_PHYSICAL_BASE + int(offset)


def _coerce_texture_name(value: str | Path) -> str:
    text = str(value).strip().replace("\\", "/")
    candidate = Path(text)
    stem = candidate.stem
    return stem or candidate.name or text


def _coerce_texture_input(value: str | Path | YdrTextureInput) -> YdrTextureInput:
    if isinstance(value, YdrTextureInput):
        return YdrTextureInput(name=_coerce_texture_name(value.name), embedded=bool(value.embedded), source=value.source)
    return YdrTextureInput(name=_coerce_texture_name(value))


def _normalize_material_textures(textures: Mapping[str, str | YdrTextureInput]) -> dict[str, YdrTextureInput]:
    return {str(slot): _coerce_texture_input(value) for slot, value in textures.items()}


def _resolve_shader(shader_value: str, render_bucket: int, shader_library: ShaderLibrary) -> tuple[ShaderDefinition, str]:
    shader_definition = shader_library.resolve_shader(shader_name=shader_value, shader_file_name=shader_value)
    if shader_definition is None:
        raise ValueError(f"Unknown YDR shader '{shader_value}'")
    if shader_value.lower().endswith(".sps"):
        shader_file_name = shader_value
    else:
        shader_file_name = shader_definition.pick_file_name(render_bucket)
        if shader_file_name is None:
            raise ValueError(f"Shader '{shader_definition.name}' has no file for render bucket {render_bucket}")
    return shader_definition, shader_file_name


def _normalize_materials(
    materials: Sequence[YdrMaterialInput] | None,
    *,
    shader: str,
    textures: Mapping[str, str | YdrTextureInput] | None,
    texture: str | YdrTextureInput | None,
) -> list[YdrMaterialInput]:
    if materials is not None and (textures is not None or texture is not None):
        raise ValueError("Pass either materials= or textures=/texture=, not both")
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
        default_textures.setdefault("DiffuseSampler", texture)
    return [YdrMaterialInput(name="default", shader=shader, textures=default_textures)]


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
        p0 = positions[i0]
        p1 = positions[i1]
        p2 = positions[i2]
        normal = _cross(_subtract(p1, p0), _subtract(p2, p0))
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


_SEMANTIC_ALIASES: dict[str, str] = {
    "BLENDWEIGHTS": "BLEND_WEIGHTS",
    "BLENDINDICES": "BLEND_INDICES",
}


def _semantic_enum(name: str) -> VertexSemantic:
    key = name.upper()
    return VertexSemantic[_SEMANTIC_ALIASES.get(key, key)]


def _select_layout(shader_definition: ShaderDefinition, *, used_uv_indices: set[int], skinned: bool = False) -> ShaderLayoutDefinition:
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
    raise ValueError(f"No supported {kind} layout found for shader '{shader_definition.name}'")


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
                chunks.extend(struct.pack("<3f", *positions[vertex_index]))
            elif semantic is VertexSemantic.BLEND_WEIGHTS and blend_weights:
                w = blend_weights[vertex_index]
                chunks.extend(bytes((_clamp_byte(w[0]), _clamp_byte(w[1]), _clamp_byte(w[2]), _clamp_byte(w[3]))))
            elif semantic is VertexSemantic.BLEND_INDICES and blend_indices:
                bi = blend_indices[vertex_index]
                chunks.extend(bytes((bi[0] & 0xFF, bi[1] & 0xFF, bi[2] & 0xFF, bi[3] & 0xFF)))
            elif semantic is VertexSemantic.NORMAL:
                chunks.extend(struct.pack("<3f", *normals[vertex_index]))
            elif semantic is VertexSemantic.COLOUR0:
                chunks.extend(_encode_colour(colours0[vertex_index]))
            elif semantic is VertexSemantic.COLOUR1:
                chunks.extend(_encode_colour(colours1[vertex_index]))
            elif VertexSemantic.TEXCOORD0 <= semantic <= VertexSemantic.TEXCOORD7:
                channel_index = int(semantic) - int(VertexSemantic.TEXCOORD0)
                chunks.extend(struct.pack("<2f", *texcoords[channel_index][vertex_index]))
            elif semantic is VertexSemantic.TANGENT:
                chunks.extend(struct.pack("<4f", *tangents[vertex_index]))
    return flags, types_value, stride, bytes(chunks)


def compute_bounds(
    positions: Sequence[tuple[float, float, float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]:
    """Return ``(centre, bb_min, bb_max, radius)`` for a list of positions."""
    if not positions:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    zs = [p[2] for p in positions]
    bb_min = (min(xs), min(ys), min(zs))
    bb_max = (max(xs), max(ys), max(zs))
    centre = (
        (bb_min[0] + bb_max[0]) * 0.5,
        (bb_min[1] + bb_max[1]) * 0.5,
        (bb_min[2] + bb_max[2]) * 0.5,
    )
    radius = max(math.dist(centre, p) for p in positions)
    return centre, bb_min, bb_max, radius


def _compute_bounds(meshes: Sequence[_PreparedMesh]) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]:
    return compute_bounds([p for mesh in meshes for p in mesh.positions])


def _mesh_bounds(positions: Sequence[tuple[float, float, float]]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    _, bb_min, bb_max, _ = compute_bounds(positions)
    return bb_min, bb_max


def _pack_aabb(bounds_min: tuple[float, float, float], bounds_max: tuple[float, float, float]) -> bytes:
    return struct.pack(
        "<8f",
        bounds_min[0],
        bounds_min[1],
        bounds_min[2],
        bounds_min[0],
        bounds_max[0],
        bounds_max[1],
        bounds_max[2],
        bounds_max[0],
    )


def _prepare_meshes(
    meshes: Sequence[YdrMeshInput],
    prepared_materials: Sequence[_PreparedMaterial],
    material_lookup: Mapping[str, int],
    *,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
) -> list[_PreparedMesh]:
    prepared: list[_PreparedMesh] = []
    for mesh in meshes:
        if len(mesh.indices) % 3 != 0:
            raise ValueError("YDR writer currently requires triangle list indices")
        if max(mesh.indices, default=-1) >= len(mesh.positions):
            raise ValueError("Mesh indices reference a vertex outside positions")
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
                raise ValueError("Mesh has blend_weights but no blend_indices")
            if len(blend_weights) != len(positions):
                raise ValueError("Mesh blend_weights length must match positions length")
            if len(blend_indices) != len(positions):
                raise ValueError("Mesh blend_indices length must match positions length")

        if not normals:
            if generate_normals:
                normals = _generate_normals(positions, indices)
            else:
                normals = [(0.0, 0.0, 1.0)] * len(positions)
        if len(normals) != len(positions):
            raise ValueError("Mesh normals length must match positions length")

        used_uv_indices = {
            int(parameter.uv_index or 0)
            for parameter in material.shader_definition.texture_parameters
            if parameter.name.lower() in {slot.lower() for slot in material.textures}
        }
        layout = _select_layout(material.shader_definition, used_uv_indices=used_uv_indices, skinned=skinned)
        expected_semantics = {semantic.lower() for semantic in layout.semantics}

        if fill_vertex_colours and not colours0 and "colour0" in expected_semantics:
            colours0 = [(1.0, 1.0, 1.0, 1.0)] * len(positions)
        if fill_vertex_colours and not colours1 and "colour1" in expected_semantics:
            colours1 = [(1.0, 1.0, 1.0, 1.0)] * len(positions)
        if colours0 and len(colours0) != len(positions):
            raise ValueError("Mesh colours0 length must match positions length")
        if colours1 and len(colours1) != len(positions):
            raise ValueError("Mesh colours1 length must match positions length")

        for parameter in material.shader_definition.texture_parameters:
            if parameter.name.lower() not in {slot.lower() for slot in material.textures}:
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
                raise ValueError(f"Mesh UV channel {uv_index} length must match positions length")

        if texcoords:
            for channel_index, channel in enumerate(texcoords):
                if channel and len(channel) != len(positions):
                    raise ValueError(f"Mesh UV channel {channel_index} length must match positions length")

        if "tangent" in expected_semantics:
            if not tangents and generate_tangents:
                if not texcoords or not texcoords[0]:
                    raise ValueError(f"Material '{material.name}' requires tangents but mesh has no UV0 to generate them")
                tangents = _generate_tangents(positions, normals, texcoords[0], indices)
            if len(tangents) != len(positions):
                raise ValueError("Mesh tangents length must match positions length")
        else:
            tangents = []

        if "colour0" not in expected_semantics:
            colours0 = []
        if "colour1" not in expected_semantics:
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
            raise ValueError("YDR writer currently supports at most 65535 unique vertices per mesh")
        index_bytes = struct.pack(f"<{len(indices)}H", *indices) if indices else b""

        prepared.append(
            _PreparedMesh(
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


def _normalize_models(source: YdrBuild) -> list[YdrModelInput]:
    return [
        YdrModelInput(
            meshes=list(model.meshes),
            render_mask=int(model.render_mask),
            flags=int(model.flags),
            skeleton_binding=int(model.skeleton_binding),
        )
        for model in source.models
    ]


def create_ydr(
    *,
    meshes: Sequence[YdrMeshInput],
    materials: Sequence[YdrMaterialInput] | None = None,
    shader: str = "default.sps",
    textures: Mapping[str, str | YdrTextureInput] | None = None,
    texture: str | YdrTextureInput | None = None,
    skeleton: YdrSkeleton | None = None,
    lights: Sequence[YdrLight] | None = None,
    embedded_textures: Ytd | None = None,
    bound: Bound | None = None,
    name: str = "",
    lod: YdrLod | str = YdrLod.HIGH,
    render_mask: int | YdrRenderMask = YdrRenderMask.STATIC_PROP,
    version: int = 165,
) -> YdrBuild:
    normalized_materials = _normalize_materials(materials, shader=shader, textures=textures, texture=texture)
    return YdrBuild(
        models=[YdrModelInput(meshes=list(meshes), render_mask=render_mask)],
        materials=normalized_materials,
        name=name,
        lod=coerce_lod(lod),
        version=int(version),
        skeleton=skeleton,
        lights=list(lights or []),
        embedded_textures=embedded_textures,
        bound=bound,
    )


def _drawable_name(source_name: str) -> str:
    base = source_name.strip() or "drawable"
    if base.lower().endswith('.#dr'):
        return base
    return f"{base}.#dr"


def _embedded_texture_game(source: YdrBuild) -> str:
    if source.embedded_textures is None:
        return "gta5"
    game = (source.embedded_textures.game or "").strip().lower()
    if game:
        if game == "gta5" and int(source.version) in _ENHANCED_YDR_VERSIONS:
            return "gta5_enhanced"
        return game
    return "gta5_enhanced" if int(source.version) in _ENHANCED_YDR_VERSIONS else "gta5"


def _relocate_embedded_texture_dictionary(
    virtual_data: bytes,
    *,
    dict_offset: int,
    graphics_offset: int,
    enhanced: bool,
) -> bytes:
    count = int.from_bytes(virtual_data[0x28:0x2A], "little")
    ptrs_offset = int.from_bytes(virtual_data[0x30:0x38], "little") - DAT_VIRTUAL_BASE
    output = bytearray(dict_offset + len(virtual_data))
    output[dict_offset : dict_offset + len(virtual_data)] = virtual_data
    virtual_delta = dict_offset
    physical_delta = graphics_offset

    def add_virtual_ptr(relative_offset: int) -> None:
        value = int.from_bytes(output[dict_offset + relative_offset : dict_offset + relative_offset + 8], "little")
        if value:
            output[dict_offset + relative_offset : dict_offset + relative_offset + 8] = (value + virtual_delta).to_bytes(8, "little")

    def add_physical_ptr(relative_offset: int) -> None:
        value = int.from_bytes(output[dict_offset + relative_offset : dict_offset + relative_offset + 8], "little")
        if value:
            output[dict_offset + relative_offset : dict_offset + relative_offset + 8] = (value + physical_delta).to_bytes(8, "little")

    add_virtual_ptr(0x08)
    add_virtual_ptr(0x20)
    add_virtual_ptr(0x30)

    for index in range(count):
        ptr_pos = dict_offset + ptrs_offset + (index * 8)
        tex_ptr = int.from_bytes(output[ptr_pos : ptr_pos + 8], "little")
        if not tex_ptr:
            continue
        output[ptr_pos : ptr_pos + 8] = (tex_ptr + virtual_delta).to_bytes(8, "little")
        tex_off = int.from_bytes(
            virtual_data[ptrs_offset + (index * 8) : ptrs_offset + (index * 8) + 8],
            "little",
        ) - DAT_VIRTUAL_BASE
        add_virtual_ptr(tex_off + 0x28)
        if enhanced:
            add_virtual_ptr(tex_off + 0x30)
            add_physical_ptr(tex_off + 0x38)
        else:
            add_physical_ptr(tex_off + 0x70)
    return bytes(output[dict_offset:])


def _write_embedded_texture_dictionary(system: ResourceWriter, graphics: _GraphicsWriter, source: YdrBuild) -> int:
    if source.embedded_textures is None or not source.embedded_textures.textures:
        return 0
    ytd_bytes = source.embedded_textures.to_bytes(game=_embedded_texture_game(source))
    header, virtual_data, graphics_data = split_rsc7_sections(ytd_bytes)
    dict_offset = system.alloc(len(virtual_data), 16)
    graphics_offset = graphics.alloc(graphics_data, 16) if graphics_data else 0
    enhanced = int(header.version) == 5
    relocated = _relocate_embedded_texture_dictionary(
        virtual_data,
        dict_offset=dict_offset,
        graphics_offset=graphics_offset,
        enhanced=enhanced,
    )
    system.write(dict_offset, relocated)
    return dict_offset


def _build_mesh_blocks(system: ResourceWriter, graphics: _GraphicsWriter, meshes: Sequence[_PreparedMesh]) -> list[_MeshBlock]:
    blocks: list[_MeshBlock] = []
    for mesh in meshes:
        decl_off = system.alloc(0x10, 16)
        system.pack_into('I', decl_off + 0x00, mesh.declaration_flags)
        system.pack_into('H', decl_off + 0x04, mesh.vertex_stride)
        system.data[decl_off + 0x06] = 0
        system.data[decl_off + 0x07] = max(1, len(mesh.layout.semantics))
        system.pack_into('Q', decl_off + 0x08, mesh.declaration_types)

        vertex_data_off = system.alloc(len(mesh.vertex_bytes), 16)
        system.write(vertex_data_off, mesh.vertex_bytes)
        index_data_off = system.alloc(len(mesh.index_bytes), 16) if mesh.index_bytes else 0
        if index_data_off:
            system.write(index_data_off, mesh.index_bytes)

        vertex_buffer_off = system.alloc(0x80, 16)
        system.pack_into('I', vertex_buffer_off + 0x00, _VERTEX_BUFFER_VFT)
        system.pack_into('I', vertex_buffer_off + 0x04, 1)
        system.pack_into('H', vertex_buffer_off + 0x08, mesh.vertex_stride)
        system.pack_into('H', vertex_buffer_off + 0x0A, 0)
        system.pack_into('I', vertex_buffer_off + 0x0C, 0)
        system.pack_into('Q', vertex_buffer_off + 0x10, _virtual(vertex_data_off))
        system.pack_into('I', vertex_buffer_off + 0x18, len(mesh.positions))
        system.pack_into('I', vertex_buffer_off + 0x1C, 0)
        system.pack_into('Q', vertex_buffer_off + 0x20, _virtual(vertex_data_off))
        system.pack_into('Q', vertex_buffer_off + 0x30, _virtual(decl_off))

        index_buffer_off = system.alloc(0x60, 16)
        system.pack_into('I', index_buffer_off + 0x00, _INDEX_BUFFER_VFT)
        system.pack_into('I', index_buffer_off + 0x04, 1)
        system.pack_into('I', index_buffer_off + 0x08, len(mesh.indices))
        system.pack_into('I', index_buffer_off + 0x0C, 0)
        system.pack_into('Q', index_buffer_off + 0x10, _virtual(index_data_off) if index_data_off else 0)

        bone_ids_pointer = 0
        bone_ids_count = 0
        if mesh.bone_ids:
            bone_ids_count = len(mesh.bone_ids)
            bone_ids_data = struct.pack(f"<{bone_ids_count}H", *mesh.bone_ids)
            bone_ids_off = system.alloc(len(bone_ids_data), 16)
            system.write(bone_ids_off, bone_ids_data)
            bone_ids_pointer = _virtual(bone_ids_off)

        bounds_min, bounds_max = _mesh_bounds(mesh.positions)
        geometry_bytes = bytearray(0x98)
        struct.pack_into('<I', geometry_bytes, 0x00, _DRAWABLE_GEOMETRY_VFT)
        struct.pack_into('<I', geometry_bytes, 0x04, 1)
        struct.pack_into('<Q', geometry_bytes, 0x18, _virtual(vertex_buffer_off))
        struct.pack_into('<Q', geometry_bytes, 0x38, _virtual(index_buffer_off))
        struct.pack_into('<I', geometry_bytes, 0x58, len(mesh.indices))
        struct.pack_into('<I', geometry_bytes, 0x5C, len(mesh.indices) // 3)
        struct.pack_into('<H', geometry_bytes, 0x60, len(mesh.positions))
        struct.pack_into('<H', geometry_bytes, 0x62, 3)
        struct.pack_into('<Q', geometry_bytes, 0x68, bone_ids_pointer)
        struct.pack_into('<H', geometry_bytes, 0x70, mesh.vertex_stride)
        struct.pack_into('<H', geometry_bytes, 0x72, bone_ids_count)
        struct.pack_into('<I', geometry_bytes, 0x74, 0)
        struct.pack_into('<Q', geometry_bytes, 0x78, _virtual(vertex_data_off))

        blocks.append(
            _MeshBlock(
                material_index=mesh.material_index,
                bounds_min=bounds_min,
                bounds_max=bounds_max,
                geometry_bytes=bytes(geometry_bytes),
            )
        )
    return blocks


def _model_block_size(geometry_count: int, geometry_lengths: Sequence[int]) -> int:
    offset = 0x30
    offset += geometry_count * 2
    if geometry_count == 1:
        offset += 6
    else:
        offset = align(offset, 16)
    offset += geometry_count * 8
    offset = align(offset, 16)
    bounds_count = geometry_count if geometry_count <= 1 else geometry_count + 1
    offset += bounds_count * 32
    for geometry_length in geometry_lengths:
        offset = align(offset, 16)
        offset += geometry_length
    return offset

def _build_model_block(model_off: int, mesh_blocks: Sequence[_MeshBlock]) -> bytes:
    geometry_count = len(mesh_blocks)
    geometry_lengths = [len(block.geometry_bytes) for block in mesh_blocks]
    block_size = _model_block_size(geometry_count, geometry_lengths)
    data = bytearray(block_size)

    shader_mapping_off = 0x30
    cursor = shader_mapping_off + (geometry_count * 2)
    if geometry_count == 1:
        cursor += 6
    else:
        cursor = align(cursor, 16)
    geometries_ptr_off = cursor
    cursor += geometry_count * 8
    cursor = align(cursor, 16)
    bounds_off = cursor

    bounds_chunks: list[bytes] = []
    if geometry_count > 1:
        all_positions_min = (
            min(block.bounds_min[0] for block in mesh_blocks),
            min(block.bounds_min[1] for block in mesh_blocks),
            min(block.bounds_min[2] for block in mesh_blocks),
        )
        all_positions_max = (
            max(block.bounds_max[0] for block in mesh_blocks),
            max(block.bounds_max[1] for block in mesh_blocks),
            max(block.bounds_max[2] for block in mesh_blocks),
        )
        bounds_chunks.append(_pack_aabb(all_positions_min, all_positions_max))
    for block in mesh_blocks:
        bounds_chunks.append(_pack_aabb(block.bounds_min, block.bounds_max))
    for index, chunk in enumerate(bounds_chunks):
        start = bounds_off + (index * 32)
        data[start : start + 32] = chunk
    cursor = bounds_off + (len(bounds_chunks) * 32)

    geometry_offsets: list[int] = []
    for block in mesh_blocks:
        cursor = align(cursor, 16)
        geometry_offsets.append(cursor)
        data[cursor : cursor + len(block.geometry_bytes)] = block.geometry_bytes
        cursor += len(block.geometry_bytes)

    struct.pack_into('<I', data, 0x00, _DRAWABLE_MODEL_VFT)
    struct.pack_into('<I', data, 0x04, 1)
    struct.pack_into('<Q', data, 0x08, _virtual(model_off + geometries_ptr_off))
    struct.pack_into('<H', data, 0x10, geometry_count)
    struct.pack_into('<H', data, 0x12, geometry_count)
    struct.pack_into('<I', data, 0x14, 0)
    struct.pack_into('<Q', data, 0x18, _virtual(model_off + bounds_off))
    struct.pack_into('<Q', data, 0x20, _virtual(model_off + shader_mapping_off))
    struct.pack_into('<I', data, 0x28, 0)
    struct.pack_into('<H', data, 0x2C, 0x00FF)
    struct.pack_into('<H', data, 0x2E, geometry_count)

    for index, block in enumerate(mesh_blocks):
        struct.pack_into('<H', data, shader_mapping_off + (index * 2), block.material_index)
        struct.pack_into('<Q', data, geometries_ptr_off + (index * 8), _virtual(model_off + geometry_offsets[index]))

    return bytes(data)


def _pages_info_length(page_counts: tuple[int, int]) -> int:
    return 16 + (8 * (page_counts[0] + page_counts[1]))


def _drawable_models_block_units(model_size: int) -> int:
    block_length = 16 + 8
    block_length += align(block_length, 16)
    block_length += model_size
    return int(math.ceil(block_length / 16.0))


def _drawable_models_total_units(model_sizes: Sequence[int]) -> int:
    return sum(_drawable_models_block_units(model_size) for model_size in model_sizes)


def _write_pages_info(system: ResourceWriter, page_counts: tuple[int, int]) -> None:
    pages_off = _PAGES_INFO_OFFSET
    system.pack_into('I', pages_off + 0x00, 0)
    system.pack_into('I', pages_off + 0x04, 0)
    system.data[pages_off + 0x08] = page_counts[0] & 0xFF
    system.data[pages_off + 0x09] = page_counts[1] & 0xFF
    system.pack_into('H', pages_off + 0x0A, 0)
    system.pack_into('I', pages_off + 0x0C, 0)


def _build_system_payload(
    source: YdrBuild,
    prepared_materials: Sequence[_PreparedMaterial],
    prepared_models: Sequence[_PreparedModel],
    page_counts: tuple[int, int],
) -> tuple[bytes, bytes]:
    pages_info_len = _pages_info_length(page_counts)
    system = ResourceWriter(initial_size=align(_ROOT_SIZE + pages_info_len, 16))
    graphics = _GraphicsWriter()

    shader_group_off, _shader_group_blocks_size = write_shader_blocks(
        system,
        prepared_materials,
        shader_parameter_entry_cls=_ShaderParameterEntry,
        texture_base_vft=_TEXTURE_BASE_VFT,
        shader_group_vft=_SHADER_GROUP_VFT,
        virtual=_virtual,
    )
    models_list_off = system.alloc(0x10 + (len(prepared_models) * 8), 16)
    models_ptrs_off = models_list_off + 0x10
    skeleton_off = write_skeleton(system, source.skeleton, virtual=_virtual)
    lights_block_off = write_lights(system, source.lights)
    bound_off = write_bound_resource(system, source.bound) if source.bound is not None else 0
    texture_dictionary_off = _write_embedded_texture_dictionary(system, graphics, source)
    model_offsets: list[int] = []
    model_sizes: list[int] = []
    for prepared_model in prepared_models:
        mesh_blocks = _build_mesh_blocks(system, graphics, prepared_model.meshes)
        model_size = _model_block_size(len(mesh_blocks), [len(block.geometry_bytes) for block in mesh_blocks])
        model_off = system.alloc(model_size, 16)
        model_bytes = _build_model_block(model_off, mesh_blocks)
        system.write(model_off, model_bytes)
        system.pack_into('H', model_off + 0x2C, ((int(prepared_model.flags) & 0xFF) << 8) | (int(prepared_model.render_mask) & 0xFF))
        system.pack_into('H', model_off + 0x2E, len(prepared_model.meshes))
        system.pack_into('I', model_off + 0x28, int(prepared_model.skeleton_binding))
        model_offsets.append(model_off)
        model_sizes.append(model_size)

    system.pack_into('Q', models_list_off + 0x00, _virtual(models_ptrs_off))
    system.pack_into('H', models_list_off + 0x08, len(prepared_models))
    system.pack_into('H', models_list_off + 0x0A, len(prepared_models))
    system.pack_into('I', models_list_off + 0x0C, 0)
    for index, model_off in enumerate(model_offsets):
        system.pack_into('Q', models_ptrs_off + (index * 8), _virtual(model_off))

    drawable_name_off = system.c_string(_drawable_name(source.name))

    all_meshes = [mesh for prepared_model in prepared_models for mesh in prepared_model.meshes]
    center, bounds_min, bounds_max, radius = _compute_bounds(all_meshes)
    _write_pages_info(system, page_counts)

    system.pack_into('I', 0x00, _DRAWABLE_FILE_VFT)
    system.pack_into('I', 0x04, 0x48434C41)
    system.pack_into('Q', 0x08, _virtual(_PAGES_INFO_OFFSET))
    system.pack_into('Q', 0x10, _virtual(shader_group_off))
    system.pack_into('Q', shader_group_off + 0x08, _virtual(texture_dictionary_off) if texture_dictionary_off else 0)
    system.pack_into('Q', 0x18, _virtual(skeleton_off) if skeleton_off else 0)
    system.pack_into('3f', 0x20, *center)
    system.pack_into('f', 0x2C, radius)
    system.pack_into('3f', 0x30, *bounds_min)
    system.pack_into('I', 0x3C, _UNKNOWN_FLOAT_SENTINEL)
    system.pack_into('3f', 0x40, *bounds_max)
    system.pack_into('I', 0x4C, _UNKNOWN_FLOAT_SENTINEL)
    system.pack_into('Q', 0x50, _virtual(models_list_off))
    system.pack_into('Q', 0x58, 0)
    system.pack_into('Q', 0x60, 0)
    system.pack_into('Q', 0x68, 0)
    system.pack_into('f', 0x70, 9998.0)
    system.pack_into('f', 0x74, 9998.0)
    system.pack_into('f', 0x78, 9998.0)
    system.pack_into('f', 0x7C, 9998.0)
    system.pack_into('I', 0x80, 0x0000FF01)
    system.pack_into('I', 0x84, 0)
    system.pack_into('I', 0x88, 0)
    system.pack_into('I', 0x8C, 0)
    system.pack_into('Q', 0x90, 0)
    system.pack_into('H', 0x98, 0)
    system.pack_into('H', 0x9A, _drawable_models_total_units(model_sizes))
    system.pack_into('I', 0x9C, 0)
    system.pack_into('Q', 0xA0, _virtual(models_list_off))
    system.pack_into('Q', 0xA8, _virtual(drawable_name_off))
    if lights_block_off:
        system.pack_into('Q', 0xB0, _virtual(lights_block_off))
        system.pack_into('H', 0xB8, len(source.lights))
        system.pack_into('H', 0xBA, len(source.lights))
        system.pack_into('I', 0xBC, 0)
    system.pack_into('Q', 0xC0, 0)
    system.pack_into('Q', 0xC8, _virtual(bound_off) if bound_off else 0)

    return system.finish(), graphics.finish()

def _aligned_page_counts(system_size: int, graphics_size: int) -> tuple[int, int]:
    return (align(system_size, 0x200) // 0x200, align(graphics_size, 0x200) // 0x200)


def ydr_to_build(source: "Ydr", *, lod: YdrLod | str | None = None, name: str | None = None) -> YdrBuild:
    return source.to_build(lod=lod, name=name)


def build_ydr_bytes(
    source: "YdrBuild | Ydr",
    *,
    shader_library: ShaderLibrary | None = None,
    generate_normals: bool = True,
    generate_tangents: bool = True,
    fill_vertex_colours: bool = True,
) -> bytes:
    from .model import Ydr

    if isinstance(source, Ydr):
        source = source.to_build()
    if not source.models:
        raise ValueError("YDR builder requires at least one mesh")
    source_lod = coerce_lod(source.lod)
    if source_lod not in LOD_POINTER_OFFSETS:
        raise ValueError(f"Unsupported YDR LOD '{source_lod}'")
    if source_lod is not YdrLod.HIGH:
        raise ValueError("YDR builder currently supports only the high LOD writer path")

    active_shader_library = shader_library if shader_library is not None else load_shader_library()
    prepared_materials, material_lookup = prepare_materials(
        source.materials,
        active_shader_library,
        prepared_material_cls=_PreparedMaterial,
        normalize_material_textures=_normalize_material_textures,
        resolve_shader=_resolve_shader,
    )
    normalized_models = _normalize_models(source)
    prepared_models = [
        _PreparedModel(
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

    page_counts = (0, 0)
    system_data = b''
    graphics_data = b''
    for _ in range(8):
        system_data, graphics_data = _build_system_payload(source, prepared_materials, prepared_models, page_counts)
        next_counts = _aligned_page_counts(len(system_data), len(graphics_data))
        if next_counts == page_counts:
            break
        page_counts = next_counts
    else:
        raise RuntimeError('YDR builder page-info sizing did not converge')

    return build_rsc7(
        system_data,
        version=source.version,
        graphics_data=graphics_data,
        system_alignment=0x200,
        graphics_alignment=0x200,
    )


def save_ydr(source: "YdrBuild | Ydr", destination: str | Path, *, shader_library: ShaderLibrary | None = None) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_ydr_bytes(source, shader_library=shader_library))
    return target


__all__ = [
    "YdrBuild",
    "YdrMaterialInput",
    "YdrMeshInput",
    "YdrModelInput",
    "YdrTextureInput",
    "build_ydr_bytes",
    "create_ydr",
    "save_ydr",
    "ydr_to_build",
]
