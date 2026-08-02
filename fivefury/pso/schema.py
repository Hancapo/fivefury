from __future__ import annotations

from collections.abc import Mapping

from .model import PsoEnum, PsoStruct


def _serialize_struct(struct_info: PsoStruct) -> bytes:
    chunk = bytearray(b"\x00\x00")
    chunk.extend(len(struct_info.entries).to_bytes(2, "big", signed=False))
    chunk.extend(int(struct_info.length).to_bytes(4, "big", signed=True))
    chunk.extend(b"\x00\x00\x00\x00")
    for entry in struct_info.entries:
        chunk.extend(int(entry.name_hash).to_bytes(4, "big", signed=False))
        chunk.append(int(entry.type_id) & 0xFF)
        chunk.append(int(entry.subtype) & 0xFF)
        chunk.extend(int(entry.data_offset).to_bytes(2, "big", signed=False))
        chunk.extend(
            int(entry.reference_key & 0xFFFFFFFF).to_bytes(4, "big", signed=False)
        )
    return bytes(chunk)


def _serialize_enum(enum_info: PsoEnum) -> bytes:
    chunk = bytearray(b"\x01\x00")
    chunk.extend(len(enum_info.entries).to_bytes(2, "big", signed=False))
    for entry in enum_info.entries:
        chunk.extend(int(entry.name_hash).to_bytes(4, "big", signed=False))
        chunk.extend(int(entry.value).to_bytes(4, "big", signed=True))
    return bytes(chunk)


def serialize_psch(
    structs: Mapping[int, PsoStruct],
    enums: Mapping[int, PsoEnum] | None = None,
) -> bytes:
    items = [
        (name_hash, _serialize_struct(info)) for name_hash, info in structs.items()
    ]
    items.extend(
        (name_hash, _serialize_enum(info)) for name_hash, info in (enums or {}).items()
    )
    header_size = 12 + len(items) * 8
    offset = header_size
    chunks: list[bytes] = []
    indexes: list[tuple[int, int]] = []
    for type_hash, chunk in items:
        indexes.append((type_hash, offset))
        chunks.append(chunk)
        offset += len(chunk)

    payload = bytearray()
    payload.extend(b"PSCH")
    payload.extend(offset.to_bytes(4, "big", signed=False))
    payload.extend(len(items).to_bytes(4, "big", signed=False))
    for type_hash, rel_offset in indexes:
        payload.extend(int(type_hash).to_bytes(4, "big", signed=False))
        payload.extend(int(rel_offset).to_bytes(4, "big", signed=True))
    for chunk in chunks:
        payload.extend(chunk)
    return bytes(payload)


__all__ = ["serialize_psch"]
