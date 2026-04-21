from __future__ import annotations

import math
from pathlib import Path

import pytest

from fivefury import (
    GameFileCache,
    GameFileType,
    Ynv,
    YnvAdjacencyType,
    YnvContentFlags,
    YnvPoint,
    YnvPointType,
    YnvPortal,
    YnvPortalType,
    YnvSector,
    YnvSectorData,
    build_ynv_bytes,
    read_ynv,
)


_REFERENCE_DIR = Path(__file__).resolve().parents[1] / "references" / "ynv"


def _reference_ynv_paths() -> list[Path]:
    return sorted(_REFERENCE_DIR.glob("*.ynv"))


def _assert_float_tuple_close(left: tuple[float, ...], right: tuple[float, ...]) -> None:
    assert len(left) == len(right)
    for lvalue, rvalue in zip(left, right, strict=True):
        if math.isnan(lvalue) and math.isnan(rvalue):
            continue
        assert lvalue == pytest.approx(rvalue)


def _assert_sector_equal(left, right) -> None:
    if left is None or right is None:
        assert left is right
        return
    _assert_float_tuple_close(left.aabb_min, right.aabb_min)
    _assert_float_tuple_close(left.aabb_max, right.aabb_max)
    if math.isnan(left.aabb_min_w) and math.isnan(right.aabb_min_w):
        pass
    else:
        assert left.aabb_min_w == pytest.approx(right.aabb_min_w)
    if math.isnan(left.aabb_max_w) and math.isnan(right.aabb_max_w):
        pass
    else:
        assert left.aabb_max_w == pytest.approx(right.aabb_max_w)
    assert left.cell_aabb.min == pytest.approx(right.cell_aabb.min)
    assert left.cell_aabb.max == pytest.approx(right.cell_aabb.max)
    assert left.unused_54h == right.unused_54h
    assert left.unused_58h == right.unused_58h
    assert left.unused_5ch == right.unused_5ch
    if left.data is None or right.data is None:
        assert left.data is right.data
    else:
        assert left.data.points_start_id == right.data.points_start_id
        assert left.data.unused_04h == right.data.unused_04h
        assert left.data.poly_ids == right.data.poly_ids
        assert left.data.unused_1ch == right.data.unused_1ch
        assert len(left.data.points) == len(right.data.points)
        for left_point, right_point in zip(left.data.points, right.data.points, strict=True):
            assert left_point.position == pytest.approx(right_point.position)
            assert left_point.angle == right_point.angle
            assert left_point.type == right_point.type
            assert right_point.direction == pytest.approx(left_point.direction)
    _assert_sector_equal(left.subtree1, right.subtree1)
    _assert_sector_equal(left.subtree2, right.subtree2)
    _assert_sector_equal(left.subtree3, right.subtree3)
    _assert_sector_equal(left.subtree4, right.subtree4)


