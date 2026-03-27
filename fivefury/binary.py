from __future__ import annotations

import io
import struct
from collections.abc import Iterable


def align(value: int, alignment: int) -> int:
    if alignment <= 0:
        raise ValueError("alignment must be positive")
    remainder = value % alignment
    return value if remainder == 0 else value + alignment - remainder


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
