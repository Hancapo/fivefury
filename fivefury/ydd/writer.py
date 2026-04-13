from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Sequence

from ..binary import align
from ..resource import ResourceBlockSpan, ResourceWriter, build_rsc7, get_resource_total_page_count, layout_resource_sections
from ..ydr import YdrBuild
from ..ydr.builder import _EMBEDDED_DRAWABLE_FILE_VFT, _ROOT_SIZE, _write_drawable_payload
from ..ydr.prepare import PreparedLods, PreparedMaterial, prepare_build
from ..ydr.shaders import ShaderLibrary, load_shader_library
from ..ydr.write_buffers import GraphicsWriter
from ..ydr.write_drawable import pages_info_length, write_pages_info
from ..ydr.write_materials import prepare_materials
from .model import Ydd, YddDrawable, YddDrawableCollection, _coerce_drawable_input

_DAT_VIRTUAL_BASE = 0x50000000
_DRAWABLE_DICTIONARY_FILE_VFT = 0x40571048
_DRAWABLE_DICTIONARY_ROOT_SIZE = 0x40


def _virtual(offset: int) -> int:
    return _DAT_VIRTUAL_BASE + int(offset)


@dataclasses.dataclass(slots=True)
class _PreparedYddDrawable:
    name_hash: int
    build: YdrBuild
    materials: list[PreparedMaterial]
    lods: PreparedLods


def _drawable_build(entry: YddDrawable, *, version: int) -> YdrBuild:
    name = entry.name or f"hash_{entry.name_hash:08X}"
    drawable = entry.drawable
    if isinstance(drawable, YdrBuild):
        build = drawable
    else:
        build = drawable.to_build(name=name)
    if build.name and int(build.version) == int(version):
        return build
    return dataclasses.replace(build, name=build.name or name, version=int(version))


def _prepare_ydd_drawables(
    entries: Sequence[YddDrawable],
    *,
    version: int,
    shader_library: ShaderLibrary,
    generate_normals: bool,
    generate_tangents: bool,
    fill_vertex_colours: bool,
) -> list[_PreparedYddDrawable]:
    prepared: list[_PreparedYddDrawable] = []
    for entry in entries:
        build = _drawable_build(entry, version=version)
        if build.model_count == 0:
            raise ValueError(f"YDD drawable '{entry.name}' has no models")
        materials, lods = prepare_build(
            build,
            shader_library,
            prepare_materials=prepare_materials,
            generate_normals=generate_normals,
            generate_tangents=generate_tangents,
            fill_vertex_colours=fill_vertex_colours,
        )
        prepared.append(
            _PreparedYddDrawable(
                name_hash=int(entry.name_hash) & 0xFFFFFFFF,
                build=build,
                materials=materials,
                lods=lods,
            )
        )
    return prepared


def _write_drawable_dictionary_root(
    system: ResourceWriter,
    *,
    page_counts: tuple[int, int],
    hashes: Sequence[int],
    drawable_root_offsets: Sequence[int],
) -> None:
    count = len(drawable_root_offsets)
    pages_info_off = system.alloc(pages_info_length(page_counts), 16)
    write_pages_info(system, pages_info_off, page_counts)

    hashes_off = system.alloc(count * 4, 4, relocate_pointers=False) if count else 0
    for index, name_hash in enumerate(hashes):
        system.pack_into("I", hashes_off + index * 4, int(name_hash) & 0xFFFFFFFF)

    drawable_ptrs_off = system.alloc(count * 8, 8) if count else 0
    for index, root_off in enumerate(drawable_root_offsets):
        system.pack_into("Q", drawable_ptrs_off + index * 8, _virtual(root_off))

    system.pack_into("I", 0x00, _DRAWABLE_DICTIONARY_FILE_VFT)
    system.pack_into("I", 0x04, 1)
    system.pack_into("Q", 0x08, _virtual(pages_info_off))
    system.pack_into("Q", 0x10, 0)
    system.pack_into("Q", 0x18, 1)
    system.pack_into("Q", 0x20, _virtual(hashes_off) if hashes_off else 0)
    system.pack_into("H", 0x28, count)
    system.pack_into("H", 0x2A, count)
    system.pack_into("I", 0x2C, 0)
    system.pack_into("Q", 0x30, _virtual(drawable_ptrs_off) if drawable_ptrs_off else 0)
    system.pack_into("H", 0x38, count)
    system.pack_into("H", 0x3A, count)
    system.pack_into("I", 0x3C, 0)


