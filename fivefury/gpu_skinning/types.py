from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

GPU_SKINNING_INFLUENCES = 4
GPU_SKINNING_LOCAL_SIZE = 256


class GpuShaderLanguage(StrEnum):
    GLSL = "glsl"
    HLSL = "hlsl"


@dataclass(frozen=True, slots=True)
class GpuSkinningBindings:
    positions: int = 0
    normals: int = 1
    influences: int = 2
    palette: int = 3
    output_positions: int = 4
    output_normals: int = 5

    def __post_init__(self) -> None:
        values = (
            self.positions,
            self.normals,
            self.influences,
            self.palette,
            self.output_positions,
            self.output_normals,
        )
        if any(value < 0 for value in values):
            raise ValueError("GPU skinning bindings cannot be negative")
        if len(set(values)) != len(values):
            raise ValueError("GPU skinning bindings must be unique")


__all__ = [
    "GPU_SKINNING_INFLUENCES",
    "GPU_SKINNING_LOCAL_SIZE",
    "GpuShaderLanguage",
    "GpuSkinningBindings",
]
