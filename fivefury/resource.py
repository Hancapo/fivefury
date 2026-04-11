from __future__ import annotations

import dataclasses
import struct
import zlib

from .binary import align

RSC7_MAGIC = 0x37435352


def get_resource_size_from_flags(flags: int) -> int:
    s0 = ((flags >> 27) & 0x1) << 0
    s1 = ((flags >> 26) & 0x1) << 1
    s2 = ((flags >> 25) & 0x1) << 2
    s3 = ((flags >> 24) & 0x1) << 3
    s4 = ((flags >> 17) & 0x7F) << 4
    s5 = ((flags >> 11) & 0x3F) << 5
    s6 = ((flags >> 7) & 0xF) << 6
    s7 = ((flags >> 5) & 0x3) << 7
    s8 = ((flags >> 4) & 0x1) << 8
    base_shift = flags & 0xF
    base_size = 0x200 << base_shift
    return base_size * (s0 + s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8)


def get_resource_page_descriptor_count(flags: int) -> int:
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
    return sum(1 for count in counts if count)


def get_resource_total_page_count(flags: int) -> int:
    counts = (
        (flags >> 17) & 0x7F,
        (flags >> 11) & 0x3F,
        (flags >> 7) & 0xF,
        (flags >> 5) & 0x3,
        (flags >> 4) & 0x1,
        (flags >> 24) & 0x1,
        (flags >> 25) & 0x1,
        (flags >> 26) & 0x1,
        (flags >> 27) & 0x1,
    )
    return sum(counts)


