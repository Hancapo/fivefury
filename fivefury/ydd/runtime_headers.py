from __future__ import annotations

import dataclasses

from ..game_target import GameTarget, coerce_game_target
from ..ydr.resource_headers import (
    EMBEDDED_DRAWABLE_FILE_VFT,
    GEN9_DRAWABLE_HEADERS,
    LEGACY_DRAWABLE_HEADERS,
    DrawableRuntimeHeaders,
)

YDD_VERSION_LEGACY = 165
YDD_VERSION_GEN9 = 159


@dataclasses.dataclass(frozen=True, slots=True)
class YddRuntimeProfile:
    game: GameTarget
    version: int
    dictionary_vft: int
    drawable_headers: DrawableRuntimeHeaders


LEGACY_YDD_RUNTIME_PROFILE = YddRuntimeProfile(
    game=GameTarget.GTA5,
    version=YDD_VERSION_LEGACY,
    dictionary_vft=0x40571048,
    drawable_headers=dataclasses.replace(
        LEGACY_DRAWABLE_HEADERS,
        drawable=EMBEDDED_DRAWABLE_FILE_VFT,
    ),
)

LEGACY_YDD_CUTSCENE_PED_RUNTIME_PROFILE = YddRuntimeProfile(
    game=GameTarget.GTA5,
    version=YDD_VERSION_LEGACY,
    dictionary_vft=0x40573568,
    drawable_headers=dataclasses.replace(
        LEGACY_DRAWABLE_HEADERS,
        drawable=0x40573158,
        texture_base=0x4061A7F8,
    ),
)

GEN9_YDD_RUNTIME_PROFILE = YddRuntimeProfile(
    game=GameTarget.GTA5_ENHANCED,
    version=YDD_VERSION_GEN9,
    dictionary_vft=0x4068E798,
    drawable_headers=GEN9_DRAWABLE_HEADERS,
)


def get_ydd_runtime_profile(game: str | GameTarget) -> YddRuntimeProfile:
    target = coerce_game_target(game)
    if target is GameTarget.GTA5_ENHANCED:
        return GEN9_YDD_RUNTIME_PROFILE
    return LEGACY_YDD_RUNTIME_PROFILE


def get_ydd_runtime_profile_for_version(version: int) -> YddRuntimeProfile:
    value = int(version)
    if value == YDD_VERSION_GEN9:
        return GEN9_YDD_RUNTIME_PROFILE
    if value == YDD_VERSION_LEGACY:
        return LEGACY_YDD_RUNTIME_PROFILE
    raise ValueError(f"Unsupported YDD resource version: {value}")


def resolve_ydd_version(
    *,
    game: str | GameTarget | None = None,
    version: int | None = None,
) -> int:
    if game is None:
        return YDD_VERSION_LEGACY if version is None else get_ydd_runtime_profile_for_version(version).version
    profile = get_ydd_runtime_profile(game)
    if version is not None and int(version) != profile.version:
        raise ValueError(
            f"YDD version {int(version)} does not match target {profile.game.value} "
            f"(expected {profile.version})"
        )
    return profile.version


__all__ = [
    "GEN9_YDD_RUNTIME_PROFILE",
    "LEGACY_YDD_CUTSCENE_PED_RUNTIME_PROFILE",
    "LEGACY_YDD_RUNTIME_PROFILE",
    "YDD_VERSION_GEN9",
    "YDD_VERSION_LEGACY",
    "YddRuntimeProfile",
    "get_ydd_runtime_profile",
    "get_ydd_runtime_profile_for_version",
    "resolve_ydd_version",
]
