from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Any

from ..binary import (
    BinaryDocument,
    BinaryEndian,
    BinaryScalarType,
)
from ..binary import (
    f32_be as _f32,
)
from ..binary import (
    i32_be as _i32,
)
from ..binary import (
    i64_be as _i64,
)
from ..binary import (
    u16_be as _u16,
)
from ..binary import (
    u32_be as _u32,
)
from ..vector import Vector2, Vector3, Vector4
from . import model as pso_model
from .codec import (
    decode_array_header,
    decode_pointer,
    parse_pmap,
    parse_psch,
    parse_psch_enums,
    parse_sections,
)
from .model import (
    ARRAY_INFO_HASH,
    PMAP,
    PSCH,
    PSIN,
    PsoBlock,
    PsoDataTypeBool,
    PsoDataTypeEnum,
    PsoDataTypeFlags,
    PsoDataTypeFloat,
    PsoDataTypeFloat2,
    PsoDataTypeFloat3,
    PsoDataTypeFloat3a,
    PsoDataTypeFloat4,
    PsoDataTypeFloat4a,
    PsoDataTypeHFloat,
    PsoDataTypeLong,
    PsoDataTypeSByte,
    PsoDataTypeSInt,
    PsoDataTypeSShort,
    PsoDataTypeString,
    PsoDataTypeStructure,
    PsoDataTypeUByte,
    PsoDataTypeUInt,
    PsoDataTypeUShort,
    PsoDocument,
    PsoEntry,
    PsoHashedString,
    PsoNode,
    PsoPointer,
)


def default_hash_name(hash_value: int) -> str:
    return f"hash_{hash_value:08X}"


@lru_cache(maxsize=64)
def _cached_schema(data: bytes) -> tuple[dict[int, Any], dict[int, Any]]:
    return parse_psch(data), parse_psch_enums(data)


