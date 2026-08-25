from __future__ import annotations

import struct


class SidecarReader:
    __slots__ = ("_offset", "_payload")

    def __init__(self, payload: bytes) -> None:
        self._payload = memoryview(payload)
        self._offset = 0

    def _unpack(self, format_value: str) -> tuple[object, ...]:
        size = struct.calcsize("<" + format_value)
        end = self._offset + size
        if end > len(self._payload):
            raise ValueError("Truncated sidecar payload")
        values = struct.unpack_from("<" + format_value, self._payload, self._offset)
        self._offset = end
        return values

    def u8(self) -> int:
        return int(self._unpack("B")[0])

    def u32(self) -> int:
        return int(self._unpack("I")[0])

    def i32(self) -> int:
        return int(self._unpack("i")[0])

    def count(self, maximum: int) -> int:
        value = self.u32()
        if value > maximum:
            raise ValueError("Sidecar sequence count exceeds its format limit")
        return value

    def text(self, maximum: int = 1 << 20) -> str:
        size = self.count(maximum)
        end = self._offset + size
        if end > len(self._payload):
            raise ValueError("Truncated sidecar string")
        try:
            value = self._payload[self._offset : end].tobytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Invalid UTF-8 in sidecar string") from exc
        self._offset = end
        return value

    def finish(self) -> None:
        if self._offset != len(self._payload):
            raise ValueError("Sidecar payload contains trailing data")


class SidecarWriter:
    __slots__ = ("_payload",)

    def __init__(self) -> None:
        self._payload = bytearray()

    def u8(self, value: int) -> None:
        self._payload.extend(struct.pack("<B", int(value)))

    def u32(self, value: int) -> None:
        self._payload.extend(struct.pack("<I", int(value) & 0xFFFFFFFF))

    def i32(self, value: int) -> None:
        self._payload.extend(struct.pack("<i", int(value)))

    def count(self, value: int, maximum: int) -> None:
        count = int(value)
        if count < 0 or count > maximum:
            raise ValueError("Sidecar sequence count exceeds its format limit")
        self.u32(count)

    def text(self, value: str, maximum: int = 1 << 20) -> None:
        encoded = str(value).encode("utf-8")
        self.count(len(encoded), maximum)
        self._payload.extend(encoded)

    def to_bytes(self) -> bytes:
        return bytes(self._payload)


__all__ = ["SidecarReader", "SidecarWriter"]
