from __future__ import annotations

import dataclasses
import struct
from typing import Any

from . import (
    FLOAT_XYZ_NAME_HASH,
    RESOURCE_FILE_BASE_SIZE,
    MetaArrayRef,
    MetaDataBlock,
    MetaDataRef,
    MetaEnumEntry,
    MetaEnumInfo,
    MetaFieldInfo,
    MetaPointer,
    MetaStructInfo,
    RawStruct,
)
from .defs import GRAPHICS_BASE, META_TYPE_NAME_ARRAYINFO, STRUCTS_BY_HASH, SYSTEM_BASE, MetaDataType
from .utils import array_info_for_field
from ..resource import parse_rsc7

@dataclasses.dataclass(slots=True)
class ParsedMeta:
    system_data: bytes
    file_vft: int
    file_unknown: int
    file_pages_info_pointer: int
    root_block_index: int
    name: str
    struct_infos: dict[int, MetaStructInfo]
    enum_infos: dict[int, MetaEnumInfo]
    data_blocks: list[MetaDataBlock]
    decoded_root: Any
    resource_version: int | None = None
    system_flags: int | None = None
    graphics_flags: int | None = None

    @classmethod
    def from_bytes(cls, data: bytes) -> "ParsedMeta":
        resource_version = None
        system_flags = None
        graphics_flags = None
        if data[:4] == struct.pack("<I", 0x37435352):
            header, payload = parse_rsc7(data)
            data = payload[: header.system_size]
            resource_version = header.version
            system_flags = header.system_flags
            graphics_flags = header.graphics_flags

        file_vft, file_unknown, file_pages_info_pointer = struct.unpack_from("<IIQ", data, 0)
        root = RESOURCE_FILE_BASE_SIZE
        (
            _unknown_10h,
            _unknown_14h,
            _has_encrypted_strings,
            _unknown_17h,
            _unknown_18h,
            root_block_index,
            structure_infos_pointer,
            enum_infos_pointer,
            data_blocks_pointer,
            name_pointer,
            _encrypted_strings_pointer,
            structure_infos_count,
            enum_infos_count,
            data_blocks_count,
            _unknown_4eh,
            *_rest,
        ) = struct.unpack_from("<ihbbiiqqqqqhhhh8I", data, root)

        struct_infos = _read_struct_infos(data, structure_infos_pointer, structure_infos_count)
        enum_infos = _read_enum_infos(data, enum_infos_pointer, enum_infos_count)
        data_blocks = _read_data_blocks(data, data_blocks_pointer, data_blocks_count)
        name = _read_string_absolute(data, name_pointer)

        parsed = cls(
            system_data=data,
            file_vft=file_vft,
            file_unknown=file_unknown,
            file_pages_info_pointer=file_pages_info_pointer,
            root_block_index=root_block_index,
            name=name,
            struct_infos=struct_infos,
            enum_infos=enum_infos,
            data_blocks=data_blocks,
            decoded_root=None,
            resource_version=resource_version,
            system_flags=system_flags,
            graphics_flags=graphics_flags,
        )
        parsed.decoded_root = parsed.decode_block_by_id(root_block_index)
        return parsed

    def struct_info_for_hash(self, name_hash: int) -> MetaStructInfo | None:
        return self.struct_infos.get(name_hash)

    def block_by_id(self, block_id: int) -> MetaDataBlock | None:
        if block_id <= 0 or block_id > len(self.data_blocks):
            return None
        return self.data_blocks[block_id - 1]

    def decode_block_by_id(self, block_id: int) -> Any:
        block = self.block_by_id(block_id)
        if block is None:
            return None
        return self.decode_struct(block.struct_name_hash, block.data)

    def decode_struct(self, name_hash: int, raw: bytes) -> Any:
        if name_hash == FLOAT_XYZ_NAME_HASH:
            return struct.unpack_from("<fff", raw, 0)
        struct_info = self.struct_infos.get(name_hash)
        struct_def = STRUCTS_BY_HASH.get(name_hash)
        if struct_def and struct_def.opaque and struct_info is None:
            return RawStruct(name_hash, raw[: struct_def.size], None)
        if struct_info is None:
            if struct_def and struct_def.opaque:
                return RawStruct(name_hash, raw[: struct_def.size], None)
            return RawStruct(name_hash, raw, None)

        values: dict[str, Any] = {}
        for index, entry in enumerate(struct_info.entries):
            if entry.name_hash == META_TYPE_NAME_ARRAYINFO:
                continue
            values[entry.name] = self._decode_field(struct_info, index, entry, raw)
        values["_meta_name_hash"] = name_hash
        values["_meta_name"] = struct_info.name
        return values

    def _decode_field(self, struct_info: MetaStructInfo, field_index: int, field: MetaFieldInfo, raw: bytes) -> Any:
        offset = field.data_offset
        data_type = field.data_type
        if data_type is MetaDataType.BOOLEAN:
            return raw[offset] != 0
        if data_type is MetaDataType.SIGNED_BYTE:
            return struct.unpack_from("<b", raw, offset)[0]
        if data_type is MetaDataType.UNSIGNED_BYTE:
            return raw[offset]
        if data_type is MetaDataType.SIGNED_SHORT:
            return struct.unpack_from("<h", raw, offset)[0]
        if data_type is MetaDataType.UNSIGNED_SHORT:
            return struct.unpack_from("<H", raw, offset)[0]
        if data_type is MetaDataType.SIGNED_INT:
            return struct.unpack_from("<i", raw, offset)[0]
        if data_type is MetaDataType.UNSIGNED_INT:
            return struct.unpack_from("<I", raw, offset)[0]
        if data_type is MetaDataType.FLOAT:
            return struct.unpack_from("<f", raw, offset)[0]
        if data_type is MetaDataType.FLOAT_XYZ:
            return struct.unpack_from("<fff", raw, offset)
        if data_type is MetaDataType.FLOAT_XYZW:
            return struct.unpack_from("<ffff", raw, offset)
        if data_type is MetaDataType.HASH:
            return struct.unpack_from("<I", raw, offset)[0]
        if data_type in (MetaDataType.BYTE_ENUM, MetaDataType.INT_ENUM, MetaDataType.INT_FLAGS_1, MetaDataType.INT_FLAGS_2, MetaDataType.SHORT_FLAGS):
            if data_type is MetaDataType.BYTE_ENUM:
                return raw[offset]
            if data_type is MetaDataType.SHORT_FLAGS:
                return struct.unpack_from("<h", raw, offset)[0]
            return struct.unpack_from("<i", raw, offset)[0]
        if data_type is MetaDataType.ARRAY_OF_CHARS:
            length = field.reference_key & 0xFFFF
            end = raw.find(b"\x00", offset, offset + length)
            if end == -1:
                end = offset + length
            return raw[offset:end].decode("ascii", errors="ignore")
        if data_type is MetaDataType.ARRAY_OF_BYTES:
            count = field.reference_key & 0xFFFF
            array_info = array_info_for_field(struct_info, field_index)
            if array_info is None:
                return bytes(raw[offset : offset + count])
            return _unpack_inline_array(array_info.data_type, raw[offset:], count)
        if data_type is MetaDataType.CHAR_POINTER:
            ref = MetaArrayRef.from_bytes(raw, offset)
            return self._resolve_char_pointer(ref)
        if data_type is MetaDataType.DATA_BLOCK_POINTER:
            ref = MetaDataRef.from_bytes(raw, offset)
            return self._resolve_data_pointer(ref)
        if data_type is MetaDataType.STRUCTURE_POINTER:
            pointer = MetaDataRef.from_bytes(raw, offset).pointer
            return self._resolve_struct_pointer(pointer)
        if data_type is MetaDataType.STRUCTURE:
            nested_hash = field.reference_key
            return self._decode_inline_structure(nested_hash, raw[offset:])
        if data_type is MetaDataType.ARRAY:
            array_ref = MetaArrayRef.from_bytes(raw, offset)
            return self._resolve_array(struct_info, field_index, array_ref)
        return None

    def _resolve_char_pointer(self, array_ref: MetaArrayRef) -> str:
        if array_ref.pointer.is_null or array_ref.count == 0:
            return ""
        block = self.block_by_id(array_ref.pointer.block_id)
        if block is None:
            return ""
        start = array_ref.pointer.offset
        end = start + array_ref.count
        return block.data[start:end].decode("ascii", errors="ignore")

    def _resolve_data_pointer(self, data_ref: MetaDataRef) -> bytes:
        if data_ref.pointer.is_null:
            return b""
        block = self.block_by_id(data_ref.pointer.block_id)
        if block is None:
            return b""
        return bytes(block.data[data_ref.pointer.offset :])

    def _resolve_struct_pointer(self, pointer: MetaPointer) -> Any:
        if pointer.is_null:
            return None
        block = self.block_by_id(pointer.block_id)
        if block is None:
            return None
        struct_info = self.struct_infos.get(block.struct_name_hash)
        if struct_info is None:
            struct_def = STRUCTS_BY_HASH.get(block.struct_name_hash)
            if struct_def is None:
                return RawStruct(block.struct_name_hash, block.data[pointer.offset :], None)
            size = struct_def.size
            return RawStruct(block.struct_name_hash, block.data[pointer.offset : pointer.offset + size], None)
        size = struct_info.structure_size
        return self.decode_struct(block.struct_name_hash, block.data[pointer.offset : pointer.offset + size])

    def _decode_inline_structure(self, name_hash: int, raw: bytes) -> Any:
        struct_info = self.struct_infos.get(name_hash)
        struct_def = STRUCTS_BY_HASH.get(name_hash)
        if struct_info is not None:
            return self.decode_struct(name_hash, raw[: struct_info.structure_size])
        if struct_def is not None:
            if struct_def.opaque:
                return RawStruct(name_hash, raw[: struct_def.size], None)
            return self.decode_struct(name_hash, raw[: struct_def.size])
        return raw

    def _resolve_array(self, struct_info: MetaStructInfo, field_index: int, array_ref: MetaArrayRef) -> Any:
        if array_ref.pointer.is_null or array_ref.count == 0:
            return []
        if field_index >= len(struct_info.entries):
            return []
        array_info = array_info_for_field(struct_info, field_index)
        if array_info is None:
            return []
        block = self.block_by_id(array_ref.pointer.block_id)
        if block is None:
            return []
        start = array_ref.pointer.offset
        end = len(block.data)
        data = block.data[start:end]
        element_type = array_info.data_type
        if element_type is MetaDataType.STRUCTURE_POINTER:
            items = []
            for index in range(array_ref.count):
                pointer_value = struct.unpack_from("<Q", data, index * 8)[0]
                items.append(self._resolve_struct_pointer(MetaPointer.from_uint64(pointer_value)))
            return items
        if element_type is MetaDataType.STRUCTURE:
            nested_hash = array_info.reference_key
            nested_info = self.struct_infos.get(nested_hash)
            nested_def = STRUCTS_BY_HASH.get(nested_hash)
            size = nested_info.structure_size if nested_info is not None else (nested_def.size if nested_def is not None else 0)
            if size <= 0:
                return [RawStruct(nested_hash, data, nested_info)]
            items = []
            for index in range(array_ref.count):
                chunk = data[index * size : (index + 1) * size]
                items.append(self._decode_inline_structure(nested_hash, chunk))
            return items
        if element_type is MetaDataType.FLOAT:
            return [value[0] for value in struct.iter_unpack("<f", data[: array_ref.count * 4])]
        if element_type is MetaDataType.UNSIGNED_INT:
            return [value[0] for value in struct.iter_unpack("<I", data[: array_ref.count * 4])]
        if element_type is MetaDataType.UNSIGNED_SHORT:
            return [value[0] for value in struct.iter_unpack("<H", data[: array_ref.count * 2])]
        if element_type is MetaDataType.UNSIGNED_BYTE:
            return list(data[: array_ref.count])
        if element_type is MetaDataType.HASH:
            return [value[0] for value in struct.iter_unpack("<I", data[: array_ref.count * 4])]
        if element_type is MetaDataType.FLOAT_XYZ:
            return [value for value in struct.iter_unpack("<fff", data[: array_ref.count * 12])]
        return bytes(data)


