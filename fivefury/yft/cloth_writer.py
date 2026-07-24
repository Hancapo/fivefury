from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence

from ..bounds.writer import write_bound_resource
from ..resource import ResourceWriter
from .cloth import (
    YftClothBridge,
    YftClothController,
    YftClothMorphController,
    YftClothMorphMap,
    YftClothTuning,
    YftEnvironmentCloth,
    YftVerletCloth,
)
from .constants import CHAR_CLOTH_ARRAY_OFFSET, ENV_CLOTH_ARRAY_OFFSET

_VIRTUAL_BASE = 0x50000000
_ENVIRONMENT_CLOTH_VFT = 0x406065D8
_CLOTH_CONTROLLER_VFT = 0x4060DB18
_CLOTH_BRIDGE_VFT = 0x4060F160
_CLOTH_TUNING_VFT = 0x40606400
_MORPH_CONTROLLER_VFT = 0x406063D8
_VERLET_CLOTH_VFT = 0x4062CB48


def _virtual(offset: int) -> int:
    return _VIRTUAL_BASE + int(offset)


def _template(raw: bytes, size: int, *, vft: int = 0) -> bytearray:
    if raw and len(raw) != size:
        raise ValueError(f"cloth block template must be exactly 0x{size:X} bytes")
    result = bytearray(raw or bytes(size))
    if vft and not struct.unpack_from("<I", result, 0)[0]:
        struct.pack_into("<I", result, 0, vft)
    if size >= 8 and not struct.unpack_from("<I", result, 4)[0]:
        struct.pack_into("<I", result, 4, 1)
    return result


def _alloc_block(
    writer: ResourceWriter, raw: bytes, size: int, *, vft: int = 0
) -> int:
    offset = writer.alloc(size, 16)
    writer.data[offset : offset + size] = _template(raw, size, vft=vft)
    return offset


def _write_array(
    writer: ResourceWriter,
    header_offset: int,
    values,
    *,
    format: str,
    item_size: int,
) -> None:
    items = list(values)
    if len(items) > 0xFFFF:
        raise ValueError("cloth arrays cannot exceed 65535 items")
    if not items:
        writer.pack_into("QHHI", header_offset, 0, 0, 0, 0)
        return
    data_offset = writer.alloc(len(items) * item_size, max(2, min(item_size, 16)))
    if format == "raw":
        for index, value in enumerate(items):
            raw = bytes(value.raw if hasattr(value, "raw") else value)
            if len(raw) != item_size:
                raise ValueError(
                    f"cloth raw array item must be exactly {item_size} bytes"
                )
            start = data_offset + index * item_size
            writer.data[start : start + item_size] = raw
    else:
        for index, value in enumerate(items):
            args = value if isinstance(value, tuple) else (value,)
            writer.pack_into(format, data_offset + index * item_size, *args)
    writer.pack_into(
        "QHHI", header_offset, _virtual(data_offset), len(items), len(items), 0
    )


def _write_tuning(writer: ResourceWriter, tuning: YftClothTuning | None) -> int:
    if tuning is None:
        return 0
    offset = writer.alloc(0x40, 16)
    writer.pack_into("I", offset, int(tuning.vft) or _CLOTH_TUNING_VFT)
    writer.pack_into("I", offset + 0x04, 1)
    writer.pack_into(
        "2f", offset + 0x10, float(tuning.rotation_rate), float(tuning.angle_threshold)
    )
    writer.pack_into("3f", offset + 0x20, *tuning.extra_force)
    writer.pack_into("I", offset + 0x30, int(tuning.flags))
    writer.pack_into(
        "2f",
        offset + 0x34,
        float(tuning.weight),
        float(tuning.distance_threshold),
    )
    writer.data[offset + 0x3C : offset + 0x3F] = bytes(
        (
            int(tuning.pin_vertex) & 0xFF,
            int(tuning.non_pin_vertex0) & 0xFF,
            int(tuning.non_pin_vertex1) & 0xFF,
        )
    )
    return offset


def _write_fixed_block(
    writer: ResourceWriter, value: bytes, size: int, *, label: str
) -> int:
    if not value:
        return 0
    if len(value) != size:
        raise ValueError(f"{label} must be exactly 0x{size:X} bytes")
    offset = writer.alloc(size, 16)
    writer.data[offset : offset + size] = value
    return offset


