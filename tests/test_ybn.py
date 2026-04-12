from __future__ import annotations

import math
import struct
import tempfile
from pathlib import Path

from fivefury import (
    DEFAULT_BOUND_MATERIAL_LIBRARY,
    BoundAabb,
    BoundBvh,
    BoundBvhNode,
    BoundBvhTree,
    BoundBVH,
    BoundBox,
    BoundChild,
    BoundComposite,
    BoundCompositeFlag,
    BoundCompositeFlags,
    BoundGeometry,
    BoundMaterial,
    BoundMaterialColor,
    BoundPolygonTriangle,
    BoundSphere,
    BoundTransform,
    GameFileCache,
    GameFileType,
    Ybn,
    build_ybn_bytes,
    build_rsc7,
    get_bound_material_color,
    parse_bound_material_names,
    read_ybn,
    save_ybn,
)
from fivefury.resource import get_resource_flags_from_block_sizes, get_resource_total_page_count, split_rsc7_sections

_RESOURCE_FILE_BASE_SIZE = 0x10


def _build_sphere_bound_block(
    *,
    center: tuple[float, float, float] = (1.0, 2.0, 3.0),
    radius: float = 2.5,
    material_index: int = 7,
) -> bytes:
    data = bytearray(_RESOURCE_FILE_BASE_SIZE + 0x70)
    offset = _RESOURCE_FILE_BASE_SIZE
    cx, cy, cz = center
    minimum = (cx - radius, cy - radius, cz - radius)
    maximum = (cx + radius, cy + radius, cz + radius)
    struct.pack_into("<I", data, 0x04, 1)
    struct.pack_into("<B", data, offset + 0x00, 0)
    struct.pack_into("<f", data, offset + 0x04, radius)
    struct.pack_into("<3f", data, offset + 0x20, *maximum)
    struct.pack_into("<f", data, offset + 0x2C, 0.0)
    struct.pack_into("<3f", data, offset + 0x30, *minimum)
    struct.pack_into("<I", data, offset + 0x3C, 1)
    struct.pack_into("<3f", data, offset + 0x40, cx, cy, cz)
    data[offset + 0x4C] = material_index & 0xFF
    struct.pack_into("<3f", data, offset + 0x50, *center)
    struct.pack_into("<3f", data, offset + 0x60, 0.0, 0.0, 0.0)
    struct.pack_into("<f", data, offset + 0x6C, (4.0 / 3.0) * math.pi * (radius**3))
    return bytes(data)


def _build_test_ybn_bytes() -> bytes:
    return build_rsc7(_build_sphere_bound_block(), version=43, system_alignment=0x200)


def _make_sphere(
    *,
    center: tuple[float, float, float] = (1.0, 2.0, 3.0),
    radius: float = 2.5,
    material_index: int = 7,
) -> BoundSphere:
    cx, cy, cz = center
    minimum = (cx - radius, cy - radius, cz - radius)
    maximum = (cx + radius, cy + radius, cz + radius)
    volume = (4.0 / 3.0) * math.pi * (radius**3)
    return BoundSphere(
        bound_type=0,
        sphere_radius=radius,
        box_max=maximum,
        margin=0.0,
        box_min=minimum,
        box_center=center,
        sphere_center=center,
        material_index=material_index,
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
        volume=volume,
    )


def _make_box(
    *,
    minimum: tuple[float, float, float] = (-1.0, -2.0, -3.0),
    maximum: tuple[float, float, float] = (1.0, 2.0, 3.0),
    material_index: int = 5,
) -> BoundBox:
    center = tuple((a + b) * 0.5 for a, b in zip(minimum, maximum, strict=True))
    dx = maximum[0] - minimum[0]
    dy = maximum[1] - minimum[1]
    dz = maximum[2] - minimum[2]
    radius = math.sqrt(max(dx * dx, dy * dy, dz * dz)) * 0.5
    return BoundBox(
        bound_type=3,
        sphere_radius=radius,
        box_max=maximum,
        margin=0.0,
        box_min=minimum,
        box_center=center,
        sphere_center=center,
        material_index=material_index,
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
        volume=dx * dy * dz,
    )


