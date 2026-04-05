from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..binary import read_c_string
from ..metahash import MetaHash
from .model import CutFile, CutHashedString, CutNode
from .names import ARRAY_INFO_HASH, hash_name

PSIN = 0x5053494E
PMAP = 0x504D4150
PSCH = 0x50534348
PSIG = 0x50534947
STRE = 0x53545245
CHKS = 0x43484B53
PsoDataTypeBool = 0x00
PsoDataTypeSByte = 0x01
PsoDataTypeUByte = 0x02
PsoDataTypeSShort = 0x03
PsoDataTypeUShort = 0x04
PsoDataTypeSInt = 0x05
PsoDataTypeUInt = 0x06
PsoDataTypeFloat = 0x07
PsoDataTypeFloat2 = 0x08
PsoDataTypeFloat3 = 0x09
PsoDataTypeFloat4 = 0x0A
PsoDataTypeString = 0x0B
PsoDataTypeStructure = 0x0C
PsoDataTypeArray = 0x0D
PsoDataTypeEnum = 0x0E
PsoDataTypeFlags = 0x0F
PsoDataTypeMap = 0x10
PsoDataTypeFloat3a = 0x14
PsoDataTypeFloat4a = 0x15
PsoDataTypeHFloat = 0x1E
PsoDataTypeLong = 0x20


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "big", signed=False)


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big", signed=False)


def _i32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "big", signed=True)


def _u64(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 8], "big", signed=False)


def _i64(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 8], "big", signed=True)


def _f32(data: bytes, offset: int) -> float:
    import struct

    return struct.unpack(">f", data[offset : offset + 4])[0]


@dataclass(slots=True)
class _PsoPointer:
    block_id: int
    offset: int

    @property
    def is_null(self) -> bool:
        return self.block_id == 0


@dataclass(slots=True)
class _PsoArrayHeader:
    pointer: _PsoPointer
    count: int


@dataclass(slots=True)
class _PsoBlock:
    name_hash: int
    offset: int
    length: int


@dataclass(slots=True)
class _PsoEntry:
    name_hash: int
    type_id: int
    subtype: int
    data_offset: int
    reference_key: int


@dataclass(slots=True)
class _PsoStruct:
    name_hash: int
    length: int
    entries: list[_PsoEntry]


def _decode_pointer_word(word: int) -> _PsoPointer:
    return _PsoPointer(block_id=word & 0xFFF, offset=word >> 12)


def _decode_pointer(data: bytes, offset: int) -> _PsoPointer:
    return _decode_pointer_word(_u32(data, offset))


def _decode_array_header(data: bytes, offset: int) -> _PsoArrayHeader:
    return _PsoArrayHeader(pointer=_decode_pointer(data, offset), count=_u16(data, offset + 8))