def _assert_roundtrip_equivalent(original: Ynv, rebuilt: Ynv) -> None:
    assert rebuilt.version == original.version
    assert rebuilt.content_flags == original.content_flags
    assert rebuilt.version_unk1 == original.version_unk1
    assert rebuilt.aabb_unk == original.aabb_unk
    assert rebuilt.area_id == original.area_id
    _assert_float_tuple_close(original.transform, rebuilt.transform)
    assert rebuilt.aabb_size == pytest.approx(original.aabb_size)
    assert rebuilt.adjacent_area_ids == original.adjacent_area_ids
    assert rebuilt.vertices_info == original.vertices_info
    assert rebuilt.indices_info == original.indices_info
    assert rebuilt.edges_info == original.edges_info
    assert rebuilt.polys_info == original.polys_info
    assert rebuilt.vertices == pytest.approx(original.vertices)
    assert rebuilt.indices == original.indices
    assert len(rebuilt.edges) == len(original.edges)
    for original_edge, rebuilt_edge in zip(original.edges, rebuilt.edges, strict=True):
        for left_part, right_part in ((original_edge.poly1, rebuilt_edge.poly1), (original_edge.poly2, rebuilt_edge.poly2)):
            assert right_part.area_id == left_part.area_id
            assert right_part.poly_id == left_part.poly_id
            assert right_part.adjacency_type == left_part.adjacency_type
            assert right_part.detail_flags == left_part.detail_flags
    assert len(rebuilt.polys) == len(original.polys)
    for original_poly, rebuilt_poly in zip(original.polys, rebuilt.polys, strict=True):
        assert rebuilt_poly.poly_flags0 == original_poly.poly_flags0
        assert rebuilt_poly.index_id == original_poly.index_id
        assert rebuilt_poly.index_count == original_poly.index_count
        assert rebuilt_poly.area_id == original_poly.area_id
        assert rebuilt_poly.unknown_08h == original_poly.unknown_08h
        assert rebuilt_poly.unknown_0ch == original_poly.unknown_0ch
        assert rebuilt_poly.unknown_10h == original_poly.unknown_10h
        assert rebuilt_poly.unknown_14h == original_poly.unknown_14h
        assert rebuilt_poly.cell_aabb.min == pytest.approx(original_poly.cell_aabb.min)
        assert rebuilt_poly.cell_aabb.max == pytest.approx(original_poly.cell_aabb.max)
        assert rebuilt_poly.poly_flags1 == original_poly.poly_flags1
        assert rebuilt_poly.poly_flags2 == original_poly.poly_flags2
        assert rebuilt_poly.slope_directions == original_poly.slope_directions
        assert rebuilt_poly.part_id == original_poly.part_id
        assert rebuilt_poly.portal_link_count == original_poly.portal_link_count
        assert rebuilt_poly.portal_link_id == original_poly.portal_link_id
    assert len(rebuilt.portals) == len(original.portals)
    for original_portal, rebuilt_portal in zip(original.portals, rebuilt.portals, strict=True):
        assert rebuilt_portal.type == original_portal.type
        assert rebuilt_portal.angle == original_portal.angle
        assert rebuilt_portal.flags_unk == original_portal.flags_unk
        assert rebuilt_portal.position_from == pytest.approx(original_portal.position_from)
        assert rebuilt_portal.position_to == pytest.approx(original_portal.position_to)
        assert rebuilt_portal.poly_id_from1 == original_portal.poly_id_from1
        assert rebuilt_portal.poly_id_from2 == original_portal.poly_id_from2
        assert rebuilt_portal.poly_id_to1 == original_portal.poly_id_to1
        assert rebuilt_portal.poly_id_to2 == original_portal.poly_id_to2
        assert rebuilt_portal.area_id_from == original_portal.area_id_from
        assert rebuilt_portal.area_id_to == original_portal.area_id_to
        assert rebuilt_portal.area_unk == original_portal.area_unk
        assert rebuilt_portal.direction == pytest.approx(original_portal.direction)
    assert rebuilt.portal_links == original.portal_links
    _assert_sector_equal(original.sector_tree, rebuilt.sector_tree)


def _minimal_sector_tree() -> YnvSector:
    return YnvSector(
        aabb_min=(0.0, 0.0, 0.0),
        aabb_max=(10.0, 10.0, 10.0),
        data=YnvSectorData(),
    )


def test_read_all_reference_ynv_samples() -> None:
    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    for path in paths:
        ynv = read_ynv(path)
        assert ynv.version == 2
        assert ynv.vertices
        assert ynv.indices
        assert ynv.edges
        assert ynv.polys
        assert ynv.sector_tree is not None


def test_reference_ynv_samples_validate_cleanly() -> None:
    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    for path in paths:
        ynv = read_ynv(path)
        assert ynv.validate() == []


def test_roundtrip_reference_ynv_sample() -> None:
    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    original = read_ynv(paths[0])
    rebuilt = read_ynv(build_ynv_bytes(original))
    _assert_roundtrip_equivalent(original, rebuilt)


def test_roundtrip_all_reference_ynv_samples() -> None:
    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    for path in paths:
        original = read_ynv(path)
        rebuilt = read_ynv(build_ynv_bytes(original))
        _assert_roundtrip_equivalent(original, rebuilt)


