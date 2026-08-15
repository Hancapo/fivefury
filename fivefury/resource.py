from __future__ import annotations

import dataclasses
import struct
import zlib

from . import _native as _native_backend
from .binary import align

RSC7_MAGIC = 0x37435352
RSC7_VIRTUAL_BASE = 0x50000000
RSC7_PHYSICAL_BASE = 0x60000000


@dataclasses.dataclass(slots=True)
class ResourcePagesInfo:
    unknown_0h: int = 0
    unknown_4h: int = 0
    system_pages_count: int = 0
    graphics_pages_count: int = 0
    unknown_ah: int = 0
    unknown_ch: int = 0

    @property
    def total_page_count(self) -> int:
        return int(self.system_pages_count) + int(self.graphics_pages_count)


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


def get_resource_chunk_sizes(flags: int, *, leaf_size: int = 0x2000) -> tuple[int, ...]:
    """Return the source chunks produced by datResourceInfo::GenerateMap."""
    largest_chunk = int(leaf_size) << (4 + (int(flags) & 0xF))
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
    return tuple(
        largest_chunk >> index
        for index, count in enumerate(counts)
        for _ in range(int(count))
    )


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


def get_resource_flags_from_block_sizes(
    block_sizes: list[int],
    version: int,
    *,
    max_page_count: int = 128,
    is_system: bool = True,
) -> int:
    """Pack RSC blocks into page flags using CodeWalker's AssignPositions2 strategy."""
    if not block_sizes:
        return (version & 0xF) << 28
    sizes = [max(0, int(block_size)) for block_size in block_sizes]
    return _native_backend.resource_pack_block_sizes(
        sizes,
        version,
        max_page_count=max_page_count,
        is_system=is_system,
    )


def get_resource_flags_from_block_layout(
    system_block_sizes: list[int],
    graphics_block_sizes: list[int] | None = None,
    *,
    version: int,
    max_page_count: int = 128,
) -> tuple[int, int]:
    system_flags = get_resource_flags_from_block_sizes(
        system_block_sizes,
        (int(version) >> 4) & 0xF,
        max_page_count=max_page_count,
        is_system=True,
    )
    system_page_count = get_resource_total_page_count(system_flags)
    graphics_flags = get_resource_flags_from_block_sizes(
        list(graphics_block_sizes or []),
        int(version) & 0xF,
        max_page_count=max(0, int(max_page_count) - system_page_count),
        is_system=False,
    )
    return (system_flags, graphics_flags)


@dataclasses.dataclass(frozen=True, slots=True)
class ResourceBlockSpan:
    offset: int
    size: int
    relocate_pointers: bool = True
    pointer_offsets: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        offset = int(self.offset)
        size = int(self.size)
        if offset < 0 or size < 0:
            raise ValueError("resource block offset and size must be non-negative")
        pointer_offsets = self.pointer_offsets
        if pointer_offsets is not None:
            normalized = tuple(sorted({int(pointer_offset) for pointer_offset in pointer_offsets}))
            if any(pointer_offset < 0 or pointer_offset + 8 > size for pointer_offset in normalized):
                raise ValueError("resource pointer field is outside its block")
            if not self.relocate_pointers and normalized:
                raise ValueError("non-relocatable resource blocks cannot declare pointer fields")
            object.__setattr__(self, "pointer_offsets", normalized)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "size", size)


def _coerce_resource_block_spans(
    blocks: list[ResourceBlockSpan]
    | list[tuple[int, int]]
    | list[tuple[int, int, bool]]
    | list[tuple[int, int, bool, tuple[int, ...] | None]],
) -> list[ResourceBlockSpan]:
    spans: list[ResourceBlockSpan] = []
    for block in blocks:
        if isinstance(block, ResourceBlockSpan):
            spans.append(block)
            continue
        if len(block) == 2:
            offset, size = block
            spans.append(ResourceBlockSpan(int(offset), int(size), True))
        elif len(block) == 3:
            offset, size, relocate_pointers = block
            spans.append(ResourceBlockSpan(int(offset), int(size), bool(relocate_pointers)))
        else:
            offset, size, relocate_pointers, pointer_offsets = block
            spans.append(
                ResourceBlockSpan(
                    int(offset),
                    int(size),
                    bool(relocate_pointers),
                    None if pointer_offsets is None else tuple(pointer_offsets),
                )
            )
    return spans


