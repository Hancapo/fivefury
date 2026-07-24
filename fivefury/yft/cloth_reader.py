from __future__ import annotations

import struct
from collections.abc import Mapping

from ..bounds.reader import read_bound_from_pointer
from ..resource import checked_virtual_offset
from .cloth import (
    YftClothBridge,
    YftClothConstraint,
    YftClothController,
    YftClothMorphController,
    YftClothMorphMap,
    YftClothTuning,
    YftClothTuningFlag,
    YftEnvironmentCloth,
    YftEnvironmentClothFlag,
    YftVerletCloth,
)
from .constants import CHAR_CLOTH_ARRAY_OFFSET, ENV_CLOTH_ARRAY_OFFSET

_VIRTUAL_BASE = 0x50000000


def _offset(pointer: int, data: bytes) -> int:
    return checked_virtual_offset(pointer, data, base=_VIRTUAL_BASE)


def _pointer(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _read_array_header(data: bytes, offset: int) -> tuple[int, int, int]:
    pointer, count, capacity = struct.unpack_from("<QHH", data, offset)
    if count > capacity:
        raise ValueError(
            f"cloth array at 0x{offset:X} has count {count} above capacity {capacity}"
        )
    return pointer, count, capacity


def _read_array(
    data: bytes,
    offset: int,
    *,
    format: str,
    item_size: int,
):
    pointer, count, _capacity = _read_array_header(data, offset)
    if not pointer or not count:
        return []
    start = _offset(pointer, data)
    end = start + count * item_size
    if end > len(data):
        raise ValueError(f"cloth array at 0x{offset:X} is truncated")
    if format == "raw":
        return [bytes(data[index : index + item_size]) for index in range(start, end, item_size)]
    return [
        value[0] if len(value) == 1 else tuple(value)
        for value in struct.iter_unpack("<" + format, data[start:end])
    ]


def _read_tuning(data: bytes, pointer: int) -> YftClothTuning | None:
    if not pointer:
        return None
    offset = _offset(pointer, data)
    if offset + 0x40 > len(data):
        raise ValueError("cloth tuning block is truncated")
    return YftClothTuning(
        rotation_rate=struct.unpack_from("<f", data, offset + 0x10)[0],
        angle_threshold=struct.unpack_from("<f", data, offset + 0x14)[0],
        extra_force=struct.unpack_from("<3f", data, offset + 0x20),
        flags=YftClothTuningFlag(struct.unpack_from("<I", data, offset + 0x30)[0]),
        weight=struct.unpack_from("<f", data, offset + 0x34)[0],
        distance_threshold=struct.unpack_from("<f", data, offset + 0x38)[0],
        pin_vertex=data[offset + 0x3C],
        non_pin_vertex0=data[offset + 0x3D],
        non_pin_vertex1=data[offset + 0x3E],
        vft=struct.unpack_from("<I", data, offset)[0],
    )


def _read_bridge(data: bytes, pointer: int) -> YftClothBridge | None:
    if not pointer:
        return None
    offset = _offset(pointer, data)
    if offset + 0x140 > len(data):
        raise ValueError("cloth bridge block is truncated")
    return YftClothBridge(
        mesh_vertex_counts=struct.unpack_from("<4I", data, offset + 0x10),
        pin_radii=tuple(
            _read_array(data, offset + 0x20 + index * 0x10, format="f", item_size=4)
            for index in range(4)
        ),
        vertex_weights=tuple(
            _read_array(data, offset + 0x60 + index * 0x10, format="f", item_size=4)
            for index in range(4)
        ),
        inflation_scales=tuple(
            _read_array(data, offset + 0xA0 + index * 0x10, format="f", item_size=4)
            for index in range(4)
        ),
        display_maps=tuple(
            _read_array(data, offset + 0xE0 + index * 0x10, format="H", item_size=2)
            for index in range(4)
        ),
        pinnable_words=_read_array(
            data, offset + 0x128, format="I", item_size=4
        ),
        raw_header=bytes(data[offset : offset + 0x140]),
    )


_MORPH_ARRAYS = (
    (0x50, "4f", 16),
    (0x60, "H", 2),
    (0x70, "H", 2),
    (0x80, "H", 2),
    (0x90, "H", 2),
    (0xA0, "4f", 16),
    (0xB0, "H", 2),
    (0xC0, "H", 2),
    (0xD0, "H", 2),
    (0xE0, "H", 2),
    (0x150, "H", 2),
    (0x160, "H", 2),
)


def _read_morph_map(data: bytes, pointer: int) -> YftClothMorphMap | None:
    if not pointer:
        return None
    offset = _offset(pointer, data)
    if offset + 0x190 > len(data):
        raise ValueError("cloth morph-map block is truncated")
    arrays = [
        _read_array(data, offset + field_offset, format=format, item_size=item_size)
        for field_offset, format, item_size in _MORPH_ARRAYS
    ]
    return YftClothMorphMap(
        position_weights=arrays[0],
        position_indices=tuple(arrays[1:5]),
        normal_weights=arrays[5],
        normal_indices=tuple(arrays[6:10]),
        display_indices=(arrays[10], arrays[11]),
        polygon_count=struct.unpack_from("<I", data, offset + 0x180)[0],
        raw_header=bytes(data[offset : offset + 0x190]),
    )


def _read_morph_controller(
    data: bytes, pointer: int
) -> YftClothMorphController | None:
    if not pointer:
        return None
    offset = _offset(pointer, data)
    if offset + 0x40 > len(data):
        raise ValueError("cloth morph-controller block is truncated")
    return YftClothMorphController(
        maps=tuple(
            _read_morph_map(data, _pointer(data, offset + 0x18 + index * 8))
            for index in range(3)
        ),
        raw_header=bytes(data[offset : offset + 0x40]),
    )


def _read_optional_fixed_block(
    data: bytes, pointer: int, size: int, *, label: str
) -> bytes:
    if not pointer:
        return b""
    offset = _offset(pointer, data)
    if offset + size > len(data):
        raise ValueError(f"{label} block is truncated")
    return bytes(data[offset : offset + size])


def _read_verlet(data: bytes, pointer: int) -> YftVerletCloth | None:
    if not pointer:
        return None
    offset = _offset(pointer, data)
    if offset + 0x180 > len(data):
        raise ValueError("Verlet cloth block is truncated")
    bound_pointer = _pointer(data, offset + 0x18)
    behavior_pointer = _pointer(data, offset + 0x130)
    auxiliary_pointer = _pointer(data, offset + 0x140)
    return YftVerletCloth(
        bounds_min=struct.unpack_from("<3f", data, offset + 0x30),
        bounds_max=struct.unpack_from("<3f", data, offset + 0x40),
        previous_vertices=_read_array(
            data, offset + 0x70, format="4f", item_size=16
        ),
        vertices=_read_array(data, offset + 0x80, format="4f", item_size=16),
        secondary_constraints=[
            YftClothConstraint(raw)
            for raw in _read_array(
                data, offset + 0x100, format="raw", item_size=16
            )
        ],
        constraints=[
            YftClothConstraint(raw)
            for raw in _read_array(
                data, offset + 0x110, format="raw", item_size=16
            )
        ],
        bound=read_bound_from_pointer(bound_pointer, data) if bound_pointer else None,
        behavior_data=_read_optional_fixed_block(
            data, behavior_pointer, 0x40, label="cloth behavior"
        ),
        auxiliary_data=_read_optional_fixed_block(
            data, auxiliary_pointer, 0x10, label="cloth auxiliary"
        ),
        raw_header=bytes(data[offset : offset + 0x180]),
    )


def _read_controller(data: bytes, pointer: int) -> YftClothController:
    offset = _offset(pointer, data)
    if offset + 0x80 > len(data):
        raise ValueError("cloth controller block is truncated")
    name = (
        data[offset + 0x58 : offset + 0x78]
        .split(b"\0", 1)[0]
        .decode("utf-8", errors="replace")
    )
    return YftClothController(
        name=name,
        bridge=_read_bridge(data, _pointer(data, offset + 0x10)),
        morph=_read_morph_controller(data, _pointer(data, offset + 0x18)),
        verlet_lods=tuple(
            _read_verlet(data, _pointer(data, offset + 0x20 + index * 8))
            for index in range(3)
        ),
        controller_type=struct.unpack_from("<I", data, offset + 0x50)[0],
        blend=struct.unpack_from("<f", data, offset + 0x78)[0],
        raw_header=bytes(data[offset : offset + 0x80]),
    )


def read_environment_cloths(
    data: bytes,
    *,
    drawable_labels: Mapping[int, str],
) -> tuple[list[YftEnvironmentCloth], int]:
    pointer, count, _capacity = _read_array_header(data, ENV_CLOTH_ARRAY_OFFSET)
    _character_pointer, character_count, _character_capacity = _read_array_header(
        data, CHAR_CLOTH_ARRAY_OFFSET
    )
    if not pointer or not count:
        return [], character_count
    array_offset = _offset(pointer, data)
    if array_offset + count * 8 > len(data):
        raise ValueError("environment-cloth pointer array is truncated")
    result: list[YftEnvironmentCloth] = []
    for index in range(count):
        cloth_pointer = _pointer(data, array_offset + index * 8)
        cloth_offset = _offset(cloth_pointer, data)
        if cloth_offset + 0x80 > len(data):
            raise ValueError("environment-cloth block is truncated")
        controller_pointer = _pointer(data, cloth_offset + 0x28)
        if not controller_pointer:
            raise ValueError("environment cloth has no controller")
        drawable_pointer = _pointer(data, cloth_offset + 0x18)
        result.append(
            YftEnvironmentCloth(
                controller=_read_controller(data, controller_pointer),
                tuning=_read_tuning(data, _pointer(data, cloth_offset + 0x10)),
                drawable_label=drawable_labels.get(
                    drawable_pointer, f"pointer_{drawable_pointer:016X}"
                ),
                behavior_data=_read_optional_fixed_block(
                    data,
                    _pointer(data, cloth_offset + 0x20),
                    0x40,
                    label="environment cloth behavior",
                ),
                initial_position=struct.unpack_from(
                    "<3f", data, cloth_offset + 0x40
                ),
                force=struct.unpack_from("<3f", data, cloth_offset + 0x50),
                user_data=_read_array(
                    data, cloth_offset + 0x60, format="i", item_size=4
                ),
                flags=YftEnvironmentClothFlag(
                    struct.unpack_from("<I", data, cloth_offset + 0x78)[0]
                ),
                raw_header=bytes(data[cloth_offset : cloth_offset + 0x80]),
            )
        )
    return result, character_count


__all__ = ["read_environment_cloths"]