def _absolute_to_offset(pointer: int) -> int:
    if pointer == 0:
        return 0
    if pointer >= GRAPHICS_BASE:
        return pointer - GRAPHICS_BASE
    if pointer >= SYSTEM_BASE:
        return pointer - SYSTEM_BASE
    return pointer


def _read_struct_infos(data: bytes, pointer: int, count: int) -> dict[int, MetaStructInfo]:
    if pointer == 0 or count <= 0:
        return {}
    base_offset = _absolute_to_offset(pointer)
    infos: dict[int, MetaStructInfo] = {}
    for index in range(count):
        off = base_offset + index * 32
        name_hash, key, unknown, unknown_ch, entries_pointer, structure_size, unknown_1ch, entries_count = struct.unpack_from(
            "<IIIIqihh", data, off
        )
        entries_offset = _absolute_to_offset(entries_pointer)
        entries = [
            MetaFieldInfo.from_bytes(data, entries_offset + entry_index * 16)
            for entry_index in range(entries_count)
        ]
        infos[name_hash] = MetaStructInfo(
            name_hash=name_hash,
            key=key,
            unknown=unknown,
            structure_size=structure_size,
            entries=entries,
            unknown_ch=unknown_ch,
            unknown_1ch=unknown_1ch,
        )
    return infos