class _PsoReader:
    def __init__(self, data: bytes):
        self.data = data
        self.sections = self._parse_sections(data)
        self.psin = self.sections[PSIN]
        self.blocks, self.root_block_id = self._parse_pmap(self.sections[PMAP])
        self.structs = self._parse_psch(self.sections[PSCH])

    def _parse_sections(self, data: bytes) -> dict[int, bytes]:
        sections: dict[int, bytes] = {}
        offset = 0
        while offset + 8 <= len(data):
            ident = _u32(data, offset)
            length = _u32(data, offset + 4)
            sections[ident] = data[offset : offset + length]
            offset += length
        return sections

    def _parse_pmap(self, data: bytes) -> tuple[dict[int, _PsoBlock], int]:
        root_id = _i32(data, 8)
        count = _u16(data, 12)
        blocks: dict[int, _PsoBlock] = {}
        offset = 16
        for index in range(count):
            name_hash = _u32(data, offset)
            block_offset = _i32(data, offset + 4)
            length = _i32(data, offset + 12)
            blocks[index + 1] = _PsoBlock(name_hash=name_hash, offset=block_offset, length=length)
            offset += 16
        return blocks, root_id

    def _parse_psch(self, data: bytes) -> dict[int, _PsoStruct]:
        count = _u32(data, 8)
        indexes: list[tuple[int, int]] = []
        offset = 12
        for _ in range(count):
            indexes.append((_u32(data, offset), _i32(data, offset + 4)))
            offset += 8
        result: dict[int, _PsoStruct] = {}
        for name_hash, rel_offset in indexes:
            abs_offset = rel_offset
            if data[abs_offset] != 0:
                continue
            entries_count = _u16(data, abs_offset + 2)
            length = _i32(data, abs_offset + 4)
            entry_offset = abs_offset + 12
            entries: list[_PsoEntry] = []
            for _ in range(entries_count):
                entries.append(
                    _PsoEntry(
                        name_hash=_u32(data, entry_offset),
                        type_id=data[entry_offset + 4],
                        subtype=data[entry_offset + 5],
                        data_offset=_u16(data, entry_offset + 6),
                        reference_key=_u32(data, entry_offset + 8),
                    )
                )
                entry_offset += 12
            result[name_hash] = _PsoStruct(name_hash=name_hash, length=length, entries=entries)
        return result

    def _block_slice(self, pointer: _PsoPointer, size: int) -> bytes:
        block = self._get_block(pointer.block_id)
        if block is None:
            return b"\x00" * size
        start = block.offset + pointer.offset
        return self.psin[start : start + size]

    def _read_c_string_pointer(self, pointer: _PsoPointer, length: int | None = None) -> str:
        if pointer.is_null:
            return ""
        block = self._get_block(pointer.block_id)
        if block is None:
            return ""
        start = block.offset + pointer.offset
        if length is None:
            return read_c_string(self.psin, start)
        return self.psin[start : start + length].split(b"\x00", 1)[0].decode("ascii", errors="ignore")

    def _read_inline_string(self, block_id: int, absolute_offset: int, entry: _PsoEntry) -> str:
        length = (entry.reference_key >> 16) & 0xFFFF
        end = absolute_offset + length
        return self.psin[absolute_offset:end].split(b"\x00", 1)[0].decode("ascii", errors="ignore")

    def _read_string(self, block_id: int, absolute_offset: int, entry: _PsoEntry) -> str | CutHashedString:
        if entry.subtype == 0:
            return self._read_inline_string(block_id, absolute_offset, entry)
        if entry.subtype in {1, 2}:
            return self._read_c_string_pointer(_decode_pointer(self.psin, absolute_offset))
        if entry.subtype == 3:
            header = _decode_array_header(self.psin, absolute_offset)
            count = max(0, header.count - 1)
            return self._read_c_string_pointer(header.pointer, count)
        if entry.subtype in {7, 8}:
            return CutHashedString(hash=_u32(self.psin, absolute_offset))
        return ""

    def _read_scalar(self, absolute_offset: int, type_id: int) -> Any:
        if type_id == PsoDataTypeBool:
            return self.psin[absolute_offset] != 0
        if type_id == PsoDataTypeSByte:
            return int.from_bytes(self.psin[absolute_offset : absolute_offset + 1], "big", signed=True)
        if type_id == PsoDataTypeUByte:
            return self.psin[absolute_offset]
        if type_id == PsoDataTypeSShort:
            return int.from_bytes(self.psin[absolute_offset : absolute_offset + 2], "big", signed=True)
        if type_id == PsoDataTypeUShort:
            return _u16(self.psin, absolute_offset)
        if type_id in {PsoDataTypeSInt, PsoDataTypeEnum, PsoDataTypeFlags}:
            return _i32(self.psin, absolute_offset)
        if type_id == PsoDataTypeUInt:
            return _u32(self.psin, absolute_offset)
        if type_id == PsoDataTypeFloat:
            return _f32(self.psin, absolute_offset)
        if type_id in {PsoDataTypeFloat3, PsoDataTypeFloat3a}:
            return (_f32(self.psin, absolute_offset), _f32(self.psin, absolute_offset + 4), _f32(self.psin, absolute_offset + 8))
        if type_id in {PsoDataTypeFloat4, PsoDataTypeFloat4a}:
            return (
                _f32(self.psin, absolute_offset),
                _f32(self.psin, absolute_offset + 4),
                _f32(self.psin, absolute_offset + 8),
                _f32(self.psin, absolute_offset + 12),
            )
        if type_id == PsoDataTypeFloat2:
            return (_f32(self.psin, absolute_offset), _f32(self.psin, absolute_offset + 4))
        if type_id == PsoDataTypeHFloat:
            return _u16(self.psin, absolute_offset)
        if type_id == PsoDataTypeLong:
            return _i64(self.psin, absolute_offset)
        return None

    def _read_pointer_target(self, pointer: _PsoPointer) -> Any:
        if pointer.is_null:
            return None
        block = self._get_block(pointer.block_id)
        if block is None:
            return None
        type_hash = block.name_hash
        if type_hash == 1:
            return self._read_c_string_pointer(pointer)
        struct_info = self.structs.get(type_hash)
        if struct_info is None:
            return {"type_hash": type_hash, "block_id": pointer.block_id, "offset": pointer.offset}
        return self._read_structure(type_hash, pointer.block_id, pointer.offset)

    def _is_empty_value(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, bool):
            return value is False
        if isinstance(value, (int, float)):
            return value == 0
        if isinstance(value, str):
            return value == ""
        if isinstance(value, CutHashedString):
            return value.hash == 0 and not value.text
        if isinstance(value, tuple):
            return all(self._is_empty_value(item) for item in value)
        if isinstance(value, list):
            return all(self._is_empty_value(item) for item in value)
        if isinstance(value, CutNode):
            return all(self._is_empty_value(item) for item in value.fields.values())
        return False

    def _trim_trailing_empty_values(self, values: list[Any]) -> list[Any]:
        end = len(values)
        while end > 0 and self._is_empty_value(values[end - 1]):
            end -= 1
        return values[:end]

    def _get_block(self, block_id: int) -> _PsoBlock | None:
        return self.blocks.get(block_id)

    def _read_array_values(self, entry: _PsoEntry, array_info: _PsoEntry, block_id: int, absolute_offset: int) -> list[Any]:
        if array_info is None:
            return []
        if entry.subtype in {0, 3, 5, 6, 7, 8}:
            header = _decode_array_header(self.psin, absolute_offset)
            if header.pointer.is_null or header.count == 0:
                return []
            target_block = self._get_block(header.pointer.block_id)
            if target_block is None:
                return []
            base = target_block.offset + header.pointer.offset
            count = header.count
            inline = False
        else:
            base = absolute_offset
            count = (entry.reference_key >> 16) & 0xFFFF
            inline = True

        if array_info.type_id == PsoDataTypeStructure:
            if array_info.reference_key != 0:
                type_hash = array_info.reference_key
                struct_info = self.structs.get(type_hash)
                if struct_info is None:
                    return []
                parent_block = self._get_block(block_id)
                if parent_block is None:
                    return []
                values = [
                    self._read_structure(
                        type_hash,
                        block_id if inline else header.pointer.block_id,
                        (base - parent_block.offset if inline else header.pointer.offset) + struct_info.length * index,
                    )
                    for index in range(count)
                ]
                return self._trim_trailing_empty_values(values) if inline else values
            values: list[Any] = []
            for index in range(count):
                pointer = _decode_pointer(self.psin, base + index * 8)
                values.append(self._read_pointer_target(pointer))
            return self._trim_trailing_empty_values(values) if inline else values

        if array_info.type_id in {PsoDataTypeBool, PsoDataTypeUByte}:
            return [self.psin[base + index] if array_info.type_id == PsoDataTypeUByte else self.psin[base + index] != 0 for index in range(count)]
        if array_info.type_id == PsoDataTypeUShort:
            return [_u16(self.psin, base + index * 2) for index in range(count)]
        if array_info.type_id == PsoDataTypeSInt:
            return [_i32(self.psin, base + index * 4) for index in range(count)]
        if array_info.type_id == PsoDataTypeUInt:
            return [_u32(self.psin, base + index * 4) for index in range(count)]
        if array_info.type_id == PsoDataTypeFloat:
            return [_f32(self.psin, base + index * 4) for index in range(count)]
        if array_info.type_id == PsoDataTypeFloat2:
            return [(_f32(self.psin, base + index * 8), _f32(self.psin, base + index * 8 + 4)) for index in range(count)]
        if array_info.type_id == PsoDataTypeFloat3:
            return [
                (
                    _f32(self.psin, base + index * 16),
                    _f32(self.psin, base + index * 16 + 4),
                    _f32(self.psin, base + index * 16 + 8),
                )
                for index in range(count)
            ]
        if array_info.type_id == PsoDataTypeString:
            if array_info.subtype in {7, 8}:
                return [CutHashedString(hash=_u32(self.psin, base + index * 4)) for index in range(count)]
            if array_info.subtype in {2, 3}:
                values: list[str] = []
                stride = 8 if array_info.subtype == 2 else 16
                for index in range(count):
                    item_offset = base + index * stride
                    if array_info.subtype == 2:
                        values.append(self._read_c_string_pointer(_decode_pointer(self.psin, item_offset)))
                    else:
                        header = _decode_array_header(self.psin, item_offset)
                        values.append(self._read_c_string_pointer(header.pointer, max(0, header.count - 1)))
                return values
        return []

    def _read_structure(self, type_hash: int, block_id: int, relative_offset: int) -> CutNode:
        struct_info = self.structs.get(type_hash)
        if struct_info is None:
            return CutNode(type_name=hash_name(type_hash), type_hash=type_hash, fields={})
        block = self._get_block(block_id)
        if block is None:
            return CutNode(type_name=hash_name(type_hash), type_hash=type_hash, fields={})
        base = block.offset + relative_offset
        fields: dict[str, Any] = {}
        array_info: _PsoEntry | None = None
        for entry in struct_info.entries:
            if entry.name_hash == ARRAY_INFO_HASH:
                array_info = entry
                continue
            name = hash_name(entry.name_hash)
            absolute_offset = base + entry.data_offset
            if entry.type_id == PsoDataTypeString:
                fields[name] = self._read_string(block_id, absolute_offset, entry)
            elif entry.type_id == PsoDataTypeStructure:
                if entry.subtype == 0:
                    fields[name] = self._read_structure(entry.reference_key, block_id, relative_offset + entry.data_offset)
                elif entry.subtype in {3, 4}:
                    fields[name] = self._read_pointer_target(_decode_pointer(self.psin, absolute_offset))
                else:
                    fields[name] = None
            elif entry.type_id == PsoDataTypeArray:
                fields[name] = self._read_array_values(entry, array_info, block_id, absolute_offset)
            elif entry.type_id == PsoDataTypeMap:
                fields[name] = None
            else:
                fields[name] = self._read_scalar(absolute_offset, entry.type_id)
        return CutNode(type_name=hash_name(type_hash), type_hash=type_hash, fields=fields)

    def read_cut(self) -> CutFile:
        root_block = self.blocks[self.root_block_id]
        root = self._read_structure(root_block.name_hash, self.root_block_id, 0)
        block_order_hashes: list[int] = []
        for block_id in sorted(self.blocks):
            name_hash = self.blocks[block_id].name_hash
            if name_hash not in block_order_hashes:
                block_order_hashes.append(name_hash)
        metadata = {
            "pso_template": {
                "sections": {
                    ident: bytes(section)
                    for ident, section in self.sections.items()
                    if ident != PSIN and ident != PMAP
                },
                "structs": self.structs,
                "root_type_hash": root_block.name_hash,
                "psin_prefix": bytes(self.sections[PSIN][8:16]),
                "pmap_unknown": _u16(self.sections[PMAP], 14),
                "block_order_hashes": block_order_hashes,
            }
        }
        return CutFile(root=root, source="cut", metadata=metadata)


def read_cut(data: bytes | str | Path) -> CutFile:
    if isinstance(data, (str, Path)):
        payload = Path(data).read_bytes()
    else:
        payload = data
    if _u32(payload, 0) != PSIN:
        raise ValueError("not a PSIN/PSO file")
    return _PsoReader(payload).read_cut()