def test_gamefilecache_parses_loose_ynv(tmp_path: Path) -> None:
    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    stream_dir = tmp_path / "stream"
    stream_dir.mkdir()
    target = stream_dir / paths[0].name
    target.write_bytes(paths[0].read_bytes())
    cache = GameFileCache(tmp_path, use_index_cache=False)
    cache.scan(use_index_cache=False)
    game_file = cache.get_file(f"stream/{paths[0].name}")
    assert game_file is not None
    assert game_file.kind == GameFileType.YNV
    assert isinstance(game_file.parsed, Ynv)
    assert game_file.parsed.vertices


def test_edge_adjacency_type_roundtrips_from_detail_bits() -> None:
    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    edge_part = read_ynv(build_ynv_bytes(read_ynv(paths[0]))).edges[0].poly1
    assert isinstance(edge_part.adjacency_type, YnvAdjacencyType)


def test_reference_point_and_portal_types_are_typed() -> None:
    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    sample = read_ynv(paths[0])
    assert sample.points
    assert isinstance(sample.points[0].type, YnvPointType)
    if sample.portals:
        assert isinstance(sample.portals[0].type, YnvPortalType)


def test_point_and_portal_direction_helpers_roundtrip() -> None:
    point = YnvPoint(angle=64, type=YnvPointType.TYPE_3).build()
    assert point.direction == pytest.approx((64.0 / 255.0) * math.tau)
    point.direction = math.pi
    assert point.angle == int(round((math.pi % math.tau) * 255.0 / math.tau)) & 0xFF

    portal = YnvPortal(type=YnvPortalType.TYPE_2, angle=32).build()
    assert portal.direction == pytest.approx((32.0 / 255.0) * math.tau)
    portal.direction = math.pi / 2.0
    assert portal.angle == int(round(((math.pi / 2.0) % math.tau) * 255.0 / math.tau)) & 0xFF


def test_build_recalculates_content_flags_from_payload_presence() -> None:
    ynv = Ynv(
        content_flags=YnvContentFlags.VEHICLE | YnvContentFlags.PORTALS,
        polys=[],
        portals=[],
        sector_tree=_minimal_sector_tree(),
    ).build()
    assert ynv.content_flags == YnvContentFlags.VEHICLE

    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    sample = read_ynv(paths[0])
    sample.content_flags = YnvContentFlags.VEHICLE
    sample.build()
    assert sample.content_flags & YnvContentFlags.POLYGONS
    if sample.portals:
        assert sample.content_flags & YnvContentFlags.PORTALS
    assert sample.content_flags & YnvContentFlags.VEHICLE


def test_build_reindexes_sector_points() -> None:
    ynv = Ynv(
        sector_tree=YnvSector(
            aabb_min=(0.0, 0.0, 0.0),
            aabb_max=(10.0, 10.0, 10.0),
            data=YnvSectorData(points_start_id=99, points=[YnvPoint(position=(1.0, 1.0, 1.0))]),
            subtree1=YnvSector(
                aabb_min=(0.0, 0.0, 0.0),
                aabb_max=(5.0, 5.0, 5.0),
                data=YnvSectorData(points_start_id=77, points=[YnvPoint(position=(2.0, 2.0, 2.0))]),
            ),
        )
    ).build()
    assert ynv.sector_tree is not None
    assert ynv.sector_tree.data is not None
    assert ynv.sector_tree.data.points_start_id == 0
    assert ynv.sector_tree.subtree1 is not None
    assert ynv.sector_tree.subtree1.data is not None
    assert ynv.sector_tree.subtree1.data.points_start_id == 1
    assert len(ynv.points) == 2
    assert ynv.validate() == []


def test_writer_rejects_invalid_poly_index_span() -> None:
    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    sample = read_ynv(paths[0])
    sample.polys[0].index_id = len(sample.indices)
    with pytest.raises(ValueError, match="index span"):
        build_ynv_bytes(sample)


def test_writer_rejects_invalid_portal_link_span() -> None:
    paths = _reference_ynv_paths()
    if not paths:
        pytest.skip("real YNV reference directory not available")
    sample = read_ynv(paths[0])
    sample.polys[0].portal_link_id = len(sample.portal_links)
    sample.polys[0].portal_link_count = 1
    with pytest.raises(ValueError, match="portal link span"):
        build_ynv_bytes(sample)
