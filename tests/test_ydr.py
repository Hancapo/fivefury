from __future__ import annotations

import struct
import tempfile
from pathlib import Path

from fivefury import BoundComposite, BoundPolygonTriangle, BoundSphere, GameFileCache, GameFileType, Ydr, load_shader_library, jenk_hash, read_ydr
from fivefury.resource import build_rsc7, get_resource_total_page_count, split_rsc7_sections
from fivefury.ydr import build_ydr_bytes
from fivefury.ydr import YdrMaterialDescriptor
from tests.helpers import write_bytes

_DAT_VIRTUAL_BASE = 0x50000000
_DAT_PHYSICAL_BASE = 0x60000000
_ROOT_OFFSET = 0x10
_RESOURCE_FILE_BASE_SIZE = 0x10
_GTAV1_TYPES = 0x7755555555996996
_GTAV1_FLAGS = (1 << 0) | (1 << 3) | (1 << 6) | (1 << 14)
_VERTEX_STRIDE = 48


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _pack_vertex(
    position: tuple[float, float, float],
    normal: tuple[float, float, float],
    texcoord: tuple[float, float],
    tangent: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 1.0),
) -> bytes:
    return struct.pack("<3f3f2f4f", *position, *normal, *texcoord, *tangent)


def _build_test_ydr_bytes() -> bytes:
    texture_name = b"test_diffuse\x00"
    vertex_bytes = b"".join(
        [
            _pack_vertex((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0)),
            _pack_vertex((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0)),
            _pack_vertex((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0)),
        ]
    )
    index_offset = _align(len(vertex_bytes), 16)
    graphics_data = bytearray(index_offset + 6)
    graphics_data[: len(vertex_bytes)] = vertex_bytes
    graphics_data[index_offset : index_offset + 6] = struct.pack("<3H", 0, 1, 2)

    shader_group_off = 0x100
    shader_ptrs_off = 0x140
    shader_fx_off = 0x150
    params_block_off = 0x180
    texture_base_off = 0x1A0
    texture_name_off = 0x220
    high_header_off = 0x240
    high_ptrs_off = 0x250
    model_off = 0x260
    shader_mapping_off = 0x290
    geometry_ptrs_off = 0x2A0
    geometry_off = 0x2B0
    vertex_buffer_off = 0x350
    index_buffer_off = 0x3D0
    vertex_decl_off = 0x430

    system_size = _align(vertex_decl_off + 0x10, 16)
    system_data = bytearray(system_size)

    def virt(offset: int) -> int:
        return _DAT_VIRTUAL_BASE + offset

    def phys(offset: int) -> int:
        return _DAT_PHYSICAL_BASE + offset

    struct.pack_into("<Q", system_data, _ROOT_OFFSET + 0x00, virt(shader_group_off))
    struct.pack_into("<3f", system_data, _ROOT_OFFSET + 0x10, 0.5, 0.5, 0.0)
    struct.pack_into("<f", system_data, _ROOT_OFFSET + 0x1C, 1.0)
    struct.pack_into("<3f", system_data, _ROOT_OFFSET + 0x20, 0.0, 0.0, 0.0)
    struct.pack_into("<3f", system_data, _ROOT_OFFSET + 0x30, 1.0, 1.0, 0.0)
    struct.pack_into("<Q", system_data, _ROOT_OFFSET + 0x40, virt(high_header_off))

    struct.pack_into("<Q", system_data, shader_group_off + 0x10, virt(shader_ptrs_off))
    struct.pack_into("<H", system_data, shader_group_off + 0x18, 1)
    struct.pack_into("<H", system_data, shader_group_off + 0x1A, 1)

    struct.pack_into("<Q", system_data, shader_ptrs_off + 0x00, virt(shader_fx_off))

    struct.pack_into("<Q", system_data, shader_fx_off + 0x00, virt(params_block_off))
    struct.pack_into("<I", system_data, shader_fx_off + 0x08, int(jenk_hash("default")))
    system_data[shader_fx_off + 0x10] = 1
    system_data[shader_fx_off + 0x11] = 0
    struct.pack_into("<I", system_data, shader_fx_off + 0x18, int(jenk_hash("default.sps")))
    system_data[shader_fx_off + 0x26] = 0
    system_data[shader_fx_off + 0x27] = 1

    system_data[params_block_off + 0x00] = 0
    struct.pack_into("<Q", system_data, params_block_off + 0x08, virt(texture_base_off))
    struct.pack_into("<I", system_data, params_block_off + 0x10, int(jenk_hash("DiffuseSampler")))

    struct.pack_into("<Q", system_data, texture_base_off + 0x28, virt(texture_name_off))
    system_data[texture_name_off : texture_name_off + len(texture_name)] = texture_name

    struct.pack_into("<Q", system_data, high_header_off + 0x00, virt(high_ptrs_off))
    struct.pack_into("<H", system_data, high_header_off + 0x08, 1)
    struct.pack_into("<H", system_data, high_header_off + 0x0A, 1)
    struct.pack_into("<Q", system_data, high_ptrs_off + 0x00, virt(model_off))

    struct.pack_into("<Q", system_data, model_off + 0x08, virt(geometry_ptrs_off))
    struct.pack_into("<H", system_data, model_off + 0x10, 1)
    struct.pack_into("<H", system_data, model_off + 0x12, 1)
    struct.pack_into("<Q", system_data, model_off + 0x20, virt(shader_mapping_off))
    struct.pack_into("<H", system_data, model_off + 0x2C, 0)
    struct.pack_into("<H", system_data, model_off + 0x2E, 1)

    struct.pack_into("<H", system_data, shader_mapping_off + 0x00, 0)
    struct.pack_into("<Q", system_data, geometry_ptrs_off + 0x00, virt(geometry_off))

    struct.pack_into("<Q", system_data, geometry_off + 0x18, virt(vertex_buffer_off))
    struct.pack_into("<Q", system_data, geometry_off + 0x38, virt(index_buffer_off))
    struct.pack_into("<I", system_data, geometry_off + 0x58, 3)
    struct.pack_into("<I", system_data, geometry_off + 0x5C, 1)
    struct.pack_into("<H", system_data, geometry_off + 0x60, 3)
    struct.pack_into("<H", system_data, geometry_off + 0x70, _VERTEX_STRIDE)
    struct.pack_into("<Q", system_data, geometry_off + 0x78, phys(0))

    struct.pack_into("<H", system_data, vertex_buffer_off + 0x08, _VERTEX_STRIDE)
    struct.pack_into("<Q", system_data, vertex_buffer_off + 0x10, phys(0))
    struct.pack_into("<I", system_data, vertex_buffer_off + 0x18, 3)
    struct.pack_into("<Q", system_data, vertex_buffer_off + 0x30, virt(vertex_decl_off))

    struct.pack_into("<I", system_data, index_buffer_off + 0x08, 3)
    struct.pack_into("<Q", system_data, index_buffer_off + 0x10, phys(index_offset))

    struct.pack_into("<I", system_data, vertex_decl_off + 0x00, _GTAV1_FLAGS)
    struct.pack_into("<H", system_data, vertex_decl_off + 0x04, _VERTEX_STRIDE)
    system_data[vertex_decl_off + 0x07] = 4
    struct.pack_into("<Q", system_data, vertex_decl_off + 0x08, _GTAV1_TYPES)

    return build_rsc7(
        bytes(system_data),
        version=165,
        graphics_data=bytes(graphics_data),
        system_alignment=0x200,
        graphics_alignment=0x200,
    )


