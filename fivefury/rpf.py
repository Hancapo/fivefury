from __future__ import annotations

import io
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, Optional

from .crypto import (
    AES_ENCRYPTION,
    NG_ENCRYPTION,
    NONE_ENCRYPTION,
    OPEN_ENCRYPTION,
    GameCrypto,
    get_game_crypto,
)
from .rpf_convert import _directory_to_rpf, _zip_to_rpf, create_rpf, load_rpf, rpf_to_zip, zip_to_rpf
from .rpf_utils import (
    RPF_BLOCK_SIZE,
    RPF_MAGIC,
    RSC7_MAGIC,
    _archive_name,
    _build_rsc7,
    _ceil_div,
    _coerce_file_bytes,
    _compress_deflate,
    _decompress_deflate,
    _is_rsc7,
    _normalize_key,
    _normalize_path,
    _pad,
    _resource_flags_from_size,
    _resource_version_from_flags,
    _size_from_resource_flags,
    _split_rsc7,
)
from .rpf_entries import (
    RpfBinaryFileEntry,
    RpfDirectoryEntry,
    RpfEntry,
    RpfFileEntry,
    RpfResourceFileEntry,
    RpfResourcePageFlags,
)
@dataclass(slots=True)
class RpfArchive:
    name: str = "archive.rpf"
    source_path: str = ""
    prefix: str = ""
    encryption: int = OPEN_ENCRYPTION
    version: int = RPF_MAGIC
    root: RpfDirectoryEntry = field(default_factory=RpfDirectoryEntry)
    children: list["RpfArchive"] = field(default_factory=list)
    parent: Optional["RpfArchive"] = None
    parent_file_entry: Optional[RpfBinaryFileEntry] = None
    crypto: GameCrypto | None = field(default=None, repr=False, compare=False)
    _source_bytes: bytes | None = field(default=None, repr=False, compare=False)
    _source_file: Optional[Path] = field(default=None, repr=False, compare=False)
    _index: dict[str, RpfEntry] = field(default_factory=dict, init=False, repr=False, compare=False)
    _index_dirty: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.name = self.name or "archive.rpf"
        if self.crypto is None:
            self.crypto = get_game_crypto()
        self.root.name = ""
        self.root.path = ""
        self.root._archive = self

    @classmethod
    def empty(cls, name: str = "archive.rpf", *, prefix: str = "", crypto: GameCrypto | None = None) -> "RpfArchive":
        return cls(name=_archive_name(name), prefix=prefix, crypto=crypto)

    @classmethod
    def from_path(cls, path: str | Path, *, crypto: GameCrypto | None = None) -> "RpfArchive":
        p = Path(path)
        archive = cls(name=p.name, source_path=str(p), crypto=crypto)
        archive._source_file = p
        archive._parse()
        return archive

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        name: str = "",
        source_path: str = "",
        prefix: str = "",
        crypto: GameCrypto | None = None,
    ) -> "RpfArchive":
        archive = cls(name=name or Path(source_path).name or "archive.rpf", source_path=source_path, prefix=prefix, crypto=crypto)
        archive._source_bytes = bytes(data)
        archive._parse()
        return archive

    @classmethod
    def from_zip(cls, source: str | Path | bytes | BinaryIO, *, name: str = "archive") -> "RpfArchive":
        if isinstance(source, (str, Path)):
            path = Path(source)
            if path.is_dir():
                return _directory_to_rpf(path, name=name or path.name)
            with zipfile.ZipFile(path, "r") as zf:
                return _zip_to_rpf(zf, name=name)
        if isinstance(source, (bytes, bytearray)):
            with zipfile.ZipFile(io.BytesIO(source), "r") as zf:
                return _zip_to_rpf(zf, name=name)
        with zipfile.ZipFile(io.BytesIO(source.read()), "r") as zf:
            return _zip_to_rpf(zf, name=name)

    def _source_read(self, offset: int, size: int) -> bytes:
        if self._source_bytes is not None:
            return self._source_bytes[offset : offset + size]
        if self._source_file is not None:
            with self._source_file.open("rb") as fh:
                fh.seek(offset)
                return fh.read(size)
        raise ValueError("Archive has no readable source")

    def _attach_archive(self, entry: RpfEntry) -> None:
        entry._archive = self
        if isinstance(entry, RpfDirectoryEntry):
            for child in entry.directories:
                self._attach_archive(child)
            for child in entry.files:
                self._attach_archive(child)

    def _parse(self) -> None:
        header = self._source_read(0, 16)
        if len(header) < 16:
            raise ValueError("Invalid RPF archive")

        version, entry_count, names_length, encryption = struct.unpack_from("<4I", header, 0)
        if version != RPF_MAGIC:
            raise ValueError("Invalid RPF7 magic")
        self.version = version
        self.encryption = encryption

        entries_offset = 16
        entries_size = entry_count * 16
        names_offset = entries_offset + entries_size

        entries_data = self._source_read(entries_offset, entries_size)
        names_data = self._source_read(names_offset, names_length)
        if encryption not in (NONE_ENCRYPTION, OPEN_ENCRYPTION):
            if self.crypto is None:
                raise ValueError(
                    f"RPF archive '{self.name}' uses encryption 0x{encryption:08X} and no game crypto is configured"
                )
            entries_data = self.crypto.decrypt_archive_table(
                entries_data,
                encryption,
                archive_name=self.name,
                archive_size=self._archive_size(),
            )
            names_data = self.crypto.decrypt_archive_table(
                names_data,
                encryption,
                archive_name=self.name,
                archive_size=self._archive_size(),
            )

        names: dict[int, str] = {0: ""}
        i = 0
        while i < len(names_data):
            end = names_data.find(b"\x00", i)
            if end < 0:
                end = len(names_data)
            names[i] = names_data[i:end].decode("utf-8", errors="replace")
            i = end + 1

        entries: list[RpfEntry] = []
        for n in range(entry_count):
            blob = entries_data[n * 16 : (n + 1) * 16]
            if len(blob) < 16:
                raise ValueError("Truncated RPF entry table")
            first_dword, second_dword = struct.unpack_from("<II", blob, 0)
            if second_dword == 0x7FFFFF00:
                entry = RpfDirectoryEntry(
                    name=names.get(first_dword & 0xFFFF, ""),
                    path="",
                    entries_index=struct.unpack_from("<I", blob, 8)[0],
                    entries_count=struct.unpack_from("<I", blob, 12)[0],
                )
                entry.name_offset = first_dword & 0xFFFF
            elif (second_dword & 0x80000000) == 0:
                low = struct.unpack_from("<Q", blob, 0)[0]
                entry = RpfBinaryFileEntry(
                    name=names.get(low & 0xFFFF, ""),
                    path="",
                    file_size=(low >> 16) & 0xFFFFFF,
                    file_offset=(low >> 40) & 0xFFFFFF,
                    file_uncompressed_size=struct.unpack_from("<I", blob, 8)[0],
                    encryption_type=struct.unpack_from("<I", blob, 12)[0],
                )
                entry.name_offset = low & 0xFFFF
                entry.is_encrypted = bool(entry.encryption_type & 0x1)
            else:
                name_offset = struct.unpack_from("<H", blob, 0)[0]
                file_size = int.from_bytes(blob[2:5], "little")
                file_offset = int.from_bytes(blob[5:8], "little") & 0x7FFFFF
                sys_flags, gfx_flags = struct.unpack_from("<II", blob, 8)
                entry = RpfResourceFileEntry(
                    name=names.get(name_offset, ""),
                    path="",
                    file_size=file_size,
                    file_offset=file_offset,
                    system_flags=RpfResourcePageFlags(sys_flags),
                    graphics_flags=RpfResourcePageFlags(gfx_flags),
                )
                entry.name_offset = name_offset
                if entry.file_size == 0xFFFFFF:
                    raw_header = self._source_read(entry.file_offset * RPF_BLOCK_SIZE, 16)
                    if len(raw_header) == 16:
                        entry.file_size = (
                            (raw_header[7] << 0)
                            | (raw_header[14] << 8)
                            | (raw_header[5] << 16)
                            | (raw_header[2] << 24)
                        )
            entries.append(entry)

        root = entries[0]
        if not isinstance(root, RpfDirectoryEntry):
            raise ValueError("Root RPF entry must be a directory")
        root.name = ""
        root.path = ""
        root.parent = None
        self.root = root
        self._attach_archive(self.root)

        def build_dir(dir_entry: RpfDirectoryEntry, prefix: str) -> None:
            start = dir_entry.entries_index
            end = min(start + dir_entry.entries_count, len(entries))
            for child in entries[start:end]:
                child.parent = dir_entry
                child.path = f"{prefix}/{child.name}" if prefix else child.name
                child._archive = self
                if isinstance(child, RpfDirectoryEntry):
                    child.directories.clear()
                    child.files.clear()
                    dir_entry.directories.append(child)
                    build_dir(child, child.path)
                else:
                    if child.name.lower().endswith(".ysc"):
                        child.is_encrypted = True
                    dir_entry.files.append(child)
                    if child.name.lower().endswith(".rpf"):
                        try:
                            nested_bytes = child.read(logical=True)
                            nested = RpfArchive.from_bytes(
                                nested_bytes,
                                name=child.name,
                                source_path=self._nested_source_path(child),
                                prefix=child.full_path,
                                crypto=self.crypto,
                            )
                            nested.parent = self
                            nested.parent_file_entry = child if isinstance(child, RpfBinaryFileEntry) else None
                            if isinstance(child, (RpfBinaryFileEntry, RpfResourceFileEntry)):
                                child.child_archive = nested
                            self.children.append(nested)
                        except Exception:
                            pass

        build_dir(self.root, "")
        self._rebuild_index()

    def _archive_size(self) -> int:
        if self._source_bytes is not None:
            return len(self._source_bytes)
        if self._source_file is not None:
            try:
                return self._source_file.stat().st_size
            except OSError:
                return 0
        return 0

    def _nested_source_path(self, entry: RpfEntry) -> str:
        base = self.source_path or self.name
        if base:
            return f"{base}/{entry.path}"
        return entry.path

    def _invalidate_index(self) -> None:
        self._index_dirty = True

    def _ensure_index(self) -> None:
        if self._index_dirty:
            self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._index.clear()
        for entry in self.iter_entries(include_directories=True, include_root=False):
            self._index[_normalize_key(entry.full_path)] = entry
        for child in self.children:
            child._rebuild_index()
            self._index.update(child._index)
        self._index_dirty = False

    def iter_entries(self, *, include_directories: bool = False, include_root: bool = False) -> Iterator[RpfEntry]:
        if include_root:
            yield self.root

        def walk(dir_entry: RpfDirectoryEntry) -> Iterator[RpfEntry]:
            for child in sorted(dir_entry.directories, key=lambda e: e.name_lower):
                if include_directories:
                    yield child
                yield from walk(child)
            for child in sorted(dir_entry.files, key=lambda e: e.name_lower):
                yield child

        yield from walk(self.root)

    def find_entry(self, path: str | Path) -> Optional[RpfEntry]:
        self._ensure_index()
        return self._index.get(_normalize_key(path))

    def read_entry_raw(self, entry: RpfFileEntry) -> bytes:
        if getattr(entry, "_data", None) is not None:
            return bytes(entry._data)  # type: ignore[attr-defined]
        size = entry.get_file_size()
        if size <= 0:
            return b""
        return self._source_read(entry.file_offset * RPF_BLOCK_SIZE, size)

    def read_entry_bytes(self, entry: RpfFileEntry, *, logical: bool = True) -> bytes:
        raw = self.read_entry_raw(entry)
        if not logical:
            return raw
        if isinstance(entry, RpfResourceFileEntry):
            if _is_rsc7(raw):
                return parse_rsc7(raw)[1]
            payload = raw[16:] if len(raw) > 16 else b""
            if entry.is_encrypted:
                payload = self.crypto.decrypt_entry_payload(
                    payload,
                    self.encryption,
                    entry_name=entry.name,
                    entry_length=entry.file_size,
                )
            try:
                return _decompress_deflate(payload)
            except ValueError:
                return payload
        if entry.is_encrypted:
            raw = self._decrypt_entry_raw(entry, raw)
        if isinstance(entry, RpfBinaryFileEntry) and entry.file_size > 0:
            return _decompress_deflate(raw)
        return raw

    def read_entry_standalone(self, entry: RpfFileEntry) -> bytes:
        raw = self.read_entry_raw(entry)
        if isinstance(entry, RpfResourceFileEntry):
            if _is_rsc7(raw):
                return raw
            payload = raw[16:] if len(raw) > 16 else b""
            if entry.is_encrypted:
                if self.crypto is None:
                    raise ValueError(f"Entry '{entry.full_path}' is encrypted and no game crypto is configured")
                payload = self.crypto.decrypt_entry_payload(
                    payload,
                    self.encryption,
                    entry_name=entry.name,
                    entry_length=entry.file_size,
                )
            version = _resource_version_from_flags(entry.system_flags.value, entry.graphics_flags.value)
            return struct.pack(
                "<IIII",
                RSC7_MAGIC,
                version,
                entry.system_flags.value,
                entry.graphics_flags.value,
            ) + payload
        if entry.is_encrypted:
            return self._decrypt_entry_raw(entry, raw)
        return raw

    def _decrypt_entry_raw(self, entry: RpfFileEntry, raw: bytes) -> bytes:
        if self.encryption in (NONE_ENCRYPTION, OPEN_ENCRYPTION):
            return raw
        if self.crypto is None:
            raise ValueError(f"Entry '{entry.full_path}' is encrypted and no game crypto is configured")
        if isinstance(entry, RpfResourceFileEntry):
            if len(raw) <= 16:
                return raw
            header = raw[:16]
            payload = self.crypto.decrypt_entry_payload(
                raw[16:],
                self.encryption,
                entry_name=entry.name,
                entry_length=entry.file_size,
            )
            return header + payload
        if isinstance(entry, RpfBinaryFileEntry):
            return self.crypto.decrypt_entry_payload(
                raw,
                self.encryption,
                entry_name=entry.name,
                entry_length=entry.file_uncompressed_size,
            )
        return raw

    def _ensure_dir(self, segments: list[str]) -> RpfDirectoryEntry:
        current = self.root
        built: list[str] = []
        for segment in segments:
            built.append(segment)
            found = next((d for d in current.directories if d.name_lower == segment.lower()), None)
            if found is None:
                found = RpfDirectoryEntry(name=segment, path="/".join(built), parent=current, _archive=self)
                current.directories.append(found)
            current = found
        return current

    def add_directory(self, path: str | Path) -> RpfDirectoryEntry:
        normalized = _normalize_path(path)
        if not normalized:
            return self.root
        parent_path, leaf = normalized.rsplit("/", 1) if "/" in normalized else ("", normalized)
        parent = self._ensure_dir(parent_path.split("/") if parent_path else [])
        existing = next((d for d in parent.directories if d.name_lower == leaf.lower()), None)
        if existing is not None:
            return existing
        entry = RpfDirectoryEntry(name=leaf, path=normalized, parent=parent, _archive=self)
        parent.directories.append(entry)
        self._invalidate_index()
        return entry

    def add_nested_archive(self, path: str | Path) -> tuple[RpfBinaryFileEntry, "RpfArchive"]:
        normalized = _normalize_path(path)
        parent_path, leaf = normalized.rsplit("/", 1) if "/" in normalized else ("", normalized)
        parent = self._ensure_dir(parent_path.split("/") if parent_path else [])
        entry = next((f for f in parent.files if f.name_lower == leaf.lower()), None)
        if isinstance(entry, RpfBinaryFileEntry) and entry.child_archive is not None:
            return entry, entry.child_archive
        if entry is None:
            entry = RpfBinaryFileEntry(name=leaf, path=normalized, parent=parent, file_uncompressed_size=0, file_size=0, _archive=self)
            parent.files.append(entry)
        child_prefix = f"{self.prefix}/{normalized}".strip("/") if self.prefix else normalized
        child = RpfArchive.empty(leaf, prefix=child_prefix, crypto=self.crypto)
        child.parent = self
        child.parent_file_entry = entry
        entry.child_archive = child
        self.children.append(child)
        self._invalidate_index()
        return entry, child

    def add_file(self, path: str | Path, data: bytes | bytearray | memoryview | object, *, compress_binary: bool = False) -> RpfFileEntry:
        data = _coerce_file_bytes(data)
        normalized = _normalize_path(path)
        parent_path, leaf = normalized.rsplit("/", 1) if "/" in normalized else ("", normalized)
        parent = self._ensure_dir(parent_path.split("/") if parent_path else [])
        existing = next((f for f in parent.files if f.name_lower == leaf.lower()), None)
        if existing is not None:
            parent.files.remove(existing)
        if leaf.lower().endswith(".rpf") and data[:4] == struct.pack("<I", RPF_MAGIC):
            entry = RpfBinaryFileEntry(name=leaf, path=normalized, parent=parent, file_uncompressed_size=len(data), file_size=0, _archive=self, _data=data)
            child_prefix = f"{self.prefix}/{normalized}".strip("/") if self.prefix else normalized
            child = RpfArchive.from_bytes(
                data,
                name=leaf,
                source_path=self._nested_source_path(entry),
                prefix=child_prefix,
                crypto=self.crypto,
            )
            child.parent = self
            child.parent_file_entry = entry
            entry.child_archive = child
            self.children.append(child)
        elif leaf.lower().endswith(".ymap") or leaf.lower().endswith(".ytyp") or _is_rsc7(data):
            if _is_rsc7(data):
                _, sys_flags, gfx_flags, _ = _split_rsc7(data)
                entry = RpfResourceFileEntry(
                    name=leaf,
                    path=normalized,
                    parent=parent,
                    file_size=len(data),
                    system_flags=RpfResourcePageFlags(sys_flags),
                    graphics_flags=RpfResourcePageFlags(gfx_flags),
                    _archive=self,
                    _data=data,
                )
            else:
                stored = _build_rsc7(data)
                entry = RpfResourceFileEntry(
                    name=leaf,
                    path=normalized,
                    parent=parent,
                    file_size=len(stored),
                    system_flags=RpfResourcePageFlags.from_size(len(data)),
                    graphics_flags=RpfResourcePageFlags(),
                    _archive=self,
                    _data=stored,
                )
        else:
            if compress_binary:
                stored = _compress_deflate(data)
                entry = RpfBinaryFileEntry(
                    name=leaf,
                    path=normalized,
                    parent=parent,
                    file_size=len(stored),
                    file_uncompressed_size=len(data),
                    _archive=self,
                    _data=stored,
                )
            else:
                entry = RpfBinaryFileEntry(
                    name=leaf,
                    path=normalized,
                    parent=parent,
                    file_size=0,
                    file_uncompressed_size=len(data),
                    _archive=self,
                    _data=data,
                )
        parent.files.append(entry)
        self._invalidate_index()
        return entry

    def add_object(self, path: str | Path, value: bytes | bytearray | memoryview | object, *, compress_binary: bool = False) -> RpfFileEntry:
        return self.add_file(path, value, compress_binary=compress_binary)

    def add(self, path: str | Path, value: bytes | bytearray | memoryview | object, *, compress_binary: bool = False) -> RpfFileEntry:
        return self.add_file(path, value, compress_binary=compress_binary)

    def add_game_file(self, path: str | Path, value: bytes | bytearray | memoryview | object, *, compress_binary: bool = False) -> RpfFileEntry:
        return self.add_file(path, value, compress_binary=compress_binary)

    def add_asset(self, path: str | Path, value: bytes | bytearray | memoryview | object, *, compress_binary: bool = False) -> RpfFileEntry:
        return self.add_file(path, value, compress_binary=compress_binary)

    def add_ymap(self, path: str | Path, ymap: object, *, version: int = 2, auto_extents: bool = False) -> RpfFileEntry:
        if auto_extents and hasattr(ymap, "recalculate_extents"):
            ymap.recalculate_extents()  # type: ignore[attr-defined]
        if not hasattr(ymap, "to_bytes"):
            raise TypeError("ymap must expose to_bytes(version=...)")
        return self.add_file(path, ymap.to_bytes(version=version))  # type: ignore[attr-defined]

    def add_ytyp(self, path: str | Path, ytyp: object, *, version: int = 2) -> RpfFileEntry:
        if not hasattr(ytyp, "to_bytes"):
            raise TypeError("ytyp must expose to_bytes(version=...)")
        return self.add_file(path, ytyp.to_bytes(version=version))  # type: ignore[attr-defined]

    def _collect_entries(self) -> list[RpfEntry]:
        ordered: list[RpfEntry] = [self.root]
        stack: list[RpfDirectoryEntry] = [self.root]
        while stack:
            directory = stack.pop()
            directory.entries_index = len(ordered)
            directory.entries_count = len(directory.directories) + len(directory.files)
            children = sorted([*directory.directories, *directory.files], key=lambda e: e.name_lower)
            for child in children:
                ordered.append(child)
                if isinstance(child, RpfDirectoryEntry):
                    stack.append(child)
        return ordered

    def _build_names(self, entries: Iterable[RpfEntry]) -> tuple[bytes, dict[str, int]]:
        buf = bytearray()
        offsets: dict[str, int] = {}
        for entry in entries:
            if entry.name in offsets:
                entry.name_offset = offsets[entry.name]
                continue
            entry.name_offset = len(buf)
            offsets[entry.name] = entry.name_offset
            buf.extend(entry.name.encode("utf-8", errors="replace"))
            buf.append(0)
        return _pad(bytes(buf), 16), offsets

    def _entry_payload(self, entry: RpfFileEntry) -> bytes:
        if getattr(entry, "_data", None) is not None:
            return bytes(entry._data)  # type: ignore[attr-defined]
        if isinstance(entry, (RpfBinaryFileEntry, RpfResourceFileEntry)) and entry.child_archive is not None:
            return entry.child_archive.to_bytes()
        if entry._archive is not None:
            return entry.read_raw()
        raise ValueError(f"Missing payload for {entry.full_path}")

    def _encode_binary_entry(self, entry: RpfBinaryFileEntry, data: bytes, offset_blocks: int) -> bytes:
        entry.file_offset = offset_blocks
        if entry.file_size == 0:
            entry.file_uncompressed_size = len(data)
        low = (entry.name_offset & 0xFFFF) | ((entry.file_size & 0xFFFFFF) << 16) | ((entry.file_offset & 0xFFFFFF) << 40)
        return struct.pack("<QII", low, entry.file_uncompressed_size, 1 if entry.is_encrypted else 0), data

    def _encode_resource_entry(self, entry: RpfResourceFileEntry, data: bytes, offset_blocks: int) -> bytes:
        entry.file_offset = offset_blocks
        if _is_rsc7(data):
            _, sys_flags, gfx_flags, _ = _split_rsc7(data)
            entry.system_flags = RpfResourcePageFlags(sys_flags)
            entry.graphics_flags = RpfResourcePageFlags(gfx_flags)
            entry.file_size = len(data)
            payload = data
        else:
            sys_flags = _resource_flags_from_size(len(data), 0)
            payload = _build_rsc7(data, version=0, sys_flags=sys_flags, gfx_flags=0)
            entry.system_flags = RpfResourcePageFlags(sys_flags)
            entry.graphics_flags = RpfResourcePageFlags()
            entry.file_size = len(payload)
        size_bytes = int(entry.file_size).to_bytes(3, "little", signed=False)
        offset_bytes = bytearray(int(entry.file_offset).to_bytes(3, "little", signed=False))
        offset_bytes[2] |= 0x80
        raw_entry = (
            int(entry.name_offset & 0xFFFF).to_bytes(2, "little", signed=False)
            + size_bytes
            + bytes(offset_bytes)
            + struct.pack("<II", entry.system_flags.value, entry.graphics_flags.value)
        )
        return raw_entry, payload

    def to_bytes(self) -> bytes:
        if self.encryption not in (NONE_ENCRYPTION, OPEN_ENCRYPTION):
            raise NotImplementedError("Writing AES/NG-encrypted RPF archives is not supported")
        entries = self._collect_entries()
        names, _ = self._build_names(entries)
        entry_count = len(entries)
        header_size = 16 + entry_count * 16 + len(names)
        data_start = _ceil_div(header_size, RPF_BLOCK_SIZE) * RPF_BLOCK_SIZE
        current_offset = data_start // RPF_BLOCK_SIZE
        encoded_entries = bytearray()
        payloads: list[tuple[int, bytes]] = []

        for entry in entries:
            if isinstance(entry, RpfDirectoryEntry):
                encoded_entries.extend(struct.pack("<IIII", entry.name_offset, 0x7FFFFF00, entry.entries_index, entry.entries_count))
                continue
            payload = self._entry_payload(entry)
            if isinstance(entry, RpfBinaryFileEntry):
                raw_entry, stored = self._encode_binary_entry(entry, payload, current_offset)
                encoded_entries.extend(raw_entry)
            elif isinstance(entry, RpfResourceFileEntry):
                raw_entry, stored = self._encode_resource_entry(entry, payload, current_offset)
                encoded_entries.extend(raw_entry)
            else:
                raise TypeError("Unsupported RPF entry type")
            payloads.append((entry.file_offset, stored))
            current_offset += _ceil_div(len(stored), RPF_BLOCK_SIZE)

        out = bytearray()
        out.extend(struct.pack("<4I", RPF_MAGIC, entry_count, len(names), self.encryption))
        out.extend(encoded_entries)
        out.extend(names)
        out.extend(b"\x00" * ((data_start - len(out))))
        for offset_blocks, stored in payloads:
            desired = offset_blocks * RPF_BLOCK_SIZE
            if len(out) < desired:
                out.extend(b"\x00" * (desired - len(out)))
            out.extend(stored)
            out.extend(b"\x00" * ((_ceil_div(len(out), RPF_BLOCK_SIZE) * RPF_BLOCK_SIZE) - len(out)))
        self._rebuild_index()
        return bytes(out)

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    def _zip_name(self, entry: RpfEntry, prefix: str = "") -> str:
        base = entry.full_path.replace("\\", "/")
        return f"{prefix}/{base}".strip("/") if prefix else base

    def _write_zip(self, zf: zipfile.ZipFile, *, prefix: str = "", logical: bool = True) -> None:
        for entry in self.iter_entries(include_directories=True, include_root=False):
            if isinstance(entry, RpfDirectoryEntry):
                if not entry.files and not entry.directories:
                    zf.writestr(self._zip_name(entry, prefix).rstrip("/") + "/", b"")
                continue
            assert isinstance(entry, RpfFileEntry)
            if logical and isinstance(entry, (RpfBinaryFileEntry, RpfResourceFileEntry)) and entry.child_archive is not None:
                entry.child_archive._write_zip(zf, prefix=prefix, logical=logical)
                continue
            zf.writestr(self._zip_name(entry, prefix), entry.read(logical=logical))

    def to_zip(self, output: str | Path | None = None, *, logical: bool = True) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            self._write_zip(zf, logical=logical)
        data = buffer.getvalue()
        if output is not None:
            Path(output).write_bytes(data)
        return data

    def extract(self, output_dir: str | Path, *, logical: bool = True) -> list[Path]:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for entry in self.iter_entries(include_directories=False):
            dest = root / entry.full_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(entry.read(logical=logical))
            written.append(dest)
        return written




