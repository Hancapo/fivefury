from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Sequence

from ..bounds import Bound
from ..binary import align
from ..resource import (
    ResourceBlockSpan,
    ResourceWriter,
    build_rsc7,
    get_resource_total_page_count,
    layout_resource_sections,
)
from ..ydr import Ydr, YdrBuild
from ..ydr.builder import (
    _EMBEDDED_DRAWABLE_FILE_VFT,
    _ROOT_SIZE,
    _write_drawable_payload,
)
from ..ydr.prepare import (
    PreparedLods,
    PreparedMaterial,
    compute_model_collection_bounds,
    prepare_build,
)
from ..ydr.shaders import ShaderLibrary, load_shader_library
from ..ydr.write_buffers import GraphicsWriter
from ..ydr.write_drawable import pages_info_length, write_pages_info
from ..ydr.write_materials import prepare_materials
from .drawables import YftDrawable
from .fragment import Yft
from .physics import YftPhysicsLod
from .physics_authoring import normalize_physics_lod, physics_lod_pointers_for
from .physics_writer import write_physics_lod_group
from .validation import assert_valid_yft

_DAT_VIRTUAL_BASE = 0x50000000
_FRAGMENT_TYPE_VFT = 0x40571138
_FRAGMENT_ROOT_SIZE = 0x120


def _virtual(offset: int) -> int:
    return _DAT_VIRTUAL_BASE + int(offset)


@dataclasses.dataclass(slots=True)
class _PreparedFragmentDrawable:
    label: str
    name: str
    build: YdrBuild
    materials: list[PreparedMaterial]
    lods: PreparedLods
    root_offset: int = 0


def _drawable_build(drawable: Ydr | YdrBuild, *, name: str, version: int) -> YdrBuild:
    build = drawable if isinstance(drawable, YdrBuild) else drawable.to_build(name=name)
    return dataclasses.replace(build, name=build.name or name, version=int(version))


def _prepare_drawable(
    drawable: Ydr | YdrBuild,
    *,
    label: str,
    name: str,
    version: int,
    shader_library: ShaderLibrary,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
) -> _PreparedFragmentDrawable:
    build = _drawable_build(drawable, name=name, version=version)
    if build.model_count == 0:
        raise ValueError(f"YFT drawable '{name}' has no models")
    materials, lods = prepare_build(
        build,
        shader_library,
        prepare_materials=prepare_materials,
        generate_normals=generate_normals,
        generate_tangents=generate_tangents,
        fill_vertex_colours=fill_vertex_colours,
    )
    return _PreparedFragmentDrawable(
        label=label, name=name, build=build, materials=materials, lods=lods
    )


def _prepared_drawables(
    yft: Yft,
    *,
    shader_library: ShaderLibrary,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
) -> tuple[
    _PreparedFragmentDrawable | None,
    list[_PreparedFragmentDrawable],
    _PreparedFragmentDrawable | None,
    _PreparedFragmentDrawable | None,
]:
    version = int(yft.version)
    main = (
        _prepare_drawable(
            yft.main_drawable,
            label="drawable",
            name=f"{yft.name}_drawable",
            version=version,
            shader_library=shader_library,
            generate_normals=generate_normals,
            generate_tangents=generate_tangents,
            fill_vertex_colours=fill_vertex_colours,
        )
        if yft.main_drawable is not None
        else None
    )
    extras = [
        _prepare_drawable(
            entry.drawable,
            label=entry.label,
            name=entry.name or entry.label or f"extra_{index}",
            version=version,
            shader_library=shader_library,
            generate_normals=generate_normals,
            generate_tangents=generate_tangents,
            fill_vertex_colours=fill_vertex_colours,
        )
        for index, entry in enumerate(yft.drawables)
    ]
    damaged = (
        _prepare_drawable(
            yft.damaged_drawable,
            label="damaged",
            name=f"{yft.name}_damaged",
            version=version,
            shader_library=shader_library,
            generate_normals=generate_normals,
            generate_tangents=generate_tangents,
            fill_vertex_colours=fill_vertex_colours,
        )
        if yft.damaged_drawable is not None
        else None
    )
    cloth = (
        _prepare_drawable(
            yft.cloth_drawable,
            label="drawable_cloth",
            name=f"{yft.name}_cloth",
            version=version,
            shader_library=shader_library,
            generate_normals=generate_normals,
            generate_tangents=generate_tangents,
            fill_vertex_colours=fill_vertex_colours,
        )
        if yft.cloth_drawable is not None
        else None
    )
    return main, extras, damaged, cloth


