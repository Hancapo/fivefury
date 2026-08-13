from __future__ import annotations

from functools import lru_cache

from .types import GpuShaderLanguage, GpuSkinningBindings


def _require_language(language: GpuShaderLanguage) -> None:
    if not isinstance(language, GpuShaderLanguage):
        raise TypeError("language must be a GpuShaderLanguage")


@lru_cache(maxsize=16)
def vertex_library(
    language: GpuShaderLanguage,
    palette_binding: int,
) -> str:
    _require_language(language)
    if palette_binding < 0:
        raise ValueError("palette_binding cannot be negative")
    if language is GpuShaderLanguage.GLSL:
        return _glsl_library(palette_binding)
    return _hlsl_library(palette_binding)


@lru_cache(maxsize=32)
def compute_shader(
    language: GpuShaderLanguage,
    bindings: GpuSkinningBindings,
    has_normals: bool,
    local_size: int,
) -> str:
    _require_language(language)
    if local_size < 32 or local_size > 1024 or local_size & (local_size - 1):
        raise ValueError("local_size must be a power of two from 32 through 1024")
    if language is GpuShaderLanguage.GLSL:
        return _glsl_compute(bindings, has_normals, local_size)
    return _hlsl_compute(bindings, has_normals, local_size)


def _glsl_library(palette_binding: int) -> str:
    return f"""layout(std430, binding = {palette_binding}) readonly buffer FiveFuryBonePalette {{
    vec4 FiveFuryBones[];
}};

uvec4 FiveFuryIndices(uint packedValue) {{
    return uvec4(
        packedValue & 0xffu,
        (packedValue >> 8u) & 0xffu,
        (packedValue >> 16u) & 0xffu,
        (packedValue >> 24u) & 0xffu
    );
}}

vec3 FiveFuryBonePosition(uint bone, vec3 value) {{
    uint base = bone * 3u;
    vec4 source = vec4(value, 1.0);
    return vec3(
        dot(source, FiveFuryBones[base]),
        dot(source, FiveFuryBones[base + 1u]),
        dot(source, FiveFuryBones[base + 2u])
    );
}}

vec3 FiveFuryBoneNormal(uint bone, vec3 value) {{
    uint base = bone * 3u;
    vec4 source = vec4(value, 0.0);
    return vec3(
        dot(source, FiveFuryBones[base]),
        dot(source, FiveFuryBones[base + 1u]),
        dot(source, FiveFuryBones[base + 2u])
    );
}}

vec3 FiveFurySkinPosition(vec3 source, uvec2 packedInfluences) {{
    vec4 weights = unpackUnorm4x8(packedInfluences.y);
    if (dot(weights, vec4(1.0)) <= 1.0e-8) {{
        return source;
    }}
    uvec4 indices = FiveFuryIndices(packedInfluences.x);
    return
        FiveFuryBonePosition(indices.x, source) * weights.x +
        FiveFuryBonePosition(indices.y, source) * weights.y +
        FiveFuryBonePosition(indices.z, source) * weights.z +
        FiveFuryBonePosition(indices.w, source) * weights.w;
}}

vec3 FiveFurySkinNormal(vec3 source, uvec2 packedInfluences) {{
    vec4 weights = unpackUnorm4x8(packedInfluences.y);
    if (dot(weights, vec4(1.0)) <= 1.0e-8) {{
        return source;
    }}
    uvec4 indices = FiveFuryIndices(packedInfluences.x);
    vec3 result =
        FiveFuryBoneNormal(indices.x, source) * weights.x +
        FiveFuryBoneNormal(indices.y, source) * weights.y +
        FiveFuryBoneNormal(indices.z, source) * weights.z +
        FiveFuryBoneNormal(indices.w, source) * weights.w;
    float lengthSquared = dot(result, result);
    return lengthSquared > 1.0e-16 ? result * inversesqrt(lengthSquared) : result;
}}
"""


def _hlsl_library(palette_binding: int) -> str:
    return f"""StructuredBuffer<float4> FiveFuryBones : register(t{palette_binding});

uint4 FiveFuryIndices(uint packedValue) {{
    return uint4(
        packedValue & 0xffu,
        (packedValue >> 8u) & 0xffu,
        (packedValue >> 16u) & 0xffu,
        (packedValue >> 24u) & 0xffu
    );
}}

float4 FiveFuryWeights(uint packedValue) {{
    return float4(FiveFuryIndices(packedValue)) * (1.0 / 255.0);
}}

float3 FiveFuryBonePosition(uint bone, float3 value) {{
    uint base = bone * 3u;
    float4 source = float4(value, 1.0);
    return float3(
        dot(source, FiveFuryBones[base]),
        dot(source, FiveFuryBones[base + 1u]),
        dot(source, FiveFuryBones[base + 2u])
    );
}}

float3 FiveFuryBoneNormal(uint bone, float3 value) {{
    uint base = bone * 3u;
    float4 source = float4(value, 0.0);
    return float3(
        dot(source, FiveFuryBones[base]),
        dot(source, FiveFuryBones[base + 1u]),
        dot(source, FiveFuryBones[base + 2u])
    );
}}

float3 FiveFurySkinPosition(float3 source, uint2 packedInfluences) {{
    float4 weights = FiveFuryWeights(packedInfluences.y);
    if (dot(weights, float4(1.0, 1.0, 1.0, 1.0)) <= 1.0e-8) {{
        return source;
    }}
    uint4 indices = FiveFuryIndices(packedInfluences.x);
    return
        FiveFuryBonePosition(indices.x, source) * weights.x +
        FiveFuryBonePosition(indices.y, source) * weights.y +
        FiveFuryBonePosition(indices.z, source) * weights.z +
        FiveFuryBonePosition(indices.w, source) * weights.w;
}}

float3 FiveFurySkinNormal(float3 source, uint2 packedInfluences) {{
    float4 weights = FiveFuryWeights(packedInfluences.y);
    if (dot(weights, float4(1.0, 1.0, 1.0, 1.0)) <= 1.0e-8) {{
        return source;
    }}
    uint4 indices = FiveFuryIndices(packedInfluences.x);
    float3 result =
        FiveFuryBoneNormal(indices.x, source) * weights.x +
        FiveFuryBoneNormal(indices.y, source) * weights.y +
        FiveFuryBoneNormal(indices.z, source) * weights.z +
        FiveFuryBoneNormal(indices.w, source) * weights.w;
    float lengthSquared = dot(result, result);
    return lengthSquared > 1.0e-16 ? result * rsqrt(lengthSquared) : result;
}}
"""


