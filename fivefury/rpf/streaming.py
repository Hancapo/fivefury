from __future__ import annotations

import struct
from shutil import copyfileobj
from typing import TYPE_CHECKING, BinaryIO

from ..crypto import NONE_ENCRYPTION, OPEN_ENCRYPTION
from ..resource import read_rsc7_header
from .entries import RpfBinaryFileEntry, RpfDirectoryEntry, RpfResourceFileEntry
from .utils import RPF_BLOCK_SIZE, RPF_MAGIC, _ceil_div

if TYPE_CHECKING:
    from .archive import RpfArchive

_COPY_BUFFER_SIZE = 1024 * 1024


def _write_file_payload(
    archive: RpfArchive,
    entry: RpfBinaryFileEntry | RpfResourceFileEntry,
    stream: BinaryIO,
    offset_blocks: int,
) -> bytes:
    source = entry._source_path
    if source is None:
        raise ValueError("file-backed RPF entry is missing its source path")
    payload_size = source.stat().st_size
    with source.open("rb") as input_stream:
        if isinstance(entry, RpfBinaryFileEntry):
            raw_entry = archive._encode_binary_entry_header(
                entry, payload_size, offset_blocks
            )
        else:
            source_header = input_stream.read(16)
            header = read_rsc7_header(source_header)
            raw_entry = archive._encode_resource_entry_header(
                entry, payload_size, offset_blocks, header
            )
            if payload_size >= 0xFFFFFF:
                from .archive import _encode_large_resource_header_size

                source_header = _encode_large_resource_header_size(
                    source_header, payload_size
                )
            stream.write(source_header)
        copyfileobj(input_stream, stream, length=_COPY_BUFFER_SIZE)
    return raw_entry


def write_archive_stream(archive: RpfArchive, stream: BinaryIO) -> int:
    """Write an archive without retaining all file payloads in memory."""

    if archive.encryption not in (NONE_ENCRYPTION, OPEN_ENCRYPTION):
        raise NotImplementedError(
            "Writing AES/NG-encrypted RPF archives is not supported"
        )
    if not stream.seekable():
        raise ValueError("RPF output stream must be seekable")

    entries = archive._collect_entries()
    names, _ = archive._build_names(entries)
    for entry in entries:
        if not 0 <= int(entry.name_offset) <= 0xFFFF:
            raise ValueError(
                "RPF7 name table exceeds the 16-bit entry offset limit "
                f"at {entry.full_path!r}"
            )
    entry_count = len(entries)
    header_size = 16 + entry_count * 16 + len(names)
    data_start = _ceil_div(header_size, RPF_BLOCK_SIZE) * RPF_BLOCK_SIZE
    encoded_entries: list[bytes | None] = [None] * entry_count

    stream.seek(0)
    stream.truncate()
    stream.write(
        struct.pack("<4I", RPF_MAGIC, entry_count, len(names), archive.encryption)
    )
    stream.write(b"\x00" * (entry_count * 16))
    stream.write(names)
    stream.write(b"\x00" * (data_start - stream.tell()))

    for index, entry in enumerate(entries):
        if isinstance(entry, RpfDirectoryEntry):
            encoded_entries[index] = struct.pack(
                "<IIII",
                entry.name_offset,
                0x7FFFFF00,
                entry.entries_index,
                entry.entries_count,
            )
            continue

        current_offset = stream.tell() // RPF_BLOCK_SIZE
        if entry._source_path is not None:
            encoded_entries[index] = _write_file_payload(
                archive, entry, stream, current_offset
            )
            padding = (-stream.tell()) % RPF_BLOCK_SIZE
            if padding:
                stream.write(b"\x00" * padding)
            continue

        payload = archive._entry_payload(entry)
        if isinstance(entry, RpfBinaryFileEntry):
            if current_offset > 0xFFFFFF:
                raise ValueError(
                    "RPF7 binary entry exceeds the 24-bit block offset limit: "
                    f"{entry.full_path!r}"
                )
            raw_entry, stored = archive._encode_binary_entry(
                entry, payload, current_offset
            )
        elif isinstance(entry, RpfResourceFileEntry):
            if current_offset > 0x7FFFFF:
                raise ValueError(
                    "RPF7 resource entry exceeds the 23-bit block offset limit: "
                    f"{entry.full_path!r}"
                )
            raw_entry, stored = archive._encode_resource_entry(
                entry, payload, current_offset
            )
        else:  # pragma: no cover - _collect_entries only emits known entry types.
            raise TypeError("Unsupported RPF entry type")
        encoded_entries[index] = raw_entry
        stream.write(stored)
        padding = (-stream.tell()) % RPF_BLOCK_SIZE
        if padding:
            stream.write(b"\x00" * padding)

    total_size = stream.tell()
    stream.seek(16)
    for raw_entry in encoded_entries:
        if (
            raw_entry is None
        ):  # pragma: no cover - guarded by the exhaustive loop above.
            raise RuntimeError("RPF entry table was not fully encoded")
        stream.write(raw_entry)
    stream.seek(total_size)
    archive._rebuild_index()
    return total_size


__all__ = ["write_archive_stream"]