def _write_bridge(writer: ResourceWriter, bridge: YftClothBridge | None) -> int:
    if bridge is None:
        return 0
    offset = _alloc_block(
        writer, bridge.raw_header, 0x140, vft=_CLOTH_BRIDGE_VFT
    )
    writer.pack_into("4I", offset + 0x10, *bridge.mesh_vertex_counts)
    for index, values in enumerate(bridge.pin_radii):
        _write_array(
            writer, offset + 0x20 + index * 0x10, values, format="f", item_size=4
        )
    for index, values in enumerate(bridge.vertex_weights):
        _write_array(
            writer, offset + 0x60 + index * 0x10, values, format="f", item_size=4
        )
    for index, values in enumerate(bridge.inflation_scales):
        _write_array(
            writer, offset + 0xA0 + index * 0x10, values, format="f", item_size=4
        )
    for index, values in enumerate(bridge.display_maps):
        _write_array(
            writer, offset + 0xE0 + index * 0x10, values, format="H", item_size=2
        )
    _write_array(
        writer, offset + 0x128, bridge.pinnable_words, format="I", item_size=4
    )
    return offset


def _write_morph_map(writer: ResourceWriter, morph_map: YftClothMorphMap | None) -> int:
    if morph_map is None:
        return 0
    offset = _alloc_block(writer, morph_map.raw_header, 0x190)
    arrays = (
        morph_map.position_weights,
        *morph_map.position_indices,
        morph_map.normal_weights,
        *morph_map.normal_indices,
        *morph_map.display_indices,
    )
    formats = (
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
    for values, (field_offset, format, item_size) in zip(arrays, formats):
        _write_array(
            writer,
            offset + field_offset,
            values,
            format=format,
            item_size=item_size,
        )
    writer.pack_into("I", offset + 0x180, int(morph_map.polygon_count))
    return offset


def _write_morph_controller(
    writer: ResourceWriter, controller: YftClothMorphController | None
) -> int:
    if controller is None:
        return 0
    offset = _alloc_block(
        writer, controller.raw_header, 0x40, vft=_MORPH_CONTROLLER_VFT
    )
    for index, morph_map in enumerate(controller.maps):
        map_offset = _write_morph_map(writer, morph_map)
        writer.pack_into(
            "Q",
            offset + 0x18 + index * 8,
            _virtual(map_offset) if map_offset else 0,
        )
    writer.pack_into("2Q", offset + 0x30, 0, 0)
    return offset


def _write_verlet(writer: ResourceWriter, cloth: YftVerletCloth | None) -> int:
    if cloth is None:
        return 0
    if cloth.previous_vertices and len(cloth.previous_vertices) != cloth.vertex_count:
        raise ValueError("cloth previous-vertex count must match vertex count")
    offset = _alloc_block(
        writer, cloth.raw_header, 0x180, vft=_VERLET_CLOTH_VFT
    )
    bound_offset = write_bound_resource(writer, cloth.bound) if cloth.bound else 0
    behavior_offset = _write_fixed_block(
        writer, cloth.behavior_data, 0x40, label="cloth behavior data"
    )
    auxiliary_offset = _write_fixed_block(
        writer, cloth.auxiliary_data, 0x10, label="cloth auxiliary data"
    )
    writer.pack_into(
        "Q", offset + 0x18, _virtual(bound_offset) if bound_offset else 0
    )
    writer.pack_into("3f", offset + 0x30, *cloth.bounds_min)
    writer.pack_into("3f", offset + 0x40, *cloth.bounds_max)
    _write_array(
        writer,
        offset + 0x70,
        cloth.previous_vertices,
        format="4f",
        item_size=16,
    )
    _write_array(
        writer, offset + 0x80, cloth.vertices, format="4f", item_size=16
    )
    _write_array(
        writer,
        offset + 0x100,
        cloth.secondary_constraints,
        format="raw",
        item_size=16,
    )
    _write_array(
        writer,
        offset + 0x110,
        cloth.constraints,
        format="raw",
        item_size=16,
    )
    writer.pack_into("I", offset + 0xEC, cloth.constraint_count)
    writer.pack_into("I", offset + 0xF0, cloth.vertex_count)
    writer.pack_into(
        "Q", offset + 0x130, _virtual(behavior_offset) if behavior_offset else 0
    )
    writer.pack_into(
        "Q", offset + 0x140, _virtual(auxiliary_offset) if auxiliary_offset else 0
    )
    writer.pack_into("H", offset + 0x14A, cloth.vertex_count)
    return offset


def _write_controller(writer: ResourceWriter, controller: YftClothController) -> int:
    if controller.bridge is None:
        raise ValueError("environment cloth requires a simulation-to-graphics bridge")
    if controller.morph is None:
        raise ValueError("environment cloth requires a morph controller")
    if controller.verlet_lods[0] is None:
        raise ValueError("environment cloth requires its highest-detail Verlet data")
    offset = _alloc_block(
        writer, controller.raw_header, 0x80, vft=_CLOTH_CONTROLLER_VFT
    )
    bridge_offset = _write_bridge(writer, controller.bridge)
    morph_offset = _write_morph_controller(writer, controller.morph)
    verlet_offsets = [
        _write_verlet(writer, verlet) for verlet in controller.verlet_lods
    ]
    writer.pack_into("Q", offset + 0x10, _virtual(bridge_offset))
    writer.pack_into("Q", offset + 0x18, _virtual(morph_offset))
    for index, verlet_offset in enumerate(verlet_offsets):
        writer.pack_into(
            "Q",
            offset + 0x20 + index * 8,
            _virtual(verlet_offset) if verlet_offset else 0,
        )
    writer.pack_into("3Q", offset + 0x38, 0, 0, 0)
    writer.pack_into("I", offset + 0x50, int(controller.controller_type))
    encoded_name = controller.name.encode("utf-8")
    if len(encoded_name) > 31:
        raise ValueError("cloth controller names cannot exceed 31 UTF-8 bytes")
    writer.data[offset + 0x58 : offset + 0x78] = encoded_name.ljust(32, b"\0")
    writer.pack_into("f", offset + 0x78, float(controller.blend))
    return offset


def write_environment_cloths(
    writer: ResourceWriter,
    cloths: Sequence[YftEnvironmentCloth],
    *,
    drawable_offsets: Mapping[str, int],
) -> None:
    writer.pack_into("QHHI", CHAR_CLOTH_ARRAY_OFFSET, 0, 0, 0, 0)
    if not cloths:
        writer.pack_into("QHHI", ENV_CLOTH_ARRAY_OFFSET, 0, 0, 0, 0)
        return
    if len(cloths) > 0xFFFF:
        raise ValueError("YFT cannot contain more than 65535 environment cloths")
    pointer_array_offset = writer.alloc(len(cloths) * 8, 8)
    for index, cloth in enumerate(cloths):
        drawable_offset = drawable_offsets.get(cloth.drawable_label)
        if drawable_offset is None:
            raise ValueError(
                f"environment cloth references unknown drawable label "
                f"'{cloth.drawable_label}'"
            )
        offset = _alloc_block(
            writer, cloth.raw_header, 0x80, vft=_ENVIRONMENT_CLOTH_VFT
        )
        tuning_offset = _write_tuning(writer, cloth.tuning)
        behavior_offset = _write_fixed_block(
            writer,
            cloth.behavior_data,
            0x40,
            label="environment cloth behavior data",
        )
        controller_offset = _write_controller(writer, cloth.controller)
        writer.pack_into(
            "Q", offset + 0x10, _virtual(tuning_offset) if tuning_offset else 0
        )
        writer.pack_into("Q", offset + 0x18, _virtual(drawable_offset))
        writer.pack_into(
            "Q", offset + 0x20, _virtual(behavior_offset) if behavior_offset else 0
        )
        writer.pack_into("Q", offset + 0x28, _virtual(controller_offset))
        writer.pack_into("2Q", offset + 0x30, 0, 0)
        writer.pack_into("3f", offset + 0x40, *cloth.initial_position)
        writer.pack_into("3f", offset + 0x50, *cloth.force)
        _write_array(
            writer, offset + 0x60, cloth.user_data, format="i", item_size=4
        )
        writer.pack_into("Q", offset + 0x70, 0)
        writer.pack_into("I", offset + 0x78, int(cloth.flags))
        writer.pack_into("Q", pointer_array_offset + index * 8, _virtual(offset))
    writer.pack_into(
        "QHHI",
        ENV_CLOTH_ARRAY_OFFSET,
        _virtual(pointer_array_offset),
        len(cloths),
        len(cloths),
        0,
    )


__all__ = ["write_environment_cloths"]
