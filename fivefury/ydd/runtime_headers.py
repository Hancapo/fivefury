from __future__ import annotations

import dataclasses
from enum import StrEnum

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


class YddRuntimeContext(StrEnum):
    GENERIC = "generic"
    CUTSCENE_PED_COMPONENT = "cutscene_ped_component"
    FULL_PED_DICTIONARY = "full_ped_dictionary"


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

LEGACY_YDD_FULL_PED_RUNTIME_PROFILE = YddRuntimeProfile(
    game=GameTarget.GTA5,
    version=YDD_VERSION_LEGACY,
    dictionary_vft=0x40573588,
    drawable_headers=DrawableRuntimeHeaders(
        drawable=0x40573178,
        shader_group=0x40613940,
        texture_base=0x4061A8F8,
        model=0x40610AB8,
        geometry=0x40618898,
        vertex_buffer=0x4061D418,
        index_buffer=0x40613238,
        skeleton=0x40613DA0,
        joints=0x40617800,
    ),
)

GEN9_YDD_RUNTIME_PROFILE = YddRuntimeProfile(
    game=GameTarget.GTA5_ENHANCED,
    version=YDD_VERSION_GEN9,
    dictionary_vft=0x4068E798,
    drawable_headers=GEN9_DRAWABLE_HEADERS,
)


def coerce_ydd_runtime_context(value: str | YddRuntimeContext) -> YddRuntimeContext:
    if isinstance(value, YddRuntimeContext):
        return value
    try:
        return YddRuntimeContext(str(value).lower())
    except ValueError as exc:
        raise ValueError(f"Unsupported YDD runtime context: {value!r}") from exc


def get_ydd_runtime_profile(
    game: str | GameTarget,
    context: str | YddRuntimeContext = YddRuntimeContext.GENERIC,
) -> YddRuntimeProfile:
    target = coerce_game_target(game)
    if target is GameTarget.GTA5_ENHANCED:
        return GEN9_YDD_RUNTIME_PROFILE
    selected = coerce_ydd_runtime_context(context)
    if selected is YddRuntimeContext.CUTSCENE_PED_COMPONENT:
        return LEGACY_YDD_CUTSCENE_PED_RUNTIME_PROFILE
    if selected is YddRuntimeContext.FULL_PED_DICTIONARY:
        return LEGACY_YDD_FULL_PED_RUNTIME_PROFILE
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


def resolve_ydd_runtime_profile(
    *,
    game: str | GameTarget | None = None,
    version: int | None = None,
    context: str | YddRuntimeContext | None = None,
    runtime_profile: YddRuntimeProfile | None = None,
) -> YddRuntimeProfile:
    if runtime_profile is not None and context is not None:
        raise ValueError("Specify either runtime_profile or runtime_context, not both")

    resolved_version = resolve_ydd_version(
        game=runtime_profile.game if game is None and runtime_profile is not None else game,
        version=runtime_profile.version if version is None and runtime_profile is not None else version,
    )
    if runtime_profile is not None:
        if int(runtime_profile.version) != resolved_version:
            raise ValueError(
                f"YDD runtime profile version {runtime_profile.version} does not "
                f"match resource version {resolved_version}"
            )
        return runtime_profile

    default_profile = get_ydd_runtime_profile_for_version(resolved_version)
    return get_ydd_runtime_profile(
        default_profile.game,
        context or YddRuntimeContext.GENERIC,
    )


__all__ = [
    "GEN9_YDD_RUNTIME_PROFILE",
    "LEGACY_YDD_CUTSCENE_PED_RUNTIME_PROFILE",
    "LEGACY_YDD_FULL_PED_RUNTIME_PROFILE",
    "LEGACY_YDD_RUNTIME_PROFILE",
    "YDD_VERSION_GEN9",
    "YDD_VERSION_LEGACY",
    "YddRuntimeContext",
    "YddRuntimeProfile",
    "coerce_ydd_runtime_context",
    "get_ydd_runtime_profile",
    "get_ydd_runtime_profile_for_version",
    "resolve_ydd_runtime_profile",
    "resolve_ydd_version",
]