def create_yft(
    drawable: Ydr | YdrBuild,
    *,
    name: str = "",
    version: int = 162,
    damaged_drawable: Ydr | YdrBuild | None = None,
    cloth_drawable: Ydr | YdrBuild | None = None,
    extra_drawables: Sequence[YftDrawable | tuple[str, Ydr | YdrBuild] | Ydr | YdrBuild] = (),
    physics_lods: Sequence[YftPhysicsLod] = (),
    physics_bound: Bound | None = None,
    physics_density: float = 1.0,
    bounding_sphere: tuple[float, float, float, float] | None = None,
) -> Yft:
    yft = Yft(version=int(version), path=name, main_drawable=drawable)
    yft.damaged_drawable = damaged_drawable
    yft.cloth_drawable = cloth_drawable
    if bounding_sphere is not None:
        yft.bounding_sphere = tuple(float(value) for value in bounding_sphere)
    for index, entry in enumerate(extra_drawables):
        if isinstance(entry, YftDrawable):
            yft.drawables.append(entry)
        elif isinstance(entry, tuple):
            label, extra = entry
            yft.drawables.append(YftDrawable(str(label), extra, name=str(label)))
        else:
            label = f"extra_{index}"
            yft.drawables.append(YftDrawable(label, entry, name=label))
    if physics_lods:
        yft.physics_lod_details = [
            normalize_physics_lod(
                lod,
                composite_bound=lod.composite_bound or physics_bound,
                density=physics_density,
            )
            for lod in physics_lods
        ]
        yft.physics_lods = physics_lod_pointers_for(yft.physics_lod_details)
    return yft


def _validate_authoring_yft(yft: Yft) -> None:
    assert_valid_yft(yft)


def _write_fragment_root(
    system: ResourceWriter,
    *,
    page_counts: tuple[int, int],
    yft: Yft,
    main: _PreparedFragmentDrawable | None,
    extras: Sequence[_PreparedFragmentDrawable],
    damaged: _PreparedFragmentDrawable | None,
    cloth: _PreparedFragmentDrawable | None,
) -> int:
    pages_info_off = system.alloc(pages_info_length(page_counts), 16)
    write_pages_info(system, pages_info_off, page_counts)

    extra_ptrs_off = system.alloc(len(extras) * 8, 8) if extras else 0
    extra_names_off = system.alloc(len(extras) * 8, 8) if extras else 0
    for index, item in enumerate(extras):
        system.pack_into("Q", extra_ptrs_off + index * 8, _virtual(item.root_offset))
        system.pack_into(
            "Q", extra_names_off + index * 8, _virtual(system.c_string(item.name))
        )

    root_child_off = system.alloc(0xE8, 16)
    if main is not None:
        system.pack_into("ff", root_child_off + 0x08, 1.0, 1.0)
        system.pack_into("Q", root_child_off + 0xA0, _virtual(main.root_offset))
        system.pack_into(
            "Q",
            root_child_off + 0xA8,
            _virtual(damaged.root_offset) if damaged is not None else 0,
        )

    system.pack_into("I", 0x00, _FRAGMENT_TYPE_VFT)
    system.pack_into("I", 0x04, 1)
    system.pack_into("Q", 0x08, _virtual(pages_info_off))
    system.pack_into("4f", 0x20, *yft.bounding_sphere)
    system.pack_into("Q", 0x30, _virtual(main.root_offset) if main is not None else 0)
    system.pack_into("Q", 0x38, _virtual(extra_ptrs_off) if extra_ptrs_off else 0)
    system.pack_into("Q", 0x40, _virtual(extra_names_off) if extra_names_off else 0)
    system.pack_into("I", 0x48, len(extras))
    system.pack_into(
        "Q", 0x50, _virtual(damaged.root_offset) if damaged is not None else 0
    )
    system.pack_into("Q", 0x58, _virtual(root_child_off))
    system.data[0xC0] = int(yft.state.entity_class) & 0xFF
    system.data[0xC1] = int(yft.state.art_asset_id).to_bytes(1, "little", signed=True)[
        0
    ]
    system.data[0xC2] = 1 if yft.state.attach_bottom_end else 0
    system.pack_into("H", 0xC4, int(yft.state.flags) & 0xFFFF)
    system.pack_into("i", 0xC8, int(yft.state.client_class_id))
    system.pack_into("f", 0xD0, float(yft.state.unbroken_elasticity))
    system.pack_into("f", 0xD4, float(yft.state.gravity_factor))
    system.pack_into("f", 0xD8, float(yft.state.buoyancy_factor))
    system.data[0xDC] = int(yft.state.glass_attachment_bone) & 0xFF
    system.data[0xDD] = int(yft.state.num_glass_pane_model_infos) & 0xFF
    system.pack_into("Q", 0xF8, _virtual(cloth.root_offset) if cloth is not None else 0)
    return root_child_off