def layout_resource_sections(
    system_data: bytes,
    system_blocks: list[ResourceBlockSpan] | list[tuple[int, int]] | list[tuple[int, int, bool]],
    graphics_data: bytes = b"",
    graphics_blocks: list[ResourceBlockSpan] | list[tuple[int, int]] | list[tuple[int, int, bool]] | None = None,
    *,
    version: int,
    max_page_count: int = 128,
    virtual_base: int = 0x50000000,
    physical_base: int = 0x60000000,
) -> tuple[bytes, bytes, int, int]:
    system_spans = _coerce_resource_block_spans(system_blocks)
    graphics_spans = _coerce_resource_block_spans(list(graphics_blocks or []))
    return _native_backend.resource_layout_sections(
        bytes(system_data),
        [(span.offset, span.size, span.relocate_pointers, span.pointer_offsets) for span in system_spans],
        bytes(graphics_data),
        [(span.offset, span.size, span.relocate_pointers, span.pointer_offsets) for span in graphics_spans],
        version=version,
        max_page_count=max_page_count,
        virtual_base=virtual_base,
        physical_base=physical_base,
    )


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
        valid_unit_counts = [units for units in candidates if units >= target_units]
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


def _decompress_raw_resource_stream(data: bytes, *, dictionary: bytes | None = None) -> bytes:
    if dictionary is None:
        decompressor = zlib.decompressobj(wbits=-15)
    else:
        decompressor = zlib.decompressobj(wbits=-15, zdict=dictionary)
    output = decompressor.decompress(data) + decompressor.flush()
    if not decompressor.eof:
        raise ValueError("resource deflate stream is truncated")
    if decompressor.unused_data or decompressor.unconsumed_tail:
        raise ValueError("resource deflate stream contains trailing data")
    return output


def decompress_resource_stream(
    data: bytes,
    *,
    expected_size: int | None = None,
) -> bytes:
    try:
        output = _decompress_raw_resource_stream(data)
    except zlib.error as exc:
        if "invalid distance too far back" not in str(exc).lower():
            raise ValueError("unable to decompress resource stream") from exc
        try:
            output = _decompress_raw_resource_stream(
                data,
                dictionary=b"\0" * 32768,
            )
        except (ValueError, zlib.error) as fallback_exc:
            raise ValueError("unable to decompress resource stream") from fallback_exc
    if expected_size is None:
        return output
    target_size = int(expected_size)
    if len(output) > target_size:
        raise ValueError(
            f"resource stream expands to 0x{len(output):X} bytes, "
            f"exceeding the declared 0x{target_size:X} bytes"
        )
    return output


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

    @property
    def chunks(self) -> tuple[ResourceChunk, ...]:
        return get_resource_chunks(self)


@dataclasses.dataclass(frozen=True, slots=True)
class ResourceChunk:
    address: int
    size: int
    section: str
    section_offset: int

    @property
    def end_address(self) -> int:
        return self.address + self.size

    def contains(self, address: int, size: int = 1) -> bool:
        if size < 0:
            return False
        return self.address <= address and address + size <= self.end_address


def get_resource_chunks(
    header: ResourceHeader,
    *,
    virtual_base: int = RSC7_VIRTUAL_BASE,
    physical_base: int = RSC7_PHYSICAL_BASE,
) -> tuple[ResourceChunk, ...]:
    chunks: list[ResourceChunk] = []
    for section, base, flags in (
        ("system", virtual_base, header.system_flags),
        ("graphics", physical_base, header.graphics_flags),
    ):
        section_offset = 0
        for size in get_resource_chunk_sizes(flags):
            chunks.append(
                ResourceChunk(
                    address=base + section_offset,
                    size=size,
                    section=section,
                    section_offset=section_offset,
                )
            )
            section_offset += size
    return tuple(chunks)


def find_resource_chunk(
    header: ResourceHeader,
    address: int,
    size: int = 1,
) -> ResourceChunk | None:
    return next(
        (chunk for chunk in header.chunks if chunk.contains(int(address), int(size))),
        None,
    )


def resolve_resource_pointer(
    header: ResourceHeader,
    address: int,
    *,
    size: int = 1,
    section: str | None = None,
    nullable: bool = True,
) -> ResourceChunk | None:
    pointer = int(address)
    if pointer == 0:
        if nullable:
            return None
        raise ValueError("required resource pointer is null")
    chunk = find_resource_chunk(header, pointer, size)
    if chunk is None:
        raise ValueError(
            f"0x{pointer:08X} is outside the system and graphics virtual spaces"
        )
    if section is not None and chunk.section != section:
        raise ValueError(
            f"0x{pointer:08X} points into {chunk.section} data instead of {section} data"
        )
    return chunk


