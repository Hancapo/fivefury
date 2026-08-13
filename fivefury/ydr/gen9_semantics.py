from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

GEN9_RESOLVED_PARAMETER_NAMES: Mapping[int, str] = MappingProxyType(
    {
        0x1C6524CB: "umGlobalParams0",
        0x376B767A: "AlphaClampNormal",
        0x3F66946B: "bDebugSwitches0",
        0x4DC15BF2: "Reflectivity",
        0x5A64DD6F: "AnimCombine",
        0x5A6F9A63: "FontOutlineMinMaxDepthEnabled",
        0x710292B6: "NearFarQMult",
        0x8406DB66: "AlphaScaleNormal",
        0x877E62AA: "AnimBlendWeights",
        0x92DB11FB: "SpecularMapIntensityMask",
        0x92E7D306: "gLodFadeInstRange",
        0xB1880B3B: "FontOutlineColor",
        0xC02F95F1: "SoftParticleRange",
        0xC34FF240: "ParallaxIntensity",
        0xC9B1E47E: "MirrorDebugParams",
        0xD02B61DF: "EnvMapAlphaScale",
        0xD22FA8BD: "AnimSculpt",
        0xDC71D41C: "gIndirectCountPerLod",
        0xED193A87: "ScatterG_GSquared_PhaseMult_Scale",
    }
)


def resolve_gen9_parameter_name(semantic_hash: int, fallback: str) -> str:
    return GEN9_RESOLVED_PARAMETER_NAMES.get(int(semantic_hash), fallback)
