from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ..authoring import ValidationReport
from ..game_target import GameTarget, coerce_game_target
from .enums import RelDatFileType
from .io import read_rel
from .model import RelFile, RelItem, rel_hash

if TYPE_CHECKING:
    from ..authoring import BuildContext


def _logical_name(value: str) -> str:
    normalized = str(value).strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.name != normalized or path.suffix.casefold() != ".dat":
        raise ValueError("REL metadata logical name must be a filename ending in .dat")
    return path.name.casefold()


def _ascii_name(value: str) -> str:
    name = str(value)
    if not name or "\x00" in name:
        raise ValueError("REL external object names must be non-empty and NUL-free")
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("REL external object names must be ASCII") from exc
    return name


@dataclass(frozen=True, slots=True)
class RelExternalNameTable:
    names: tuple[str, ...]

    def __init__(self, names: tuple[str, ...] | list[str]) -> None:
        object.__setattr__(self, "names", tuple(_ascii_name(name) for name in names))

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> RelExternalNameTable:
        payload = bytes(data)
        if payload and payload[-1] != 0:
            raise ValueError("REL external name table is not NUL-terminated")
        parts = payload.split(b"\x00")
        if parts and not parts[-1]:
            parts.pop()
        try:
            names = tuple(part.decode("ascii") for part in parts)
        except UnicodeDecodeError as exc:
            raise ValueError("REL external name table contains non-ASCII data") from exc
        return cls(names)

    def to_bytes(self) -> bytes:
        return b"".join(name.encode("ascii") + b"\x00" for name in self.names)

    @property
    def offsets(self) -> tuple[int, ...]:
        values: list[int] = []
        offset = 0
        for name in self.names:
            values.append(offset)
            offset += len(name) + 1
        return tuple(values)

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        hashes = [rel_hash(name) for name in self.names]
        if len(hashes) != len(set(hashes)):
            report.issue(
                "rel.nametable.hash_collision",
                "REL external object names must have unique hashes",
                path="names",
            )
        encoded_size = sum(len(name) + 1 for name in self.names)
        if encoded_size > 0x1000000:
            report.issue(
                "rel.nametable.capacity",
                "REL external name table exceeds its 24-bit offset field",
                path="names",
            )
        return report


@dataclass(frozen=True, slots=True)
class RelMetadataChunk:
    logical_name: str
    schema: int
    runtime_payload: bytes
    release_payload: bytes
    name_table: RelExternalNameTable
    game: GameTarget = GameTarget.GTA5

    def __post_init__(self) -> None:
        object.__setattr__(self, "logical_name", _logical_name(self.logical_name))
        object.__setattr__(self, "schema", int(self.schema))
        object.__setattr__(self, "runtime_payload", bytes(self.runtime_payload))
        object.__setattr__(self, "release_payload", bytes(self.release_payload))
        object.__setattr__(self, "game", coerce_game_target(self.game))

    @classmethod
    def from_rel(
        cls,
        logical_name: str,
        rel: RelFile,
        *,
        context: BuildContext,
    ) -> RelMetadataChunk:
        if int(rel.rel_type) != int(RelDatFileType.DAT54_DATA_ENTRIES):
            raise ValueError("Compiled REL metadata authoring currently supports DAT54")
        release_payload = rel.to_bytes()
        names = RelExternalNameTable(
            tuple(_require_item_name(item) for item in _data_order_items(rel))
        )
        names.validate().raise_for_errors()
        runtime_payload = _build_dat54_runtime_payload(
            read_rel(release_payload),
            release_payload,
            names,
        )
        chunk = cls(
            logical_name=logical_name,
            schema=int(rel.rel_type),
            runtime_payload=runtime_payload,
            release_payload=release_payload,
            name_table=names,
            game=context.game,
        )
        chunk.validate(context=context).raise_for_errors()
        return chunk

    @property
    def runtime_name(self) -> str:
        return f"{self.logical_name}{self.schema}"

    @property
    def release_name(self) -> str:
        return f"{self.runtime_name}.rel"

    @property
    def name_table_name(self) -> str:
        return f"{self.runtime_name}.nametable"

    @property
    def payloads(self) -> dict[str, bytes]:
        return {
            self.runtime_name: self.runtime_payload,
            self.release_name: self.release_payload,
            self.name_table_name: self.name_table.to_bytes(),
        }

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        report = ValidationReport()
        if context is not None and context.game is not self.game:
            report.issue(
                "rel.metadata.target_mismatch",
                "REL metadata target does not match the build context",
                path="game",
            )
        report.extend(self.name_table.validate(), path="name_table")
        try:
            rel = read_rel(self.release_payload, path=self.release_name)
        except (TypeError, ValueError, struct.error) as exc:
            report.issue(
                "rel.metadata.release.invalid",
                f"REL release payload cannot be read: {exc}",
                path="release_payload",
            )
            return report
        if int(rel.rel_type) != self.schema:
            report.issue(
                "rel.metadata.schema_mismatch",
                "REL release payload schema does not match its physical filename",
                path="schema",
            )
            return report
        ordered = _data_order_items(rel)
        if len(ordered) != len(self.name_table.names):
            report.issue(
                "rel.metadata.names.count_mismatch",
                "REL external name count does not match the object count",
                path="name_table.names",
            )
            return report
        for index, (item, name) in enumerate(zip(ordered, self.name_table.names, strict=True)):
            if rel_hash(name) != item.name_hash:
                report.issue(
                    "rel.metadata.names.hash_mismatch",
                    "REL external object name does not match its object hash",
                    path=f"name_table.names[{index}]",
                )
        if self.schema == int(RelDatFileType.DAT54_DATA_ENTRIES):
            expected = _build_dat54_runtime_payload(
                rel,
                self.release_payload,
                self.name_table,
            )
            if expected != self.runtime_payload:
                report.issue(
                    "rel.metadata.runtime.invalid",
                    "REL runtime payload does not match the release payload and name table",
                    path="runtime_payload",
                )
        return report


