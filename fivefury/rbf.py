from __future__ import annotations

import dataclasses
import struct
from pathlib import Path
from typing import Any

RBF_MAGIC = b"RBF0"


@dataclasses.dataclass(slots=True)
class RbfStructure:
    name: str
    children: list["RbfNode"] = dataclasses.field(default_factory=list)
    attributes: list["RbfNode"] = dataclasses.field(default_factory=list)
    pending_attributes: int = 0

    def add_child(self, value: "RbfNode") -> None:
        if self.pending_attributes > 0:
            self.pending_attributes -= 1
            self.attributes.append(value)
        else:
            self.children.append(value)

    def child_structures(self, name: str | None = None) -> list["RbfStructure"]:
        return [
            child
            for child in self.children
            if isinstance(child, RbfStructure) and (name is None or child.name == name)
        ]


@dataclasses.dataclass(slots=True)
class RbfValue:
    name: str
    value: Any


@dataclasses.dataclass(slots=True)
class RbfBytes:
    value: bytes


RbfNode = RbfStructure | RbfValue | RbfBytes


def read_rbf_bytes(source: bytes | str | Path) -> bytes:
    if isinstance(source, bytes):
        return source
    candidate = Path(str(source))
    if candidate.exists():
        return candidate.read_bytes()
    return str(source).encode("utf-8")


def is_rbf(source: bytes | str | Path) -> bool:
    return read_rbf_bytes(source).startswith(RBF_MAGIC)


def read_rbf(source: bytes | str | Path) -> RbfStructure:
    data = read_rbf_bytes(source)
    if not data.startswith(RBF_MAGIC):
        raise ValueError("Not an RBF stream")
    offset = 4
    descriptors: list[tuple[str, int]] = []
    current: RbfStructure | None = None
    stack: list[RbfStructure] = []
    while offset < len(data):
        descriptor_index = data[offset]
        offset += 1
        if descriptor_index == 0xFF:
            marker = data[offset]
            offset += 1
            if marker != 0xFF:
                raise ValueError("Invalid RBF close marker")
            if not stack:
                if current is None:
                    raise ValueError("RBF stream closed before root")
                if offset != len(data):
                    raise ValueError("Trailing data after RBF root")
                return current
            current = stack.pop()
            continue
        if descriptor_index == 0xFD:
            marker = data[offset]
            offset += 1
            if marker != 0xFF:
                raise ValueError("Invalid RBF bytes marker")
            length, offset = _read_i32(data, offset)
            value = data[offset : offset + length]
            offset += length
            if current is None:
                raise ValueError("RBF bytes node outside a structure")
            current.add_child(RbfBytes(value))
            continue

        data_type = data[offset]
        offset += 1
        if descriptor_index == len(descriptors):
            name_length, offset = _read_i16(data, offset)
            name = data[offset : offset + name_length].decode("ascii")
            offset += name_length
            descriptors.append((name, data_type))
        elif descriptor_index < len(descriptors):
            name, _declared_type = descriptors[descriptor_index]
        else:
            raise ValueError(f"Invalid RBF descriptor index {descriptor_index}")

        value, offset = _read_rbf_value(data, offset, name, data_type, current, stack)
        current = value if isinstance(value, RbfStructure) else current
    raise ValueError("Unexpected end of RBF stream")


def rbf_string_field(node: RbfStructure, name: str) -> str:
    for child in node.children:
        if isinstance(child, RbfValue) and child.name == name:
            return str(child.value).replace("\0", "").strip()
        if isinstance(child, RbfStructure) and child.name == name and child.children:
            value = child.children[0]
            if isinstance(value, RbfBytes):
                return value.value.decode("ascii", errors="ignore").replace("\0", "").strip()
            if isinstance(value, RbfValue):
                return str(value.value).replace("\0", "").strip()
    return ""


def _read_rbf_value(
    data: bytes,
    offset: int,
    name: str,
    data_type: int,
    current: RbfStructure | None,
    stack: list[RbfStructure],
) -> tuple[RbfNode, int]:
    if data_type == 0:
        value = RbfStructure(name=name)
        if current is not None:
            current.add_child(value)
            stack.append(current)
        offset += 4
        pending_attributes, offset = _read_i16(data, offset)
        value.pending_attributes = pending_attributes
        return value, offset
    if current is None:
        raise ValueError("RBF primitive node outside a structure")
    if data_type == 0x10:
        number, offset = _read_u32(data, offset)
        value = RbfValue(name=name, value=number)
    elif data_type == 0x20:
        value = RbfValue(name=name, value=True)
    elif data_type == 0x30:
        value = RbfValue(name=name, value=False)
    elif data_type == 0x40:
        number, offset = _read_f32(data, offset)
        value = RbfValue(name=name, value=number)
    elif data_type == 0x50:
        numbers = struct.unpack_from("<fff", data, offset)
        offset += 12
        value = RbfValue(name=name, value=numbers)
    elif data_type == 0x60:
        length, offset = _read_i16(data, offset)
        text = data[offset : offset + length].decode("ascii")
        offset += length
        value = RbfValue(name=name, value=text)
    else:
        raise ValueError(f"Unsupported RBF data type 0x{data_type:02X}")
    current.add_child(value)
    return value, offset


def _read_i16(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<h", data, offset)[0], offset + 2


def _read_i32(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<i", data, offset)[0], offset + 4


def _read_u32(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<I", data, offset)[0], offset + 4


def _read_f32(data: bytes, offset: int) -> tuple[float, int]:
    return struct.unpack_from("<f", data, offset)[0], offset + 4


__all__ = [
    "RBF_MAGIC",
    "RbfBytes",
    "RbfNode",
    "RbfStructure",
    "RbfValue",
    "is_rbf",
    "rbf_string_field",
    "read_rbf",
    "read_rbf_bytes",
]