def _build_test_ydr_with_bound_bytes() -> bytes:
    source = _build_test_ydr_bytes()
    header, system_data, graphics_data = split_rsc7_sections(source)
    system = bytearray(system_data)
    bound_off = _align(len(system), 16)
    if bound_off > len(system):
        system.extend(b"\x00" * (bound_off - len(system)))
    bound_block = bytearray(_RESOURCE_FILE_BASE_SIZE + 0x70)
    struct.pack_into("<I", bound_block, 0x04, 1)
    struct.pack_into("<B", bound_block, _RESOURCE_FILE_BASE_SIZE + 0x00, 0)
    struct.pack_into("<f", bound_block, _RESOURCE_FILE_BASE_SIZE + 0x04, 0.75)
    struct.pack_into("<3f", bound_block, _RESOURCE_FILE_BASE_SIZE + 0x20, 1.25, 1.25, 0.75)
    struct.pack_into("<3f", bound_block, _RESOURCE_FILE_BASE_SIZE + 0x30, -0.25, -0.25, -0.75)
    struct.pack_into("<I", bound_block, _RESOURCE_FILE_BASE_SIZE + 0x3C, 1)
    struct.pack_into("<3f", bound_block, _RESOURCE_FILE_BASE_SIZE + 0x40, 0.5, 0.5, 0.0)
    struct.pack_into("<3f", bound_block, _RESOURCE_FILE_BASE_SIZE + 0x50, 0.5, 0.5, 0.0)
    struct.pack_into("<f", bound_block, _RESOURCE_FILE_BASE_SIZE + 0x6C, 1.0)
    system.extend(bound_block)
    struct.pack_into("<Q", system, _ROOT_OFFSET + 0xB8, _DAT_VIRTUAL_BASE + bound_off)
    return build_rsc7(
        bytes(system),
        version=header.version,
        graphics_data=graphics_data,
        system_alignment=0x200,
        graphics_alignment=0x200,
    )


