from __future__ import annotations

from pathlib import Path

from ..bounds import write_bound_resource
from ..binary import align
from ..resource import ResourceBlockSpan, ResourceWriter, build_rsc7, get_resource_total_page_count, layout_resource_sections, split_rsc7_sections
from .build_types import YdrBuild, YdrMaterialInput, YdrMeshInput, YdrModelInput, YdrTextureInput, create_ydr
from .defs import DAT_VIRTUAL_BASE, LOD_ORDER, YdrLod
from .prepare import (
    PreparedMaterial,
    ShaderParameterEntry,
    compute_model_collection_bounds,
    default_root_render_mask_flags,
    drawable_name,
    normalize_materials,
    prepare_build,
    select_layout,
)
from .shaders import ShaderLibrary, load_shader_library
from .write_buffers import GraphicsWriter
from .write_drawable import pages_info_length, write_drawable_models_block, write_drawable_root, write_pages_info
from .write_lights import write_lights
from .write_materials import prepare_materials, write_shader_blocks
from .write_joints import write_joints
from .write_models import prepare_model_block, write_model_block
from .write_skeleton import write_skeleton

_DRAWABLE_FILE_VFT = 0x40573178
_SHADER_GROUP_VFT = 0x406137F0
_TEXTURE_BASE_VFT = 0x40613CA0
_DRAWABLE_MODEL_VFT = 0x40610A98
_DRAWABLE_GEOMETRY_VFT = 0x40618798
_VERTEX_BUFFER_VFT = 0x4061D3F8
_INDEX_BUFFER_VFT = 0x4061D158
_UNKNOWN_FLOAT_SENTINEL = 0x7F800001
_ROOT_SIZE = 0xD0
_ENHANCED_YDR_VERSIONS = frozenset({154, 159, 171})


def _virtual(offset: int) -> int:
    return DAT_VIRTUAL_BASE + int(offset)


def _relocate_embedded_texture_dictionary(
    virtual_data: bytes,
    *,
    dict_offset: int,
    graphics_offset: int,
    enhanced: bool,
) -> bytes:
    count = int.from_bytes(virtual_data[0x28:0x2A], 'little')
    ptrs_offset = int.from_bytes(virtual_data[0x30:0x38], 'little') - DAT_VIRTUAL_BASE
    output = bytearray(dict_offset + len(virtual_data))
    output[dict_offset : dict_offset + len(virtual_data)] = virtual_data
    virtual_delta = dict_offset
    physical_delta = graphics_offset

    def add_virtual_ptr(relative_offset: int) -> None:
        value = int.from_bytes(output[dict_offset + relative_offset : dict_offset + relative_offset + 8], 'little')
        if value:
            output[dict_offset + relative_offset : dict_offset + relative_offset + 8] = (value + virtual_delta).to_bytes(8, 'little')

    def add_physical_ptr(relative_offset: int) -> None:
        value = int.from_bytes(output[dict_offset + relative_offset : dict_offset + relative_offset + 8], 'little')
        if value:
            output[dict_offset + relative_offset : dict_offset + relative_offset + 8] = (value + physical_delta).to_bytes(8, 'little')

    add_virtual_ptr(0x08)
    add_virtual_ptr(0x20)
    add_virtual_ptr(0x30)
    for index in range(count):
        ptr_pos = dict_offset + ptrs_offset + (index * 8)
        tex_ptr = int.from_bytes(output[ptr_pos : ptr_pos + 8], 'little')
        if not tex_ptr:
            continue
        output[ptr_pos : ptr_pos + 8] = (tex_ptr + virtual_delta).to_bytes(8, 'little')
        tex_off = int.from_bytes(
            virtual_data[ptrs_offset + (index * 8) : ptrs_offset + (index * 8) + 8],
            'little',
        ) - DAT_VIRTUAL_BASE
        add_virtual_ptr(tex_off + 0x28)
        if enhanced:
            add_virtual_ptr(tex_off + 0x30)
            add_physical_ptr(tex_off + 0x38)
        else:
            add_physical_ptr(tex_off + 0x70)
    return bytes(output[dict_offset:])


