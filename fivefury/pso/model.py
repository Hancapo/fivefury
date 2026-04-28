from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ARRAY_INFO_HASH = 0x100
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


@dataclass(slots=True)
class PsoPointer:
    block_id: int
    offset: int

    @property
    def is_null(self) -> bool:
        return self.block_id == 0


@dataclass(slots=True)
class PsoArrayHeader:
    pointer: PsoPointer
    count: int


@dataclass(slots=True)
class PsoBlock:
    name_hash: int
    offset: int
    length: int


@dataclass(slots=True)
class PsoEntry:
    name_hash: int
    type_id: int
    subtype: int
    data_offset: int
    reference_key: int


@dataclass(slots=True)
class PsoStruct:
    name_hash: int
    length: int
    entries: list[PsoEntry]


@dataclass(slots=True)
class PsoHashedString:
    hash: int
    text: str | None = None

    def __str__(self) -> str:
        return self.text if self.text else f"0x{self.hash:08X}"


@dataclass(slots=True)
class PsoNode:
    type_name: str
    type_hash: int | None = None
    fields: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.fields is None:
            self.fields = {}

    def get(self, name: str, default: Any = None) -> Any:
        return self.fields.get(name, default) if self.fields is not None else default

    def __getitem__(self, key: str) -> Any:
        if self.fields is None:
            raise KeyError(key)
        return self.fields[key]

    def __contains__(self, key: str) -> bool:
        return self.fields is not None and key in self.fields


@dataclass(slots=True)
class PsoDocument:
    root: PsoNode
    metadata: dict[str, Any]


__all__ = [
    "ARRAY_INFO_HASH",
    "CHKS",
    "PMAP",
    "PSCH",
    "PSIG",
    "PSIN",
    "STRE",
    "PsoArrayHeader",
    "PsoBlock",
    "PsoDataTypeArray",
    "PsoDataTypeBool",
    "PsoDataTypeEnum",
    "PsoDataTypeFlags",
    "PsoDataTypeFloat",
    "PsoDataTypeFloat2",
    "PsoDataTypeFloat3",
    "PsoDataTypeFloat3a",
    "PsoDataTypeFloat4",
    "PsoDataTypeFloat4a",
    "PsoDataTypeHFloat",
    "PsoDataTypeLong",
    "PsoDataTypeMap",
    "PsoDataTypeSByte",
    "PsoDataTypeSInt",
    "PsoDataTypeSShort",
    "PsoDataTypeString",
    "PsoDataTypeStructure",
    "PsoDataTypeUByte",
    "PsoDataTypeUInt",
    "PsoDataTypeUShort",
    "PsoEntry",
    "PsoDocument",
    "PsoHashedString",
    "PsoNode",
    "PsoPointer",
    "PsoStruct",
]