def test_shader_library_reads_real_xml() -> None:
    library = load_shader_library(reload=True)

    shader = library.get_shader("normal_spec")
    assert shader is not None
    assert shader.pick_file_name(0) == "normal_spec.sps"
    assert shader.pick_file_name(3) == "normal_spec_cutout.sps"
    assert shader.get_parameter("DiffuseSampler") is not None
    assert shader.get_parameter("DiffuseSampler").uv_index == 0
    assert shader.get_parameter("BumpSampler").type_name == "Texture"


def test_read_ydr_parses_mesh_material_and_texture_names() -> None:
    ydr = read_ydr(_build_test_ydr_bytes(), path="triangle.ydr")

    assert isinstance(ydr, Ydr)
    assert ydr.version == 165
    assert ydr.bounding_box_min == (0.0, 0.0, 0.0)
    assert ydr.bounding_box_max == (1.0, 1.0, 0.0)
    assert len(ydr.materials) == 1

    material = ydr.materials[0]
    assert material.shader_definition is not None
    assert material.shader_definition.name == "default"
    assert material.resolved_shader_file_name == "default.sps"
    assert material.texture_names == ["test_diffuse"]
    assert material.get_texture("DiffuseSampler") is not None
    assert material.get_texture("DiffuseSampler").uv_index == 0
    assert material.get_texture("DiffuseSampler").parameter_type == "Texture"
    assert ydr.texture_names == ["test_diffuse"]

    descriptor = material.material_descriptor
    assert isinstance(descriptor, YdrMaterialDescriptor)
    assert descriptor.shader_name == "default"
    assert descriptor.shader_file_name == "default.sps"
    assert descriptor.get_texture("DiffuseSampler") is not None
    assert descriptor.get_texture("DiffuseSampler").texture_name == "test_diffuse"
    assert descriptor.get_texture("DiffuseSampler").uv_index == 0
    assert "Position" in descriptor.expected_semantics
    assert "TexCoord0" in descriptor.expected_semantics

    meshes = ydr.meshes
    assert len(meshes) == 1
    mesh = meshes[0]
    assert mesh.indices == [0, 1, 2]
    assert mesh.positions == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    assert mesh.normals == [(0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (0.0, 0.0, 1.0)]
    assert len(mesh.texcoords) == 1
    assert mesh.texcoords[0] == [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    assert mesh.material is material
    assert mesh.material.primary_texture_name == "test_diffuse"


def test_gamefilecache_parses_loose_ydr_as_renderable_model() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        write_bytes(root / "stream" / "triangle.ydr", _build_test_ydr_bytes())

        cache = GameFileCache(root, use_index_cache=False)
        cache.scan(use_index_cache=False)

        game_file = cache.get_file("stream/triangle.ydr")
        assert game_file is not None
        assert game_file.kind == GameFileType.YDR
        assert isinstance(game_file.parsed, Ydr)
        assert game_file.parsed.meshes[0].material.primary_texture_name == "test_diffuse"
        assert game_file.parsed.meshes[0].material.shader_definition is not None
        assert game_file.parsed.meshes[0].material.shader_definition.name == "default"
        assert game_file.parsed.meshes[0].material.material_descriptor.get_texture("DiffuseSampler") is not None
        assert game_file.parsed.meshes[0].indices == [0, 1, 2]


def test_read_ydr_reads_embedded_bound() -> None:
    ydr = read_ydr(_build_test_ydr_with_bound_bytes(), path="triangle_bound.ydr")

    assert isinstance(ydr.bound, BoundSphere)
    assert ydr.bound.sphere_center == (0.5, 0.5, 0.0)
    assert ydr.bound.sphere_radius == 0.75


def test_read_real_reference_ydr_embedded_bound() -> None:
    ydr = read_ydr(Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\prop_fire_hosereel.ydr"))

    assert ydr.bound is not None
    assert ydr.bound.bound_type.name in {"GEOMETRY", "GEOMETRY_BVH", "COMPOSITE", "BOX", "SPHERE", "CAPSULE", "CYLINDER", "DISC"}


def test_roundtrip_real_debug_ydr_rebuilds_page_metadata_from_block_layout_if_available() -> None:
    path = Path(r"C:\Users\vicho\OneDrive\Desktop\ydr_debug\bad\city61market.ydr")
    if not path.exists():
        return

    source = read_ydr(path)
    raw = build_ydr_bytes(source)
    header, system_data, _ = split_rsc7_sections(raw)
    pages_info_offset = int.from_bytes(system_data[0x08:0x10], "little") - _DAT_VIRTUAL_BASE

    assert get_resource_total_page_count(header.system_flags) == 8
    assert system_data[pages_info_offset + 0x08] == 8
    assert system_data[pages_info_offset + 0x09] == 0


def test_read_real_reference_ydr_does_not_confuse_models_pointer_with_joints() -> None:
    source = Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\prop_fire_hosereel.ydr")
    _header, system_data, _graphics_data = split_rsc7_sections(source.read_bytes())

    assert int.from_bytes(system_data[0x90:0x98], "little") == 0
    assert int.from_bytes(system_data[0xA0:0xA8], "little") != 0

    ydr = read_ydr(source)
    assert ydr.joints is None


def test_read_real_reference_ydr_decodes_embedded_geometry_polygons() -> None:
    ydr = read_ydr(Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\prop_fire_hosereel.ydr"))

    assert isinstance(ydr.bound, BoundComposite)
    geometry = ydr.bound.geometries[0]

    assert geometry.polygon_count > 0
    assert len(geometry.polygon_material_indices) == geometry.polygon_count
    assert sum(geometry.polygon_type_counts.values()) == geometry.polygon_count
    assert isinstance(geometry.polygons[0], BoundPolygonTriangle)
    assert geometry.polygons[0].index == 0
    assert geometry.polygons[0].material_index >= 0
    assert geometry.get_material(geometry.polygons[0].material_index) is not None
    assert geometry.get_material(geometry.polygons[0].material_index).name
    assert len(geometry.get_material(geometry.polygons[0].material_index).color) == 3
    assert len(geometry.vertices_shrunk) == geometry.vertex_count
    assert geometry.octants is not None
    assert geometry.octants.counts == (4, 4, 4, 4, 4, 4, 4, 4)
    assert geometry.octants.total_items == 32


def test_real_reference_ydr_roundtrip_preserves_embedded_assets(tmp_path: Path) -> None:
    source_path = Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\prop_fire_hosereel.ydr")
    source = read_ydr(source_path)

    out_path = tmp_path / "prop_fire_hosereel_roundtrip.ydr"
    source.save(out_path)
    rebuilt = read_ydr(out_path)

    assert rebuilt.embedded_textures is not None
    assert source.embedded_textures is not None
    assert rebuilt.embedded_textures.names() == source.embedded_textures.names()
    assert isinstance(rebuilt.bound, BoundComposite)
    assert isinstance(source.bound, BoundComposite)
    assert rebuilt.bound.child_count == source.bound.child_count
    assert rebuilt.bound.geometries[0].polygon_count == source.bound.geometries[0].polygon_count
    assert rebuilt.bound.geometries[0].octants is not None
    assert source.bound.geometries[0].octants is not None
    assert rebuilt.bound.geometries[0].octants.items == source.bound.geometries[0].octants.items


def test_real_reference_ydr_directory_roundtrips_preserving_declarations(tmp_path: Path) -> None:
    reference_dir = Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\ydrs")
    paths = sorted(reference_dir.glob("*.ydr"))
    if not paths:
        pytest.skip("real YDR reference directory not available")

    sparse_uv_files: set[str] = set()

    for source_path in paths:
        source = read_ydr(source_path)
        out_path = tmp_path / source_path.name
        source.save(out_path)
        rebuilt = read_ydr(out_path)

        assert len(rebuilt.meshes) == len(source.meshes), source_path.name
        for source_mesh, rebuilt_mesh in zip(source.meshes, rebuilt.meshes, strict=True):
            assert rebuilt_mesh.declaration_flags == source_mesh.declaration_flags, source_path.name
            assert rebuilt_mesh.declaration_types == source_mesh.declaration_types, source_path.name
            assert rebuilt_mesh.vertex_buffer_flags == source_mesh.vertex_buffer_flags, source_path.name
            assert rebuilt_mesh.vertex_stride == source_mesh.vertex_stride, source_path.name
            assert rebuilt_mesh.bone_ids == source_mesh.bone_ids, source_path.name
            assert rebuilt_mesh.blend_indices == source_mesh.blend_indices, source_path.name
            assert len(rebuilt_mesh.texcoords) == len(source_mesh.texcoords), source_path.name
            if any(not channel for channel in source_mesh.texcoords[:-1]):
                sparse_uv_files.add(source_path.name)

    assert {"ch2_09_l2_a.ydr", "ch2_09_l4.ydr"} <= sparse_uv_files


def test_real_reference_skinned_ydr_reads_packed_blend_indices(tmp_path: Path) -> None:
    source_path = Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\ydrs\lux_prop_lighter_luxe.ydr")
    if not source_path.exists():
        pytest.skip("real skinned YDR reference not available")

    source = read_ydr(source_path)
    mesh = source.meshes[0]

    assert source.has_skeleton
    assert mesh.bone_ids == [0, 1, 2]
    assert any(any(component != 0 for component in item) for item in mesh.blend_indices)

    out_path = tmp_path / source_path.name
    source.save(out_path)
    rebuilt = read_ydr(out_path)

    assert rebuilt.meshes[0].bone_ids == mesh.bone_ids
    assert rebuilt.meshes[0].blend_indices == mesh.blend_indices