def _build_yft_payload(
    yft: Yft,
    prepared: tuple[
        _PreparedFragmentDrawable | None,
        list[_PreparedFragmentDrawable],
        _PreparedFragmentDrawable | None,
        _PreparedFragmentDrawable | None,
    ],
    *,
    page_counts: tuple[int, int],
) -> tuple[bytes, bytes, list[ResourceBlockSpan], list[ResourceBlockSpan]]:
    system = ResourceWriter(initial_size=align(_FRAGMENT_ROOT_SIZE, 16))
    graphics = GraphicsWriter()
    main, extras, damaged, cloth = prepared
    for item in [main, *extras, damaged, cloth]:
        if item is None:
            continue
        item.root_offset = system.alloc(_ROOT_SIZE, 16)
        _write_drawable_payload(
            system,
            graphics,
            item.build,
            item.materials,
            item.lods,
            page_counts,
            root_off=item.root_offset,
            drawable_file_vft=_EMBEDDED_DRAWABLE_FILE_VFT,
            write_pages=False,
        )
    root_child_off = _write_fragment_root(
        system,
        page_counts=page_counts,
        yft=yft,
        main=main,
        extras=extras,
        damaged=damaged,
        cloth=cloth,
    )
    fallback_bound = None
    if main is not None and getattr(main.build, "bound", None) is not None:
        fallback_bound = main.build.bound
    physics_group_off, normalized_lods = write_physics_lod_group(
        system,
        yft.physics_lod_details,
        root_child_offset=root_child_off,
        main_drawable_offset=main.root_offset if main is not None else 0,
        damaged_drawable_offset=damaged.root_offset if damaged is not None else 0,
        fallback_bound=fallback_bound,
    )
    if physics_group_off:
        system.pack_into("Q", 0xF0, _virtual(physics_group_off))
        yft.physics_lod_details = list(normalized_lods)
        yft.physics_lods = physics_lod_pointers_for(normalized_lods)
    return system.finish(), graphics.finish(), system.block_spans, graphics.block_spans


def build_yft_bytes(
    source: Yft,
    *,
    shader_library: ShaderLibrary | None = None,
    generate_normals: bool = True,
    generate_tangents: bool = True,
    fill_vertex_colours: bool = True,
    lossless: bool = False,
) -> bytes:
    if lossless:
        if not source.raw_bytes:
            raise ValueError("lossless YFT writing requires a YFT read from bytes")
        return bytes(source.raw_bytes)

    _validate_authoring_yft(source)
    active_shader_library = (
        shader_library if shader_library is not None else load_shader_library()
    )
    prepared = _prepared_drawables(
        source,
        shader_library=active_shader_library,
        generate_normals=generate_normals,
        generate_tangents=generate_tangents,
        fill_vertex_colours=fill_vertex_colours,
    )
    if prepared[0] is None:
        raise ValueError("YFT writer requires a common drawable")
    if source.bounding_sphere == (0.0, 0.0, 0.0, 0.0):
        _center, _bounds_min, _bounds_max, radius = compute_model_collection_bounds(
            [model for lods in prepared[0].lods.values() for model in lods]
        )
        source = dataclasses.replace(source, bounding_sphere=(*_center, float(radius)))

    page_counts = (0, 0)
    system_flags = None
    graphics_flags = None
    system_data = b""
    graphics_data = b""
    for _ in range(16):
        system_data, graphics_data, system_blocks, graphics_blocks = _build_yft_payload(
            source, prepared, page_counts=page_counts
        )
        system_data, graphics_data, system_flags, graphics_flags = (
            layout_resource_sections(
                system_data,
                system_blocks,
                graphics_data,
                graphics_blocks,
                version=int(source.version),
            )
        )
        next_counts = (
            get_resource_total_page_count(system_flags),
            get_resource_total_page_count(graphics_flags),
        )
        if next_counts == page_counts:
            break
        page_counts = next_counts
    else:
        raise RuntimeError("YFT builder page-info sizing did not converge")

    assert system_flags is not None
    assert graphics_flags is not None
    return build_rsc7(
        system_data,
        version=int(source.version),
        graphics_data=graphics_data,
        system_alignment=0x200,
        graphics_alignment=0x200,
        system_flags=system_flags,
        graphics_flags=graphics_flags,
    )


def save_yft(source: Yft, destination: str | Path, **kwargs) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_yft_bytes(source, **kwargs))
    return target


__all__ = [
    "build_yft_bytes",
    "create_yft",
    "save_yft",
]
