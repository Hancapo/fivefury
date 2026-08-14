from __future__ import annotations

import struct

from .model import RelIndexHash


def named_item_header(
    index: RelIndexHash,
    data: bytes,
    name_by_offset: dict[int, str],
    label: str,
) -> tuple[int, dict[str, object]]:
    if len(data) < 8:
        raise ValueError(f"{label} header is truncated")
    packed, flags = struct.unpack_from("<II", data)
    type_id = packed & 0xFF
    name_table_offset = packed >> 8
    return type_id, {
        "name_hash": index.name_hash,
        "name": name_by_offset.get(name_table_offset),
        "data_offset": index.offset,
        "data_length": index.length,
        "raw_data": data,
        "name_table_offset": name_table_offset,
        "flags": flags,
    }


def require_exact_size(data: bytes, size: int, label: str) -> None:
    if len(data) != size:
        raise ValueError(f"{label} length is invalid")


__all__ = ["named_item_header", "require_exact_size"]
