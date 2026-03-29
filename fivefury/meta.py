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



from .meta_read import ParsedMeta, read_meta
from .meta_builder import MetaBuilder, build_meta_system

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


