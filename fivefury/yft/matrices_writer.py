from __future__ import annotations

from ..resource import ResourceWriter
from .matrices import YftSharedMatrixSet


def write_shared_matrix_set(
    system: ResourceWriter,
    value: YftSharedMatrixSet | None,
) -> int:
    if value is None:
        return 0
    offset = system.alloc(0x20 + value.matrix_count * 0x30, 16)
    system.data[offset + 0x10] = value.matrix_count & 0xFF
    system.data[offset + 0x11] = value.matrix_count & 0xFF
    system.data[offset + 0x12] = 1 if value.is_skinned else 0
    for index, matrix in enumerate(value.matrices):
        system.pack_into(
            "12f",
            offset + 0x20 + index * 0x30,
            *(float(component) for component in matrix),
        )
    return offset


__all__ = ["write_shared_matrix_set"]