def _make_geometry() -> BoundGeometry:
    vertices = [
        (-1.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
    ]
    polygon = BoundPolygonTriangle(
        polygon_type=0,
        raw=b"",
        tri_area=1.0,
        tri_index1=0,
        tri_index2=1,
        tri_index3=2,
        edge_index1=0xFFFF,
        edge_index2=0xFFFF,
        edge_index3=0xFFFF,
        material_index=0,
    )
    return BoundGeometry(
        bound_type=4,
        sphere_radius=1.5,
        box_max=(1.0, 1.0, 0.0),
        margin=0.0,
        box_min=(-1.0, 0.0, 0.0),
        box_center=(0.0, 0.5, 0.0),
        sphere_center=(0.0, 0.5, 0.0),
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
        volume=1.0,
        center_geom=(0.0, 0.5, 0.0),
        vertices=vertices,
        polygons=[polygon],
        polygon_material_indices=[0],
        materials=[
            BoundMaterial(
                type=56,
                procedural_id=1,
                room_id=2,
                ped_density=3,
                flags=4,
                material_color_index=5,
            )
        ],
        material_colours=[BoundMaterialColor(10, 20, 30, 40)],
        vertex_colours=[
            BoundMaterialColor(255, 0, 0, 255),
            BoundMaterialColor(0, 255, 0, 255),
            BoundMaterialColor(0, 0, 255, 255),
        ],
    )


def _make_bvh_geometry() -> BoundBVH:
    geometry = _make_geometry()
    bounds = BoundAabb(geometry.box_min, geometry.box_max)
    center = tuple((bounds.minimum[axis] + bounds.maximum[axis]) * 0.5 for axis in range(3))
    quantum = tuple(max(abs(bounds.minimum[axis] - center[axis]), abs(bounds.maximum[axis] - center[axis])) / 32767.0 or (1.0 / 32767.0) for axis in range(3))
    quantum_inverse = tuple(1.0 / value for value in quantum)
    return BoundBVH(
        bound_type=8,
        sphere_radius=geometry.sphere_radius,
        box_max=geometry.box_max,
        margin=geometry.margin,
        box_min=geometry.box_min,
        box_center=geometry.box_center,
        sphere_center=geometry.sphere_center,
        material_index=geometry.material_index,
        procedural_id=geometry.procedural_id,
        room_id=geometry.room_id,
        ped_density=geometry.ped_density,
        unk_flags=geometry.unk_flags,
        poly_flags=geometry.poly_flags,
        material_color_index=geometry.material_color_index,
        unknown_3ch=geometry.unknown_3ch,
        unknown_60h=geometry.unknown_60h,
        volume=geometry.volume,
        quantum=geometry.quantum,
        center_geom=geometry.center_geom,
        vertices=geometry.vertices,
        vertices_shrunk=geometry.vertices_shrunk,
        polygons=geometry.polygons,
        polygon_material_indices=geometry.polygon_material_indices,
        materials=geometry.materials,
        material_colours=geometry.material_colours,
        vertex_colours=geometry.vertex_colours,
        bvh=BoundBvh(
            minimum=bounds.minimum,
            maximum=bounds.maximum,
            center=center,
            quantum_inverse=quantum_inverse,
            quantum=quantum,
            nodes=[BoundBvhNode(minimum=bounds.minimum, maximum=bounds.maximum, item_id=0, item_count=1)],
            trees=[BoundBvhTree(minimum=bounds.minimum, maximum=bounds.maximum, node_index=0, node_index2=1)],
        ),
    )


def _make_large_bvh_geometry(*, polygon_count: int = 12, with_trivial_bvh: bool = False) -> BoundBVH:
    vertices: list[tuple[float, float, float]] = []
    polygons: list[BoundPolygonTriangle] = []
    polygon_material_indices: list[int] = []
    for index in range(polygon_count):
        x = float(index % 4)
        y = float(index // 4)
        base = len(vertices)
        vertices.extend(
            [
                (x, y, 0.0),
                (x + 0.9, y, 0.0),
                (x, y + 0.9, 0.0),
            ]
        )
        polygons.append(
            BoundPolygonTriangle(
                polygon_type=0,
                raw=b"",
                index=index,
                tri_area=0.405,
                tri_index1=base,
                tri_index2=base + 1,
                tri_index3=base + 2,
                edge_index1=0xFFFF,
                edge_index2=0xFFFF,
                edge_index3=0xFFFF,
                material_index=0,
            )
        )
        polygon_material_indices.append(0)

    box_min = (0.0, 0.0, 0.0)
    box_max = (
        max(vertex[0] for vertex in vertices),
        max(vertex[1] for vertex in vertices),
        0.0,
    )
    box_center = ((box_min[0] + box_max[0]) * 0.5, (box_min[1] + box_max[1]) * 0.5, 0.0)
    trivial_bvh = None
    if with_trivial_bvh:
        trivial_bvh = BoundBvh(
            minimum=box_min,
            maximum=box_max,
            center=box_center,
            quantum_inverse=(32767.0, 32767.0, 32767.0),
            quantum=(1.0 / 32767.0, 1.0 / 32767.0, 1.0 / 32767.0),
            nodes=[BoundBvhNode(minimum=box_min, maximum=box_max, item_id=0, item_count=polygon_count)],
            trees=[BoundBvhTree(minimum=box_min, maximum=box_max, node_index=0, node_index2=1)],
        )
    return BoundBVH(
        bound_type=8,
        sphere_radius=max(box_max[0], box_max[1]),
        box_max=box_max,
        margin=0.04,
        box_min=box_min,
        box_center=box_center,
        sphere_center=box_center,
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
        volume=float(polygon_count),
        center_geom=box_center,
        vertices=vertices,
        polygons=polygons,
        polygon_material_indices=polygon_material_indices,
        materials=[BoundMaterial(type=56)],
        bvh=trivial_bvh,
    )


def test_read_ybn_reads_sphere_bound() -> None:
    ybn = read_ybn(_build_test_ybn_bytes(), path="sphere.ybn")

    assert isinstance(ybn, Ybn)
    assert ybn.version == 43
    assert isinstance(ybn.bound, BoundSphere)
    assert ybn.bound.bound_type.value == 0
    assert ybn.bound.sphere_center == (1.0, 2.0, 3.0)
    assert ybn.bound.sphere_radius == 2.5
    assert ybn.bound.material_index == 7


def test_build_ybn_bytes_roundtrips_sphere_bound() -> None:
    source = _make_sphere()

    data = build_ybn_bytes(source)
    ybn = read_ybn(data, path="roundtrip_sphere.ybn")
    header, system_data, _ = split_rsc7_sections(data)

    assert isinstance(ybn.bound, BoundSphere)
    assert ybn.bound.sphere_center == source.sphere_center
    assert ybn.bound.sphere_radius == source.sphere_radius
    assert ybn.bound.material_index == source.material_index
    assert ybn.bound.file_vft != 0
    assert ybn.bound.file_pages_info is not None
    assert ybn.bound.file_pages_info.system_pages_count == get_resource_total_page_count(header.system_flags)
    assert int.from_bytes(system_data[8:16], "little") != 0


def test_default_bound_material_library_has_expected_names() -> None:
    assert DEFAULT_BOUND_MATERIAL_LIBRARY.count >= 200
    assert DEFAULT_BOUND_MATERIAL_LIBRARY.get_name(0) == "DEFAULT"
    assert DEFAULT_BOUND_MATERIAL_LIBRARY.get_name(7) == "RUMBLE_STRIP"
    assert DEFAULT_BOUND_MATERIAL_LIBRARY.get_color(7) == get_bound_material_color(7)


def test_parse_bound_material_names_uses_simple_name_per_line_format() -> None:
    library = parse_bound_material_names("# comment\nDEFAULT | #112233\nCONCRETE\nROCK | 10 20 30\n")

    assert library.count == 3
    assert library.get_name(2) == "ROCK"
    assert library.get_color(0) == (17, 34, 51)
    assert library.get_color(2) == (10, 20, 30)


def test_roundtrip_real_west02_ybn_if_available() -> None:
    source_path = Path(r"C:\Users\vicho\OneDrive\Desktop\west02_0.ybn")
    if not source_path.exists():
        return

    source = read_ybn(source_path)
    data = source.to_bytes()
    roundtrip = read_ybn(data)
    header, system_data, _ = split_rsc7_sections(data)

    assert roundtrip.bound.file_vft != 0
    assert roundtrip.bound.file_pages_info is not None
    assert roundtrip.bound.file_pages_info.system_pages_count == get_resource_total_page_count(header.system_flags)
    assert int.from_bytes(system_data[0:4], "little") != 0
    assert int.from_bytes(system_data[8:16], "little") != 0
    assert len(roundtrip.bound.geometries) == len(source.bound.geometries)
    assert len(roundtrip.bound.geometries[0].polygons) == len(source.bound.geometries[0].polygons)
    assert len(roundtrip.bound.geometries[0].bvh.nodes) == len(source.bound.geometries[0].bvh.nodes)
    assert len(roundtrip.bound.geometries[0].bvh.trees) == len(source.bound.geometries[0].bvh.trees)


def test_resource_page_flags_match_codewalker_assign_positions2_for_real_ybn_if_available() -> None:
    source_path = Path(r"C:\Users\vicho\OneDrive\Desktop\ybn_debug\bad\aliencity2.ybn")
    if not source_path.exists():
        return

    from fivefury.bounds import BoundResourcePagesInfo, build_bound_system_layout

    source = read_ybn(source_path)
    _, block_spans = build_bound_system_layout(
        source.bound,
        root_pages_info=BoundResourcePagesInfo(system_pages_count=16, graphics_pages_count=0),
    )

    block_sizes = [span.size for span in block_spans]
    flags = get_resource_flags_from_block_sizes(block_sizes, (source.version >> 4) & 0xF, is_system=True)

    assert flags == 0x20101A82
    assert get_resource_total_page_count(flags) == 16


def test_roundtrip_ybn_rebuilds_mismatched_page_metadata_from_codewalker_layout_if_available() -> None:
    source_path = Path(r"C:\Users\vicho\OneDrive\Desktop\ybn_debug\bad\aliencity2.ybn")
    if not source_path.exists():
        return

    source = read_ybn(source_path.read_bytes(), path=source_path)
    data = source.to_bytes()
    header, _, _ = split_rsc7_sections(data)
    roundtrip = read_ybn(data)

    assert source.bound.file_pages_info is not None
    assert source.bound.file_pages_info.system_pages_count == 1
    assert source.validate() == ["YBN ResourcePagesInfo system page count does not match the RSC7 header"]
    assert roundtrip.bound.file_pages_info is not None
    assert roundtrip.bound.file_pages_info.system_pages_count == 16
    assert get_resource_total_page_count(header.system_flags) == 16
    assert roundtrip.validate() == []


def test_read_ybn_normalizes_real_bounds_from_codewalker_layout_if_available() -> None:
    source_path = Path(r"C:\Users\vicho\OneDrive\Desktop\ybn_debug\good\aliencity2_codewalker_by_xml_reimport.ybn")
    if not source_path.exists():
        return

    ybn = read_ybn(source_path)

    assert ybn.validate() == []


def test_gamefilecache_parses_loose_ybn() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        path = root / "physics" / "sphere.ybn"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_build_test_ybn_bytes())

        cache = GameFileCache(root, use_index_cache=False)
        cache.scan(use_index_cache=False)

        game_file = cache.get_file("physics/sphere.ybn")
        assert game_file is not None
        assert game_file.kind == GameFileType.YBN
        assert isinstance(game_file.parsed, Ybn)
        assert isinstance(game_file.parsed.bound, BoundSphere)
        assert game_file.parsed.bound.sphere_radius == 2.5


def test_ybn_from_bound_and_save_roundtrip_composite() -> None:
    sphere = _make_sphere(center=(0.0, 0.0, 0.0), radius=1.0, material_index=7)
    box = _make_box(minimum=(-0.5, -0.5, -0.5), maximum=(0.5, 0.5, 0.5), material_index=5)
    root = BoundComposite(
        bound_type=10,
        sphere_radius=2.0,
        box_max=(2.0, 2.0, 2.0),
        margin=0.0,
        box_min=(-2.0, -2.0, -2.0),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
        volume=1.0,
        children=[
            BoundChild(
                bound=sphere,
                transform=BoundTransform(
                    column1=(1.0, 0.0, 0.0),
                    column2=(0.0, 1.0, 0.0),
                    column3=(0.0, 0.0, 1.0),
                    column4=(1.0, 2.0, 3.0),
                ),
                bounds=BoundAabb(sphere.box_min, sphere.box_max),
            ),
            BoundChild(
                bound=box,
                transform=BoundTransform(
                    column1=(1.0, 0.0, 0.0),
                    column2=(0.0, 1.0, 0.0),
                    column3=(0.0, 0.0, 1.0),
                    column4=(-1.0, 0.0, 0.5),
                ),
                bounds=BoundAabb(box.box_min, box.box_max),
            ),
        ],
    )

    ybn = Ybn.from_bound(root)

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "composite.ybn"
        save_ybn(ybn, path)
        parsed = read_ybn(path)

    assert isinstance(parsed.bound, BoundComposite)
    assert parsed.bound.child_count == 2
    assert isinstance(parsed.bound.children[0].bound, BoundSphere)
    assert isinstance(parsed.bound.children[1].bound, BoundBox)
    assert parsed.bound.children[0].transform is not None
    assert parsed.bound.children[0].transform.translation == (1.0, 2.0, 3.0)
    assert parsed.bound.children[1].transform is not None
    assert parsed.bound.children[1].transform.translation == (-1.0, 0.0, 0.5)


def test_build_ybn_bytes_roundtrips_geometry_bound() -> None:
    source = _make_geometry()

    ybn = read_ybn(build_ybn_bytes(source), path="roundtrip_geometry.ybn")

    assert isinstance(ybn.bound, BoundGeometry)
    assert ybn.bound.vertex_count == 3
    assert ybn.bound.polygon_count == 1
    for actual, expected in zip(ybn.bound.vertices[0], source.vertices[0], strict=True):
        assert math.isclose(actual, expected, abs_tol=1e-5)
    assert isinstance(ybn.bound.polygons[0], BoundPolygonTriangle)
    assert ybn.bound.polygons[0].vertex_indices == (0, 1, 2)
    assert ybn.bound.polygon_material_indices == [0]
    assert len(ybn.bound.materials) == 1
    assert ybn.bound.materials[0].type == 56
    assert ybn.bound.materials[0].name == "METAL_SOLID_MEDIUM"
    assert ybn.bound.material_colours[0].rgba == (10, 20, 30, 40)
    assert ybn.bound.vertex_colours[2].rgba == (0, 0, 255, 255)
    assert len(ybn.bound.vertices_shrunk) == ybn.bound.vertex_count
    assert ybn.bound.octants is not None
    assert ybn.bound.octants.has_items
    assert len(ybn.bound.octants.items) == 8
    assert ybn.bound.octants.total_items > 0


def test_ybn_from_bound_and_save_roundtrip_composite_with_geometry_child() -> None:
    geometry = _make_geometry()
    root = BoundComposite(
        bound_type=10,
        sphere_radius=2.0,
        box_max=(2.0, 2.0, 2.0),
        margin=0.0,
        box_min=(-2.0, -2.0, -2.0),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
        volume=1.0,
        children=[
            BoundChild(
                bound=geometry,
                transform=BoundTransform(
                    column1=(1.0, 0.0, 0.0),
                    column2=(0.0, 1.0, 0.0),
                    column3=(0.0, 0.0, 1.0),
                    column4=(2.0, 0.0, 0.0),
                ),
                bounds=BoundAabb(geometry.box_min, geometry.box_max),
            )
        ],
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "composite_geometry.ybn"
        save_ybn(root, path)
        parsed = read_ybn(path)

    assert isinstance(parsed.bound, BoundComposite)
    assert parsed.bound.child_count == 1
    child = parsed.bound.children[0]
    assert child.transform is not None
    assert child.transform.translation == (2.0, 0.0, 0.0)
    assert isinstance(child.bound, BoundGeometry)
    assert child.bound.vertex_count == 3
    assert child.bound.polygon_count == 1


def test_build_ybn_bytes_roundtrips_composite_bvh_when_child_count_is_six() -> None:
    root = BoundComposite(
        bound_type=10,
        sphere_radius=1.0,
        box_max=(1.0, 1.0, 1.0),
        margin=0.0,
        box_min=(-1.0, -1.0, -1.0),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
        volume=1.0,
    )
    for index in range(6):
        sphere = _make_sphere(center=(0.0, 0.0, 0.0), radius=0.25, material_index=7)
        root.add_child(
            sphere,
            transform=BoundTransform(
                column1=(1.0, 0.0, 0.0),
                column2=(0.0, 1.0, 0.0),
                column3=(0.0, 0.0, 1.0),
                column4=(float(index) * 2.0, 0.0, 0.0),
                flags2=1,
                flags3=1,
            ),
            bounds=BoundAabb(sphere.box_min, sphere.box_max),
        )

    data = build_ybn_bytes(root)
    parsed = read_ybn(data, path="composite_bvh.ybn")
    _, system_data, _ = split_rsc7_sections(data)

    assert isinstance(parsed.bound, BoundComposite)
    assert parsed.bound.child_count == 6
    assert parsed.bound.bvh is not None
    assert parsed.bound.bvh.node_count > 0
    assert parsed.bound.bvh.tree_count > 0
    assert int.from_bytes(system_data[0xA8:0xB0], "little") != 0


def test_build_ybn_bytes_roundtrips_bvh_geometry_bound() -> None:
    source = _make_bvh_geometry()

    ybn = read_ybn(build_ybn_bytes(source), path="roundtrip_bvh_geometry.ybn")

    assert isinstance(ybn.bound, BoundBVH)
    assert ybn.bound.vertex_count == 3
    assert ybn.bound.polygon_count == 1
    assert ybn.bound.bvh is not None
    assert ybn.bound.bvh.node_count == 1
    assert ybn.bound.bvh.tree_count == 1
    assert ybn.bound.bvh.nodes[0].item_id == 0
    assert ybn.bound.bvh.nodes[0].item_count == 1


def test_build_ybn_bytes_generates_nontrivial_bvh_for_large_geometry() -> None:
    source = _make_large_bvh_geometry()

    raw = build_ybn_bytes(source)
    ybn = read_ybn(raw, path="generated_large_bvh.ybn")

    assert isinstance(ybn.bound, BoundBVH)
    assert ybn.bound.bvh is not None
    assert ybn.bound.bvh.node_count > 1
    assert ybn.bound.bvh.tree_count >= 1
    assert ybn.bound.bvh.leaf_nodes
    assert all(node.item_count <= 4 for node in ybn.bound.bvh.leaf_nodes)

    from fivefury.binary import u32
    from fivefury.resource import split_rsc7_sections

    _, system_data, _ = split_rsc7_sections(raw)
    assert u32(system_data, 0x84) == u32(system_data, 0xD0)


def test_build_ybn_bytes_rebuilds_trivial_large_bvh() -> None:
    source = _make_large_bvh_geometry(with_trivial_bvh=True)

    ybn = read_ybn(build_ybn_bytes(source), path="rebuilt_large_bvh.ybn")

    assert isinstance(ybn.bound, BoundBVH)
    assert ybn.bound.bvh is not None
    assert ybn.bound.bvh.node_count > 1
    assert ybn.bound.bvh.tree_count >= 1
    assert ybn.bound.bvh.leaf_nodes
    assert all(node.item_count <= 4 for node in ybn.bound.bvh.leaf_nodes)


def test_read_real_reference_ybn() -> None:
    path = Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\apa_ch2_04_12.ybn")

    ybn = read_ybn(path)

    assert ybn.bound.bound_type.name == "COMPOSITE"
    assert getattr(ybn.bound, "children", None)
    assert ybn.bound.file_pages_info is not None
    assert ybn.bound.file_pages_info.system_pages_count == 8


def test_roundtrip_real_reference_ybn_preserves_page_count_metadata() -> None:
    path = Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\apa_ch2_04_12.ybn")

    source = read_ybn(path)
    raw = source.to_bytes()
    header, _, _ = split_rsc7_sections(raw)
    roundtrip = read_ybn(raw)

    assert source.bound.file_pages_info is not None
    assert roundtrip.bound.file_pages_info is not None
    assert roundtrip.bound.file_pages_info.system_pages_count == get_resource_total_page_count(header.system_flags)
    assert roundtrip.system_pages_count == get_resource_total_page_count(header.system_flags)


def test_read_real_reference_ybn_decodes_geometry_polygons_and_bvh() -> None:
    path = Path(r"C:\Users\vicho\OneDrive\Documents\WalkerPy\references\apa_ch2_04_12.ybn")

    ybn = read_ybn(path)
    geometry = ybn.bound.geometries[0]

    assert isinstance(geometry, BoundBVH)
    assert geometry.polygon_count > 0
    assert len(geometry.polygon_material_indices) == geometry.polygon_count
    assert sum(geometry.polygon_type_counts.values()) == geometry.polygon_count
    assert isinstance(geometry.polygons[0], BoundPolygonTriangle)
    assert geometry.polygons[0].index == 0
    assert geometry.polygons[0].material_index >= 0
    assert geometry.bvh is not None
    assert geometry.bvh.node_count > 0
    assert geometry.bvh.tree_count > 0
    assert geometry.bvh.leaf_nodes


def test_build_ybn_bytes_does_not_emit_octants_for_bvh_geometry() -> None:
    source = _make_large_bvh_geometry()

    ybn = read_ybn(build_ybn_bytes(source), path="large_bvh_no_octants.ybn")

    assert isinstance(ybn.bound, BoundBVH)
    assert ybn.bound.octants is None


def test_build_ybn_bytes_rejects_invalid_geometry_indices() -> None:
    source = _make_geometry()
    source.polygons[0].tri_index3 = 99

    try:
        build_ybn_bytes(source)
    except ValueError as exc:
        assert "invalid vertex index" in str(exc)
    else:
        raise AssertionError("expected build_ybn_bytes to reject invalid geometry indices")


def test_build_ybn_bytes_rejects_invalid_geometry_material_indices() -> None:
    source = _make_geometry()
    source.polygons[0].material_index = 9
    source.polygon_material_indices = [9]

    try:
        build_ybn_bytes(source)
    except ValueError as exc:
        assert "invalid material index" in str(exc)
    else:
        raise AssertionError("expected build_ybn_bytes to reject invalid geometry material indices")


def test_build_ybn_bytes_normalizes_inverted_bound_boxes() -> None:
    source = _make_box(minimum=(-1.0, -2.0, -3.0), maximum=(4.0, 5.0, 6.0))
    source.box_min, source.box_max = source.box_max, source.box_min

    parsed = read_ybn(build_ybn_bytes(source), path="normalized_box.ybn")

    assert parsed.bound.box_min == (-1.0, -2.0, -3.0)
    assert parsed.bound.box_max == (4.0, 5.0, 6.0)


def test_build_ybn_bytes_falls_back_from_invalid_child_bounds() -> None:
    child = _make_box(minimum=(-1.0, -1.0, -1.0), maximum=(1.0, 1.0, 1.0))
    root = BoundComposite(
        bound_type=10,
        sphere_radius=1.0,
        box_max=(1.0, 1.0, 1.0),
        margin=0.0,
        box_min=(-1.0, -1.0, -1.0),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
        unknown_3ch=1,
        unknown_60h=(0.0, 0.0, 0.0),
        volume=1.0,
        children=[
            BoundChild(
                bound=child,
                bounds=BoundAabb((5.0, 5.0, 5.0), (0.0, 0.0, 0.0)),
            )
        ],
    )

    parsed = read_ybn(build_ybn_bytes(root), path="invalid_child_bounds_fallback.ybn")

    assert isinstance(parsed.bound, BoundComposite)
    assert parsed.bound.children[0].bounds is not None
    assert parsed.bound.children[0].bounds.minimum == child.box_min
    assert parsed.bound.children[0].bounds.maximum == child.box_max


def test_bound_composite_flags_expose_enum_aliases() -> None:
    flags = BoundCompositeFlags()
    flags.type_flags = BoundCompositeFlag.MAP_DYNAMIC | BoundCompositeFlag.MAP_COVER
    flags.include_flags = BoundCompositeFlag.OBJECT | BoundCompositeFlag.GLASS

    assert flags.flags1 == (BoundCompositeFlag.MAP_DYNAMIC | BoundCompositeFlag.MAP_COVER)
    assert flags.flags2 == (BoundCompositeFlag.OBJECT | BoundCompositeFlag.GLASS)
    assert flags.type_flags == flags.flags1
    assert flags.include_flags == flags.flags2


def test_build_ybn_bytes_rejects_invalid_triangle_edge_indices() -> None:
    source = _make_geometry()
    source.polygons[0].edge_index1 = BoundPolygonTriangle.pack_edge_index(5)

    try:
        build_ybn_bytes(source)
    except ValueError as exc:
        assert "invalid polygon index" in str(exc)
    else:
        raise AssertionError("expected build_ybn_bytes to reject invalid triangle edge indices")
