from __future__ import annotations

from pathlib import Path
from typing import Any

from ..binary import u32_be as _u32
from ..pso import (
    CHKS,
    PMAP,
    PSCH,
    PSIG,
    PSIN,
    STRE,
    PsoArrayHeader as _PsoArrayHeader,
    PsoBlock as _PsoBlock,
    PsoDataTypeArray,
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
    PsoDataTypeMap,
    PsoDataTypeSByte,
    PsoDataTypeSInt,
    PsoDataTypeSShort,
    PsoDataTypeString,
    PsoDataTypeStructure,
    PsoDataTypeUByte,
    PsoDataTypeUInt,
    PsoDataTypeUShort,
    PsoEntry as _PsoEntry,
    PsoHashedString,
    PsoNode,
    PsoPointer as _PsoPointer,
    PsoReader,
    PsoStruct as _PsoStruct,
    decode_array_header as _decode_array_header,
    decode_pointer as _decode_pointer,
    decode_pointer_word as _decode_pointer_word,
)
from .model import CutFile, CutHashedString, CutNode
from .names import hash_name

__all__ = [
    "CHKS",
    "PMAP",
    "PSCH",
    "PSIG",
    "PSIN",
    "STRE",
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
    "_PsoArrayHeader",
    "_PsoBlock",
    "_PsoEntry",
    "_PsoPointer",
    "_PsoReader",
    "_PsoStruct",
    "_decode_array_header",
    "_decode_pointer",
    "_decode_pointer_word",
    "read_cut",
]


def _to_cut_value(value: Any) -> Any:
    if isinstance(value, PsoHashedString):
        return CutHashedString(hash=value.hash, text=value.text)
    if isinstance(value, PsoNode):
        return _to_cut_node(value)
    if isinstance(value, list):
        return [_to_cut_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_to_cut_value(item) for item in value)
    return value


def _to_cut_node(node: PsoNode) -> CutNode:
    return CutNode(
        type_name=node.type_name,
        type_hash=node.type_hash,
        fields={name: _to_cut_value(value) for name, value in (node.fields or {}).items()},
    )


class _PsoReader(PsoReader):
    def __init__(self, data: bytes):
        super().__init__(data, name_resolver=hash_name)

    def read_cut(self) -> CutFile:
        document = self.read()
        return CutFile(root=_to_cut_node(document.root), source="cut", metadata=document.metadata)


def read_cut(data: bytes | str | Path) -> CutFile:
    if isinstance(data, (str, Path)):
        payload = Path(data).read_bytes()
    else:
        payload = data
    if _u32(payload, 0) != PSIN:
        raise ValueError("not a PSIN/PSO file")
    return _PsoReader(payload).read_cut()