def _embedded_texture_game(source: YdrBuild) -> str:
    if source.embedded_textures is None:
        return 'gta5'
    game = (source.embedded_textures.game or '').strip().lower()
    if game:
        if game == 'gta5' and int(source.version) in _ENHANCED_YDR_VERSIONS:
            return 'gta5_enhanced'
        return game
    return 'gta5_enhanced' if int(source.version) in _ENHANCED_YDR_VERSIONS else 'gta5'


def _write_embedded_texture_dictionary(system: ResourceWriter, graphics: GraphicsWriter, source: YdrBuild) -> int:
    if source.embedded_textures is None or not source.embedded_textures.textures:
        return 0
    ytd_bytes = source.embedded_textures.to_bytes(game=_embedded_texture_game(source))
    header, virtual_data, graphics_data = split_rsc7_sections(ytd_bytes)
    dict_offset = system.alloc(len(virtual_data), 16)
    graphics_offset = graphics.alloc(graphics_data, 16, relocate_pointers=False) if graphics_data else 0
    relocated = _relocate_embedded_texture_dictionary(
        virtual_data,
        dict_offset=dict_offset,
        graphics_offset=graphics_offset,
        enhanced=int(header.version) == 5,
    )
    system.write(dict_offset, relocated)
    return dict_offset


def _build_system_payload(
    source: YdrBuild,
    prepared_materials: list[PreparedMaterial],
    prepared_lods,
    page_counts: tuple[int, int],
) -> tuple[bytes, bytes, list[ResourceBlockSpan], list[ResourceBlockSpan]]:
    system = ResourceWriter(initial_size=align(_ROOT_SIZE, 16))
    graphics = GraphicsWriter()

    shader_group_off, _shader_group_blocks_size = write_shader_blocks(
        system,
        prepared_materials,
        shader_parameter_entry_cls=ShaderParameterEntry,
        texture_base_vft=_TEXTURE_BASE_VFT,
        shader_group_vft=_SHADER_GROUP_VFT,
        virtual=_virtual,
    )
    skeleton_off = write_skeleton(system, source.skeleton, virtual=_virtual)
    joints_off = write_joints(system, source.joints, virtual=_virtual)
    lights_block_off = write_lights(system, source.lights)
    bound_off = write_bound_resource(system, source.bound) if source.bound is not None else 0
    texture_dictionary_off = _write_embedded_texture_dictionary(system, graphics, source)

    prepared_model_blocks_by_lod: dict[YdrLod, list[PreparedModelBlock]] = {}
    for lod_name in LOD_ORDER:
        prepared_models = prepared_lods.get(lod_name)
        if not prepared_models:
            continue
        prepared_model_blocks_by_lod[lod_name] = []
        for prepared_model in prepared_models:
            prepared_block = prepare_model_block(
                system,
                graphics,
                prepared_model,
                virtual=_virtual,
                vertex_buffer_vft=_VERTEX_BUFFER_VFT,
                index_buffer_vft=_INDEX_BUFFER_VFT,
                drawable_geometry_vft=_DRAWABLE_GEOMETRY_VFT,
            )
            prepared_model_blocks_by_lod[lod_name].append(prepared_block)

    def _write_model(model_off: int, lod_name: YdrLod, model_index: int) -> None:
        write_model_block(
            system,
            model_off,
            prepared_model_blocks_by_lod[lod_name][model_index],
            drawable_model_vft=_DRAWABLE_MODEL_VFT,
            virtual=_virtual,
        )

    drawable_models_layout = write_drawable_models_block(
        system,
        prepared_model_blocks_by_lod,
        write_model=_write_model,
        virtual=_virtual,
    )

    pages_info_off = system.alloc(pages_info_length(page_counts), 16)
    write_pages_info(system, pages_info_off, page_counts)

    center, bounds_min, bounds_max, radius = compute_model_collection_bounds(
        [model for lod_models in prepared_lods.values() for model in lod_models]
    )
    write_drawable_root(
        system,
        drawable_file_vft=_DRAWABLE_FILE_VFT,
        unknown_float_sentinel=_UNKNOWN_FLOAT_SENTINEL,
        pages_info_off=pages_info_off,
        shader_group_off=shader_group_off,
        texture_dictionary_off=texture_dictionary_off,
        skeleton_off=skeleton_off,
        joints_off=joints_off,
        drawable_models_layout=drawable_models_layout,
        drawable_name_off=system.c_string(drawable_name(source.name)),
        lights_block_off=lights_block_off,
        lights_count=len(source.lights),
        bound_off=bound_off,
        center=center,
        bounds_min=bounds_min,
        bounds_max=bounds_max,
        radius=radius,
        lod_distances={lod_name: float(source.lod_distances.get(lod_name, 9998.0)) for lod_name in LOD_ORDER},
        render_mask_flags={
            lod_name: int(source.render_mask_flags.get(lod_name, default_root_render_mask_flags(prepared_lods.get(lod_name, ()))))
            for lod_name in LOD_ORDER
        },
        unknown_98=source.unknown_98,
        unknown_9c=source.unknown_9c,
        virtual=_virtual,
    )
    return system.finish(), graphics.finish(), system.block_spans, graphics.block_spans


