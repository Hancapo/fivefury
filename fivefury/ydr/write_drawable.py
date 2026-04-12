from __future__ import annotations

import dataclasses
from typing import Callable, Mapping, Sequence

from ..resource import ResourceWriter
from .defs import LOD_ORDER, YdrLod
from .write_models import PreparedModelBlock


@dataclasses.dataclass(slots=True)
class DrawableModelsLayout:
    block_start: int = 0
    block_end: int = 0
    lod_headers: dict[YdrLod, int] = dataclasses.field(default_factory=dict)
    counts_by_lod: dict[YdrLod, int] = dataclasses.field(default_factory=dict)

    @property
    def block_size(self) -> int:
        if self.block_end <= self.block_start:
            return 0
        return self.block_end - self.block_start

    @property
    def total_units(self) -> int:
        if self.block_size <= 0:
            return 0
        return (self.block_size + 15) // 16

    def get_pointer(self, lod: YdrLod) -> int:
        return self.lod_headers.get(lod, 0)


def pages_info_length(page_counts: tuple[int, int]) -> int:
    return 16 + (8 * (page_counts[0] + page_counts[1]))


def write_pages_info(system: ResourceWriter, pages_off: int, page_counts: tuple[int, int]) -> None:
    system.pack_into("I", pages_off + 0x00, 0)
    system.pack_into("I", pages_off + 0x04, 0)
    system.data[pages_off + 0x08] = page_counts[0] & 0xFF
    system.data[pages_off + 0x09] = page_counts[1] & 0xFF
    system.pack_into("H", pages_off + 0x0A, 0)
    system.pack_into("I", pages_off + 0x0C, 0)


