from __future__ import annotations

import dataclasses
import struct
from collections.abc import Iterable, Mapping
from typing import Any

from ..binary import align, pad_bytes
from ..resource import get_resource_flags_from_blocks, get_resource_total_page_count
from ..metahash import MetaHash
from . import (
    FLOAT_XYZ_NAME_HASH,
    META_FILE_VFT,
    META_ROOT_SIZE,
    RESOURCE_FILE_BASE_SIZE,
    MetaArrayRef,
    MetaDataRef,
    MetaEnumInfo,
    MetaFieldInfo,
    MetaPointer,
    MetaStructInfo,
    RawStruct,
)
from .defs import (
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
    MetaDataType,
)
from .utils import array_info_for_field
from ..hashing import jenk_hash

@dataclasses.dataclass(slots=True)
class _WritableBlock:
    name_hash: int
    data: bytes = b""


class MetaBuilder:
    MAX_BLOCK_LENGTH = 0x4000
    RESERVED_SYSTEM_PAGE_SLOTS = 128
    RESERVED_PAGES_INFO_SIZE = 16 + (8 * RESERVED_SYSTEM_PAGE_SLOTS)
    META_LAYOUT_OFFSET = 0x480

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
        self._block_group: dict[int, list[int]] = {}
        self.page_size: int = 0x2000
        self.page_count: int = 1
        self.page_flags: int = 0

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
        self._block_group.clear()
        self.used_struct_hashes.clear()
        self.used_enum_hashes.clear()
        if root_name_hash and root_value is not None:
            root_block_id = self._reserve_block(root_name_hash)
            root_payload = self._encode_struct_payload(root_name_hash, root_value)
            self._set_block(root_block_id, root_payload)
        else:
            root_block_id = 0
        return self._compose_system_stream(root_block_id)

    def _choose_page_size(self) -> int:
        max_block_size = max((len(block.data) for block in self.blocks), default=0)
        page_size = 0x2000
        while page_size < max_block_size:
            page_size <<= 1
        return page_size

    def _layout_data_blocks(self, start_offset: int) -> tuple[int, list[int], int]:
        page_size = self._choose_page_size()
        offsets: list[int] = []
        offset = align(start_offset, 16)
        for block in self.blocks:
            block_length = len(block.data)
            offset = align(offset, 16)
            if block_length:
                start_page = offset // page_size
                end_page = (offset + block_length - 1) // page_size
                if end_page != start_page:
                    offset = align(offset, page_size)
            offsets.append(offset)
            offset += block_length
        total_size = align(offset, page_size)
        return page_size, offsets, total_size

    def _reserve_block(self, name_hash: int) -> int:
        self.blocks.append(_WritableBlock(name_hash=name_hash))
        block_id = len(self.blocks)
        self._block_group.setdefault(name_hash, []).append(block_id - 1)
        return block_id

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
            for index in self._block_group.get(name_hash, ()):
                block = self.blocks[index]
                if len(block.data) >= self.MAX_BLOCK_LENGTH:
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
            array_info = array_info_for_field(struct_info, field_index)
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
        array_info = array_info_for_field(struct_info, field_index)
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
        offset = self.META_LAYOUT_OFFSET

        struct_infos_offset = offset if struct_infos else 0
        offset += len(struct_infos) * 32
        offset = align(offset, 16)

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

        enum_infos_offset = offset if enum_infos else 0
        offset += len(enum_infos) * 24
        offset = align(offset, 16)

        enum_entry_offsets: dict[int, int] = {}
        enum_entry_payloads: list[tuple[MetaEnumInfo, bytes, int]] = []
        for info in enum_infos:
            payload = b"".join(struct.pack("<Ii", entry.name_hash, entry.value) for entry in info.entries)
            enum_entry_offsets[info.name_hash] = offset
            enum_entry_payloads.append((info, payload, offset))
            offset += len(payload)

        offset = align(offset, 16)
        data_blocks_offset = offset if self.blocks else 0
        offset += len(self.blocks) * 16

        name_bytes = self.name.encode("ascii", errors="ignore") + b"\x00" if self.name else b""
        name_offset = offset if name_bytes else 0
        offset += len(name_bytes)

        offset = align(offset, 16)
        page_size, block_offsets, total_size = self._layout_data_blocks(offset)
        page_count = max(1, total_size // page_size)
        self.page_size = page_size
        self.page_count = page_count
        page_flags = get_resource_flags_from_blocks(page_count, page_size, 0)
        self.page_flags = page_flags
        pages_info_count = get_resource_total_page_count(page_flags)
        pages_info_offset = META_ROOT_SIZE
        pages_info_size = 16 + (8 * pages_info_count)

        system = bytearray(total_size)

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
        system[pages_info_offset : pages_info_offset + pages_info_size] = struct.pack("<IIBBHI", 0, 0, pages_info_count, 0, 0, 0) + (b"\x00" * (8 * pages_info_count))

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
        vals = [float(v) for v in items]
        return struct.pack(f"<{len(vals)}f", *vals)
    if data_type in (MetaDataType.UNSIGNED_INT, MetaDataType.HASH):
        vals = [_coerce_hash(v) if data_type is MetaDataType.HASH else int(v) for v in items]
        return struct.pack(f"<{len(vals)}I", *vals)
    if data_type is MetaDataType.UNSIGNED_SHORT:
        vals = [int(v) for v in items]
        return struct.pack(f"<{len(vals)}H", *vals)
    if data_type is MetaDataType.UNSIGNED_BYTE:
        return bytes(int(item) & 0xFF for item in items)
    if data_type is MetaDataType.FLOAT_XYZ:
        flat = []
        for item in items:
            flat.extend(_coerce_vector(item, 3))
        return struct.pack(f"<{len(flat)}f", *flat)
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


def _pack_inline_array(data_type: MetaDataType, value: Any, count: int) -> bytes:
    if count <= 0:
        return b""
    items = list(value or [])
    if len(items) < count:
        items.extend(0 for _ in range(count - len(items)))
    items = items[:count]
    if data_type is MetaDataType.FLOAT:
        return struct.pack(f"<{count}f", *(float(v) for v in items))
    if data_type is MetaDataType.UNSIGNED_INT:
        return struct.pack(f"<{count}I", *(int(v) for v in items))
    if data_type is MetaDataType.HASH:
        return struct.pack(f"<{count}I", *(_coerce_hash(v) for v in items))
    if data_type is MetaDataType.SIGNED_INT:
        return struct.pack(f"<{count}i", *(int(v) for v in items))
    if data_type is MetaDataType.UNSIGNED_SHORT:
        return struct.pack(f"<{count}H", *(int(v) for v in items))
    if data_type is MetaDataType.SIGNED_SHORT:
        return struct.pack(f"<{count}h", *(int(v) for v in items))
    if data_type is MetaDataType.UNSIGNED_BYTE:
        return bytes(int(item) & 0xFF for item in items)
    if data_type is MetaDataType.SIGNED_BYTE:
        return struct.pack(f"<{count}b", *(int(v) for v in items))
    raw = bytes(value or b"")[:count]
    return raw + (b"\x00" * (count - len(raw)))








