from __future__ import annotations

from enum import Enum


class RpfExportMode(str, Enum):
    """Representation written when an archive entry is exported."""

    STORED = "stored"
    STANDALONE = "standalone"
    LOGICAL = "logical"

    @property
    def description(self) -> str:
        if self is RpfExportMode.STORED:
            return "Returns bytes as stored in the RPF entry, without rebuilding a standalone resource container."
        if self is RpfExportMode.STANDALONE:
            return "Returns standalone files. GTA resources are rebuilt with a valid RSC7 header and payload."
        return "Returns the logical payload. GTA resources are unpacked to their inner data without the RSC7 container."

    def __str__(self) -> str:
        return self.value


class RpfPlatform(str, Enum):
    """Platform byte order used by an RPF archive."""

    PC = "pc"
    PS3 = "ps3"

    @property
    def byte_order(self) -> str:
        return "big" if self is RpfPlatform.PS3 else "little"

    @property
    def struct_prefix(self) -> str:
        return ">" if self is RpfPlatform.PS3 else "<"


class RpfExtractionConflict(str, Enum):
    """Policy used when an RPF path is both a file and a directory."""

    ERROR = "error"
    SUFFIX = "suffix"
    SKIP = "skip"


def coerce_export_mode(mode: RpfExportMode) -> RpfExportMode:
    if not isinstance(mode, RpfExportMode):
        raise TypeError("mode must be an instance of RpfExportMode")
    return mode


def coerce_extraction_conflict(value: RpfExtractionConflict) -> RpfExtractionConflict:
    if not isinstance(value, RpfExtractionConflict):
        raise TypeError("conflict must be an instance of RpfExtractionConflict")
    return value


__all__ = [
    "RpfExportMode",
    "RpfExtractionConflict",
    "RpfPlatform",
    "coerce_export_mode",
    "coerce_extraction_conflict",
]
