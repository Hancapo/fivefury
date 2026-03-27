from __future__ import annotations

import dataclasses
import struct
from collections.abc import Iterable, Mapping
from typing import Any

from .binary import align, pad_bytes
from .metahash import MetaHash
from .meta_defs import (
    ENUMS_BY_HASH,
    GRAPHICS_BASE,
    KNOWN_STRUCTS,
    META_NAME_REVERSE,
    META_TYPE_NAME_ARRAYINFO,
    META_TYPE_NAME_BYTE,
    META_TYPE_NAME_FLOAT,
    META_TYPE_NAME_HASH,
    META_TYPE_NAME_POINTER,
    META_TYPE_NAME_STRING,
    META_TYPE_NAME_UINT,
    META_TYPE_NAME_USHORT,
    STRUCTS_BY_HASH,
    SYSTEM_BASE,
    EnumDef,
    MetaDataType,
    StructDef,
)
from .hashing import jenk_hash
from .resource import build_rsc7, parse_rsc7


META_FILE_VFT = 0x405BC808
META_ROOT_SIZE = 112
RESOURCE_FILE_BASE_SIZE = 16
RESOURCE_PAGES_INFO_SIZE = 16
FLOAT_XYZ_NAME_HASH = jenk_hash("FloatXYZ")


@dataclasses.dataclass(slots=True, frozen=True)
class MetaPointer:
    block_id: int
    offset: int

    @classmethod
    def from_uint64(cls, value: int) -> "MetaPointer":
        return cls(value & 0xFFF, (value >> 12) & 0xFFFFF)

    @property
    def value(self) -> int:
        return ((self.offset & 0xFFFFF) << 12) | (self.block_id & 0xFFF)

    @property
    def is_null(self) -> bool:
        return self.block_id == 0


@dataclasses.dataclass(slots=True, frozen=True)
class MetaArrayRef:
    pointer: MetaPointer
    count: int
    capacity: int
    unknown: int = 0

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "MetaArrayRef":
        pointer_value, count, capacity, unknown = struct.unpack_from("<QHHI", data, offset)
        return cls(MetaPointer.from_uint64(pointer_value), count, capacity, unknown)

    def to_bytes(self) -> bytes:
        return struct.pack("<QHHI", self.pointer.value, self.count, self.capacity, self.unknown)


@dataclasses.dataclass(slots=True, frozen=True)
class MetaDataRef:
    pointer: MetaPointer

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "MetaDataRef":
        (pointer_value,) = struct.unpack_from("<Q", data, offset)
        return cls(MetaPointer.from_uint64(pointer_value))

    def to_bytes(self) -> bytes:
        return struct.pack("<Q", self.pointer.value)


@dataclasses.dataclass(slots=True, frozen=True)
class MetaFieldInfo:
    name_hash: int
    data_offset: int
    data_type: MetaDataType
    unknown_9h: int
    reference_type_index: int
    reference_key: int

    @classmethod
    def from_bytes(cls, data: bytes, offset: int) -> "MetaFieldInfo":
        name_hash, data_offset, data_type, unknown_9h, ref_index, ref_key = struct.unpack_from(
            "<IIBBH I".replace(" ", ""), data, offset
        )
        return cls(
            name_hash=name_hash,
            data_offset=data_offset,
            data_type=MetaDataType(data_type),
            unknown_9h=unknown_9h,
            reference_type_index=ref_index,
            reference_key=ref_key,
        )

    @property
    def name(self) -> str:
        return META_NAME_REVERSE.get(self.name_hash, f"0x{self.name_hash:08X}")


@dataclasses.dataclass(slots=True)
class MetaStructInfo:
    name_hash: int
    key: int
    unknown: int
    structure_size: int
    entries: list[MetaFieldInfo]
    unknown_ch: int = 0
    unknown_1ch: int = 0

    @property
    def name(self) -> str:
        return META_NAME_REVERSE.get(self.name_hash, f"0x{self.name_hash:08X}")


@dataclasses.dataclass(slots=True)
class MetaEnumEntry:
    name_hash: int
    value: int

    @property
    def name(self) -> str:
        return META_NAME_REVERSE.get(self.name_hash, f"0x{self.name_hash:08X}")


