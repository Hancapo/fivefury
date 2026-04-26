from __future__ import annotations

import re
import struct
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .metahash import HashLike, MetaHash, coerce_meta_hash

GXT2_MAGIC: int = 0x47585432
GXT2_MAGIC_BYTES: bytes = struct.pack("<I", GXT2_MAGIC)

_ENTRY_STRUCT = struct.Struct("<II")
_HEADER_STRUCT = struct.Struct("<II")
_HEX_KEY_RE = re.compile(r"^(?:0x)?([0-9a-fA-F]{8})$")


def _coerce_key(value: HashLike | None) -> MetaHash:
    return coerce_meta_hash(value)


def _parse_text_key(value: str) -> MetaHash:
    text = value.strip()
    match = _HEX_KEY_RE.match(text)
    if match is not None:
        return MetaHash(int(match.group(1), 16))
    return MetaHash(text)


@dataclass(slots=True)
class Gxt2Entry:
    key: MetaHash = field(default_factory=MetaHash)
    text: str = ""
    offset: int = 0

    def __init__(self, key: HashLike | None = 0, text: str = "", *, offset: int = 0) -> None:
        self.key = _coerce_key(key)
        self.text = str(text)
        self.offset = int(offset)

    @property
    def hash(self) -> int:
        return self.key.uint

    @property
    def name(self) -> str | None:
        return self.key.text

    def __str__(self) -> str:
        return f"0x{self.hash:08X} = {self.text}"


@dataclass(slots=True)
class Gxt2:
    entries: list[Gxt2Entry] = field(default_factory=list)
    path: str | None = None

    def __init__(
        self,
        entries: Iterable[Gxt2Entry | tuple[HashLike, str]] | Mapping[HashLike, str] | None = None,
        *,
        path: str | Path | None = None,
    ) -> None:
        self.entries = []
        self.path = str(path) if path is not None else None
        if entries is not None:
            self.update(entries)

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, *, path: str | Path | None = None) -> "Gxt2":
        return read_gxt2(data, path=path)

    @classmethod
    def from_file(cls, path: str | Path) -> "Gxt2":
        return read_gxt2(path)

    @classmethod
    def from_text(cls, text: str, *, path: str | Path | None = None) -> "Gxt2":
        gxt = cls(path=path)
        for line_number, source_line in enumerate(text.splitlines(), start=1):
            line = source_line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            if "=" not in line:
                raise ValueError(f"Invalid GXT2 text line {line_number}: expected 'key = text'")
            raw_key, value = line.split("=", 1)
            gxt.set(_parse_text_key(raw_key), value.strip())
        gxt.sort()
        return gxt

    @classmethod
    def from_mapping(cls, entries: Mapping[HashLike, str], *, path: str | Path | None = None) -> "Gxt2":
        return cls(entries, path=path)

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    def sort(self) -> None:
        self.entries.sort(key=lambda entry: entry.hash)

    def sorted_entries(self) -> list[Gxt2Entry]:
        return sorted(self.entries, key=lambda entry: entry.hash)

    def entry(self, key: HashLike) -> Gxt2Entry | None:
        key_hash = _coerce_key(key).uint
        for entry in self.entries:
            if entry.hash == key_hash:
                return entry
        return None

    def get(self, key: HashLike, default: str | None = None) -> str | None:
        entry = self.entry(key)
        return entry.text if entry is not None else default

    def set(self, key: HashLike, text: str) -> Gxt2Entry:
        coerced = _coerce_key(key)
        existing = self.entry(coerced)
        if existing is not None:
            existing.key = coerced
            existing.text = str(text)
            return existing
        entry = Gxt2Entry(coerced, text)
        self.entries.append(entry)
        return entry

    def remove(self, key: HashLike) -> bool:
        key_hash = _coerce_key(key).uint
        for index, entry in enumerate(self.entries):
            if entry.hash == key_hash:
                del self.entries[index]
                return True
        return False

    def update(self, entries: Iterable[Gxt2Entry | tuple[HashLike, str]] | Mapping[HashLike, str]) -> None:
        source = entries.items() if isinstance(entries, Mapping) else entries
        for item in source:
            if isinstance(item, Gxt2Entry):
                self.set(item.key, item.text)
            else:
                key, text = item
                self.set(key, text)

    def items(self, *, sort_entries: bool = False) -> Iterator[tuple[int, str]]:
        source = self.sorted_entries() if sort_entries else self.entries
        for entry in source:
            yield entry.hash, entry.text

    def to_dict(self, *, sort_entries: bool = False) -> dict[int, str]:
        return dict(self.items(sort_entries=sort_entries))

    def to_text(self, *, sort_entries: bool = True) -> str:
        source = self.sorted_entries() if sort_entries else self.entries
        return "".join(f"0x{entry.hash:08X} = {entry.text}\n" for entry in source)

    def to_bytes(self, *, sort_entries: bool = True) -> bytes:
        return build_gxt2_bytes(self, sort_entries=sort_entries)

    def save(self, path: str | Path, *, sort_entries: bool = True) -> None:
        Path(path).write_bytes(self.to_bytes(sort_entries=sort_entries))

    def __contains__(self, key: object) -> bool:
        try:
            return self.entry(key) is not None  # type: ignore[arg-type]
        except Exception:
            return False

    def __getitem__(self, key: HashLike) -> str:
        entry = self.entry(key)
        if entry is None:
            raise KeyError(key)
        return entry.text

    def __setitem__(self, key: HashLike, text: str) -> None:
        self.set(key, text)

    def __delitem__(self, key: HashLike) -> None:
        if not self.remove(key):
            raise KeyError(key)