def write_drawable_models_block(
    system: ResourceWriter,
    model_blocks_by_lod: Mapping[YdrLod, Sequence[PreparedModelBlock]],
    *,
    write_model: Callable[[int, YdrLod, int], None],
    virtual: Callable[[int], int],
) -> DrawableModelsLayout:
    layout = DrawableModelsLayout()
    lod_blocks = {
        lod_name: list(model_blocks_by_lod.get(lod_name, ()))
        for lod_name in LOD_ORDER
        if model_blocks_by_lod.get(lod_name)
    }
    if not lod_blocks:
        return layout

    cursor = 0
    lod_header_offsets: dict[YdrLod, int] = {}
    model_offsets: dict[tuple[YdrLod, int], int] = {}
    for lod_name in LOD_ORDER:
        prepared_blocks = lod_blocks.get(lod_name)
        if not prepared_blocks:
            continue
        cursor = ((cursor + 15) // 16) * 16
        lod_header_offsets[lod_name] = cursor
        cursor += 0x10 + (len(prepared_blocks) * 8)
        for model_index, prepared_block in enumerate(prepared_blocks):
            cursor = ((cursor + 15) // 16) * 16
            model_offsets[(lod_name, model_index)] = cursor
            cursor += int(prepared_block.model_size)

    block_start = system.alloc(cursor, 16)
    layout.block_start = block_start
    layout.block_end = block_start + cursor

    for lod_name in LOD_ORDER:
        prepared_blocks = lod_blocks.get(lod_name)
        if not prepared_blocks:
            continue
        header_off = block_start + lod_header_offsets[lod_name]
        ptrs_off = header_off + 0x10
        system.pack_into("Q", header_off + 0x00, virtual(ptrs_off))
        system.pack_into("H", header_off + 0x08, len(prepared_blocks))
        system.pack_into("H", header_off + 0x0A, len(prepared_blocks))
        system.pack_into("I", header_off + 0x0C, 0)
        for model_index, prepared_block in enumerate(prepared_blocks):
            model_off = block_start + model_offsets[(lod_name, model_index)]
            write_model(model_off, lod_name, model_index)
            system.pack_into("Q", ptrs_off + (model_index * 8), virtual(model_off))
        layout.lod_headers[lod_name] = header_off
        layout.counts_by_lod[lod_name] = len(prepared_blocks)
    return layout


def write_drawable_root(
    system: ResourceWriter,
    *,
    drawable_file_vft: int,
    unknown_float_sentinel: int,
    pages_info_off: int,
    shader_group_off: int,
    texture_dictionary_off: int,
    skeleton_off: int,
    joints_off: int,
    drawable_models_layout: DrawableModelsLayout,
    drawable_name_off: int,
    lights_block_off: int,
    lights_count: int,
    bound_off: int,
    center: tuple[float, float, float],
    bounds_min: tuple[float, float, float],
    bounds_max: tuple[float, float, float],
    radius: float,
    lod_distances: Mapping[YdrLod, float],
    render_mask_flags: Mapping[YdrLod, int],
    unknown_98: int,
    unknown_9c: int,
    virtual: Callable[[int], int],
) -> None:
    system.pack_into("I", 0x00, int(drawable_file_vft))
    system.pack_into("I", 0x04, 1)
    system.pack_into("Q", 0x08, virtual(pages_info_off))

    system.pack_into("Q", 0x10, virtual(shader_group_off))
    if texture_dictionary_off:
        system.pack_into("Q", shader_group_off + 0x08, virtual(texture_dictionary_off))
    system.pack_into("Q", 0x18, virtual(skeleton_off) if skeleton_off else 0)
    system.pack_into("3f", 0x20, *center)
    system.pack_into("f", 0x2C, radius)
    system.pack_into("3f", 0x30, *bounds_min)
    system.pack_into("I", 0x3C, int(unknown_float_sentinel))
    system.pack_into("3f", 0x40, *bounds_max)
    system.pack_into("I", 0x4C, int(unknown_float_sentinel))
    system.pack_into("Q", 0x50, virtual(drawable_models_layout.get_pointer(YdrLod.HIGH)) if drawable_models_layout.get_pointer(YdrLod.HIGH) else 0)
    system.pack_into("Q", 0x58, virtual(drawable_models_layout.get_pointer(YdrLod.MEDIUM)) if drawable_models_layout.get_pointer(YdrLod.MEDIUM) else 0)
    system.pack_into("Q", 0x60, virtual(drawable_models_layout.get_pointer(YdrLod.LOW)) if drawable_models_layout.get_pointer(YdrLod.LOW) else 0)
    system.pack_into("Q", 0x68, virtual(drawable_models_layout.get_pointer(YdrLod.VERY_LOW)) if drawable_models_layout.get_pointer(YdrLod.VERY_LOW) else 0)
    system.pack_into("f", 0x70, float(lod_distances.get(YdrLod.HIGH, 0.0)))
    system.pack_into("f", 0x74, float(lod_distances.get(YdrLod.MEDIUM, 0.0)))
    system.pack_into("f", 0x78, float(lod_distances.get(YdrLod.LOW, 0.0)))
    system.pack_into("f", 0x7C, float(lod_distances.get(YdrLod.VERY_LOW, 0.0)))
    system.pack_into("I", 0x80, int(render_mask_flags.get(YdrLod.HIGH, 0)))
    system.pack_into("I", 0x84, int(render_mask_flags.get(YdrLod.MEDIUM, 0)))
    system.pack_into("I", 0x88, int(render_mask_flags.get(YdrLod.LOW, 0)))
    system.pack_into("I", 0x8C, int(render_mask_flags.get(YdrLod.VERY_LOW, 0)))
    system.pack_into("Q", 0x90, virtual(joints_off) if joints_off else 0)
    system.pack_into("H", 0x98, int(unknown_98))
    system.pack_into("H", 0x9A, drawable_models_layout.total_units)
    system.pack_into("I", 0x9C, int(unknown_9c))
    system.pack_into("Q", 0xA0, virtual(drawable_models_layout.block_start) if drawable_models_layout.block_start else 0)
    system.pack_into("Q", 0xA8, virtual(drawable_name_off))
    if lights_block_off:
        system.pack_into("Q", 0xB0, virtual(lights_block_off))
        system.pack_into("H", 0xB8, int(lights_count))
        system.pack_into("H", 0xBA, int(lights_count))
        system.pack_into("I", 0xBC, 0)
    system.pack_into("Q", 0xC0, 0)
    system.pack_into("Q", 0xC8, virtual(bound_off) if bound_off else 0)


__all__ = [
    "DrawableModelsLayout",
    "pages_info_length",
    "write_drawable_models_block",
    "write_drawable_root",
    "write_pages_info",
]
