from __future__ import annotations

from ..defs import COMPONENT_SIZES, VertexComponentType, VertexSemantic
from ..shaders import ShaderDefinition, ShaderLayoutDefinition

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

_CANONICAL_COMPONENT_TYPES: dict[VertexSemantic, VertexComponentType] = {
    VertexSemantic.POSITION: VertexComponentType.FLOAT3,
    VertexSemantic.BLEND_WEIGHTS: VertexComponentType.COLOUR,
    VertexSemantic.BLEND_INDICES: VertexComponentType.COLOUR,
    VertexSemantic.NORMAL: VertexComponentType.FLOAT3,
    VertexSemantic.COLOUR0: VertexComponentType.COLOUR,
    VertexSemantic.COLOUR1: VertexComponentType.COLOUR,
    VertexSemantic.TANGENT: VertexComponentType.FLOAT4,
}


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


def select_layout(
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
