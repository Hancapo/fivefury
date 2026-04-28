from __future__ import annotations

from .model import PsoStruct


def serialize_psch(structs: dict[int, PsoStruct]) -> bytes:
    items = list(structs.items())
    header_size = 12 + len(items) * 8
    offset = header_size
    chunks: list[bytes] = []
    indexes: list[tuple[int, int]] = []
    for type_hash, struct_info in items:
        chunk = bytearray()
        chunk.extend(b"\x00\x00")
        chunk.extend(int(len(struct_info.entries)).to_bytes(2, "big", signed=False))
        chunk.extend(int(struct_info.length).to_bytes(4, "big", signed=True))
        chunk.extend(b"\x00\x00\x00\x00")
        for entry in struct_info.entries:
            chunk.extend(int(entry.name_hash).to_bytes(4, "big", signed=False))
            chunk.append(int(entry.type_id) & 0xFF)
            chunk.append(int(entry.subtype) & 0xFF)
            chunk.extend(int(entry.data_offset).to_bytes(2, "big", signed=False))
            chunk.extend(int(entry.reference_key & 0xFFFFFFFF).to_bytes(4, "big", signed=False))
        indexes.append((type_hash, offset))
        chunks.append(bytes(chunk))
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