def _read_enum_infos(data: bytes, pointer: int, count: int) -> dict[int, MetaEnumInfo]:
    if pointer == 0 or count <= 0:
        return {}
    base_offset = _absolute_to_offset(pointer)
    infos: dict[int, MetaEnumInfo] = {}
    for index in range(count):
        off = base_offset + index * 24
        name_hash, key, entries_pointer, entries_count, unknown_14h = struct.unpack_from("<IIqii", data, off)
        entries_offset = _absolute_to_offset(entries_pointer)
        entries = [
            MetaEnumEntry(*struct.unpack_from("<Ii", data, entries_offset + entry_index * 8))
            for entry_index in range(entries_count)
        ]
        infos[name_hash] = MetaEnumInfo(name_hash=name_hash, key=key, entries=entries, unknown_14h=unknown_14h)
    return infos


def _read_data_blocks(data: bytes, pointer: int, count: int) -> list[MetaDataBlock]:
    if pointer == 0 or count <= 0:
        return []
    base_offset = _absolute_to_offset(pointer)
    blocks: list[MetaDataBlock] = []
    for index in range(count):
        off = base_offset + index * 16
        name_hash, data_length, data_pointer = struct.unpack_from("<IIq", data, off)
        data_offset = _absolute_to_offset(data_pointer)
        block_data = bytes(data[data_offset : data_offset + data_length])
        blocks.append(MetaDataBlock(index=index + 1, struct_name_hash=name_hash, data=block_data))
    return blocks


