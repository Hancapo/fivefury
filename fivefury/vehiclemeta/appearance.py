from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from ..authoring import Diagnostic
from ..colors import RGBA8, RGBAUnit
from ..game_target import GameTarget
from ..gamefile import GameFileType
from .carcols import VehicleModelColor
from .variations import VehicleVariation


class VehicleAppearanceSourceTier(IntEnum):
    MODS = 0
    DLC = 1
    UPDATE = 2
    BASE = 3


@dataclass(frozen=True, slots=True)
class VehicleAppearanceSource:
    path: str
    kind: GameFileType
    tier: VehicleAppearanceSourceTier


@dataclass(frozen=True, slots=True)
class ResolvedVehicleColor:
    index: int
    packed_argb: int
    srgb: RGBA8
    linear: RGBAUnit
    metallic_id: int
    name: str
    source: VehicleAppearanceSource
    definition: VehicleModelColor


@dataclass(frozen=True, slots=True)
class ResolvedVehicleAppearance:
    game: GameTarget
    model_name: str | None
    model_hash: int
    primary_index: int | None
    secondary_index: int | None
    specular_index: int | None
    wheel_trim_index: int | None
    body_5_index: int | None
    body_6_index: int | None
    primary: ResolvedVehicleColor | None
    secondary: ResolvedVehicleColor | None
    specular: ResolvedVehicleColor | None
    wheel_trim: ResolvedVehicleColor | None
    body_5: ResolvedVehicleColor | None
    body_6: ResolvedVehicleColor | None
    livery_index: int | None
    secondary_livery_index: int | None
    dirt_level: float | None
    variation: VehicleVariation | None
    sources: tuple[VehicleAppearanceSource, ...]
    diagnostics: tuple[Diagnostic, ...]


__all__ = [
    "ResolvedVehicleAppearance",
    "ResolvedVehicleColor",
    "VehicleAppearanceSource",
    "VehicleAppearanceSourceTier",
]
