from __future__ import annotations

import dataclasses
import enum
import struct
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from ..hashing import jenk_hash
from .defs import COMPONENT_SIZES, VertexComponentType
from .gen9_shader_enums import YdrGen9Shader, coerce_gen9_shader_name

_G9_XML_PATH = Path(__file__).with_name('ShadersGen9Conversion.xml')
_G9_SHADER_PRESET_META = 0x6D657461
_G9_PARAM_MULTIPLIER = 12
_G9_SRV_VFT = 0x00000001406B77D8
_G9_TEXTURE_FLAGS = 0x00260000
_G9_TEXTURE_DIMENSION_2D = 1
_G9_TEXTURE_TILE_AUTO = 255
_G9_TEXTURE_USAGE_COUNT = 1
_G9_TEXTURE_BLOCK_UNKNOWN_44 = 0
_G9_VERTEX_BUFFER_BIND_FLAGS = 0x00580409
_G9_VERTEX_BUFFER_BIND_FLAGS_SKINNED = 0x00586409
_G9_INDEX_BUFFER_BIND_FLAGS = 0x0058020A
_G9_UNKNOWN0 = 0
_G9_UNKNOWN1 = 1


class ShaderParamTypeG9(enum.IntEnum):
    TEXTURE = 0
    UNKNOWN = 1
    SAMPLER = 2
    CBUFFER = 3


class ShaderResourceViewDimensionG9(enum.IntEnum):
    TEXTURE_2D = 0x41
    TEXTURE_2D_ARRAY = 0x61
    TEXTURE_CUBE = 0x82
    TEXTURE_3D = 0xA3
    BUFFER = 0x14


@dataclasses.dataclass(slots=True, frozen=True)
class ShaderGen9ParameterDefinition:
    name: str
    kind: str
    index: int = 0
    legacy_name: str | None = None
    sampler_value: int | None = None
    buffer_index: int | None = None
    param_offset: int | None = None
    param_length: int | None = None

    @property
    def kind_enum(self) -> ShaderParamTypeG9:
        lowered = self.kind.strip().lower()
        if lowered == 'texture':
            return ShaderParamTypeG9.TEXTURE
        if lowered == 'unknown':
            return ShaderParamTypeG9.UNKNOWN
        if lowered == 'sampler':
            return ShaderParamTypeG9.SAMPLER
        if lowered == 'cbuffer':
            return ShaderParamTypeG9.CBUFFER
        raise ValueError(f'Unsupported Gen9 shader parameter kind {self.kind!r}')

    @property
    def name_hash(self) -> int:
        return int(jenk_hash(self.name))

    @property
    def legacy_name_hash(self) -> int:
        return int(jenk_hash(self.legacy_name)) if self.legacy_name else 0

    @property
    def candidate_names(self) -> tuple[str, ...]:
        if self.legacy_name and self.legacy_name.lower() != self.name.lower():
            return (self.name, self.legacy_name)
        return (self.name,)

    def pack_info(self) -> bytes:
        data = int(self.kind_enum) & 0x3
        if self.kind_enum is ShaderParamTypeG9.TEXTURE:
            data |= (int(self.index) & 0xFF) << 2
        elif self.kind_enum is ShaderParamTypeG9.SAMPLER:
            data |= (int(self.index) & 0xFF) << 2
        elif self.kind_enum is ShaderParamTypeG9.CBUFFER:
            data |= (int(self.buffer_index or 0) & 0x3F) << 2
            data |= (int(self.param_offset or 0) & 0xFFF) << 8
            data |= (int(self.param_length or 0) & 0xFFF) << 20
        return struct.pack('<II', self.name_hash, data & 0xFFFFFFFF)


