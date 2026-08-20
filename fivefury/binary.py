from __future__ import annotations

import io
import struct
from collections.abc import Iterable
from enum import IntEnum

from . import _native as _native_backend
from .vector import Vector3, Vector4


class BinaryEndian(IntEnum):
    LITTLE = 0
    BIG = 1


class BinaryScalarType(IntEnum):
    UNSIGNED_BYTE = 0
    SIGNED_BYTE = 1
    UNSIGNED_SHORT = 2
    SIGNED_SHORT = 3
    UNSIGNED_INT = 4
    SIGNED_INT = 5
    UNSIGNED_LONG = 6
    SIGNED_LONG = 7
    FLOAT = 8


class BinaryDocument:
    """Immutable native view over binary data with checked bulk reads."""

    __slots__ = ("_data", "_native")

    def __init__(self, data: bytes | bytearray | memoryview):
        self._data = data if isinstance(data, bytes) else bytes(data)
        self._native = _native_backend._binary_document_new(self._data)

    def __len__(self) -> int:
        return _native_backend._binary_document_size(self._native)

    def slice(self, offset: int, length: int) -> bytes:
        return _native_backend._binary_document_slice(self._native, offset, length)

    def c_string(self, offset: int, maximum: int | None = None) -> str:
        raw = _native_backend._binary_document_c_string(
            self._native,
            offset,
            -1 if maximum is None else maximum,
        )
        return raw.decode("ascii", errors="ignore")

    def read_array(
        self,
        offset: int,
        count: int,
        scalar_type: BinaryScalarType,
        *,
        endian: BinaryEndian = BinaryEndian.LITTLE,
        stride: int = 0,
        components: int = 1,
    ) -> list[object]:
        return _native_backend._binary_document_read_array(
            self._native,
            offset,
            count,
            int(scalar_type),
            int(endian),
            stride,
            components,
        )


def align(value: int, alignment: int) -> int:
    if alignment <= 0:
        raise ValueError("alignment must be positive")
    remainder = value % alignment
    return value if remainder == 0 else value + alignment - remainder


def fits_unsigned(value: object, bits: int) -> bool:
    if bits <= 0:
        raise ValueError("bits must be positive")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return 0 <= number < (1 << bits)


def pad_bytes(data: bytes, alignment: int, fill: bytes = b"\x00") -> bytes:
    padded = align(len(data), alignment)
    if padded == len(data):
        return data
    return data + (fill * (padded - len(data)))


def read_c_string(data: bytes, offset: int = 0) -> str:
    end = data.find(b"\x00", offset)
    if end == -1:
        end = len(data)
    return data[offset:end].decode("ascii", errors="ignore")


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def vec3(data: bytes, offset: int) -> Vector3:
    return Vector3(*struct.unpack_from("<3f", data, offset))


def vec4(data: bytes, offset: int) -> Vector4:
    return Vector4(*struct.unpack_from("<4f", data, offset))


def u16_be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def u32_be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def i32_be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">i", data, offset)[0]


def u64_be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">Q", data, offset)[0]


def i64_be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">q", data, offset)[0]


def f32_be(data: bytes, offset: int) -> float:
    return struct.unpack_from(">f", data, offset)[0]


def pack_u16_be(value: int) -> bytes:
    return struct.pack(">H", value)


def pack_u32_be(value: int) -> bytes:
    return struct.pack(">I", value & 0xFFFFFFFF)


def pack_i32_be(value: int) -> bytes:
    return struct.pack(">i", value)


def pack_i64_be(value: int) -> bytes:
    return struct.pack(">q", value)


def pack_f32_be(value: float) -> bytes:
    return struct.pack(">f", value)


def pack_u24(value: int) -> bytes:
    return bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF))


def unpack_u24(data: bytes) -> int:
    if len(data) != 3:
        raise ValueError("u24 values require exactly 3 bytes")
    return data[0] | (data[1] << 8) | (data[2] << 16)


def pack_struct(fmt: str, *values: object) -> bytes:
    return struct.pack("<" + fmt, *values)


def unpack_struct(fmt: str, data: bytes, offset: int = 0) -> tuple[object, ...]:
    size = struct.calcsize("<" + fmt)
    return struct.unpack("<" + fmt, data[offset : offset + size])


def iter_unpack(fmt: str, data: bytes) -> Iterable[tuple[object, ...]]:
    return struct.iter_unpack("<" + fmt, data)


class ByteReader:
    def __init__(self, data: bytes):
        self._buffer = memoryview(data)
        self._offset = 0

    @property
    def offset(self) -> int:
        return self._offset

    def seek(self, offset: int) -> None:
        self._offset = offset

    def tell(self) -> int:
        return self._offset

    def read(self, size: int) -> bytes:
        start = self._offset
        end = start + size
        self._offset = end
        return self._buffer[start:end].tobytes()

    def unpack(self, fmt: str) -> tuple[object, ...]:
        size = struct.calcsize("<" + fmt)
        values = struct.unpack("<" + fmt, self._buffer[self._offset : self._offset + size])
        self._offset += size
        return values


class ByteWriter:
    def __init__(self):
        self._buffer = io.BytesIO()

    def tell(self) -> int:
        return self._buffer.tell()

    def write(self, data: bytes) -> None:
        self._buffer.write(data)

    def pack(self, fmt: str, *values: object) -> None:
        self._buffer.write(struct.pack("<" + fmt, *values))

    def pad(self, alignment: int, fill: bytes = b"\x00") -> None:
        pos = self.tell()
        padded = align(pos, alignment)
        if padded != pos:
            self._buffer.write(fill * (padded - pos))

    def getvalue(self) -> bytes:
        return self._buffer.getvalue()


__all__ = [
    "BinaryDocument",
    "BinaryEndian",
    "BinaryScalarType",
    "ByteReader",
    "ByteWriter",
    "align",
    "f32",
    "f32_be",
    "fits_unsigned",
    "i16",
    "i32",
    "i32_be",
    "i64_be",
    "iter_unpack",
    "pack_f32_be",
    "pack_i32_be",
    "pack_i64_be",
    "pack_struct",
    "pack_u16_be",
    "pack_u24",
    "pack_u32_be",
    "pad_bytes",
    "read_c_string",
    "u16",
    "u16_be",
    "u32",
    "u32_be",
    "u64",
    "u64_be",
    "unpack_struct",
    "unpack_u24",
    "vec3",
    "vec4",
]
