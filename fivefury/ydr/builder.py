from __future__ import annotations

import dataclasses
import math
import struct
from pathlib import Path
from typing import Mapping, Sequence

from ..binary import align
from ..hashing import jenk_hash
from ..resource import build_rsc7
from .defs import DAT_PHYSICAL_BASE, DAT_VIRTUAL_BASE, LOD_POINTER_OFFSETS, VertexComponentType, VertexSemantic
from .model import YdrLight
from .shaders import ShaderDefinition, ShaderLibrary, ShaderLayoutDefinition, ShaderParameterDefinition, load_shader_library


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


@dataclasses.dataclass(slots=True)
class YdrModelInput:
    meshes: Sequence[YdrMeshInput]
    render_mask: int = 0
    flags: int = 0
    skeleton_binding: int = 0


@dataclasses.dataclass(slots=True)
class YdrBuild:
    models: list[YdrModelInput]
    materials: list[YdrMaterialInput]
    name: str = ""
    lod: str = "high"
    version: int = 165
    lights: list[YdrLight] = dataclasses.field(default_factory=list)

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
    declaration_flags: int
    declaration_types: int
    vertex_stride: int
    vertex_bytes: bytes
    index_bytes: bytes
    layout: ShaderLayoutDefinition


@dataclasses.dataclass(slots=True)
class _PreparedModel:
    meshes: list[_PreparedMesh]
    render_mask: int = 0
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


class _SystemWriter:
    def __init__(self, initial_size: int = 0x80):
        self.data = bytearray(initial_size)
        self.cursor = align(initial_size, 16)

    def ensure(self, size: int) -> None:
        if size > len(self.data):
            self.data.extend(b"\x00" * (size - len(self.data)))

    def alloc(self, size: int, alignment: int = 16) -> int:
        offset = align(self.cursor, alignment)
        end = offset + size
        self.ensure(end)
        self.cursor = end
        return offset

    def write(self, offset: int, value: bytes) -> None:
        self.ensure(offset + len(value))
        self.data[offset : offset + len(value)] = value

    def pack_into(self, fmt: str, offset: int, *values: object) -> None:
        size = struct.calcsize("<" + fmt)
        self.ensure(offset + size)
        struct.pack_into("<" + fmt, self.data, offset, *values)

    def c_string(self, value: str) -> int:
        encoded = value.encode("ascii", errors="ignore") + b"\x00"
        offset = self.alloc(len(encoded), 8)
        self.write(offset, encoded)
        return offset

    def finish(self) -> bytes:
        return bytes(self.data[: self.cursor])


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


def _write_lights(system: _SystemWriter, lights: Sequence[YdrLight]) -> int:
    if not lights:
        return 0
    lights_block_off = system.alloc(len(lights) * 0xA8, 16)
    for index, light in enumerate(lights):
        light_off = lights_block_off + (index * 0xA8)
        system.pack_into("I", light_off + 0x00, int(light.unknown_0h))
        system.pack_into("I", light_off + 0x04, int(light.unknown_4h))
        system.pack_into("3f", light_off + 0x08, *light.position)
        system.pack_into("I", light_off + 0x14, int(light.unknown_14h))
        system.write(light_off + 0x18, bytes((int(light.color[0]) & 0xFF, int(light.color[1]) & 0xFF, int(light.color[2]) & 0xFF)))
        system.write(light_off + 0x1B, bytes((int(light.flashiness) & 0xFF,)))
        system.pack_into("f", light_off + 0x1C, float(light.intensity))
        system.pack_into("I", light_off + 0x20, int(light.flags))
        system.pack_into("H", light_off + 0x24, int(light.bone_id) & 0xFFFF)
        system.write(light_off + 0x26, bytes((int(light.light_type) & 0xFF, int(light.group_id) & 0xFF)))
        system.pack_into("I", light_off + 0x28, int(light.time_flags))
        system.pack_into("f", light_off + 0x2C, float(light.falloff))
        system.pack_into("f", light_off + 0x30, float(light.falloff_exponent))
        system.pack_into("3f", light_off + 0x34, *light.culling_plane_normal)
        system.pack_into("f", light_off + 0x40, float(light.culling_plane_offset))
        system.write(light_off + 0x44, bytes((int(light.shadow_blur) & 0xFF, int(light.unknown_45h) & 0xFF)))
        system.pack_into("H", light_off + 0x46, int(light.unknown_46h) & 0xFFFF)
        system.pack_into("I", light_off + 0x48, int(light.unknown_48h))
        system.pack_into("f", light_off + 0x4C, float(light.volume_intensity))
        system.pack_into("f", light_off + 0x50, float(light.volume_size_scale))
        system.write(
            light_off + 0x54,
            bytes(
                (
                    int(light.volume_outer_color[0]) & 0xFF,
                    int(light.volume_outer_color[1]) & 0xFF,
                    int(light.volume_outer_color[2]) & 0xFF,
                    int(light.light_hash) & 0xFF,
                )
            ),
        )
        system.pack_into("f", light_off + 0x58, float(light.volume_outer_intensity))
        system.pack_into("f", light_off + 0x5C, float(light.corona_size))
        system.pack_into("f", light_off + 0x60, float(light.volume_outer_exponent))
        system.write(
            light_off + 0x64,
            bytes(
                (
                    int(light.light_fade_distance) & 0xFF,
                    int(light.shadow_fade_distance) & 0xFF,
                    int(light.specular_fade_distance) & 0xFF,
                    int(light.volumetric_fade_distance) & 0xFF,
                )
            ),
        )
        system.pack_into("f", light_off + 0x68, float(light.shadow_near_clip))
        system.pack_into("f", light_off + 0x6C, float(light.corona_intensity))
        system.pack_into("f", light_off + 0x70, float(light.corona_z_bias))
        system.pack_into("3f", light_off + 0x74, *light.direction)
        system.pack_into("3f", light_off + 0x80, *light.tangent)
        system.pack_into("f", light_off + 0x8C, float(light.cone_inner_angle))
        system.pack_into("f", light_off + 0x90, float(light.cone_outer_angle))
        system.pack_into("3f", light_off + 0x94, *light.extent)
        system.pack_into("I", light_off + 0xA0, int(light.projected_texture_hash))
        system.pack_into("I", light_off + 0xA4, int(light.unknown_a4h))
    return lights_block_off


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


