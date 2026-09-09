from __future__ import annotations

from collections.abc import Sequence

from ... import _native as _native_backend
from ...vector import Vector2, Vector3, Vector4
from ..defs import VertexComponentType, VertexSemantic
from ..shaders import ShaderLayoutDefinition
from .layout import (
    _CANONICAL_COMPONENT_TYPES,
    _DEFAULT_DECLARATION_TYPES,
    _canonical_component_type,
    _semantic_enum,
    _semantics_from_flags_types,
    _stride_from_flags_types,
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
    position_buffer: memoryview | None = None,
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
        nominal_arity = (
            3 if semantic in (VertexSemantic.POSITION, VertexSemantic.NORMAL)
            else 4 if semantic is VertexSemantic.TANGENT
            else 2 if VertexSemantic.TEXCOORD0 <= semantic <= VertexSemantic.TEXCOORD7
            else None
        )
        if arity == nominal_arity:
            return values
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
        position_buffer
        if (
            position_buffer is not None
            and component_types.get(VertexSemantic.POSITION) == VertexComponentType.FLOAT3
        )
        else positions,
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
    position_buffer: memoryview | None = None,
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
        position_buffer=position_buffer,
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
    position_buffer: memoryview | None = None,
) -> tuple[int, int, int, bytes]:
    component_types = {
        semantic: _canonical_component_type(semantic, component_type)
        for semantic, component_type in _semantics_from_flags_types(flags, types_value)
    }
    # Decoded static declarations must not discard subsequently authored skin.
    for semantic, channel in (
        (VertexSemantic.BLEND_WEIGHTS, blend_weights),
        (VertexSemantic.BLEND_INDICES, blend_indices),
    ):
        if channel:
            component_types.setdefault(semantic, _canonical_component_type(semantic))
    return _encode_vertex_bytes(
        sorted(component_types.items()),
        positions,
        normals,
        texcoords,
        tangents,
        colours0,
        colours1,
        blend_weights=blend_weights,
        blend_indices=blend_indices,
        position_buffer=position_buffer,
    )
