from __future__ import annotations

import math
from pathlib import Path

import pytest

import fivefury.ynv.assimp as ynv_assimp
from fivefury import (
    YNV_MAX_POLYGON_VERTICES,
    AssimpScene,
    GameTarget,
    YdrMeshInput,
    YnvEdgeFlags,
    YnvPortal,
    YnvSourcePolygon,
    build_ynv_bytes,
    build_ynv_cell,
    build_ynv_cells,
    clip_ynv_polygon_to_cell,
    get_ynv_area_id,
    get_ynv_cell_span,
    get_ynv_file_coords,
    obj_to_nav,
    read_ynv,
)


def _fake_scene(positions: list[tuple[float, float, float]]) -> AssimpScene:
    return AssimpScene(
        meshes=[
            YdrMeshInput(
                positions=positions,
                indices=[0, 1, 2],
                material="default",
            )
        ],
        materials=[],
        name="fake_nav",
    )


def test_obj_to_nav_writes_single_valid_ynv(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ynv_assimp,
        "read_assimp_scene",
        lambda *args, **kwargs: _fake_scene([(10.0, 10.0, 0.0), (20.0, 10.0, 0.0), (10.0, 20.0, 0.0)]),
    )
    obj_path = tmp_path / "triangle.obj"
    obj_path.write_text("# fake\n", encoding="utf-8")

    outputs = obj_to_nav(obj_path, tmp_path / "out")

    assert len(outputs) == 1
    assert outputs[0].name == "navmesh[120][120].ynv"
    ynv = read_ynv(outputs[0])
    assert ynv.area_id == 4040
    assert len(ynv.polys) == 1
    assert ynv.validate() == []


def test_obj_to_nav_splits_triangle_across_nav_cells(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ynv_assimp,
        "read_assimp_scene",
        lambda *args, **kwargs: _fake_scene([(-10.0, 10.0, 0.0), (10.0, 10.0, 0.0), (10.0, 40.0, 0.0)]),
    )
    obj_path = tmp_path / "split.obj"
    obj_path.write_text("# fake\n", encoding="utf-8")

    outputs = obj_to_nav(obj_path, tmp_path / "out")

    names = sorted(path.name for path in outputs)
    assert names == ["navmesh[117][120].ynv", "navmesh[120][120].ynv"]
    for path in outputs:
        ynv = read_ynv(path)
        assert ynv.polys
        assert ynv.validate() == []


def test_public_grid_helpers_match_gta_nav_coordinates() -> None:
    assert get_ynv_cell_span(-10.0, 10.0) == range(39, 41)
    assert get_ynv_area_id(40, 40) == 4040
    assert get_ynv_file_coords(40, 40) == (120, 120)


def test_build_cell_returns_source_polygon_provenance() -> None:
    ynv, provenance = build_ynv_cell(
        [
            YnvSourcePolygon(
                [(10.0, 10.0, 0.0), (20.0, 10.0, 0.0), (10.0, 20.0, 0.0)],
                source_key="floor",
            )
        ]
    )

    assert ynv.area_id == 4040
    assert provenance == {"floor": (0,)}
    assert ynv.validate() == []


def test_build_cell_writes_enhanced_runtime_headers() -> None:
    ynv, _ = build_ynv_cell(
        [
            YnvSourcePolygon(
                [(10.0, 10.0, 0.0), (20.0, 10.0, 0.0), (10.0, 20.0, 0.0)]
            )
        ],
        game=GameTarget.GTA5_ENHANCED,
    )

    rebuilt = read_ynv(build_ynv_bytes(ynv))

    assert rebuilt.game is GameTarget.GTA5_ENHANCED
    assert rebuilt.file_vft == 0x406D2160
    assert rebuilt.vertices_info.vft == 0x406D21A8
    assert rebuilt.indices_info.vft == 0x406D21A8
    assert rebuilt.edges_info.vft == 0x406D21A8
    assert rebuilt.polys_info.vft == 0x406D21A8


def test_provenance_can_bind_portals_to_authored_polygons() -> None:
    ynv, provenance = build_ynv_cell(
        [
            YnvSourcePolygon(
                [(10.0, 10.0, 0.0), (20.0, 10.0, 0.0), (10.0, 20.0, 0.0)],
                source_key="portal-floor",
            )
        ]
    )
    polygon_id = provenance["portal-floor"][0]
    ynv.portals.append(
        YnvPortal(
            position_from=(12.0, 12.0, 0.0),
            position_to=(14.0, 14.0, 0.0),
            poly_id_from1=polygon_id,
            poly_id_from2=polygon_id,
            poly_id_to1=polygon_id,
            poly_id_to2=polygon_id,
            area_id_from=ynv.area_id,
            area_id_to=ynv.area_id,
        )
    )

    assert ynv.validate() == []


def test_build_cells_preserves_cross_cell_adjacency_and_provenance() -> None:
    cells = build_ynv_cells(
        [
            YnvSourcePolygon(
                [(-10.0, 10.0, 0.0), (10.0, 10.0, 0.0), (10.0, 40.0, 0.0)],
                source_key=77,
            )
        ]
    )

    assert [ynv.area_id for ynv, _ in cells] == [4039, 4040]
    assert all(provenance == {77: (0,)} for _, provenance in cells)
    assert all(
        any(edge.flags & YnvEdgeFlags.EXTERNAL_EDGE for edge in ynv.edges)
        for ynv, _ in cells
    )
    assert all(ynv.validate() == [] for ynv, _ in cells)
    rebuilt = [read_ynv(ynv.to_bytes()) for ynv, _ in cells]
    assert all(
        any(
            edge.flags & YnvEdgeFlags.EXTERNAL_EDGE
            and edge.poly2.area_id != ynv.area_id
            for edge in ynv.edges
        )
        for ynv in rebuilt
    )


def test_polygon_over_binary_vertex_limit_is_triangulated() -> None:
    vertices = [
        (
            40.0 + math.cos(index * math.tau / 20.0) * 10.0,
            40.0 + math.sin(index * math.tau / 20.0) * 10.0,
            0.0,
        )
        for index in range(20)
    ]

    ynv, provenance = build_ynv_cell(
        [YnvSourcePolygon(vertices, source_key="large")]
    )

    assert len(ynv.polys) == 18
    assert len(provenance["large"]) == 18
    assert all(poly.index_count <= YNV_MAX_POLYGON_VERTICES for poly in ynv.polys)
    assert ynv.validate() == []


def test_authoring_rejects_nonfinite_vertices() -> None:
    with pytest.raises(ValueError, match="finite"):
        clip_ynv_polygon_to_cell(
            [(0.0, 0.0, 0.0), (1.0, float("nan"), 0.0), (1.0, 1.0, 0.0)],
            40,
            40,
        )