def parse_rsc7(data: bytes) -> tuple[ResourceHeader, bytes]:
    if len(data) < 16:
        raise ValueError("RSC7 data is too short")
    magic, version, system_flags, graphics_flags = struct.unpack_from("<IIII", data, 0)
    if magic != RSC7_MAGIC:
        raise ValueError("data does not start with an RSC7 header")
    header = ResourceHeader(version=version, system_flags=system_flags, graphics_flags=graphics_flags)
    payload = decompress_resource_stream(data[16:], expected_size=header.total_size)
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


def read_resource_pages_info(pointer: int, system_data: bytes) -> ResourcePagesInfo | None:
    if not pointer:
        return None
    offset = checked_virtual_offset(pointer, system_data)
    unknown_0h, unknown_4h, system_pages_count, graphics_pages_count, unknown_ah, unknown_ch = struct.unpack_from(
        "<IIBBHI",
        system_data,
        offset,
    )
    return ResourcePagesInfo(
        unknown_0h=unknown_0h,
        unknown_4h=unknown_4h,
        system_pages_count=system_pages_count,
        graphics_pages_count=graphics_pages_count,
        unknown_ah=unknown_ah,
        unknown_ch=unknown_ch,
    )


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
    return list(struct.unpack_from(f"<{count}Q", data, start))


class ResourceWriter:
    def __init__(self, initial_size: int = 0x80, *, initial_pointer_offsets: tuple[int, ...] | None = None):
        initial_span = ResourceBlockSpan(0, initial_size, pointer_offsets=initial_pointer_offsets)
        self.data = bytearray(initial_size)
        self.cursor = align(initial_size, 16)
        self.block_sizes: list[int] = [initial_size]
        self.block_offsets: list[int] = [0]
        self.block_relocate_pointers: list[bool] = [True]
        self.block_pointer_offsets: list[tuple[int, ...] | None] = [initial_span.pointer_offsets]

    def ensure(self, size: int) -> None:
        if size > len(self.data):
            self.data.extend(bytes(size - len(self.data)))

    def alloc(
        self,
        size: int,
        alignment: int = 16,
        *,
        relocate_pointers: bool = True,
        pointer_offsets: tuple[int, ...] | None = None,
    ) -> int:
        offset = align(self.cursor, alignment)
        span = ResourceBlockSpan(offset, size, relocate_pointers, pointer_offsets)
        end = offset + size
        self.ensure(end)
        self.cursor = end
        self.block_sizes.append(size)
        self.block_offsets.append(offset)
        self.block_relocate_pointers.append(bool(relocate_pointers))
        self.block_pointer_offsets.append(span.pointer_offsets)
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
        offset = self.alloc(len(encoded), alignment, relocate_pointers=False)
        self.write(offset, encoded)
        return offset

    @property
    def block_spans(self) -> list[ResourceBlockSpan]:
        return [
            ResourceBlockSpan(
                offset=offset,
                size=size,
                relocate_pointers=relocate_pointers,
                pointer_offsets=pointer_offsets,
            )
            for offset, size, relocate_pointers, pointer_offsets in zip(
                self.block_offsets,
                self.block_sizes,
                self.block_relocate_pointers,
                self.block_pointer_offsets,
                strict=True,
            )
        ]

    def require_explicit_pointer_fields(self) -> None:
        for index, span in enumerate(self.block_spans):
            if span.relocate_pointers and span.pointer_offsets is None:
                raise ValueError(
                    f"resource block {index} at 0x{span.offset:X} does not declare its pointer fields"
                )

    def finish(self) -> bytes:
        return bytes(self.data[: self.cursor])


def write_resource_pages_info(writer: ResourceWriter, pages_info: ResourcePagesInfo) -> int:
    offset = writer.alloc(0x10 + (8 * pages_info.total_page_count), 16, relocate_pointers=False)
    writer.pack_into(
        "IIBBHI",
        offset,
        int(pages_info.unknown_0h),
        int(pages_info.unknown_4h),
        int(pages_info.system_pages_count) & 0xFF,
        int(pages_info.graphics_pages_count) & 0xFF,
        int(pages_info.unknown_ah) & 0xFFFF,
        int(pages_info.unknown_ch),
    )
    return offset


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
