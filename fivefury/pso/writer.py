from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..binary import pack_i32_be as _i32
from ..binary import pack_u16_be as _u16
from ..binary import pack_u32_be as _u32
from .codec import joaat_checksum

PSO_BLOCK_ALIGNMENT = 16


def _block_offsets(
    blocks: Sequence[PsoBlockBuilder],
    *,
    block_alignment: int = PSO_BLOCK_ALIGNMENT,
) -> list[int]:
    alignment = int(block_alignment)
    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("PSO block alignment must be a positive power of two")

    offsets: list[int] = []
    current_offset = 16
    for block in blocks:
        current_offset = (current_offset + alignment - 1) & ~(alignment - 1)
        offsets.append(current_offset)
        current_offset += len(block.data)
    return offsets


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


def build_psin_section(
    blocks: Sequence[PsoBlockBuilder],
    prefix: bytes = b"\x70" * 8,
    *,
    block_alignment: int = PSO_BLOCK_ALIGNMENT,
) -> bytes:
    psin_body = bytearray(prefix)
    while len(psin_body) < 8:
        psin_body.append(0x70)

    payload = bytearray()
    payload.extend(b"PSIN")
    block_offsets = _block_offsets(blocks, block_alignment=block_alignment)
    section_length = max(
        (offset + len(block.data) for offset, block in zip(block_offsets, blocks)),
        default=16,
    )
    payload.extend(_u32(section_length))
    payload.extend(psin_body[:8])
    for offset, block in zip(block_offsets, blocks):
        payload.extend(b"\x00" * (offset - len(payload)))
        payload.extend(block.data)
    return bytes(payload)


def build_pmap_section(
    blocks: Sequence[PsoBlockBuilder],
    root_block_id: int,
    pmap_unknown: int = 0x7070,
    *,
    block_alignment: int = PSO_BLOCK_ALIGNMENT,
) -> bytes:
    payload = bytearray()
    payload.extend(b"PMAP")
    payload.extend(_u32(16 + len(blocks) * 16))
    payload.extend(_i32(root_block_id))
    payload.extend(_u16(len(blocks)))
    payload.extend(_u16(int(pmap_unknown)))

    for block, current_offset in zip(
        blocks,
        _block_offsets(blocks, block_alignment=block_alignment),
    ):
        payload.extend(_u32(block.name_hash))
        payload.extend(_i32(current_offset))
        payload.extend(_i32(0))
        payload.extend(_i32(len(block.data)))
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
    "PSO_BLOCK_ALIGNMENT",
    "PsoBlockBuilder",
    "PsoPointerPatch",
    "build_chks_section",
    "build_pmap_section",
    "build_psin_section",
    "encode_pointer_word",
    "finalize_sections_with_checksum",
    "patch_pointers",
]
