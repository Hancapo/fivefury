from __future__ import annotations

from enum import StrEnum

from fivefury import (
    AngleMode,
    CutEventBehavior,
    RpfExportMode,
    RpfExtractionConflict,
    RpfPlatform,
    RpfSourceKind,
    TextureGraphIssueSeverity,
    TextureResolutionSeverity,
    TextureResolutionStatus,
    YddRuntimeContext,
)


def test_public_text_enums_use_python_311_str_enum_semantics() -> None:
    members = (
        AngleMode.DEGREES,
        CutEventBehavior.INSTANT,
        RpfExportMode.STANDALONE,
        RpfExtractionConflict.SUFFIX,
        RpfPlatform.PC,
        RpfSourceKind.RAW,
        TextureGraphIssueSeverity.WARNING,
        TextureResolutionSeverity.INFO,
        TextureResolutionStatus.FOUND,
        YddRuntimeContext.GENERIC,
    )

    assert all(isinstance(member, StrEnum) for member in members)
    assert all(str(member) == member.value for member in members)