@dataclasses.dataclass(slots=True)
class MetaEnumInfo:
    name_hash: int
    key: int
    entries: list[MetaEnumEntry]
    unknown_14h: int = 0

    @property
    def name(self) -> str:
        return META_NAME_REVERSE.get(self.name_hash, f"0x{self.name_hash:08X}")


@dataclasses.dataclass(slots=True)
class MetaDataBlock:
    index: int
    struct_name_hash: int
    data: bytes

    @property
    def struct_name(self) -> str:
        return META_NAME_REVERSE.get(self.struct_name_hash, f"0x{self.struct_name_hash:08X}")


@dataclasses.dataclass(slots=True)
class RawStruct:
    name_hash: int
    data: bytes
    struct_info: MetaStructInfo | None = None

    @property
    def name(self) -> str:
        return META_NAME_REVERSE.get(self.name_hash, f"0x{self.name_hash:08X}")


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
            array_info = self._array_info_for_field(struct_info, field_index)
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

    def _array_info_for_field(self, struct_info: MetaStructInfo, field_index: int) -> MetaFieldInfo | None:
        if not (0 <= field_index < len(struct_info.entries)):
            return None
        if field_index > 0 and struct_info.entries[field_index - 1].name_hash == META_TYPE_NAME_ARRAYINFO:
            return struct_info.entries[field_index - 1]
        ref_index = struct_info.entries[field_index].reference_type_index
        if 0 <= ref_index < len(struct_info.entries):
            candidate = struct_info.entries[ref_index]
            if candidate.name_hash == META_TYPE_NAME_ARRAYINFO:
                return candidate
        return None

    def _resolve_array(self, struct_info: MetaStructInfo, field_index: int, array_ref: MetaArrayRef) -> Any:
        if array_ref.pointer.is_null or array_ref.count == 0:
            return []
        if field_index >= len(struct_info.entries):
            return []
        array_info = self._array_info_for_field(struct_info, field_index)
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


@dataclasses.dataclass(slots=True)
class Meta:
    Name: str = ""
    root_name_hash: int = 0
    root_value: Mapping[str, Any] | RawStruct | None = None
    struct_infos: list[MetaStructInfo] = dataclasses.field(default_factory=list)
    enum_infos: list[MetaEnumInfo] = dataclasses.field(default_factory=list)
    resource_version: int = 2

    @property
    def name(self) -> str:
        return self.Name

    @name.setter
    def name(self, value: str) -> None:
        self.Name = value

    def to_bytes(self) -> bytes:
        if self.root_name_hash == 0 or self.root_value is None:
            return build_meta_system(
                root_name_hash=0,
                root_value=None,
                struct_infos=self.struct_infos,
                enum_infos=self.enum_infos,
                name=self.Name,
            )
        return build_meta_system(
            root_name_hash=self.root_name_hash,
            root_value=self.root_value,
            struct_infos=self.struct_infos,
            enum_infos=self.enum_infos,
            name=self.Name,
        )

    def to_rsc7(self) -> bytes:
        return build_rsc7(self.to_bytes(), version=self.resource_version, system_alignment=0x2000)

    @classmethod
    def from_bytes(cls, data: bytes) -> "Meta":
        parsed = ParsedMeta.from_bytes(data)
        meta = cls(
            Name=parsed.name,
            root_name_hash=parsed.data_blocks[parsed.root_block_index - 1].struct_name_hash if parsed.root_block_index > 0 and parsed.data_blocks else 0,
            root_value=parsed.decoded_root,
            struct_infos=list(parsed.struct_infos.values()),
            enum_infos=list(parsed.enum_infos.values()),
            resource_version=parsed.resource_version or 2,
        )
        return meta


@dataclasses.dataclass(slots=True)
class _WritableBlock:
    name_hash: int
    data: bytes = b""


