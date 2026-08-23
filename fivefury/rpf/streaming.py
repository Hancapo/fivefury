from __future__ import annotations

import struct
import zlib
from typing import TYPE_CHECKING, BinaryIO

from ..resource import read_rsc7_header
from .entries import RpfBinaryFileEntry, RpfDirectoryEntry, RpfResourceFileEntry
from .modes import RpfEncryption
from .sources import RpfSourceKind
from .utils import RPF_BLOCK_SIZE, RPF_MAGIC, _ceil_div

if TYPE_CHECKING:
    from .archive import RpfArchive

_COPY_BUFFER_SIZE = 1024 * 1024


class _PayloadWriter:
    def __init__(
        self,
        archive: RpfArchive,
        entry: RpfBinaryFileEntry | RpfResourceFileEntry,
        stream: BinaryIO,
        entry_length: int,
    ) -> None:
        self.archive = archive
        self.entry = entry
        self.stream = stream
        self.entry_length = entry_length
        self.pending = bytearray()
        self.written = 0

    def write(self, chunk: bytes) -> None:
        if not self.entry.is_encrypted:
            self.stream.write(chunk)
            self.written += len(chunk)
            return
        self.pending.extend(chunk)
        aligned = len(self.pending) - len(self.pending) % 16
        if not aligned:
            return
        self._write_encrypted(bytes(self.pending[:aligned]))
        del self.pending[:aligned]

    def finish(self) -> int:
        if self.pending:
            self.stream.write(self.pending)
            self.written += len(self.pending)
            self.pending.clear()
        return self.written

    def _write_encrypted(self, payload: bytes) -> None:
        assert self.archive.crypto is not None
        encoded = self.archive.crypto.encrypt_entry_payload(
            payload,
            self.archive.encryption,
            entry_name=self.entry.name,
            entry_length=self.entry_length,
        )
        self.stream.write(encoded)
        self.written += len(encoded)


def _encrypt_stored_payload(
    archive: RpfArchive,
    entry: RpfBinaryFileEntry | RpfResourceFileEntry,
    stored: bytes,
) -> bytes:
    if not entry.is_encrypted:
        return stored
    assert archive.crypto is not None
    if isinstance(entry, RpfResourceFileEntry):
        return stored[:16] + archive.crypto.encrypt_entry_payload(
            stored[16:],
            archive.encryption,
            entry_name=entry.name,
            entry_length=len(stored),
        )
    return archive.crypto.encrypt_entry_payload(
        stored,
        archive.encryption,
        entry_name=entry.name,
        entry_length=entry.file_uncompressed_size,
    )


def _write_file_payload(
    archive: RpfArchive,
    entry: RpfBinaryFileEntry | RpfResourceFileEntry,
    stream: BinaryIO,
    offset_blocks: int,
) -> bytes:
    source = entry._source
    if source is None:
        raise ValueError("file-backed RPF entry is missing its source")
    with source.path.open("rb") as input_stream:
        if isinstance(entry, RpfBinaryFileEntry):
            if source.kind is RpfSourceKind.DEFLATE:
                compressor = zlib.compressobj(
                    level=source.compression_level,
                    method=zlib.DEFLATED,
                    wbits=-15,
                )
                writer = _PayloadWriter(archive, entry, stream, source.size)
                while chunk := input_stream.read(_COPY_BUFFER_SIZE):
                    writer.write(compressor.compress(chunk))
                writer.write(compressor.flush())
                payload_size = writer.finish()
                entry.file_size = payload_size
                entry.file_uncompressed_size = source.size
                return archive._encode_binary_entry_header(
                    entry, payload_size, offset_blocks
                )
            payload_size = source.size
            raw_entry = archive._encode_binary_entry_header(
                entry, payload_size, offset_blocks
            )
            writer = _PayloadWriter(archive, entry, stream, source.size)
            while chunk := input_stream.read(_COPY_BUFFER_SIZE):
                writer.write(chunk)
            writer.finish()
            return raw_entry
        else:
            if source.kind is not RpfSourceKind.RSC7:
                raise ValueError("Resource entries require an RSC7 file source")
            payload_size = source.size
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
        writer = _PayloadWriter(archive, entry, stream, payload_size)
        while chunk := input_stream.read(_COPY_BUFFER_SIZE):
            writer.write(chunk)
        writer.finish()
    return raw_entry


def write_archive_stream(archive: RpfArchive, stream: BinaryIO) -> int:
    """Write an archive without retaining all file payloads in memory."""

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
    stream.write(b"\x00" * header_size)
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
        if (
            isinstance(entry, RpfBinaryFileEntry)
            and archive.encryption not in (RpfEncryption.NONE, RpfEncryption.OPEN)
            and (
                entry.file_size > 0
                or (
                    entry._source is not None
                    and entry._source.kind is RpfSourceKind.DEFLATE
                )
            )
        ):
            entry.is_encrypted = True
        if entry._source is not None:
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
        stored = _encrypt_stored_payload(archive, entry, stored)
        stream.write(stored)
        padding = (-stream.tell()) % RPF_BLOCK_SIZE
        if padding:
            stream.write(b"\x00" * padding)

    final_padding = (-stream.tell()) % 2048
    if final_padding:
        stream.write(b"\x00" * final_padding)
    total_size = stream.tell()
    entries_data = bytearray()
    for raw_entry in encoded_entries:
        if (
            raw_entry is None
        ):  # pragma: no cover - guarded by the exhaustive loop above.
            raise RuntimeError("RPF entry table was not fully encoded")
        entries_data.extend(raw_entry)
    if archive.encryption not in (RpfEncryption.NONE, RpfEncryption.OPEN):
        assert archive.crypto is not None
        entries_data = bytearray(
            archive.crypto.encrypt_archive_table(
                bytes(entries_data),
                archive.encryption,
                archive_name=archive.name,
                archive_size=total_size,
            )
        )
        names = archive.crypto.encrypt_archive_table(
            names,
            archive.encryption,
            archive_name=archive.name,
            archive_size=total_size,
        )
    stream.seek(0)
    encoded_names_length = (
        len(names)
        | ((archive.name_shift & 0x7) << 28)
        | (0x80000000 if archive.xcompressed else 0)
    )
    stream.write(
        struct.pack(
            "<4I",
            RPF_MAGIC,
            entry_count,
            encoded_names_length,
            archive.encryption,
        )
    )
    stream.write(entries_data)
    stream.write(names)
    stream.seek(total_size)
    archive._rebuild_index()
    return total_size


__all__ = ["write_archive_stream"]
