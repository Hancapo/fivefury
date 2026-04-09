from __future__ import annotations

from enum import IntEnum, StrEnum

DAT_VIRTUAL_BASE = 0x50000000
DAT_PHYSICAL_BASE = 0x60000000


class VertexComponentType(IntEnum):
    NOTHING = 0
    HALF2 = 1
    FLOAT = 2
    HALF4 = 3
    FLOAT_UNK = 4
    FLOAT2 = 5
    FLOAT3 = 6
    FLOAT4 = 7
    UBYTE4 = 8
    COLOUR = 9
    RGBA8_SNORM = 10
    UNK1 = 11
    UNK2 = 12
    UNK3 = 13
    UNK4 = 14
    UNK5 = 15


class VertexSemantic(IntEnum):
    POSITION = 0
    BLEND_WEIGHTS = 1
    BLEND_INDICES = 2
    NORMAL = 3
    COLOUR0 = 4
    COLOUR1 = 5
    TEXCOORD0 = 6
    TEXCOORD1 = 7
    TEXCOORD2 = 8
    TEXCOORD3 = 9
    TEXCOORD4 = 10
    TEXCOORD5 = 11
    TEXCOORD6 = 12
    TEXCOORD7 = 13
    TANGENT = 14
    BINORMAL = 15


class YdrLod(StrEnum):
    HIGH = "high"
    MEDIUM = "med"
    LOW = "low"
    VERY_LOW = "vlow"


class YdrRenderMask(IntEnum):
    STATIC_PROP = 227
    INTERIOR_PROP = 235
    SHELL = 239
    FULL = 255


def coerce_lod(value: "YdrLod | str") -> YdrLod:
    if isinstance(value, YdrLod):
        return value
    return YdrLod(str(value).strip().lower())


def coerce_render_mask(value: "YdrRenderMask | int") -> int:
    if isinstance(value, YdrRenderMask):
        return int(value)
    return max(0, min(255, int(value)))


LOD_ORDER = (YdrLod.HIGH, YdrLod.MEDIUM, YdrLod.LOW, YdrLod.VERY_LOW)
LOD_POINTER_OFFSETS = {
    YdrLod.HIGH: 0x40,
    YdrLod.MEDIUM: 0x48,
    YdrLod.LOW: 0x50,
    YdrLod.VERY_LOW: 0x58,
}

COMPONENT_SIZES: dict[int, int] = {
    int(VertexComponentType.NOTHING): 0,
    int(VertexComponentType.HALF2): 4,
    int(VertexComponentType.FLOAT): 4,
    int(VertexComponentType.HALF4): 8,
    int(VertexComponentType.FLOAT_UNK): 0,
    int(VertexComponentType.FLOAT2): 8,
    int(VertexComponentType.FLOAT3): 12,
    int(VertexComponentType.FLOAT4): 16,
    int(VertexComponentType.UBYTE4): 4,
    int(VertexComponentType.COLOUR): 4,
    int(VertexComponentType.RGBA8_SNORM): 4,
}


__all__ = [
    "COMPONENT_SIZES",
    "DAT_PHYSICAL_BASE",
    "DAT_VIRTUAL_BASE",
    "LOD_ORDER",
    "LOD_POINTER_OFFSETS",
    "YdrLod",
    "YdrRenderMask",
    "coerce_lod",
    "coerce_render_mask",
    "VertexComponentType",
    "VertexSemantic",
]