def _read_utf8_z(data: bytes, offset: int, end: int) -> str:
    terminator = data.find(b"\x00", offset, end)
    if terminator < 0:
        terminator = end
    return data[offset:terminator].decode("utf-8")


def read_gxt2(source: bytes | bytearray | memoryview | str | Path, *, path: str | Path | None = None) -> Gxt2:
    if isinstance(source, (str, Path)):
        source_path = Path(source)
        data = source_path.read_bytes()
        if path is None:
            path = source_path
    else:
        data = bytes(source)

    if len(data) < 16:
        raise ValueError("GXT2 data is too small")

    magic, entry_count = _HEADER_STRUCT.unpack_from(data, 0)
    if magic != GXT2_MAGIC:
        raise ValueError(f"Invalid GXT2 magic 0x{magic:08X}")

    table_size = 8 + (entry_count * _ENTRY_STRUCT.size)
    if table_size + 8 > len(data):
        raise ValueError("GXT2 entry table is truncated")

    second_magic, end_offset = _HEADER_STRUCT.unpack_from(data, table_size)
    if second_magic != GXT2_MAGIC:
        raise ValueError(f"Invalid GXT2 string-block magic 0x{second_magic:08X}")
    if end_offset < table_size + 8 or end_offset > len(data):
        raise ValueError("GXT2 string-block end offset is out of range")

    entries: list[Gxt2Entry] = []
    for index in range(entry_count):
        entry_offset = 8 + (index * _ENTRY_STRUCT.size)
        key_hash, text_offset = _ENTRY_STRUCT.unpack_from(data, entry_offset)
        if text_offset < table_size + 8 or text_offset >= end_offset:
            raise ValueError(f"GXT2 text offset for entry {index} is out of range")
        entries.append(Gxt2Entry(key_hash, _read_utf8_z(data, text_offset, end_offset), offset=text_offset))
    gxt = Gxt2(path=path)
    gxt.entries = entries
    return gxt


def build_gxt2_bytes(
    gxt: Gxt2 | Iterable[Gxt2Entry | tuple[HashLike, str]] | Mapping[HashLike, str],
    *,
    sort_entries: bool = True,
) -> bytes:
    source = gxt if isinstance(gxt, Gxt2) else Gxt2(gxt)
    entries = source.sorted_entries() if sort_entries else list(source.entries)
    entry_count = len(entries)
    strings_offset = 16 + (entry_count * _ENTRY_STRUCT.size)
    cursor = strings_offset

    encoded_strings: list[bytes] = []
    offsets: list[int] = []
    for entry in entries:
        if "\x00" in entry.text:
            raise ValueError("GXT2 strings cannot contain NUL characters")
        encoded = entry.text.encode("utf-8") + b"\x00"
        offsets.append(cursor)
        encoded_strings.append(encoded)
        cursor += len(encoded)

    writer = bytearray()
    writer += _HEADER_STRUCT.pack(GXT2_MAGIC, entry_count)
    for entry, offset in zip(entries, offsets):
        entry.offset = offset
        writer += _ENTRY_STRUCT.pack(entry.hash, offset)
    writer += _HEADER_STRUCT.pack(GXT2_MAGIC, cursor)
    for encoded in encoded_strings:
        writer += encoded
    return bytes(writer)


def read_gxt2_text(source: str | Path) -> Gxt2:
    path = Path(source)
    return Gxt2.from_text(path.read_text(encoding="utf-8"), path=path)


def save_gxt2(
    gxt: Gxt2 | Iterable[Gxt2Entry | tuple[HashLike, str]] | Mapping[HashLike, str],
    path: str | Path,
    *,
    sort_entries: bool = True,
) -> None:
    Path(path).write_bytes(build_gxt2_bytes(gxt, sort_entries=sort_entries))


def save_gxt2_text(gxt: Gxt2, path: str | Path, *, sort_entries: bool = True) -> None:
    Path(path).write_text(gxt.to_text(sort_entries=sort_entries), encoding="utf-8")


__all__ = [
    "GXT2_MAGIC",
    "GXT2_MAGIC_BYTES",
    "Gxt2",
    "Gxt2Entry",
    "build_gxt2_bytes",
    "read_gxt2",
    "read_gxt2_text",
    "save_gxt2",
    "save_gxt2_text",
]