def _require_item_name(item: RelItem) -> str:
    if item.name is None:
        raise ValueError(
            f"REL object 0x{item.name_hash:08X} requires an external object name"
        )
    name = _ascii_name(item.name)
    if rel_hash(name) != item.name_hash:
        raise ValueError(
            f"REL object name {name!r} does not match hash 0x{item.name_hash:08X}"
        )
    return name


def _data_order_items(rel: RelFile) -> list[RelItem]:
    return sorted(rel.items, key=lambda item: item.data_offset)


def _table_position(data: bytes, data_length: int) -> int:
    name_table_position = 8 + data_length
    if name_table_position + 8 > len(data):
        raise ValueError("REL inline name table is truncated")
    name_table_length = struct.unpack_from("<I", data, name_table_position)[0]
    position = name_table_position + name_table_length + 4
    if position + 4 > len(data):
        raise ValueError("REL object index is truncated")
    return position


def _remap_reference_offset(
    value: int,
    items: list[RelItem],
    ordinal_by_offset: dict[int, int],
) -> int:
    for item in items:
        start = 8 + item.data_offset
        if start <= value < start + item.data_length:
            return value + 3 * (ordinal_by_offset[item.data_offset] + 1)
    raise ValueError(f"REL reference offset {value} does not belong to an object")


def _build_dat54_runtime_payload(
    rel: RelFile,
    release_payload: bytes,
    names: RelExternalNameTable,
) -> bytes:
    if int(rel.rel_type) != int(RelDatFileType.DAT54_DATA_ENTRIES):
        raise ValueError("Runtime name-offset insertion currently supports DAT54")
    schema, data_length = struct.unpack_from("<II", release_payload, 0)
    data_block = release_payload[8 : 8 + data_length]
    items = _data_order_items(rel)
    if len(items) != len(names.names):
        raise ValueError("REL external name count does not match the object count")

    rebuilt_data = bytearray()
    new_offsets: dict[int, int] = {}
    cursor = 0
    for item, name_offset in zip(items, names.offsets, strict=True):
        if item.data_offset < cursor or item.data_offset + item.data_length > len(data_block):
            raise ValueError("REL object range is invalid")
        rebuilt_data += data_block[cursor : item.data_offset]
        raw = data_block[item.data_offset : item.data_offset + item.data_length]
        if not raw:
            raise ValueError("REL object payload is empty")
        new_offsets[item.data_offset] = len(rebuilt_data)
        rebuilt_data += raw[:1]
        rebuilt_data += int(name_offset).to_bytes(3, "little")
        rebuilt_data += raw[1:]
        cursor = item.data_offset + item.data_length
    rebuilt_data += data_block[cursor:]

    index_position = _table_position(release_payload, data_length)
    inline_tables = release_payload[8 + data_length : index_position]
    index_count = struct.unpack_from("<I", release_payload, index_position)[0]
    position = index_position + 4
    index_entries = [
        struct.unpack_from("<III", release_payload, position + index * 12)
        for index in range(index_count)
    ]
    position += index_count * 12
    hash_count = struct.unpack_from("<I", release_payload, position)[0]
    position += 4
    hash_offsets = list(
        struct.unpack_from(f"<{hash_count}I", release_payload, position)
    ) if hash_count else []
    position += hash_count * 4
    pack_count = struct.unpack_from("<I", release_payload, position)[0]
    position += 4
    pack_offsets = list(
        struct.unpack_from(f"<{pack_count}I", release_payload, position)
    ) if pack_count else []
    position += pack_count * 4
    if position != len(release_payload):
        raise ValueError("REL release payload contains an unsupported trailing section")

    ordinal_by_offset = {item.data_offset: index for index, item in enumerate(items)}
    output = bytearray(struct.pack("<II", schema, len(rebuilt_data)))
    output += rebuilt_data
    output += inline_tables
    output += struct.pack("<I", index_count)
    for name_hash, item_offset, item_length in index_entries:
        if item_offset not in new_offsets:
            raise ValueError("REL object index references an unknown object offset")
        output += struct.pack(
            "<III",
            name_hash,
            new_offsets[item_offset],
            item_length + 3,
        )
    output += struct.pack("<I", hash_count)
    output += b"".join(
        struct.pack(
            "<I",
            _remap_reference_offset(value, items, ordinal_by_offset),
        )
        for value in hash_offsets
    )
    output += struct.pack("<I", pack_count)
    output += b"".join(
        struct.pack(
            "<I",
            _remap_reference_offset(value, items, ordinal_by_offset),
        )
        for value in pack_offsets
    )
    return bytes(output)


__all__ = ["RelExternalNameTable", "RelMetadataChunk"]