def _semantic_enum(name: str) -> VertexSemantic:
    return VertexSemantic[name.upper()]


def _select_layout(shader_definition: ShaderDefinition, *, used_uv_indices: set[int]) -> ShaderLayoutDefinition:
    for layout in shader_definition.layouts:
        semantics = {semantic.lower() for semantic in layout.semantics}
        if "blendweights" in semantics or "blendindices" in semantics:
            continue
        if any(f"texcoord{uv_index}" not in semantics for uv_index in used_uv_indices):
            continue
        return layout
    raise ValueError(f"No supported static layout found for shader '{shader_definition.name}'")


def _encode_vertex_bytes(
    layout: ShaderLayoutDefinition,
    positions: Sequence[tuple[float, float, float]],
    normals: Sequence[tuple[float, float, float]],
    texcoords: Sequence[Sequence[tuple[float, float]]],
    tangents: Sequence[tuple[float, float, float, float]],
    colours0: Sequence[tuple[float, float, float, float]],
    colours1: Sequence[tuple[float, float, float, float]],
) -> tuple[int, int, int, bytes]:
    component_by_semantic: dict[VertexSemantic, VertexComponentType] = {
        VertexSemantic.POSITION: VertexComponentType.FLOAT3,
        VertexSemantic.NORMAL: VertexComponentType.FLOAT3,
        VertexSemantic.COLOUR0: VertexComponentType.COLOUR,
        VertexSemantic.COLOUR1: VertexComponentType.COLOUR,
        VertexSemantic.TANGENT: VertexComponentType.FLOAT4,
    }
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
        types_value |= int(component_type) << (int(semantic) * 4)
        if component_type is VertexComponentType.FLOAT3:
            stride += 12
        elif component_type is VertexComponentType.FLOAT2:
            stride += 8
        elif component_type is VertexComponentType.FLOAT4:
            stride += 16
        elif component_type is VertexComponentType.COLOUR:
            stride += 4
        else:
            raise ValueError(f"Unsupported vertex component type: {component_type}")

    chunks = bytearray()
    for vertex_index in range(len(positions)):
        for semantic, _component_type in semantics:
            if semantic is VertexSemantic.POSITION:
                chunks.extend(struct.pack("<3f", *positions[vertex_index]))
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