def _glsl_compute(
    bindings: GpuSkinningBindings,
    has_normals: bool,
    local_size: int,
) -> str:
    normal_inputs = (
        f"""layout(std430, binding = {bindings.normals}) readonly buffer FiveFurySourceNormalBuffer {{
    float FiveFurySourceNormals[];
}};
layout(std430, binding = {bindings.output_normals}) writeonly buffer FiveFuryOutputNormalBuffer {{
    float FiveFuryOutputNormals[];
}};
"""
        if has_normals
        else ""
    )
    normal_main = (
        """    vec3 sourceNormal = vec3(
        FiveFurySourceNormals[base],
        FiveFurySourceNormals[base + 1u],
        FiveFurySourceNormals[base + 2u]
    );
    vec3 outputNormal = FiveFurySkinNormal(sourceNormal, packedInfluences);
    FiveFuryOutputNormals[base] = outputNormal.x;
    FiveFuryOutputNormals[base + 1u] = outputNormal.y;
    FiveFuryOutputNormals[base + 2u] = outputNormal.z;
"""
        if has_normals
        else ""
    )
    return f"""#version 430 core
layout(local_size_x = {local_size}) in;
layout(std430, binding = {bindings.positions}) readonly buffer FiveFurySourcePositionBuffer {{
    float FiveFurySourcePositions[];
}};
{normal_inputs}layout(std430, binding = {bindings.influences}) readonly buffer FiveFuryInfluenceBuffer {{
    uvec2 FiveFuryPackedInfluences[];
}};
layout(std430, binding = {bindings.output_positions}) writeonly buffer FiveFuryOutputPositionBuffer {{
    float FiveFuryOutputPositions[];
}};
layout(location = 0) uniform uint FiveFuryVertexCount;

{_glsl_library(bindings.palette)}
void main() {{
    uint vertex = gl_GlobalInvocationID.x;
    if (vertex >= FiveFuryVertexCount) {{
        return;
    }}
    uint base = vertex * 3u;
    vec3 sourcePosition = vec3(
        FiveFurySourcePositions[base],
        FiveFurySourcePositions[base + 1u],
        FiveFurySourcePositions[base + 2u]
    );
    uvec2 packedInfluences = FiveFuryPackedInfluences[vertex];
    vec3 outputPosition = FiveFurySkinPosition(sourcePosition, packedInfluences);
    FiveFuryOutputPositions[base] = outputPosition.x;
    FiveFuryOutputPositions[base + 1u] = outputPosition.y;
    FiveFuryOutputPositions[base + 2u] = outputPosition.z;
{normal_main}}}
"""


def _hlsl_compute(
    bindings: GpuSkinningBindings,
    has_normals: bool,
    local_size: int,
) -> str:
    normal_inputs = (
        f"""StructuredBuffer<float> FiveFurySourceNormals : register(t{bindings.normals});
RWStructuredBuffer<float> FiveFuryOutputNormals : register(u{bindings.output_normals});
"""
        if has_normals
        else ""
    )
    normal_main = (
        """    float3 sourceNormal = float3(
        FiveFurySourceNormals[base],
        FiveFurySourceNormals[base + 1u],
        FiveFurySourceNormals[base + 2u]
    );
    float3 outputNormal = FiveFurySkinNormal(sourceNormal, packedInfluences);
    FiveFuryOutputNormals[base] = outputNormal.x;
    FiveFuryOutputNormals[base + 1u] = outputNormal.y;
    FiveFuryOutputNormals[base + 2u] = outputNormal.z;
"""
        if has_normals
        else ""
    )
    return f"""StructuredBuffer<float> FiveFurySourcePositions : register(t{bindings.positions});
{normal_inputs}StructuredBuffer<uint2> FiveFuryPackedInfluences : register(t{bindings.influences});
RWStructuredBuffer<float> FiveFuryOutputPositions : register(u{bindings.output_positions});
cbuffer FiveFurySkinningConstants : register(b0) {{
    uint FiveFuryVertexCount;
}};

{_hlsl_library(bindings.palette)}
[numthreads({local_size}, 1, 1)]
void main(uint3 dispatchThread : SV_DispatchThreadID) {{
    uint vertex = dispatchThread.x;
    if (vertex >= FiveFuryVertexCount) {{
        return;
    }}
    uint base = vertex * 3u;
    float3 sourcePosition = float3(
        FiveFurySourcePositions[base],
        FiveFurySourcePositions[base + 1u],
        FiveFurySourcePositions[base + 2u]
    );
    uint2 packedInfluences = FiveFuryPackedInfluences[vertex];
    float3 outputPosition = FiveFurySkinPosition(sourcePosition, packedInfluences);
    FiveFuryOutputPositions[base] = outputPosition.x;
    FiveFuryOutputPositions[base + 1u] = outputPosition.y;
    FiveFuryOutputPositions[base + 2u] = outputPosition.z;
{normal_main}}}
"""


__all__ = ["compute_shader", "vertex_library"]