@dataclasses.dataclass(slots=True, frozen=True)
class ShaderGen9Definition:
    name: str
    file_name: str
    buffer_sizes: tuple[int, ...]
    parameters: tuple[ShaderGen9ParameterDefinition, ...]
    _by_name: dict[str, ShaderGen9ParameterDefinition] = dataclasses.field(init=False, repr=False)
    _by_hash: dict[int, ShaderGen9ParameterDefinition] = dataclasses.field(init=False, repr=False)
    _by_legacy_name: dict[str, ShaderGen9ParameterDefinition] = dataclasses.field(init=False, repr=False)
    _by_legacy_hash: dict[int, ShaderGen9ParameterDefinition] = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, '_by_name', {parameter.name.lower(): parameter for parameter in self.parameters})
        object.__setattr__(self, '_by_hash', {parameter.name_hash: parameter for parameter in self.parameters})
        object.__setattr__(self, '_by_legacy_name', {
            parameter.legacy_name.lower(): parameter
            for parameter in self.parameters
            if parameter.legacy_name
        })
        object.__setattr__(self, '_by_legacy_hash', {
            parameter.legacy_name_hash: parameter
            for parameter in self.parameters
            if parameter.legacy_name_hash
        })

    @property
    def name_hash(self) -> int:
        return int(jenk_hash(self.name))

    @property
    def file_name_hash(self) -> int:
        return int(jenk_hash(self.file_name))

    @property
    def num_buffers(self) -> int:
        return len(self.buffer_sizes)

    @property
    def texture_parameters(self) -> tuple[ShaderGen9ParameterDefinition, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.kind_enum is ShaderParamTypeG9.TEXTURE)

    @property
    def sampler_parameters(self) -> tuple[ShaderGen9ParameterDefinition, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.kind_enum is ShaderParamTypeG9.SAMPLER)

    @property
    def cbuffer_parameters(self) -> tuple[ShaderGen9ParameterDefinition, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.kind_enum is ShaderParamTypeG9.CBUFFER)

    @property
    def unknown_parameters(self) -> tuple[ShaderGen9ParameterDefinition, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.kind_enum is ShaderParamTypeG9.UNKNOWN)

    @property
    def texture_count(self) -> int:
        return len(self.texture_parameters)

    @property
    def sampler_count(self) -> int:
        return len(self.sampler_parameters)

    @property
    def unknown_count(self) -> int:
        return len(self.unknown_parameters)

    def get_parameter(self, value: str | int) -> ShaderGen9ParameterDefinition | None:
        if isinstance(value, str):
            lowered = value.lower()
            return self._by_name.get(lowered) or self._by_legacy_name.get(lowered)
        hash_value = int(value)
        return self._by_hash.get(hash_value) or self._by_legacy_hash.get(hash_value)

    def require_parameter(self, value: str | int) -> ShaderGen9ParameterDefinition:
        parameter = self.get_parameter(value)
        if parameter is None:
            raise ValueError(f"Unknown YDR Gen9 shader parameter '{value}' for shader '{self.name}'")
        return parameter


@dataclasses.dataclass(slots=True)
class ShaderGen9Library:
    shaders: tuple[ShaderGen9Definition, ...]
    _by_name: dict[str, ShaderGen9Definition] = dataclasses.field(init=False, repr=False)
    _by_file_name: dict[str, ShaderGen9Definition] = dataclasses.field(init=False, repr=False)
    _by_hash: dict[int, ShaderGen9Definition] = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._by_name = {shader.name.lower(): shader for shader in self.shaders}
        self._by_file_name = {shader.file_name.lower(): shader for shader in self.shaders}
        self._by_hash = {}
        for shader in self.shaders:
            self._by_hash[shader.name_hash] = shader
            self._by_hash[shader.file_name_hash] = shader

    def get_shader(self, value: str | int | YdrGen9Shader) -> ShaderGen9Definition | None:
        if isinstance(value, str):
            lowered = value.lower()
            return self._by_name.get(lowered) or self._by_file_name.get(lowered)
        return self._by_hash.get(int(value))

    def require_shader(self, value: str | int | YdrGen9Shader) -> ShaderGen9Definition:
        shader = self.get_shader(value)
        if shader is None:
            raise ValueError(f"Unknown YDR Gen9 shader '{value}'")
        return shader


def resolve_gen9_shader_reference(
    shader_value: str | YdrGen9Shader,
    shader_library: ShaderGen9Library,
) -> tuple[ShaderGen9Definition, str]:
    shader_name = coerce_gen9_shader_name(shader_value)
    shader_definition = shader_library.require_shader(shader_name)
    return shader_definition, shader_definition.file_name


def _parse_shader_parameter(node: ET.Element) -> ShaderGen9ParameterDefinition:
    kind = str(node.attrib.get('type') or '').strip()
    return ShaderGen9ParameterDefinition(
        name=str(node.attrib.get('name') or '').strip(),
        kind=kind,
        index=int(node.attrib.get('index') or 0),
        legacy_name=(str(node.attrib.get('old')).strip() or None) if node.attrib.get('old') is not None else None,
        sampler_value=int(node.attrib.get('sampler')) if node.attrib.get('sampler') is not None else None,
        buffer_index=int(node.attrib.get('buffer')) if node.attrib.get('buffer') is not None else None,
        param_offset=int(node.attrib.get('offset')) if node.attrib.get('offset') is not None else None,
        param_length=int(node.attrib.get('length')) if node.attrib.get('length') is not None else None,
    )


