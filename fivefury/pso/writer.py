from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..binary import pack_i32_be as _i32, pack_u16_be as _u16, pack_u32_be as _u32
from .codec import joaat_checksum


@dataclass(slots=True)
class PsoBlockBuilder:
    name_hash: int
    data: bytearray = field(default_factory=bytearray)

    def append(self, payload: bytes) -> int:
        offset = len(self.data)
        self.data.extend(payload)
        return offset


@dataclass(slots=True)
class PsoPointerPatch:
    buffer: bytearray
    offset: int
    block_hash: int
    relative_offset: int


def encode_pointer_word(block_id: int, relative_offset: int) -> int:
    return ((relative_offset & 0xFFFFFFFF) << 12) | (block_id & 0xFFF)


def patch_pointers(patches: Sequence[PsoPointerPatch], block_ids: dict[int, int]) -> None:
    for patch in patches:
        block_id = block_ids[patch.block_hash]
        patch.buffer[patch.offset : patch.offset + 4] = _u32(encode_pointer_word(block_id, patch.relative_offset))


def build_psin_section(blocks: Sequence[PsoBlockBuilder], prefix: bytes = b"\x70" * 8) -> bytes:
    psin_body = bytearray(prefix)
    while len(psin_body) < 8:
        psin_body.append(0x70)

    payload = bytearray()
    payload.extend(b"PSIN")
    payload.extend(_u32(16 + sum(len(block.data) for block in blocks)))
    payload.extend(psin_body[:8])
    for block in blocks:
        payload.extend(block.data)
    return bytes(payload)


def build_pmap_section(blocks: Sequence[PsoBlockBuilder], root_block_id: int, pmap_unknown: int = 0x7070) -> bytes:
    payload = bytearray()
    payload.extend(b"PMAP")
    payload.extend(_u32(16 + len(blocks) * 16))
    payload.extend(_i32(root_block_id))
    payload.extend(_u16(len(blocks)))
    payload.extend(_u16(int(pmap_unknown)))

    current_offset = 16
    for block in blocks:
        payload.extend(_u32(block.name_hash))
        payload.extend(_i32(current_offset))
        payload.extend(_i32(0))
        payload.extend(_i32(len(block.data)))
        current_offset += len(block.data)
    return bytes(payload)


def build_chks_section(template_chks: bytes | None = None) -> bytes:
    payload = bytearray()
    payload.extend(b"CHKS")
    payload.extend(_u32(20))
    payload.extend(b"\x00\x00\x00\x00")
    payload.extend(b"\x00\x00\x00\x00")
    payload.extend(template_chks[16:20] if template_chks is not None and len(template_chks) >= 20 else _u32(0x79707070))
    return bytes(payload)


def finalize_sections_with_checksum(sections: Sequence[bytes]) -> bytes:
    file_data = bytearray().join(sections)
    file_size = len(file_data)
    file_data[-12:-8] = _u32(0)
    file_data[-8:-4] = _u32(0)
    checksum = joaat_checksum(file_data)
    file_data[-12:-8] = _u32(file_size)
    file_data[-8:-4] = _u32(checksum)
    return bytes(file_data)


__all__ = [
    "PsoBlockBuilder",
    "PsoPointerPatch",
    "build_chks_section",
    "build_pmap_section",
    "build_psin_section",
    "encode_pointer_word",
    "finalize_sections_with_checksum",
    "patch_pointers",
]