def ydr_to_build(source: 'Ydr', *, lod: YdrLod | str | None = None, name: str | None = None) -> YdrBuild:
    return source.to_build(lod=lod, name=name)


def build_ydr_bytes(
    source: 'YdrBuild | Ydr',
    *,
    shader_library: ShaderLibrary | None = None,
    generate_normals: bool = True,
    generate_tangents: bool = True,
    fill_vertex_colours: bool = True,
) -> bytes:
    from .model import Ydr

    if isinstance(source, Ydr):
        source = source.to_build()
    if source.model_count == 0:
        raise ValueError('YDR builder requires at least one mesh')

    active_shader_library = shader_library if shader_library is not None else load_shader_library()
    prepared_materials, prepared_lods = prepare_build(
        source,
        active_shader_library,
        prepare_materials=prepare_materials,
        generate_normals=generate_normals,
        generate_tangents=generate_tangents,
        fill_vertex_colours=fill_vertex_colours,
    )

    page_counts = (0, 0)
    system_data = b''
    graphics_data = b''
    system_flags = None
    graphics_flags = None
    for _ in range(16):
        system_data, graphics_data, system_blocks, graphics_blocks = _build_system_payload(
            source,
            prepared_materials,
            prepared_lods,
            page_counts,
        )
        system_data, graphics_data, system_flags, graphics_flags = layout_resource_sections(
            system_data,
            system_blocks,
            graphics_data,
            graphics_blocks,
            version=int(source.version),
        )
        system_page_count = get_resource_total_page_count(system_flags)
        next_counts = (system_page_count, get_resource_total_page_count(graphics_flags))
        if next_counts == page_counts:
            break
        page_counts = next_counts
    else:
        raise RuntimeError('YDR builder page-info sizing did not converge')

    assert system_flags is not None
    assert graphics_flags is not None

    return build_rsc7(
        system_data,
        version=source.version,
        graphics_data=graphics_data,
        system_alignment=0x200,
        graphics_alignment=0x200,
        system_flags=system_flags,
        graphics_flags=graphics_flags,
    )


def save_ydr(source: 'YdrBuild | Ydr', destination: str | Path, *, shader_library: ShaderLibrary | None = None) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_ydr_bytes(source, shader_library=shader_library))
    return target


_normalize_materials = normalize_materials
_select_layout = select_layout


__all__ = [
    'YdrBuild',
    'YdrMaterialInput',
    'YdrMeshInput',
    'YdrModelInput',
    'YdrTextureInput',
    'build_ydr_bytes',
    'create_ydr',
    'save_ydr',
    'ydr_to_build',
]
