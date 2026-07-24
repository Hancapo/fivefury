from __future__ import annotations

import struct

from ..binary import u64 as _u64
from .io_helpers import try_virtual_offset
from .matrices import YftSharedMatrixSet


def read_shared_matrix_set(
    data: bytes,
    pointer: int,
) -> YftSharedMatrixSet | None:
    offset = try_virtual_offset(data, pointer)
    if offset is None:
        return None
    if offset + 0x20 > len(data):
        raise ValueError("shared matrix set header is truncated")
    if _u64(data, offset) or _u64(data, offset + 8) or _u64(data, offset + 0x18):
        raise ValueError(
            "shared matrix set driver header is not a legacy resource header"
        )
    count = data[offset + 0x10]
    if data[offset + 0x11] != count:
        raise ValueError("shared matrix set counts disagree")
    matrices_end = offset + 0x20 + count * 0x30
    if matrices_end > len(data):
        raise ValueError("shared matrix set matrices are truncated")
    matrices = [
        struct.unpack_from("<12f", data, offset + 0x20 + index * 0x30)
        for index in range(count)
    ]
    return YftSharedMatrixSet(
        matrices=matrices,
        is_skinned=bool(data[offset + 0x12]),
    )


__all__ = ["read_shared_matrix_set"]
