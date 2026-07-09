from __future__ import annotations

import dataclasses
import struct
import zlib

from ..resource import RSC7_MAGIC, ResourceHeader

PS3_SYSTEM_LEAF_SIZE = 4096
PS3_GRAPHICS_LEAF_SIZE = 5504
PS3_VIRTUAL_BASE = 0x50000000
PS3_PHYSICAL_BASE = 0x60000000


def get_ps3_resource_size_from_flags(flags: int, leaf_size: int) -> int:
    base_size = int(leaf_size) << (int(flags) & 0xF)
    counts = (
        (flags >> 4) & 0x1,
        (flags >> 5) & 0x3,
        (flags >> 7) & 0xF,
        (flags >> 11) & 0x3F,
        (flags >> 17) & 0x7F,
        (flags >> 24) & 0x1,
        (flags >> 25) & 0x1,
        (flags >> 26) & 0x1,
        (flags >> 27) & 0x1,
    )
    numerator_weights = (16, 8, 4, 2, 1, 0, 0, 0, 0)
    size = sum(count * weight * base_size for count, weight in zip(counts, numerator_weights, strict=True))
    tail_divisors = (2, 4, 8, 16)
    size += sum(counts[5 + index] * (base_size // divisor) for index, divisor in enumerate(tail_divisors))
    return int(size)


def split_ps3_rsc7_sections(data: bytes) -> tuple[ResourceHeader, bytes, bytes]:
    if len(data) < 16:
        raise ValueError("CDR data is too short")
    magic, version, system_flags, graphics_flags = struct.unpack_from("<4I", data, 0)
    if magic != RSC7_MAGIC:
        raise ValueError("CDR data must be a standalone RSC7 resource")
    header = ResourceHeader(version=version, system_flags=system_flags, graphics_flags=graphics_flags)
    try:
        payload = zlib.decompress(data[16:], wbits=-15)
    except zlib.error as exc:
        raise ValueError("CDR resource payload is not valid raw DEFLATE data") from exc
    system_size = get_ps3_resource_size_from_flags(system_flags, PS3_SYSTEM_LEAF_SIZE)
    graphics_size = get_ps3_resource_size_from_flags(graphics_flags, PS3_GRAPHICS_LEAF_SIZE)
    expected_size = system_size + graphics_size
    if len(payload) != expected_size:
        raise ValueError(f"CDR resource size mismatch: expected {expected_size}, got {len(payload)}")
    return header, payload[:system_size], payload[system_size:]


@dataclasses.dataclass(frozen=True, slots=True)
class Ps3ResourceView:
    system: bytes
    graphics: bytes

    def _check(self, data: bytes, offset: int, size: int) -> None:
        if offset < 0 or size < 0 or offset + size > len(data):
            raise ValueError(f"PS3 resource range is out of bounds: offset=0x{offset:X}, size=0x{size:X}")

    def system_offset(self, pointer: int) -> int:
        offset = int(pointer) - PS3_VIRTUAL_BASE
        self._check(self.system, offset, 1)
        return offset

    def resolve(self, pointer: int, size: int = 0) -> tuple[bytes, int]:
        value = int(pointer)
        if PS3_VIRTUAL_BASE <= value < PS3_PHYSICAL_BASE:
            data, offset = self.system, value - PS3_VIRTUAL_BASE
        elif PS3_PHYSICAL_BASE <= value < 0x70000000:
            data, offset = self.graphics, value - PS3_PHYSICAL_BASE
        else:
            raise ValueError(f"invalid PS3 resource pointer 0x{value:08X}")
        self._check(data, offset, max(1, int(size)))
        return data, offset

    def bytes_at(self, pointer: int, size: int) -> bytes:
        if not pointer or size <= 0:
            return b""
        data, offset = self.resolve(pointer, size)
        return data[offset : offset + size]

    def u8(self, offset: int) -> int:
        self._check(self.system, offset, 1)
        return self.system[offset]

    def u16(self, offset: int) -> int:
        self._check(self.system, offset, 2)
        return struct.unpack_from(">H", self.system, offset)[0]

    def s16(self, offset: int) -> int:
        self._check(self.system, offset, 2)
        return struct.unpack_from(">h", self.system, offset)[0]

    def u32(self, offset: int) -> int:
        self._check(self.system, offset, 4)
        return struct.unpack_from(">I", self.system, offset)[0]

    def s32(self, offset: int) -> int:
        self._check(self.system, offset, 4)
        return struct.unpack_from(">i", self.system, offset)[0]

    def f32(self, offset: int) -> float:
        self._check(self.system, offset, 4)
        return struct.unpack_from(">f", self.system, offset)[0]

    def vec3(self, offset: int) -> tuple[float, float, float]:
        self._check(self.system, offset, 12)
        return struct.unpack_from(">3f", self.system, offset)

    def c_string(self, pointer: int) -> str:
        if not pointer:
            return ""
        data, offset = self.resolve(pointer)
        end = data.find(b"\0", offset)
        if end < 0:
            end = len(data)
        return data[offset:end].decode("ascii", errors="replace")


__all__ = [
    "PS3_GRAPHICS_LEAF_SIZE",
    "PS3_PHYSICAL_BASE",
    "PS3_SYSTEM_LEAF_SIZE",
    "PS3_VIRTUAL_BASE",
    "Ps3ResourceView",
    "get_ps3_resource_size_from_flags",
    "split_ps3_rsc7_sections",
]
