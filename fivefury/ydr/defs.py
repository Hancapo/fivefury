from __future__ import annotations

import dataclasses
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


@dataclasses.dataclass(slots=True)
class YdrSkeletonBinding:
    unknown_1: int = 0
    has_skin: int = 0
    unknown_2: int = 0
    bone_index: int = 0

    @classmethod
    def from_int(cls, value: int) -> "YdrSkeletonBinding":
        raw = int(value) & 0xFFFFFFFF
        return cls(
            unknown_1=raw & 0xFF,
            has_skin=(raw >> 8) & 0xFF,
            unknown_2=(raw >> 16) & 0xFF,
            bone_index=(raw >> 24) & 0xFF,
        )

    @classmethod
    def skinned(
        cls,
        *,
        bone_index: int = 0,
        unknown_1: int = 0x11,
        unknown_2: int = 0,
    ) -> "YdrSkeletonBinding":
        return cls(
            unknown_1=int(unknown_1) & 0xFF,
            has_skin=1,
            unknown_2=int(unknown_2) & 0xFF,
            bone_index=int(bone_index) & 0xFF,
        )

    @classmethod
    def rigid(
        cls,
        *,
        bone_index: int = 0,
        unknown_1: int = 0,
        unknown_2: int = 0,
    ) -> "YdrSkeletonBinding":
        return cls(
            unknown_1=int(unknown_1) & 0xFF,
            has_skin=0,
            unknown_2=int(unknown_2) & 0xFF,
            bone_index=int(bone_index) & 0xFF,
        )

    @property
    def is_skinned(self) -> bool:
        return bool(self.has_skin)

    def to_int(self) -> int:
        return (
            (int(self.unknown_1) & 0xFF)
            | ((int(self.has_skin) & 0xFF) << 8)
            | ((int(self.unknown_2) & 0xFF) << 16)
            | ((int(self.bone_index) & 0xFF) << 24)
        )

    def __int__(self) -> int:
        return self.to_int()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return int(self) == (int(other) & 0xFFFFFFFF)
        if isinstance(other, YdrSkeletonBinding):
            return (
                int(self.unknown_1) == int(other.unknown_1)
                and int(self.has_skin) == int(other.has_skin)
                and int(self.unknown_2) == int(other.unknown_2)
                and int(self.bone_index) == int(other.bone_index)
            )
        return NotImplemented


def coerce_skeleton_binding(value: "YdrSkeletonBinding | int") -> YdrSkeletonBinding:
    if isinstance(value, YdrSkeletonBinding):
        return YdrSkeletonBinding(
            unknown_1=int(value.unknown_1) & 0xFF,
            has_skin=int(value.has_skin) & 0xFF,
            unknown_2=int(value.unknown_2) & 0xFF,
            bone_index=int(value.bone_index) & 0xFF,
        )
    return YdrSkeletonBinding.from_int(int(value))


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
    "YdrSkeletonBinding",
    "coerce_lod",
    "coerce_render_mask",
    "coerce_skeleton_binding",
    "VertexComponentType",
    "VertexSemantic",
]