class MetaBuilder:
    MAX_BLOCK_LENGTH = 0x4000

    def __init__(
        self,
        *,
        struct_infos: Iterable[MetaStructInfo] = (),
        enum_infos: Iterable[MetaEnumInfo] = (),
        name: str = "",
    ) -> None:
        struct_info_list = list(struct_infos)
        enum_info_list = list(enum_infos)
        self.name = name
        self.struct_infos: dict[int, MetaStructInfo] = {info.name_hash: info for info in struct_info_list}
        self.enum_infos: dict[int, MetaEnumInfo] = {info.name_hash: info for info in enum_info_list}
        self.struct_info_order: list[int] = [info.name_hash for info in struct_info_list]
        self.enum_info_order: list[int] = [info.name_hash for info in enum_info_list]
        self.used_struct_hashes: set[int] = set()
        self.used_enum_hashes: set[int] = set()
        self.blocks: list[_WritableBlock] = []

    def register_struct(self, info: MetaStructInfo) -> None:
        if info.name_hash not in self.struct_infos:
            self.struct_info_order.append(info.name_hash)
        self.struct_infos[info.name_hash] = info

    def register_enum(self, info: MetaEnumInfo) -> None:
        if info.name_hash not in self.enum_infos:
            self.enum_info_order.append(info.name_hash)
        self.enum_infos[info.name_hash] = info

    def build(self, root_name_hash: int = 0, root_value: Mapping[str, Any] | RawStruct | None = None) -> bytes:
        self.blocks.clear()
        self.used_struct_hashes.clear()
        self.used_enum_hashes.clear()
        if root_name_hash and root_value is not None:
            root_block_id = self._reserve_block(root_name_hash)
            root_payload = self._encode_struct_payload(root_name_hash, root_value)
            self._set_block(root_block_id, root_payload)
        else:
            root_block_id = 0
        return self._compose_system_stream(root_block_id)

    def _reserve_block(self, name_hash: int) -> int:
        self.blocks.append(_WritableBlock(name_hash=name_hash))
        return len(self.blocks)

    def _set_block(self, block_id: int, data: bytes) -> None:
        self.blocks[block_id - 1].data = pad_bytes(data, 16)

    def _add_block(
        self,
        name_hash: int,
        data: bytes,
        *,
        align_item: int = 16,
        group: bool = True,
    ) -> MetaPointer:
        item = pad_bytes(data, align_item) if align_item > 1 else bytes(data)
        if group:
            for index, block in enumerate(self.blocks):
                if block.name_hash != name_hash:
                    continue
                if len(block.data) + len(item) > self.MAX_BLOCK_LENGTH:
                    continue
                pointer = MetaPointer(block_id=index + 1, offset=len(block.data))
                self.blocks[index].data = block.data + item
                return pointer
        block_id = self._reserve_block(name_hash)
        self.blocks[block_id - 1].data = item
        return MetaPointer(block_id=block_id, offset=0)

    def _lookup_struct_info(self, name_hash: int) -> MetaStructInfo:
        info = self.struct_infos.get(name_hash)
        if info is not None:
            return info
        struct_def = STRUCTS_BY_HASH.get(name_hash)
        if struct_def is None:
            raise KeyError(f"No structure info registered for 0x{name_hash:08X}")
        if struct_def.opaque:
            raise KeyError(f"Opaque structure 0x{name_hash:08X} needs explicit MetaStructInfo")
        raise KeyError(f"Explicit MetaStructInfo required for 0x{name_hash:08X}")

    def _mark_enum_used(self, name_hash: int) -> None:
        if name_hash in self.enum_infos:
            self.used_enum_hashes.add(name_hash)

    def _mark_struct_used(self, name_hash: int) -> None:
        if name_hash in self.used_struct_hashes:
            return
        struct_info = self.struct_infos.get(name_hash)
        if struct_info is None:
            return
        self.used_struct_hashes.add(name_hash)
        for entry in struct_info.entries:
            if entry.name_hash == META_TYPE_NAME_ARRAYINFO:
                continue
            if entry.data_type in (
                MetaDataType.BYTE_ENUM,
                MetaDataType.INT_ENUM,
                MetaDataType.INT_FLAGS_1,
                MetaDataType.INT_FLAGS_2,
                MetaDataType.SHORT_FLAGS,
            ):
                self._mark_enum_used(entry.reference_key)
            elif entry.data_type is MetaDataType.STRUCTURE and entry.reference_key:
                self._mark_struct_used(entry.reference_key)

    def _array_info_for_field(self, struct_info: MetaStructInfo, field_index: int) -> MetaFieldInfo | None:
        if not (0 <= field_index < len(struct_info.entries)):
            return None
        if field_index > 0 and struct_info.entries[field_index - 1].name_hash == META_TYPE_NAME_ARRAYINFO:
            return struct_info.entries[field_index - 1]
        ref_index = struct_info.entries[field_index].reference_type_index
        if 0 <= ref_index < len(struct_info.entries):
            candidate = struct_info.entries[ref_index]
            if candidate.name_hash == META_TYPE_NAME_ARRAYINFO:
                return candidate
        return None

    def _encode_struct_payload(self, name_hash: int, value: Mapping[str, Any] | RawStruct) -> bytes:
        self._mark_struct_used(name_hash)
        if name_hash == FLOAT_XYZ_NAME_HASH:
            x, y, z = _coerce_float_xyz(value)
            return struct.pack("<ffff", x, y, z, 0.0)
        if isinstance(value, RawStruct):
            return pad_bytes(value.data, 16)
        struct_info = self._lookup_struct_info(name_hash)
        payload = bytearray(struct_info.structure_size)
        for index, entry in enumerate(struct_info.entries):
            if entry.name_hash == META_TYPE_NAME_ARRAYINFO:
                continue
            field_value = self._field_value(value, entry.name)
            encoded = self._encode_field(struct_info, index, entry, field_value)
            offset = entry.data_offset
            payload[offset : offset + len(encoded)] = encoded
        return bytes(payload)

    def _field_value(self, value: Mapping[str, Any], field_name: str) -> Any:
        if field_name in value:
            return value[field_name]
        snake_name = _camel_to_snake(field_name)
        return value.get(snake_name)

    def _encode_field(self, struct_info: MetaStructInfo, field_index: int, field: MetaFieldInfo, value: Any) -> bytes:
        data_type = field.data_type
        if data_type is MetaDataType.BOOLEAN:
            return struct.pack("<?", bool(value))
        if data_type is MetaDataType.SIGNED_BYTE:
            return struct.pack("<b", int(value or 0))
        if data_type is MetaDataType.UNSIGNED_BYTE:
            return struct.pack("<B", int(value or 0))
        if data_type is MetaDataType.SIGNED_SHORT:
            return struct.pack("<h", int(value or 0))
        if data_type is MetaDataType.UNSIGNED_SHORT:
            return struct.pack("<H", int(value or 0))
        if data_type is MetaDataType.SIGNED_INT:
            return struct.pack("<i", int(value or 0))
        if data_type is MetaDataType.UNSIGNED_INT:
            return struct.pack("<I", int(value or 0))
        if data_type is MetaDataType.FLOAT:
            return struct.pack("<f", float(value or 0.0))
        if data_type is MetaDataType.FLOAT_XYZ:
            x, y, z = _coerce_vector(value, 3)
            return struct.pack("<fff", x, y, z)
        if data_type is MetaDataType.FLOAT_XYZW:
            x, y, z, w = _coerce_vector(value, 4)
            return struct.pack("<ffff", x, y, z, w)
        if data_type is MetaDataType.HASH:
            return struct.pack("<I", _coerce_hash(value))
        if data_type is MetaDataType.BYTE_ENUM:
            return struct.pack("<B", int(value or 0))
        if data_type is MetaDataType.INT_ENUM:
            return struct.pack("<i", int(value or 0))
        if data_type is MetaDataType.SHORT_FLAGS:
            return struct.pack("<h", int(value or 0))
        if data_type in (MetaDataType.INT_FLAGS_1, MetaDataType.INT_FLAGS_2):
            return struct.pack("<i", int(value or 0))
        if data_type is MetaDataType.ARRAY_OF_CHARS:
            length = field.reference_key & 0xFFFF
            text = (value or "").encode("ascii", errors="ignore")[:length]
            return text + (b"\x00" * (length - len(text)))
        if data_type is MetaDataType.ARRAY_OF_BYTES:
            count = field.reference_key & 0xFFFF
            array_info = self._array_info_for_field(struct_info, field_index)
            if array_info is None:
                raw = bytes(value or b"")[:count]
                return raw + (b"\x00" * (count - len(raw)))
            return _pack_inline_array(array_info.data_type, value, count)
        if data_type is MetaDataType.CHAR_POINTER:
            if not value:
                return MetaArrayRef(MetaPointer(0, 0), 0, 0, 0).to_bytes()
            raw = str(value).encode("ascii", errors="ignore") + b"\x00"
            pointer = self._add_block(META_TYPE_NAME_STRING, raw, align_item=1, group=True)
            return MetaArrayRef(pointer, len(raw) - 1, len(raw) - 1, 0).to_bytes()
        if data_type is MetaDataType.DATA_BLOCK_POINTER:
            raw = bytes(value or b"")
            if not raw:
                return MetaDataRef(MetaPointer(0, 0)).to_bytes()
            target_hash = field.reference_key if field.reference_key not in (0, 2) else META_TYPE_NAME_BYTE
            pointer = self._add_block(target_hash, raw, align_item=1, group=False)
            return MetaDataRef(pointer).to_bytes()
        if data_type is MetaDataType.STRUCTURE_POINTER:
            if value is None:
                return MetaDataRef(MetaPointer(0, 0)).to_bytes()
            target_hash = _value_struct_hash(value, fallback=field.reference_key)
            self._mark_struct_used(target_hash)
            pointer = self._add_block(target_hash, self._encode_struct_payload(target_hash, value))
            return MetaDataRef(pointer).to_bytes()
        if data_type is MetaDataType.STRUCTURE:
            target_hash = field.reference_key or _value_struct_hash(value, fallback=0)
            self._mark_struct_used(target_hash)
            if value is None:
                nested_info = self.struct_infos.get(field.reference_key)
                if nested_info is not None:
                    return bytes(nested_info.structure_size)
                nested_def = STRUCTS_BY_HASH.get(field.reference_key)
                if nested_def is not None:
                    return bytes(nested_def.size)
                raise KeyError(f"No size information available for inline structure 0x{field.reference_key:08X}")
            return self._encode_struct_payload(target_hash, value)
        if data_type is MetaDataType.ARRAY:
            return self._encode_array(struct_info, field_index, value)
        raise NotImplementedError(f"Unsupported META field type {data_type}")

    def _encode_array(self, struct_info: MetaStructInfo, field_index: int, value: Any) -> bytes:
        items = list(value or [])
        if field_index <= 0:
            return MetaArrayRef(MetaPointer(0, 0), 0, 0, 0).to_bytes()
        array_info = self._array_info_for_field(struct_info, field_index)
        if array_info is None:
            return MetaArrayRef(MetaPointer(0, 0), 0, 0, 0).to_bytes()
        element_type = array_info.data_type
        if not items:
            return MetaArrayRef(MetaPointer(0, 0), 0, 0, 0).to_bytes()
        if element_type is MetaDataType.STRUCTURE_POINTER:
            raw = bytearray()
            for item in items:
                target_hash = _value_struct_hash(item, fallback=0)
                self._mark_struct_used(target_hash)
                pointer = self._add_block(target_hash, self._encode_struct_payload(target_hash, item))
                raw.extend(struct.pack("<Q", pointer.value))
            pointer = self._add_block(META_TYPE_NAME_POINTER, bytes(raw), align_item=16, group=True)
            return MetaArrayRef(pointer, len(items), len(items), 0).to_bytes()
        if element_type is MetaDataType.STRUCTURE:
            target_hash = array_info.reference_key
            self._mark_struct_used(target_hash)
            raw = bytearray()
            for item in items:
                raw.extend(self._encode_struct_payload(target_hash, item))
            pointer = self._add_block(target_hash, bytes(raw), align_item=16, group=True)
            return MetaArrayRef(pointer, len(items), len(items), 0).to_bytes()
        raw = _pack_primitive_array(element_type, items)
        block_type = _primitive_block_hash(element_type)
        pointer = self._add_block(block_type, raw, align_item=16, group=True)
        return MetaArrayRef(pointer, len(items), len(items), 0).to_bytes()

    def _compose_system_stream(self, root_block_id: int) -> bytes:
        struct_infos = [self.struct_infos[name_hash] for name_hash in self.struct_info_order if name_hash in self.used_struct_hashes]
        enum_infos = [self.enum_infos[name_hash] for name_hash in self.enum_info_order if name_hash in self.used_enum_hashes]
        offset = RESOURCE_FILE_BASE_SIZE + META_ROOT_SIZE

        struct_entry_offsets: dict[int, int] = {}
        struct_entry_payloads: list[tuple[MetaStructInfo, bytes, int]] = []
        for info in struct_infos:
            payload = b"".join(
                struct.pack(
                    "<IIBBHI",
                    entry.name_hash,
                    entry.data_offset,
                    int(entry.data_type),
                    entry.unknown_9h,
                    entry.reference_type_index,
                    entry.reference_key,
                )
                for entry in info.entries
            )
            struct_entry_offsets[info.name_hash] = offset
            struct_entry_payloads.append((info, payload, offset))
            offset += len(payload)

        enum_entry_offsets: dict[int, int] = {}
        enum_entry_payloads: list[tuple[MetaEnumInfo, bytes, int]] = []
        for info in enum_infos:
            payload = b"".join(struct.pack("<Ii", entry.name_hash, entry.value) for entry in info.entries)
            enum_entry_offsets[info.name_hash] = offset
            enum_entry_payloads.append((info, payload, offset))
            offset += len(payload)

        struct_infos_offset = offset if struct_infos else 0
        offset += len(struct_infos) * 32

        enum_infos_offset = offset if enum_infos else 0
        offset += len(enum_infos) * 24

        data_blocks_offset = offset if self.blocks else 0
        offset += len(self.blocks) * 16

        name_bytes = self.name.encode("ascii", errors="ignore") + b"\x00" if self.name else b""
        name_offset = offset if name_bytes else 0
        offset += len(name_bytes)

        offset = align(offset, 16)
        block_offsets: list[int] = []
        for block in self.blocks:
            block_offsets.append(offset)
            offset += len(block.data)

        pages_info_offset = offset
        pages_info = struct.pack("<IIBBHI", 0, 0, 1, 0, 0, 0) + (b"\x00" * 8)
        offset += len(pages_info)

        system = bytearray(offset)

        struct.pack_into("<IIQ", system, 0, META_FILE_VFT, 1, SYSTEM_BASE + pages_info_offset)
        struct.pack_into(
            "<ihbbiiqqqqqhhhh8I",
            system,
            RESOURCE_FILE_BASE_SIZE,
            0x50524430,
            0x0079,
            0,
            0,
            0,
            root_block_id,
            SYSTEM_BASE + struct_infos_offset if struct_infos_offset else 0,
            SYSTEM_BASE + enum_infos_offset if enum_infos_offset else 0,
            SYSTEM_BASE + data_blocks_offset if data_blocks_offset else 0,
            SYSTEM_BASE + name_offset if name_offset else 0,
            0,
            len(struct_infos),
            len(enum_infos),
            len(self.blocks),
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )

        for info, payload, entry_offset in struct_entry_payloads:
            system[entry_offset : entry_offset + len(payload)] = payload
        for info, payload, entry_offset in enum_entry_payloads:
            system[entry_offset : entry_offset + len(payload)] = payload

        for index, info in enumerate(struct_infos):
            off = struct_infos_offset + index * 32
            struct.pack_into(
                "<IIIIqihh",
                system,
                off,
                info.name_hash,
                info.key,
                info.unknown,
                info.unknown_ch,
                SYSTEM_BASE + struct_entry_offsets[info.name_hash],
                info.structure_size,
                info.unknown_1ch,
                len(info.entries),
            )

        for index, info in enumerate(enum_infos):
            off = enum_infos_offset + index * 24
            struct.pack_into(
                "<IIqii",
                system,
                off,
                info.name_hash,
                info.key,
                SYSTEM_BASE + enum_entry_offsets[info.name_hash],
                len(info.entries),
                info.unknown_14h,
            )

        for index, block in enumerate(self.blocks):
            off = data_blocks_offset + index * 16
            struct.pack_into(
                "<IIq",
                system,
                off,
                block.name_hash,
                len(block.data),
                SYSTEM_BASE + block_offsets[index],
            )
            block_offset = block_offsets[index]
            system[block_offset : block_offset + len(block.data)] = block.data

        if name_bytes:
            system[name_offset : name_offset + len(name_bytes)] = name_bytes
        system[pages_info_offset : pages_info_offset + len(pages_info)] = pages_info
        return bytes(system)