def read_gen9_shader_library(path: str | Path | None = None) -> ShaderGen9Library:
    xml_path = Path(path) if path is not None else _G9_XML_PATH
    root = ET.fromstring(xml_path.read_text(encoding='utf-8'))
    shaders: list[ShaderGen9Definition] = []
    for item in root.findall('Item'):
        name = str(item.findtext('Name') or '').strip()
        file_name = str(item.findtext('FileName') or '').strip()
        buffer_sizes_text = str(item.findtext('BufferSizes') or '').strip()
        if buffer_sizes_text:
            buffer_sizes = tuple(int(part) for part in re.split(r'[\s,]+', buffer_sizes_text) if part.strip())
        else:
            buffer_sizes = ()
        parameters_node = item.find('Parameters')
        parameters = tuple(_parse_shader_parameter(node) for node in parameters_node.findall('Item')) if parameters_node is not None else ()
        shaders.append(ShaderGen9Definition(name=name, file_name=file_name, buffer_sizes=buffer_sizes, parameters=parameters))
    return ShaderGen9Library(tuple(shaders))


_GEN9_SHADER_LIBRARY: ShaderGen9Library | None = None


def load_gen9_shader_library(*, reload: bool = False) -> ShaderGen9Library:
    global _GEN9_SHADER_LIBRARY
    if reload or _GEN9_SHADER_LIBRARY is None:
        _GEN9_SHADER_LIBRARY = read_gen9_shader_library()
    return _GEN9_SHADER_LIBRARY


_G9_TO_LEGACY_COMPONENT_INDEX = {
    0: 0,
    4: 3,
    8: 14,
    16: 1,
    20: 2,
    24: 4,
    25: 5,
    28: 6,
    29: 7,
    30: 8,
    31: 9,
    32: 10,
    33: 11,
    34: 12,
    35: 13,
}
_LEGACY_TO_G9_COMPONENT_INDEX = {legacy: g9 for g9, legacy in _G9_TO_LEGACY_COMPONENT_INDEX.items()}


class VertexDeclarationG9ElementFormat(int):
    NONE = 0
    R32G32B32A32_FLOAT = 2
    R32G32B32_FLOAT = 6
    R16G16B16A16_FLOAT = 10
    R32G32_TYPELESS = 16
    D3DX_R10G10B10A2 = 24
    R8G8B8A8_UNORM = 28
    R8G8B8A8_UINT = 30
    R16G16_FLOAT = 34


def get_gen9_component_type(legacy_component_index: int, declaration_types: int) -> int:
    if legacy_component_index == 1:
        return VertexDeclarationG9ElementFormat.R8G8B8A8_UNORM
    if legacy_component_index == 2:
        return VertexDeclarationG9ElementFormat.R8G8B8A8_UINT
    component_type = VertexComponentType((int(declaration_types) >> (legacy_component_index * 4)) & 0xF)
    if component_type is VertexComponentType.HALF2:
        return VertexDeclarationG9ElementFormat.R16G16_FLOAT
    if component_type is VertexComponentType.HALF4:
        return VertexDeclarationG9ElementFormat.R16G16B16A16_FLOAT
    if component_type is VertexComponentType.FLOAT2:
        return VertexDeclarationG9ElementFormat.R32G32_TYPELESS
    if component_type is VertexComponentType.FLOAT3:
        return VertexDeclarationG9ElementFormat.R32G32B32_FLOAT
    if component_type is VertexComponentType.FLOAT4:
        return VertexDeclarationG9ElementFormat.R32G32B32A32_FLOAT
    if component_type is VertexComponentType.UBYTE4:
        return VertexDeclarationG9ElementFormat.R8G8B8A8_UINT
    if component_type in {VertexComponentType.COLOUR, VertexComponentType.RGBA8_SNORM}:
        return VertexDeclarationG9ElementFormat.R8G8B8A8_UNORM
    return VertexDeclarationG9ElementFormat.NONE


def get_legacy_component_type_from_gen9(format_value: int) -> VertexComponentType:
    format_id = int(format_value)
    if format_id == VertexDeclarationG9ElementFormat.R32G32B32_FLOAT:
        return VertexComponentType.FLOAT3
    if format_id == VertexDeclarationG9ElementFormat.R32G32B32A32_FLOAT:
        return VertexComponentType.FLOAT4
    if format_id == VertexDeclarationG9ElementFormat.R8G8B8A8_UNORM:
        return VertexComponentType.COLOUR
    if format_id == VertexDeclarationG9ElementFormat.R8G8B8A8_UINT:
        return VertexComponentType.UBYTE4
    if format_id == VertexDeclarationG9ElementFormat.R32G32_TYPELESS:
        return VertexComponentType.FLOAT2
    if format_id == VertexDeclarationG9ElementFormat.R16G16_FLOAT:
        return VertexComponentType.HALF2
    if format_id == VertexDeclarationG9ElementFormat.R16G16B16A16_FLOAT:
        return VertexComponentType.HALF4
    return VertexComponentType.FLOAT4


