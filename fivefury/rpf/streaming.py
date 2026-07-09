from __future__ import annotations

import struct
from typing import TYPE_CHECKING, BinaryIO

from ..crypto import NONE_ENCRYPTION, OPEN_ENCRYPTION
from .entries import RpfBinaryFileEntry, RpfDirectoryEntry, RpfResourceFileEntry
from .utils import RPF_BLOCK_SIZE, RPF_MAGIC, _ceil_div

if TYPE_CHECKING:
    from . import RpfArchive


def write_archive_stream(archive: "RpfArchive", stream: BinaryIO) -> int:
    """Write an archive without retaining all file payloads in memory."""

    if archive.encryption not in (NONE_ENCRYPTION, OPEN_ENCRYPTION):
        raise NotImplementedError("Writing AES/NG-encrypted RPF archives is not supported")
    if not stream.seekable():
        raise ValueError("RPF output stream must be seekable")

    entries = archive._collect_entries()
    names, _ = archive._build_names(entries)
    entry_count = len(entries)
    header_size = 16 + entry_count * 16 + len(names)
    data_start = _ceil_div(header_size, RPF_BLOCK_SIZE) * RPF_BLOCK_SIZE
    encoded_entries: list[bytes | None] = [None] * entry_count

    stream.seek(0)
    stream.truncate()
    stream.write(struct.pack("<4I", RPF_MAGIC, entry_count, len(names), archive.encryption))
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
        payload = archive._entry_payload(entry)
        if isinstance(entry, RpfBinaryFileEntry):
            raw_entry, stored = archive._encode_binary_entry(entry, payload, current_offset)
        elif isinstance(entry, RpfResourceFileEntry):
            raw_entry, stored = archive._encode_resource_entry(entry, payload, current_offset)
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
        if raw_entry is None:  # pragma: no cover - guarded by the exhaustive loop above.
            raise RuntimeError("RPF entry table was not fully encoded")
        stream.write(raw_entry)
    stream.seek(total_size)
    archive._rebuild_index()
    return total_size


__all__ = ["write_archive_stream"]