def build_meta_system(
    *,
    root_name_hash: int = 0,
    root_value: Mapping[str, Any] | RawStruct | None = None,
    struct_infos: Iterable[MetaStructInfo] = (),
    enum_infos: Iterable[MetaEnumInfo] = (),
    name: str = "",
) -> bytes:
    return MetaBuilder(struct_infos=struct_infos, enum_infos=enum_infos, name=name).build(
        root_name_hash=root_name_hash,
        root_value=root_value,
    )


def _pack_primitive_array(data_type: MetaDataType, items: list[Any]) -> bytes:
    if data_type is MetaDataType.FLOAT:
        return b"".join(struct.pack("<f", float(item)) for item in items)
    if data_type in (MetaDataType.UNSIGNED_INT, MetaDataType.HASH):
        return b"".join(struct.pack("<I", _coerce_hash(item) if data_type is MetaDataType.HASH else int(item)) for item in items)
    if data_type is MetaDataType.UNSIGNED_SHORT:
        return b"".join(struct.pack("<H", int(item)) for item in items)
    if data_type is MetaDataType.UNSIGNED_BYTE:
        return bytes(int(item) & 0xFF for item in items)
    if data_type is MetaDataType.FLOAT_XYZ:
        return b"".join(struct.pack("<fff", *_coerce_vector(item, 3)) for item in items)
    raise NotImplementedError(f"Unsupported array element type {data_type}")