def _compute_bounds(meshes: Sequence[_PreparedMesh]) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]:
    all_positions = [position for mesh in meshes for position in mesh.positions]
    if not all_positions:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0
    xs = [position[0] for position in all_positions]
    ys = [position[1] for position in all_positions]
    zs = [position[2] for position in all_positions]
    bounds_min = (min(xs), min(ys), min(zs))
    bounds_max = (max(xs), max(ys), max(zs))
    center = (
        (bounds_min[0] + bounds_max[0]) * 0.5,
        (bounds_min[1] + bounds_max[1]) * 0.5,
        (bounds_min[2] + bounds_max[2]) * 0.5,
    )
    radius = max(math.dist(center, position) for position in all_positions)
    return center, bounds_min, bounds_max, radius


def _mesh_bounds(positions: Sequence[tuple[float, float, float]]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if not positions:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    xs = [position[0] for position in positions]
    ys = [position[1] for position in positions]
    zs = [position[2] for position in positions]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


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


def _normalize_parameter_key(value: str) -> str:
    return str(value).strip().lower()


def _coerce_parameter_inline(value: float | tuple[float, ...] | int | str) -> bytes:
    if isinstance(value, str):
        raise ValueError("String shader parameters are not supported by the YDR builder yet")
    if isinstance(value, (int, float)):
        components = [float(value), 0.0, 0.0, 0.0]
    else:
        components = [float(component) for component in value]
        if not components or len(components) > 4:
            raise ValueError("Shader parameter tuples must have between 1 and 4 components")
        while len(components) < 4:
            components.append(0.0)
    return struct.pack("<4f", *components)


def _prepare_materials(materials: Sequence[YdrMaterialInput], shader_library: ShaderLibrary) -> tuple[list[_PreparedMaterial], dict[str, int]]:
    prepared: list[_PreparedMaterial] = []
    index_by_name: dict[str, int] = {}
    for index, material in enumerate(materials):
        key = material.name.lower()
        if key in index_by_name:
            raise ValueError(f"Duplicate YDR material name '{material.name}'")
        shader_definition, shader_file_name = _resolve_shader(material.shader, int(material.render_bucket), shader_library)
        normalized_textures = _normalize_material_textures(material.textures)
        valid_texture_slots = {parameter.name.lower(): parameter for parameter in shader_definition.texture_parameters}
        for slot_name in normalized_textures:
            if slot_name.lower() not in valid_texture_slots:
                raise ValueError(
                    f"Material '{material.name}' uses texture slot '{slot_name}' which is not defined by shader '{shader_file_name}'"
                )
        prepared.append(
            _PreparedMaterial(
                index=index,
                name=material.name,
                shader_definition=shader_definition,
                shader_file_name=shader_file_name,
                render_bucket=int(material.render_bucket),
                textures=normalized_textures,
                parameters={str(name): value for name, value in material.parameters.items()},
            )
        )
        index_by_name[key] = index
    return prepared, index_by_name

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
        layout = _select_layout(material.shader_definition, used_uv_indices=used_uv_indices)
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
    lights: Sequence[YdrLight] | None = None,
    name: str = "",
    lod: str = "high",
    version: int = 165,
) -> YdrBuild:
    normalized_materials = _normalize_materials(materials, shader=shader, textures=textures, texture=texture)
    return YdrBuild(
        models=[YdrModelInput(meshes=list(meshes))],
        materials=normalized_materials,
        name=name,
        lod=lod.lower(),
        version=int(version),
        lights=list(lights or []),
    )


def _drawable_name(source_name: str) -> str:
    base = source_name.strip() or "drawable"
    if base.lower().endswith('.#dr'):
        return base
    return f"{base}.#dr"


def _build_parameter_entries(material: _PreparedMaterial, system: _SystemWriter) -> list[_ShaderParameterEntry]:
    texture_slots = {slot.lower(): texture for slot, texture in material.textures.items()}
    numeric_params = {_normalize_parameter_key(name): value for name, value in material.parameters.items()}
    entries: list[_ShaderParameterEntry] = []
    for definition in material.shader_definition.parameters:
        key = definition.name.lower()
        if definition.is_texture:
            texture_input = texture_slots.get(key)
            if texture_input is None:
                continue
            texture_name_off = system.c_string(texture_input.name)
            texture_base_off = system.alloc(0x50, 16)
            system.pack_into('I', texture_base_off + 0x00, _TEXTURE_BASE_VFT)
            system.pack_into('I', texture_base_off + 0x04, 1)
            system.pack_into('Q', texture_base_off + 0x28, _virtual(texture_name_off))
            system.pack_into('H', texture_base_off + 0x30, 1)
            system.pack_into('H', texture_base_off + 0x32, 2)
            entries.append(_ShaderParameterEntry(definition=definition, data_type=0, data_pointer=_virtual(texture_base_off)))
            continue
        if key not in numeric_params:
            continue
        entries.append(
            _ShaderParameterEntry(
                definition=definition,
                data_type=1,
                inline_data=_coerce_parameter_inline(numeric_params[key]),
            )
        )
    return entries