def _build_ydd_payload(
    prepared: Sequence[_PreparedYddDrawable],
    *,
    page_counts: tuple[int, int],
) -> tuple[bytes, bytes, list[ResourceBlockSpan], list[ResourceBlockSpan]]:
    system = ResourceWriter(initial_size=align(_DRAWABLE_DICTIONARY_ROOT_SIZE, 16))
    graphics = GraphicsWriter()
    root_offsets: list[int] = []

    for item in prepared:
        root_off = system.alloc(_ROOT_SIZE, 16)
        root_offsets.append(root_off)
        _write_drawable_payload(
            system,
            graphics,
            item.build,
            item.materials,
            item.lods,
            page_counts,
            root_off=root_off,
            drawable_file_vft=_EMBEDDED_DRAWABLE_FILE_VFT,
            write_pages=False,
        )

    _write_drawable_dictionary_root(
        system,
        page_counts=page_counts,
        hashes=[item.name_hash for item in prepared],
        drawable_root_offsets=root_offsets,
    )
    return system.finish(), graphics.finish(), system.block_spans, graphics.block_spans


def create_ydd(
    drawables: YddDrawableCollection,
    *,
    name: str = "",
    version: int = 165,
) -> Ydd:
    ydd = Ydd(version=int(version), path=name)
    ydd.with_drawables(drawables)
    return ydd


def build_ydd_bytes(
    source: Ydd | YddDrawableCollection,
    *,
    shader_library: ShaderLibrary | None = None,
    generate_normals: bool = True,
    generate_tangents: bool = True,
    fill_vertex_colours: bool = True,
) -> bytes:
    ydd = source if isinstance(source, Ydd) else create_ydd(source)
    if not ydd.drawables:
        raise ValueError("YDD writer requires at least one drawable")

    active_shader_library = shader_library if shader_library is not None else load_shader_library()
    prepared = _prepare_ydd_drawables(
        [_coerce_drawable_input(entry, index) for index, entry in enumerate(ydd.drawables)],
        version=int(ydd.version),
        shader_library=active_shader_library,
        generate_normals=generate_normals,
        generate_tangents=generate_tangents,
        fill_vertex_colours=fill_vertex_colours,
    )

    page_counts = (0, 0)
    system_flags = None
    graphics_flags = None
    system_data = b""
    graphics_data = b""
    for _ in range(16):
        system_data, graphics_data, system_blocks, graphics_blocks = _build_ydd_payload(
            prepared,
            page_counts=page_counts,
        )
        system_data, graphics_data, system_flags, graphics_flags = layout_resource_sections(
            system_data,
            system_blocks,
            graphics_data,
            graphics_blocks,
            version=int(ydd.version),
        )
        next_counts = (get_resource_total_page_count(system_flags), get_resource_total_page_count(graphics_flags))
        if next_counts == page_counts:
            break
        page_counts = next_counts
    else:
        raise RuntimeError("YDD builder page-info sizing did not converge")

    assert system_flags is not None
    assert graphics_flags is not None
    return build_rsc7(
        system_data,
        version=int(ydd.version),
        graphics_data=graphics_data,
        system_alignment=0x200,
        graphics_alignment=0x200,
        system_flags=system_flags,
        graphics_flags=graphics_flags,
    )


def save_ydd(source: Ydd | YddDrawableCollection, destination: str | Path, *, shader_library: ShaderLibrary | None = None) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_ydd_bytes(source, shader_library=shader_library))
    return target


__all__ = [
    "build_ydd_bytes",
    "create_ydd",
    "save_ydd",
]
