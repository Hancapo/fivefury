from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ..binary import u32_be as _u32
from ..pso import (
    CHKS,
    PMAP,
    PSCH,
    PSIG,
    PSIN,
    STRE,
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
    PsoReader,
)
from ..pso import (
    PsoArrayHeader as _PsoArrayHeader,
)
from ..pso import (
    PsoBlock as _PsoBlock,
)
from ..pso import (
    PsoEntry as _PsoEntry,
)
from ..pso import (
    PsoPointer as _PsoPointer,
)
from ..pso import (
    PsoStruct as _PsoStruct,
)
from ..pso import (
    decode_array_header as _decode_array_header,
)
from ..pso import (
    decode_pointer as _decode_pointer,
)
from ..pso import (
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


class _PsoReader(PsoReader):
    def __init__(self, data: bytes):
        super().__init__(data, name_resolver=hash_name)

    def _hashed_string(self, hash_value: int) -> CutHashedString:
        return CutHashedString(hash=hash_value)

    def _node(
        self,
        type_hash: int,
        fields: dict[str, Any] | None = None,
    ) -> CutNode:
        return CutNode(
            type_name=self._name(type_hash),
            type_hash=type_hash,
            fields=fields or {},
        )

    def _node_fields(self, value: Any) -> dict[str, Any] | None:
        return value.fields if isinstance(value, CutNode) else None

    def _empty_hashed_string(self, value: Any) -> bool | None:
        if isinstance(value, CutHashedString):
            return value.hash == 0 and not value.text
        return None

    def read_cut(self) -> CutFile:
        document = self.read()
        return CutFile(
            root=cast(CutNode, document.root),
            source="cut",
            metadata=document.metadata,
        )


def read_cut(data: bytes | str | Path) -> CutFile:
    if isinstance(data, (str, Path)):
        payload = Path(data).read_bytes()
    else:
        payload = data
    if _u32(payload, 0) != PSIN:
        raise ValueError("not a PSIN/PSO file")
    return _PsoReader(payload).read_cut()