def _write_shader_parameters_block(system: _SystemWriter, material: _PreparedMaterial) -> tuple[int, int, int, int, int]:
    entries = _build_parameter_entries(material, system)
    if not entries:
        return 0, 0, 0, 0, 0

    inline_size = sum(len(entry.inline_data) for entry in entries)
    parameter_count = len(entries)
    parameter_size = (parameter_count * 16) + inline_size
    parameter_data_size = align(32 + parameter_size + (parameter_count * 4), 16)
    params_off = system.alloc(parameter_data_size, 16)

    inline_off = params_off + (parameter_count * 16)
    for index, entry in enumerate(entries):
        entry_off = params_off + (index * 16)
        system.data[entry_off] = entry.data_type & 0xFF
        if entry.data_type == 0:
            system.pack_into('Q', entry_off + 0x08, entry.data_pointer)
        else:
            system.write(inline_off, entry.inline_data)
            system.pack_into('Q', entry_off + 0x08, _virtual(inline_off))
            inline_off += len(entry.inline_data)

    hashes_off = params_off + parameter_size
    for index, entry in enumerate(entries):
        system.pack_into('I', hashes_off + (index * 4), entry.definition.name_hash)

    texture_count = sum(1 for entry in entries if entry.data_type == 0)
    return _virtual(params_off), parameter_count, parameter_size, parameter_data_size, texture_count

def _write_shader_blocks(system: _SystemWriter, materials: Sequence[_PreparedMaterial]) -> tuple[int, int]:
    shader_group_off = system.alloc(0x40, 16)
    shader_ptrs_off = system.alloc(len(materials) * 8, 8) if materials else 0
    if materials:
        system.pack_into('Q', shader_group_off + 0x10, _virtual(shader_ptrs_off))
        system.pack_into('H', shader_group_off + 0x18, len(materials))
        system.pack_into('H', shader_group_off + 0x1A, len(materials))
    system.pack_into('I', shader_group_off + 0x00, _SHADER_GROUP_VFT)
    system.pack_into('I', shader_group_off + 0x04, 1)
    system.pack_into('I', shader_group_off + 0x30, 4)

    for material in materials:
        shader_off = system.alloc(0x30, 16)
        if shader_ptrs_off:
            system.pack_into('Q', shader_ptrs_off + (material.index * 8), _virtual(shader_off))
        params_pointer, parameter_count, parameter_size, parameter_data_size, texture_param_count = _write_shader_parameters_block(system, material)
        system.pack_into('Q', shader_off + 0x00, params_pointer)
        system.pack_into('I', shader_off + 0x08, material.shader_definition.name_hash)
        system.pack_into('I', shader_off + 0x0C, 0)
        system.data[shader_off + 0x10] = parameter_count & 0xFF
        system.data[shader_off + 0x11] = material.render_bucket & 0xFF
        system.pack_into('H', shader_off + 0x12, 0x8000)
        system.pack_into('H', shader_off + 0x14, parameter_size)
        system.pack_into('H', shader_off + 0x16, parameter_data_size)
        system.pack_into('I', shader_off + 0x18, int(jenk_hash(material.shader_file_name)))
        system.pack_into('I', shader_off + 0x1C, 0)
        system.pack_into('I', shader_off + 0x20, ((1 << material.render_bucket) | 0xFF00) & 0xFFFFFFFF)
        system.pack_into('H', shader_off + 0x24, 0)
        system.data[shader_off + 0x26] = 0
        system.data[shader_off + 0x27] = texture_param_count & 0xFF
    return shader_group_off, 4