class PsoReader:
    def __init__(self, data: bytes, *, name_resolver: Callable[[int], str] | None = None):
        self.data = data
        self.name_resolver = name_resolver or default_hash_name
        self.sections = parse_sections(data)
        self.psin = self.sections[PSIN]
        self.psin_document = BinaryDocument(self.psin)
        self.blocks, self.root_block_id = parse_pmap(self.sections[PMAP])
        self.structs, self.enums = _cached_schema(self.sections[PSCH])
        self._names: dict[int, str] = {}

    def _name(self, hash_value: int) -> str:
        cached = self._names.get(hash_value)
        if cached is None:
            cached = self.name_resolver(hash_value)
            self._names[hash_value] = cached
        return cached

    def _hashed_string(self, hash_value: int) -> PsoHashedString:
        return PsoHashedString(hash=hash_value)

    def _node(
        self,
        type_hash: int,
        fields: dict[str, Any] | None = None,
    ) -> PsoNode:
        return PsoNode(
            type_name=self._name(type_hash),
            type_hash=type_hash,
            fields=fields or {},
        )

    def _node_fields(self, value: Any) -> dict[str, Any] | None:
        return value.fields if isinstance(value, PsoNode) else None

    def _empty_hashed_string(self, value: Any) -> bool | None:
        if isinstance(value, PsoHashedString):
            return value.hash == 0 and not value.text
        return None

    def _block_slice(self, pointer: PsoPointer, size: int) -> bytes:
        block = self._get_block(pointer.block_id)
        if block is None:
            return b"\x00" * size
        start = block.offset + pointer.offset
        return self.psin_document.slice(start, size)

    def _read_c_string_pointer(self, pointer: PsoPointer, length: int | None = None) -> str:
        if pointer.is_null:
            return ""
        block = self._get_block(pointer.block_id)
        if block is None:
            return ""
        start = block.offset + pointer.offset
        return self.psin_document.c_string(start, length)

    def _read_inline_string(self, absolute_offset: int, entry: PsoEntry) -> str:
        length = (entry.reference_key >> 16) & 0xFFFF
        return self.psin_document.c_string(absolute_offset, length)

    def _read_string(self, absolute_offset: int, entry: PsoEntry) -> str | PsoHashedString:
        if entry.subtype == 0:
            return self._read_inline_string(absolute_offset, entry)
        if entry.subtype in {1, 2}:
            return self._read_c_string_pointer(decode_pointer(self.psin, absolute_offset))
        if entry.subtype == 3:
            header = decode_array_header(self.psin, absolute_offset)
            count = max(0, header.count - 1)
            return self._read_c_string_pointer(header.pointer, count)
        if entry.subtype in {7, 8}:
            return self._hashed_string(_u32(self.psin, absolute_offset))
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
            return Vector3(
                _f32(self.psin, absolute_offset),
                _f32(self.psin, absolute_offset + 4),
                _f32(self.psin, absolute_offset + 8),
            )
        if type_id in {PsoDataTypeFloat4, PsoDataTypeFloat4a}:
            return Vector4(
                _f32(self.psin, absolute_offset),
                _f32(self.psin, absolute_offset + 4),
                _f32(self.psin, absolute_offset + 8),
                _f32(self.psin, absolute_offset + 12),
            )
        if type_id == PsoDataTypeFloat2:
            return Vector2(
                _f32(self.psin, absolute_offset),
                _f32(self.psin, absolute_offset + 4),
            )
        if type_id == PsoDataTypeHFloat:
            return _u16(self.psin, absolute_offset)
        if type_id == PsoDataTypeLong:
            return _i64(self.psin, absolute_offset)
        return None

    def _read_pointer_target(self, pointer: PsoPointer) -> Any:
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
        empty_hashed_string = self._empty_hashed_string(value)
        if empty_hashed_string is not None:
            return empty_hashed_string
        if isinstance(value, (Vector2, Vector3, Vector4)):
            return all(self._is_empty_value(item) for item in value)
        if isinstance(value, list):
            return all(self._is_empty_value(item) for item in value)
        node_fields = self._node_fields(value)
        if node_fields is not None:
            return all(self._is_empty_value(item) for item in node_fields.values())
        return False

    def _trim_trailing_empty_values(self, values: list[Any]) -> list[Any]:
        end = len(values)
        while end > 0 and self._is_empty_value(values[end - 1]):
            end -= 1
        return values[:end]

    def _get_block(self, block_id: int) -> PsoBlock | None:
        return self.blocks.get(block_id)

    def _read_array_values(self, entry: PsoEntry, array_info: PsoEntry | None, block_id: int, absolute_offset: int) -> list[Any]:
        if array_info is None:
            return []
        if entry.subtype in {0, 3, 5, 6, 7, 8}:
            header = decode_array_header(self.psin, absolute_offset)
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
                pointer = decode_pointer(self.psin, base + index * 8)
                values.append(self._read_pointer_target(pointer))
            return self._trim_trailing_empty_values(values) if inline else values

        if array_info.type_id in {PsoDataTypeBool, PsoDataTypeUByte}:
            values = self.psin_document.read_array(
                base,
                count,
                BinaryScalarType.UNSIGNED_BYTE,
                endian=BinaryEndian.BIG,
            )
            return values if array_info.type_id == PsoDataTypeUByte else [bool(value) for value in values]
        if array_info.type_id == PsoDataTypeUShort:
            return self.psin_document.read_array(
                base, count, BinaryScalarType.UNSIGNED_SHORT, endian=BinaryEndian.BIG
            )
        if array_info.type_id == PsoDataTypeSInt:
            return self.psin_document.read_array(
                base, count, BinaryScalarType.SIGNED_INT, endian=BinaryEndian.BIG
            )
        if array_info.type_id == PsoDataTypeUInt:
            return self.psin_document.read_array(
                base, count, BinaryScalarType.UNSIGNED_INT, endian=BinaryEndian.BIG
            )
        if array_info.type_id == PsoDataTypeFloat:
            return self.psin_document.read_array(
                base, count, BinaryScalarType.FLOAT, endian=BinaryEndian.BIG
            )
        if array_info.type_id == PsoDataTypeFloat2:
            values = self.psin_document.read_array(
                base, count, BinaryScalarType.FLOAT, endian=BinaryEndian.BIG, components=2
            )
            return [Vector2.from_iterable(value) for value in values]
        if array_info.type_id == PsoDataTypeFloat3:
            values = self.psin_document.read_array(
                base,
                count,
                BinaryScalarType.FLOAT,
                endian=BinaryEndian.BIG,
                stride=16,
                components=3,
            )
            return [Vector3.from_iterable(value) for value in values]
        if array_info.type_id == PsoDataTypeString:
            if array_info.subtype in {7, 8}:
                return [
                    self._hashed_string(_u32(self.psin, base + index * 4))
                    for index in range(count)
                ]
            if array_info.subtype in {2, 3}:
                values: list[str] = []
                stride = 8 if array_info.subtype == 2 else 16
                for index in range(count):
                    item_offset = base + index * stride
                    if array_info.subtype == 2:
                        values.append(self._read_c_string_pointer(decode_pointer(self.psin, item_offset)))
                    else:
                        header = decode_array_header(self.psin, item_offset)
                        values.append(self._read_c_string_pointer(header.pointer, max(0, header.count - 1)))
                return values
        return []

    def _read_structure(self, type_hash: int, block_id: int, relative_offset: int) -> PsoNode:
        struct_info = self.structs.get(type_hash)
        if struct_info is None:
            return self._node(type_hash)
        block = self._get_block(block_id)
        if block is None:
            return self._node(type_hash)
        base = block.offset + relative_offset
        fields: dict[str, Any] = {}
        array_info: PsoEntry | None = None
        for entry in struct_info.entries:
            if entry.name_hash == ARRAY_INFO_HASH:
                array_info = entry
                continue
            name = self._name(entry.name_hash)
            absolute_offset = base + entry.data_offset
            match entry.type_id:
                case pso_model.PsoDataTypeString:
                    fields[name] = self._read_string(absolute_offset, entry)
                case pso_model.PsoDataTypeStructure:
                    match entry.subtype:
                        case 0:
                            fields[name] = self._read_structure(
                                entry.reference_key,
                                block_id,
                                relative_offset + entry.data_offset,
                            )
                        case 3 | 4:
                            fields[name] = self._read_pointer_target(
                                decode_pointer(self.psin, absolute_offset)
                            )
                        case _:
                            fields[name] = None
                case pso_model.PsoDataTypeArray:
                    fields[name] = self._read_array_values(
                        entry, array_info, block_id, absolute_offset
                    )
                case pso_model.PsoDataTypeMap:
                    fields[name] = None
                case _:
                    fields[name] = self._read_scalar(absolute_offset, entry.type_id)
        return self._node(type_hash, fields)

    def read(self) -> PsoDocument:
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
                "enums": self.enums,
                "root_type_hash": root_block.name_hash,
                "psin_prefix": bytes(self.sections[PSIN][8:16]),
                "pmap_unknown": _u16(self.sections[PMAP], 14),
                "block_order_hashes": block_order_hashes,
            }
        }
        return PsoDocument(root=root, metadata=metadata)


__all__ = ["PsoReader", "default_hash_name"]