def _primitive_block_hash(data_type: MetaDataType) -> int:
    if data_type is MetaDataType.FLOAT:
        return META_TYPE_NAME_FLOAT
    if data_type is MetaDataType.HASH:
        return META_TYPE_NAME_HASH
    if data_type is MetaDataType.UNSIGNED_INT:
        return META_TYPE_NAME_UINT
    if data_type is MetaDataType.UNSIGNED_SHORT:
        return META_TYPE_NAME_USHORT
    if data_type is MetaDataType.UNSIGNED_BYTE:
        return 0x11
    if data_type is MetaDataType.FLOAT_XYZ:
        return 3805007828
    raise NotImplementedError(f"No primitive block hash for {data_type}")


def _coerce_hash(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, MetaHash):
        return int(value)
    if isinstance(value, str):
        return jenk_hash(value)
    return int(value)


def _coerce_vector(value: Any, size: int) -> tuple[float, ...]:
    if value is None:
        return tuple(0.0 for _ in range(size))
    if len(value) != size:
        raise ValueError(f"Expected vector of length {size}")
    return tuple(float(component) for component in value)


def _value_struct_hash(value: Any, *, fallback: int) -> int:
    if isinstance(value, RawStruct):
        return value.name_hash
    if isinstance(value, Mapping):
        meta_name_hash = value.get("_meta_name_hash")
        if meta_name_hash:
            return int(meta_name_hash)
    if fallback:
        return fallback
    raise ValueError("Structure hash is required for pointer/inline structure encoding")