def _decompose_page_count(block_count: int) -> list[int]:
    if block_count < 0:
        raise ValueError("block_count must be non-negative")
    weights = (256, 128, 64, 32, 16, 8, 4, 2, 1)
    caps = (1, 3, 15, 63, 127, 1, 1, 1, 1)
    remaining = block_count
    counts: list[int] = []
    for weight, cap in zip(weights, caps, strict=True):
        take = min(cap, remaining // weight)
        counts.append(take)
        remaining -= take * weight
    if remaining:
        raise ValueError("block_count is too large to encode into RSC7 flags")
    return counts


def get_resource_flags_from_blocks(block_count: int, block_size: int, version: int) -> int:
    if block_count < 0 or block_size <= 0:
        raise ValueError("block_count and block_size must be positive")
    size_shift = 0
    base_test = block_size
    while base_test > 0x200:
        size_shift += 1
        base_test >>= 1
    if base_test != 0x200 or size_shift > 0xF:
        raise ValueError("block_size must be a power-of-two multiple of 0x200")
    s8, s7, s6, s5, s4, s3, s2, s1, s0 = _decompose_page_count(block_count)
    flags = 0
    flags |= (version & 0xF) << 28
    flags |= s0 << 27
    flags |= s1 << 26
    flags |= s2 << 25
    flags |= s3 << 24
    flags |= s4 << 17
    flags |= s5 << 11
    flags |= s6 << 7
    flags |= s7 << 5
    flags |= s8 << 4
    flags |= size_shift & 0xF
    return flags


def get_resource_flags_from_size(size: int, version: int) -> int:
    if size <= 0:
        return (version & 0xF) << 28
    rounded = align(size, 0x200)
    block_count = rounded >> 9
    return get_resource_flags_from_blocks(block_count, 0x200, version)


def get_resource_flags_from_size_adaptive(size: int, version: int) -> int:
    if size <= 0:
        return (version & 0xF) << 28
    block_size = 0x200
    while True:
        rounded = align(size, block_size)
        block_count = rounded // block_size
        try:
            return get_resource_flags_from_blocks(block_count, block_size, version)
        except ValueError as exc:
            if "too large to encode" not in str(exc):
                raise
            block_size <<= 1
            if block_size > (0x200 << 0xF):
                raise ValueError("resource size is too large to encode into RSC7 flags") from exc


def _rsc7_block_pad(position: int) -> int:
    return (16 - (position % 16)) % 16


def get_resource_flags_from_block_sizes(block_sizes: list[int], version: int, *, max_page_count: int = 128) -> int:
    if not block_sizes:
        return (version & 0xF) << 28

    largest_block_size = 0
    start_page_size = 0x2000
    total_block_size = 0
    for block_size in block_sizes:
        size = max(0, int(block_size))
        total_block_size += size
        total_block_size += _rsc7_block_pad(total_block_size)
        if size > largest_block_size:
            largest_block_size = size
    while start_page_size < largest_block_size:
        start_page_size *= 2

    page_size_mult = 1
    while True:
        current_position = 0
        current_page_size = start_page_size
        current_page_start = 0
        current_page_space = start_page_size
        current_remainder = total_block_size
        page_count = 1
        page_counts = [0] * 9
        page_count_index = 0
        target_page_size = max(65536 * page_size_mult, start_page_size >> 5)
        min_page_size = max(512 * page_size_mult, min(target_page_size, start_page_size) >> 4)

        base_shift = 0
        base_size = 512
        while base_size < min_page_size:
            base_shift += 1
            base_size *= 2
            if base_shift >= 0xF:
                break

        base_size_max = base_size << 8
        base_size_max_test = start_page_size
        while base_size_max_test < base_size_max:
            page_count_index += 1
            base_size_max_test *= 2
        page_counts[page_count_index] = 1

        root_block_size = int(block_sizes[0])
        remaining = sorted((int(size) for size in block_sizes[1:]), reverse=True)

        while True:
            block_size = 0
            if current_position == 0:
                block_size = root_block_size
            else:
                for candidate in remaining:
                    if candidate <= current_page_space:
                        block_size = candidate
                        remaining.remove(candidate)
                        break

            if block_size:
                origin = current_position
                current_position += block_size
                current_position += _rsc7_block_pad(current_position)
                used_space = current_position - origin
                current_page_space -= used_space
                current_remainder -= used_space
            elif remaining:
                current_page_start += current_page_size
                current_position = current_page_start
                block_size = remaining[0]
                while block_size <= (current_page_size >> 1):
                    if current_page_size <= min_page_size:
                        break
                    if page_count_index >= 8:
                        break
                    if (current_page_size <= target_page_size) and (current_remainder >= (current_page_size - min_page_size)):
                        break
                    current_page_size >>= 1
                    page_count_index += 1
                current_page_space = current_page_size
                page_counts[page_count_index] += 1
                page_count += 1
            else:
                break

        flags = get_resource_flags_from_page_counts(page_counts, version)
        if (
            page_count == get_resource_total_page_count(flags)
            and get_resource_size_from_flags(flags) >= current_position
            and page_count <= max_page_count
        ):
            return flags

        start_page_size *= 2
        page_size_mult *= 2


def get_resource_flags_from_page_counts(page_counts: list[int], version: int, *, base_shift: int = 0) -> int:
    if len(page_counts) != 9:
        raise ValueError("page_counts must contain exactly 9 entries")
    flags = 0
    flags |= (version & 0xF) << 28
    flags |= (int(page_counts[8]) & 0x1) << 27
    flags |= (int(page_counts[7]) & 0x1) << 26
    flags |= (int(page_counts[6]) & 0x1) << 25
    flags |= (int(page_counts[5]) & 0x1) << 24
    flags |= (int(page_counts[4]) & 0x7F) << 17
    flags |= (int(page_counts[3]) & 0x3F) << 11
    flags |= (int(page_counts[2]) & 0xF) << 7
    flags |= (int(page_counts[1]) & 0x3) << 5
    flags |= (int(page_counts[0]) & 0x1) << 4
    flags |= int(base_shift) & 0xF
    return flags


def get_resource_flags_from_size_with_page_count(size: int, version: int, page_count: int) -> int:
    if size <= 0:
        return (version & 0xF) << 28
    if page_count <= 0:
        raise ValueError("page_count must be positive")

    capacities = (1, 3, 15, 63, 127, 1, 1, 1, 1)
    weights = (256, 128, 64, 32, 16, 8, 4, 2, 1)
    best_flags: int | None = None
    best_size: int | None = None

    for base_shift in range(16):
        base_size = 0x200 << base_shift
        target_units = (size + base_size - 1) // base_size
        if target_units > sum(capacity * weight for capacity, weight in zip(capacities, weights, strict=True)):
            continue

        # Exact-page bounded knapsack over a tiny state space:
        # max pages = 128, max unit sum = 511.
        states: dict[int, dict[int, list[int]]] = {0: {0: [0] * 9}}
        for index, (capacity, weight) in enumerate(zip(capacities, weights, strict=True)):
            next_states: dict[int, dict[int, list[int]]] = {}
            for used_pages, unit_map in states.items():
                page_bucket = next_states.setdefault(used_pages, {})
                for used_units, counts in unit_map.items():
                    page_bucket.setdefault(used_units, list(counts))
                for used_units, counts in unit_map.items():
                    max_take = min(capacity, page_count - used_pages)
                    for take in range(1, max_take + 1):
                        new_pages = used_pages + take
                        new_units = used_units + (take * weight)
                        counts_copy = list(counts)
                        counts_copy[index] = take
                        bucket = next_states.setdefault(new_pages, {})
                        bucket.setdefault(new_units, counts_copy)
            states = next_states

        candidates = states.get(page_count)
        if not candidates:
            continue
        valid_unit_counts = [units for units in candidates.keys() if units >= target_units]
        if not valid_unit_counts:
            continue
        best_units_for_shift = min(valid_unit_counts)
        flags = get_resource_flags_from_page_counts(candidates[best_units_for_shift], version, base_shift=base_shift)
        encoded_size = get_resource_size_from_flags(flags)
        if encoded_size < size:
            continue
        if best_size is None or encoded_size < best_size:
            best_size = encoded_size
            best_flags = flags

    if best_flags is None:
        raise ValueError("could not encode resource size with the requested page count")
    return best_flags


def compress_resource_stream(data: bytes) -> bytes:
    return zlib.compress(data, level=9, wbits=-15)


def decompress_resource_stream(data: bytes) -> bytes:
    return zlib.decompress(data, wbits=-15)


@dataclasses.dataclass(slots=True)
class ResourceHeader:
    version: int
    system_flags: int
    graphics_flags: int

    @property
    def system_size(self) -> int:
        return get_resource_size_from_flags(self.system_flags)

    @property
    def graphics_size(self) -> int:
        return get_resource_size_from_flags(self.graphics_flags)

    @property
    def total_size(self) -> int:
        return self.system_size + self.graphics_size

    def pack(self) -> bytes:
        return struct.pack("<IIII", RSC7_MAGIC, self.version, self.system_flags, self.graphics_flags)


def parse_rsc7(data: bytes) -> tuple[ResourceHeader, bytes]:
    if len(data) < 16:
        raise ValueError("RSC7 data is too short")
    magic, version, system_flags, graphics_flags = struct.unpack_from("<IIII", data, 0)
    if magic != RSC7_MAGIC:
        raise ValueError("data does not start with an RSC7 header")
    header = ResourceHeader(version=version, system_flags=system_flags, graphics_flags=graphics_flags)
    payload = decompress_resource_stream(data[16:])
    return header, payload


def split_rsc7_sections(data: bytes) -> tuple[ResourceHeader, bytes, bytes]:
    header, payload = parse_rsc7(data)
    system_data = payload[: header.system_size]
    graphics_data = payload[header.system_size : header.system_size + header.graphics_size]
    return header, system_data, graphics_data


def virtual_to_offset(address: int, *, base: int = 0x50000000) -> int:
    return int(address) - int(base)


def physical_to_offset(address: int, *, base: int = 0x60000000) -> int:
    return int(address) - int(base)


def checked_virtual_offset(
    address: int,
    data: bytes,
    *,
    base: int = 0x50000000,
    allow_plain_offset: bool = False,
) -> int:
    value = int(address)
    offset = virtual_to_offset(value, base=base) if not allow_plain_offset or value >= base else value
    if offset < 0 or offset >= len(data):
        raise ValueError("virtual pointer is out of range")
    return offset


def read_virtual_pointer_array(
    data: bytes,
    pointer: int,
    count: int,
    *,
    base: int = 0x50000000,
    allow_plain_offset: bool = False,
) -> list[int]:
    if not pointer or count <= 0:
        return []
    start = checked_virtual_offset(pointer, data, base=base, allow_plain_offset=allow_plain_offset)
    end = start + (count * 8)
    if end > len(data):
        raise ValueError("pointer array is truncated")
    return [struct.unpack_from("<Q", data, start + (index * 8))[0] for index in range(count)]


class ResourceWriter:
    def __init__(self, initial_size: int = 0x80):
        self.data = bytearray(initial_size)
        self.cursor = align(initial_size, 16)
        self.block_sizes: list[int] = [initial_size]

    def ensure(self, size: int) -> None:
        if size > len(self.data):
            self.data.extend(b"\x00" * (size - len(self.data)))

    def alloc(self, size: int, alignment: int = 16) -> int:
        offset = align(self.cursor, alignment)
        end = offset + size
        self.ensure(end)
        self.cursor = end
        self.block_sizes.append(size)
        return offset

    def write(self, offset: int, value: bytes) -> None:
        self.ensure(offset + len(value))
        self.data[offset : offset + len(value)] = value

    def pack_into(self, fmt: str, offset: int, *values: object) -> None:
        size = struct.calcsize("<" + fmt)
        self.ensure(offset + size)
        struct.pack_into("<" + fmt, self.data, offset, *values)

    def c_string(self, value: str, *, encoding: str = "ascii", alignment: int = 8) -> int:
        encoded = value.encode(encoding, errors="ignore") + b"\x00"
        offset = self.alloc(len(encoded), alignment)
        self.write(offset, encoded)
        return offset

    def finish(self) -> bytes:
        return bytes(self.data[: self.cursor])


def build_rsc7(
    system_data: bytes | object,
    *,
    version: int = 2,
    graphics_data: bytes = b"",
    system_alignment: int | None = None,
    graphics_alignment: int | None = None,
    system_flags: int | None = None,
    graphics_flags: int | None = None,
) -> bytes:
    if not isinstance(system_data, (bytes, bytearray, memoryview)):
        if hasattr(system_data, "to_bytes"):
            system_data = system_data.to_bytes()  # type: ignore[assignment]
        elif hasattr(system_data, "build"):
            system_data = system_data.build()  # type: ignore[assignment]
        else:
            raise TypeError("system_data must be bytes or expose to_bytes()/build()")
    system_data = bytes(system_data)
    if system_alignment:
        system_data = system_data + (b"\x00" * (align(len(system_data), system_alignment) - len(system_data)))
    if graphics_alignment:
        graphics_data = graphics_data + (b"\x00" * (align(len(graphics_data), graphics_alignment) - len(graphics_data)))
    if system_flags is None:
        system_flags = get_resource_flags_from_size_adaptive(len(system_data), (version >> 4) & 0xF)
    if graphics_flags is None:
        graphics_flags = get_resource_flags_from_size_adaptive(len(graphics_data), version & 0xF)
    system_target_size = get_resource_size_from_flags(system_flags)
    graphics_target_size = get_resource_size_from_flags(graphics_flags)
    if len(system_data) > system_target_size:
        raise ValueError("system_data is larger than the size encoded in system_flags")
    if len(graphics_data) > graphics_target_size:
        raise ValueError("graphics_data is larger than the size encoded in graphics_flags")
    if len(system_data) < system_target_size:
        system_data = system_data + (b"\x00" * (system_target_size - len(system_data)))
    if len(graphics_data) < graphics_target_size:
        graphics_data = graphics_data + (b"\x00" * (graphics_target_size - len(graphics_data)))
    payload = system_data + graphics_data
    header = ResourceHeader(version=version, system_flags=system_flags, graphics_flags=graphics_flags)
    return header.pack() + compress_resource_stream(payload)