def build_gen9_vertex_declaration(declaration_flags: int, declaration_types: int, vertex_stride: int, vertex_count: int) -> bytes:
    offsets = [0] * 52
    sizes = [0] * 52
    types = [0] * 52
    offset = 0
    for index in range(52):
        offsets[index] = offset
        legacy_index = _G9_TO_LEGACY_COMPONENT_INDEX.get(index, -1)
        if legacy_index < 0:
            continue
        if ((int(declaration_flags) >> legacy_index) & 0x1) == 0:
            continue
        component_type = VertexComponentType((int(declaration_types) >> (legacy_index * 4)) & 0xF)
        offset += COMPONENT_SIZES.get(int(component_type), 0)
        sizes[index] = int(vertex_stride) & 0xFF
        types[index] = int(get_gen9_component_type(legacy_index, declaration_types)) & 0xFF
    data = ((int(vertex_stride) & 0xFF) << 2) | ((int(vertex_count) & 0x3FFFFF) << 10)
    parts = [
        b''.join(int(value).to_bytes(4, 'little', signed=False) for value in offsets),
        bytes(sizes),
        bytes(types),
        int(data).to_bytes(8, 'little', signed=False),
    ]
    return b''.join(parts)


def decode_gen9_vertex_declaration(data: bytes, offset: int = 0) -> tuple[int, int, int, int]:
    offsets_size = 52 * 4
    offsets_end = offset + offsets_size
    sizes_end = offsets_end + 52
    types_end = sizes_end + 52
    data_end = types_end + 8
    if data_end > len(data):
        raise ValueError('Gen9 vertex declaration is truncated')
    type_values = data[sizes_end:types_end]
    packed = int.from_bytes(data[types_end:data_end], 'little', signed=False)
    vertex_stride = (packed >> 2) & 0xFF
    vertex_count = (packed >> 10) & 0x3FFFFF
    flags = 0
    declaration_types = 0
    for g9_index, type_value in enumerate(type_values):
        if not type_value:
            continue
        legacy_index = _G9_TO_LEGACY_COMPONENT_INDEX.get(g9_index)
        if legacy_index is None:
            continue
        flags |= 1 << legacy_index
        declaration_types |= int(get_legacy_component_type_from_gen9(type_value)) << (legacy_index * 4)
    return flags, declaration_types, vertex_stride, vertex_count


def build_shader_resource_view_g9(
    *,
    dimension: ShaderResourceViewDimensionG9,
    vft: int = _G9_SRV_VFT,
    unknown_08h: int = 0,
    unknown_12h: int = 0xFFFF,
    unknown_14h: int = 0xFFFFFFFF,
    unknown_18h: int = 0,
) -> bytes:
    return struct.pack(
        '<QQHHIQ',
        int(vft),
        int(unknown_08h),
        int(dimension),
        int(unknown_12h) & 0xFFFF,
        int(unknown_14h) & 0xFFFFFFFF,
        int(unknown_18h),
    )


def build_shader_param_infos_g9(shader: ShaderGen9Definition, *, multiplier: int = _G9_PARAM_MULTIPLIER) -> bytes:
    parts = [
        struct.pack(
            '<8B',
            int(shader.num_buffers) & 0xFF,
            int(shader.texture_count) & 0xFF,
            int(shader.unknown_count) & 0xFF,
            int(shader.sampler_count) & 0xFF,
            len(shader.parameters) & 0xFF,
            int(_G9_UNKNOWN0) & 0xFF,
            int(_G9_UNKNOWN1) & 0xFF,
            int(multiplier) & 0xFF,
        )
    ]
    parts.extend(parameter.pack_info() for parameter in shader.parameters)
    return b''.join(parts)


__all__ = [
    'ShaderGen9Definition',
    'ShaderGen9Library',
    'ShaderGen9ParameterDefinition',
    'ShaderParamTypeG9',
    'ShaderResourceViewDimensionG9',
    'VertexDeclarationG9ElementFormat',
    '_G9_INDEX_BUFFER_BIND_FLAGS',
    '_G9_PARAM_MULTIPLIER',
    '_G9_SHADER_PRESET_META',
    '_G9_SRV_VFT',
    '_G9_TEXTURE_BLOCK_UNKNOWN_44',
    '_G9_TEXTURE_DIMENSION_2D',
    '_G9_TEXTURE_FLAGS',
    '_G9_TEXTURE_TILE_AUTO',
    '_G9_TEXTURE_USAGE_COUNT',
    '_G9_UNKNOWN0',
    '_G9_UNKNOWN1',
    '_G9_VERTEX_BUFFER_BIND_FLAGS',
    '_G9_VERTEX_BUFFER_BIND_FLAGS_SKINNED',
    'build_gen9_vertex_declaration',
    'build_shader_param_infos_g9',
    'build_shader_resource_view_g9',
    'decode_gen9_vertex_declaration',
    'load_gen9_shader_library',
    'read_gen9_shader_library',
    'resolve_gen9_shader_reference',
]