def _camel_to_snake(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0 and not value[index - 1].isupper():
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _coerce_float_xyz(value: Any) -> tuple[float, float, float]:
    if isinstance(value, Mapping):
        return (
            float(value.get("x", 0.0)),
            float(value.get("y", 0.0)),
            float(value.get("z", 0.0)),
        )
    if isinstance(value, (list, tuple)):
        return (
            float(value[0]) if len(value) > 0 else 0.0,
            float(value[1]) if len(value) > 1 else 0.0,
            float(value[2]) if len(value) > 2 else 0.0,
        )
    return (0.0, 0.0, 0.0)


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


def _pack_inline_array(data_type: MetaDataType, value: Any, count: int) -> bytes:
    if count <= 0:
        return b""
    items = list(value or [])
    if len(items) < count:
        items.extend(0 for _ in range(count - len(items)))
    items = items[:count]
    if data_type is MetaDataType.FLOAT:
        return b"".join(struct.pack("<f", float(item)) for item in items)
    if data_type is MetaDataType.UNSIGNED_INT:
        return b"".join(struct.pack("<I", int(item)) for item in items)
    if data_type is MetaDataType.HASH:
        return b"".join(struct.pack("<I", _coerce_hash(item)) for item in items)
    if data_type is MetaDataType.SIGNED_INT:
        return b"".join(struct.pack("<i", int(item)) for item in items)
    if data_type is MetaDataType.UNSIGNED_SHORT:
        return b"".join(struct.pack("<H", int(item)) for item in items)
    if data_type is MetaDataType.SIGNED_SHORT:
        return b"".join(struct.pack("<h", int(item)) for item in items)
    if data_type is MetaDataType.UNSIGNED_BYTE:
        return bytes(int(item) & 0xFF for item in items)
    if data_type is MetaDataType.SIGNED_BYTE:
        return b"".join(struct.pack("<b", int(item)) for item in items)
    raw = bytes(value or b"")[:count]
    return raw + (b"\x00" * (count - len(raw)))