def _build_mesh_blocks(system: _SystemWriter, graphics: _GraphicsWriter, meshes: Sequence[_PreparedMesh]) -> list[_MeshBlock]:
    blocks: list[_MeshBlock] = []
    for mesh in meshes:
        decl_off = system.alloc(0x10, 16)
        system.pack_into('I', decl_off + 0x00, mesh.declaration_flags)
        system.pack_into('H', decl_off + 0x04, mesh.vertex_stride)
        system.data[decl_off + 0x06] = 0
        system.data[decl_off + 0x07] = max(1, len(mesh.layout.semantics))
        system.pack_into('Q', decl_off + 0x08, mesh.declaration_types)

        vertex_data_off = graphics.alloc(mesh.vertex_bytes, alignment=16)
        index_data_off = system.alloc(len(mesh.index_bytes), 16) if mesh.index_bytes else 0
        if index_data_off:
            system.write(index_data_off, mesh.index_bytes)

        vertex_buffer_off = system.alloc(0x80, 16)
        system.pack_into('I', vertex_buffer_off + 0x00, _VERTEX_BUFFER_VFT)
        system.pack_into('I', vertex_buffer_off + 0x04, 1)
        system.pack_into('H', vertex_buffer_off + 0x08, mesh.vertex_stride)
        system.pack_into('H', vertex_buffer_off + 0x0A, 0)
        system.pack_into('I', vertex_buffer_off + 0x0C, 0)
        system.pack_into('Q', vertex_buffer_off + 0x10, _physical(vertex_data_off))
        system.pack_into('I', vertex_buffer_off + 0x18, len(mesh.positions))
        system.pack_into('I', vertex_buffer_off + 0x1C, 0)
        system.pack_into('Q', vertex_buffer_off + 0x20, _physical(vertex_data_off))
        system.pack_into('Q', vertex_buffer_off + 0x30, _virtual(decl_off))

        index_buffer_off = system.alloc(0x60, 16)
        system.pack_into('I', index_buffer_off + 0x00, _INDEX_BUFFER_VFT)
        system.pack_into('I', index_buffer_off + 0x04, 1)
        system.pack_into('I', index_buffer_off + 0x08, len(mesh.indices))
        system.pack_into('I', index_buffer_off + 0x0C, 0)
        system.pack_into('Q', index_buffer_off + 0x10, _virtual(index_data_off) if index_data_off else 0)

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
        struct.pack_into('<Q', geometry_bytes, 0x68, 0)
        struct.pack_into('<H', geometry_bytes, 0x70, mesh.vertex_stride)
        struct.pack_into('<H', geometry_bytes, 0x72, 0)
        struct.pack_into('<I', geometry_bytes, 0x74, 0)
        struct.pack_into('<Q', geometry_bytes, 0x78, _physical(vertex_data_off))

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


def _write_pages_info(system: _SystemWriter, page_counts: tuple[int, int]) -> None:
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
    system = _SystemWriter(initial_size=align(_ROOT_SIZE + pages_info_len, 16))
    graphics = _GraphicsWriter()

    shader_group_off, _shader_group_blocks_size = _write_shader_blocks(system, prepared_materials)
    models_list_off = system.alloc(0x10 + (len(prepared_models) * 8), 16)
    models_ptrs_off = models_list_off + 0x10
    lights_block_off = _write_lights(system, source.lights)
    model_offsets: list[int] = []
    model_sizes: list[int] = []
    for prepared_model in prepared_models:
        mesh_blocks = _build_mesh_blocks(system, graphics, prepared_model.meshes)
        model_size = _model_block_size(len(mesh_blocks), [len(block.geometry_bytes) for block in mesh_blocks])
        model_off = system.alloc(model_size, 16)
        model_bytes = _build_model_block(model_off, mesh_blocks)
        system.write(model_off, model_bytes)
        system.pack_into('I', model_off + 0x2C, ((int(prepared_model.flags) & 0xFF) << 8) | (int(prepared_model.render_mask) & 0xFF))
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
    system.pack_into('I', 0x04, 1)
    system.pack_into('Q', 0x08, _virtual(_PAGES_INFO_OFFSET))
    system.pack_into('Q', 0x10, _virtual(shader_group_off))
    system.pack_into('Q', 0x18, 0)
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
    system.pack_into('Q', 0xC8, 0)

    return system.finish(), graphics.finish()

def _aligned_page_counts(system_size: int, graphics_size: int) -> tuple[int, int]:
    return (align(system_size, 0x200) // 0x200, align(graphics_size, 0x200) // 0x200)


def ydr_to_build(source: "Ydr", *, lod: str | None = None, name: str | None = None) -> YdrBuild:
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
    if source.lod not in LOD_POINTER_OFFSETS:
        raise ValueError(f"Unsupported YDR LOD '{source.lod}'")
    if source.lod != 'high':
        raise ValueError("YDR builder currently supports only the high LOD writer path")

    active_shader_library = shader_library if shader_library is not None else load_shader_library()
    prepared_materials, material_lookup = _prepare_materials(source.materials, active_shader_library)
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
