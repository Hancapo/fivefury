from __future__ import annotations

from ..binary import i32_be as _i32, u16_be as _u16, u32_be as _u32
from .model import PsoArrayHeader, PsoBlock, PsoEntry, PsoPointer, PsoStruct


def decode_pointer_word(word: int) -> PsoPointer:
    return PsoPointer(block_id=word & 0xFFF, offset=word >> 12)


def decode_pointer(data: bytes, offset: int) -> PsoPointer:
    return decode_pointer_word(_u32(data, offset))


def decode_array_header(data: bytes, offset: int) -> PsoArrayHeader:
    return PsoArrayHeader(pointer=decode_pointer(data, offset), count=_u16(data, offset + 8))


def parse_sections(data: bytes) -> dict[int, bytes]:
    sections: dict[int, bytes] = {}
    offset = 0
    while offset + 8 <= len(data):
        ident = _u32(data, offset)
        length = _u32(data, offset + 4)
        if length <= 0 or offset + length > len(data):
            raise ValueError(f"invalid PSO section length at offset {offset}: {length}")
        sections[ident] = data[offset : offset + length]
        offset += length
    return sections


def parse_pmap(data: bytes) -> tuple[dict[int, PsoBlock], int]:
    root_id = _i32(data, 8)
    count = _u16(data, 12)
    blocks: dict[int, PsoBlock] = {}
    offset = 16
    for index in range(count):
        name_hash = _u32(data, offset)
        block_offset = _i32(data, offset + 4)
        length = _i32(data, offset + 12)
        blocks[index + 1] = PsoBlock(name_hash=name_hash, offset=block_offset, length=length)
        offset += 16
    return blocks, root_id


def parse_psch(data: bytes) -> dict[int, PsoStruct]:
    count = _u32(data, 8)
    indexes: list[tuple[int, int]] = []
    offset = 12
    for _ in range(count):
        indexes.append((_u32(data, offset), _i32(data, offset + 4)))
        offset += 8
    result: dict[int, PsoStruct] = {}
    for name_hash, rel_offset in indexes:
        abs_offset = rel_offset
        if data[abs_offset] != 0:
            continue
        entries_count = _u16(data, abs_offset + 2)
        length = _i32(data, abs_offset + 4)
        entry_offset = abs_offset + 12
        entries: list[PsoEntry] = []
        for _ in range(entries_count):
            entries.append(
                PsoEntry(
                    name_hash=_u32(data, entry_offset),
                    type_id=data[entry_offset + 4],
                    subtype=data[entry_offset + 5],
                    data_offset=_u16(data, entry_offset + 6),
                    reference_key=_u32(data, entry_offset + 8),
                )
            )
            entry_offset += 12
        result[name_hash] = PsoStruct(name_hash=name_hash, length=length, entries=entries)
    return result


def joaat_checksum(data: bytes) -> int:
    hash_value = 0x3FAC7125
    for byte in data:
        signed = byte if byte < 128 else byte - 256
        hash_value = (hash_value + signed) & 0xFFFFFFFF
        hash_value = (hash_value + ((hash_value << 10) & 0xFFFFFFFF)) & 0xFFFFFFFF
        hash_value ^= hash_value >> 6
    hash_value = (hash_value + ((hash_value << 3) & 0xFFFFFFFF)) & 0xFFFFFFFF
    hash_value ^= hash_value >> 11
    hash_value = (hash_value + ((hash_value << 15) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return hash_value


__all__ = [
    "decode_array_header",
    "decode_pointer",
    "decode_pointer_word",
    "joaat_checksum",
    "parse_pmap",
    "parse_psch",
    "parse_sections",
]