def _read_string_absolute(data: bytes, pointer: int) -> str:
    if pointer == 0:
        return ""
    offset = _absolute_to_offset(pointer)
    end = data.find(b"\x00", offset)
    if end == -1:
        end = len(data)
    return data[offset:end].decode("ascii", errors="ignore")


def read_meta(data: bytes) -> ParsedMeta:
    return ParsedMeta.from_bytes(data)

def _inline_array_format(data_type: MetaDataType) -> tuple[str, int] | None:
    if data_type is MetaDataType.FLOAT:
        return "<f", 4
    if data_type in (MetaDataType.UNSIGNED_INT, MetaDataType.HASH):
        return "<I", 4
    if data_type is MetaDataType.SIGNED_INT:
        return "<i", 4
    if data_type is MetaDataType.UNSIGNED_SHORT:
        return "<H", 2
    if data_type is MetaDataType.SIGNED_SHORT:
        return "<h", 2
    if data_type is MetaDataType.UNSIGNED_BYTE:
        return "<B", 1
    if data_type is MetaDataType.SIGNED_BYTE:
        return "<b", 1
    return None


def _unpack_inline_array(data_type: MetaDataType, raw: bytes, count: int) -> Any:
    if count <= 0:
        return tuple()
    if data_type is MetaDataType.UNSIGNED_BYTE:
        return tuple(raw[:count])
    fmt = _inline_array_format(data_type)
    if fmt is None:
        return bytes(raw[:count])
    pack_fmt, size = fmt
    limit = count * size
    return tuple(value[0] for value in struct.iter_unpack(pack_fmt, raw[:limit]))





