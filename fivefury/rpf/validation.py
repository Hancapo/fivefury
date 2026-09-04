from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise

from ..authoring import ValidationReport
from .entries import (
    RpfBinaryFileEntry,
    RpfDirectoryEntry,
    RpfEntry,
    RpfFileEntry,
    RpfResourceFileEntry,
)
from .modes import RpfEncryption, RpfPlatform
from .utils import RPF_BLOCK_SIZE, _is_rpf7, _is_rsc7

_MAX_NAME_OFFSET = 0xFFFF
_MAX_BINARY_BLOCK_OFFSET = 0xFFFFFF
_MAX_RESOURCE_BLOCK_OFFSET = 0x7FFFFF
_MAX_STORED_SIZE = 0xFFFFFF
_MAX_UNCOMPRESSED_SIZE = 0xFFFFFFFF


def _payload_size(entry: RpfFileEntry) -> int:
    if entry._source is not None:
        return entry._source.size
    data = getattr(entry, "_data", None)
    if data is not None:
        return len(data)
    if entry.child_archive is not None:
        return entry.get_file_size()
    return entry.get_file_size()


def _validate_name(report: ValidationReport, entry: RpfEntry, index: int) -> None:
    path = f"entries[{index}].name"
    if "\x00" in entry.name:
        report.issue("rpf.name.nul", "Entry names cannot contain NUL bytes.", path=path)
    try:
        entry.name.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        report.issue("rpf.name.utf8", "Entry name is not valid UTF-8.", path=path)
    if not 0 <= int(entry.name_offset) <= _MAX_NAME_OFFSET:
        report.issue(
            "rpf.name.offset",
            "Entry name offset exceeds the 16-bit RPF7 field.",
            path=path,
        )


def _validate_file(
    report: ValidationReport,
    entry: RpfFileEntry,
    index: int,
    *,
    platform: RpfPlatform,
) -> None:
    path = f"entries[{index}]"
    size = _payload_size(entry)
    if size < 0:
        report.issue("rpf.payload.size", "Payload size cannot be negative.", path=path)
        return
    if entry.file_offset and entry.file_offset * RPF_BLOCK_SIZE % RPF_BLOCK_SIZE:
        report.issue("rpf.payload.alignment", "Payload offset is not block-aligned.", path=path)

    if isinstance(entry, RpfBinaryFileEntry):
        if size > _MAX_UNCOMPRESSED_SIZE:
            report.issue(
                "rpf.binary.uncompressed_size",
                "Binary payload exceeds the 32-bit uncompressed-size field.",
                path=path,
            )
        if entry.file_offset > _MAX_BINARY_BLOCK_OFFSET:
            report.issue(
                "rpf.binary.offset",
                "Binary payload offset exceeds the 24-bit RPF7 field.",
                path=path,
            )
        if entry.file_size and size > _MAX_STORED_SIZE:
            report.issue(
                "rpf.binary.stored_size",
                "Compressed binary payload exceeds the 24-bit RPF7 field.",
                path=path,
            )
        if entry.name.lower().endswith(".rpf"):
            data = getattr(entry, "_data", None)
            if data is not None and not _is_rpf7(data):
                report.issue(
                    "rpf.nested.magic",
                    "Nested RPF payload does not start with an RPF7 header.",
                    path=path,
                )
        return

    if not isinstance(entry, RpfResourceFileEntry):
        return
    if entry.is_encrypted and not entry.name.lower().endswith(".ysc"):
        report.issue(
            "rpf.resource.encryption",
            "Resource entries do not have a serialized encryption field.",
            path=path,
        )
    if entry.file_offset > _MAX_RESOURCE_BLOCK_OFFSET:
        report.issue(
            "rpf.resource.offset",
            "Resource payload offset exceeds the 23-bit RPF7 field.",
            path=path,
        )
    if size >= _MAX_STORED_SIZE and platform is not RpfPlatform.PC:
        report.issue(
            "rpf.resource.large_platform",
            "Large-resource size sentinels are only valid in PC RPF7 archives.",
            path=path,
        )
    data = getattr(entry, "_data", None)
    if data is not None and not _is_rsc7(data):
        report.issue(
            "rpf.resource.header",
            "Resource payload does not start with an RSC7 header.",
            path=path,
        )


def _validate_loaded_ranges(
    report: ValidationReport,
    entries: Iterable[RpfEntry],
) -> None:
    ranges: list[tuple[int, int, int]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, RpfFileEntry) or entry._stored_source is None:
            continue
        start = entry._stored_source.offset
        end = start + entry._stored_source.size
        ranges.append((start, end, index))
    ranges.sort()
    for previous, current in pairwise(ranges):
        if current[0] < previous[1]:
            report.issue(
                "rpf.payload.overlap",
                f"Payload overlaps entries[{previous[2]}].",
                path=f"entries[{current[2]}]",
            )


def validate_rpf_archive(archive: object) -> ValidationReport:
    from .archive import RpfArchive

    if not isinstance(archive, RpfArchive):
        raise TypeError("archive must be an RpfArchive")
    report = ValidationReport()
    if not isinstance(archive.platform, RpfPlatform):
        report.issue("rpf.platform.type", "platform must be an RpfPlatform.", path="platform")
    if not isinstance(archive.encryption, RpfEncryption):
        report.issue(
            "rpf.encryption.type",
            "encryption must be an RpfEncryption.",
            path="encryption",
        )
    elif archive.platform is RpfPlatform.PS3 and archive.encryption not in (
        RpfEncryption.NONE,
        RpfEncryption.OPEN,
        RpfEncryption.PS3_AES,
    ):
        report.issue(
            "rpf.encryption.platform",
            "PS3 archives require NONE, OPEN, or PS3_AES encryption.",
            path="encryption",
        )
    elif (
        archive.encryption not in (RpfEncryption.NONE, RpfEncryption.OPEN)
        and archive.crypto is None
    ):
        report.issue(
            "rpf.encryption.crypto",
            "Encrypted archives require a GameCrypto context.",
            path="crypto",
        )

    entries = archive._collect_entries()
    names, _ = archive._build_names(entries)
    if len(names) > 0x0FFFFFFF:
        report.issue(
            "rpf.names.size",
            "Name table exceeds the 28-bit RPF7 header field.",
            path="entries",
        )
    for index, entry in enumerate(entries):
        _validate_name(report, entry, index)
        if isinstance(entry, RpfDirectoryEntry):
            end = entry.entries_index + entry.entries_count
            if end > len(entries):
                report.issue(
                    "rpf.directory.range",
                    "Directory child range exceeds the entry table.",
                    path=f"entries[{index}]",
                )
        elif isinstance(entry, RpfFileEntry):
            _validate_file(report, entry, index, platform=archive.platform)

    if archive._source_file is not None or archive._source_bytes is not None:
        _validate_loaded_ranges(report, entries)
    return report


__all__ = ["validate_rpf_archive"]
