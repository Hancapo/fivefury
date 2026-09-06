from __future__ import annotations

import copy

from fivefury import (
    GameTarget,
    Vector3,
    Ynv,
    YnvNetwork,
    YnvSourcePolygon,
    build_ynv_cell,
)


def _cell(
    area_id: int,
    *,
    path: str = "",
    game: GameTarget = GameTarget.GTA5,
) -> Ynv:
    cell, _ = build_ynv_cell(
        [
            YnvSourcePolygon(
                [Vector3(), Vector3(10.0, 0.0, 0.0), Vector3(0.0, 10.0, 0.0)]
            )
        ],
        game=game,
    )
    cell.area_id = area_id
    cell.path = path
    for poly in cell.polys:
        poly.area_id = area_id
    for edge in cell.edges:
        edge.clear_neighbor()
    return cell


def _two_poly_cell(area_id: int) -> Ynv:
    cell, _ = build_ynv_cell(
        [
            YnvSourcePolygon(
                [Vector3(), Vector3(10.0, 0.0, 0.0), Vector3(10.0, 10.0, 0.0)]
            ),
            YnvSourcePolygon(
                [Vector3(), Vector3(10.0, 10.0, 0.0), Vector3(0.0, 10.0, 0.0)]
            ),
        ]
    )
    cell.area_id = area_id
    for poly in cell.polys:
        poly.area_id = area_id
    for edge in cell.edges:
        for part in (edge.poly1, edge.poly2):
            if part.area_id == 4040:
                part.area_id = area_id
    return cell


def _connect(
    source: Ynv,
    target: Ynv,
    *,
    source_poly: int = 0,
    source_edge: int = 0,
    target_poly: int = 0,
) -> None:
    poly = source.polys[source_poly]
    source.edges[poly.index_id + source_edge].set_neighbor(
        target.area_id,
        target_poly,
    )


def _codes(network: YnvNetwork) -> list[str]:
    return [issue.code for issue in network.validate()]


def test_reciprocal_external_edges_are_valid() -> None:
    left = _cell(100, path="left.ynv")
    right = _cell(101, path="right.ynv")
    _connect(left, right)
    _connect(right, left)

    assert YnvNetwork([left, right]).validate().valid


def test_missing_reciprocal_edge_reports_source_location() -> None:
    left = _cell(100, path="left.ynv")
    right = _cell(101, path="right.ynv")
    _connect(left, right)

    report = YnvNetwork([left, right]).validate()
    issue = next(
        issue
        for issue in report
        if issue.code == "ynv.network.edge.reciprocal.missing"
    )

    assert issue.asset == "left.ynv"
    assert issue.path == "polys[0].edges[0]"
    assert "(100, 0) -> (101, 0)" in issue.message


def test_duplicate_reciprocal_edges_are_rejected() -> None:
    left = _cell(100)
    right = _cell(101)
    _connect(left, right)
    _connect(right, left, source_edge=0)
    _connect(right, left, source_edge=1)

    assert "ynv.network.edge.reciprocal.duplicate" in _codes(
        YnvNetwork([left, right])
    )


def test_missing_target_area_is_rejected() -> None:
    cell = _cell(100)
    cell.edges[0].set_neighbor(101, 0)

    assert "ynv.network.edge.target_area.missing" in _codes(YnvNetwork([cell]))


def test_target_polygon_range_is_rejected() -> None:
    left = _cell(100)
    right = _cell(101)
    left.edges[0].set_neighbor(right.area_id, 9)

    assert "ynv.network.edge.target_poly_id.range" in _codes(
        YnvNetwork([left, right])
    )


def test_duplicate_area_ids_are_rejected_for_each_cell() -> None:
    first = _cell(100, path="first.ynv")
    second = _cell(100, path="second.ynv")

    issues = [
        issue
        for issue in YnvNetwork([first, second]).validate()
        if issue.code == "ynv.network.area_id.duplicate"
    ]

    assert [issue.asset for issue in issues] == ["first.ynv", "second.ynv"]


def test_local_reciprocal_edges_are_valid() -> None:
    assert YnvNetwork([_two_poly_cell(100)]).validate().valid


def test_closed_edge_sentinel_is_ignored() -> None:
    assert YnvNetwork([_cell(100)]).validate().valid


def test_partial_sentinel_is_not_ignored() -> None:
    cell = _cell(100)
    cell.edges[0].poly1.poly_id = 0
    cell.edges[0].poly2.poly_id = 0

    assert "ynv.network.edge.target_area.missing" in _codes(YnvNetwork([cell]))


def test_individual_reference_mismatch_is_preserved() -> None:
    left = _cell(100)
    right = _cell(101)
    _connect(left, right)
    _connect(right, left)
    left.edges[0].poly2.area_id = 0x3FFF
    left.edges[0].poly2.poly_id = 0x7FFF

    assert "ynv.edge.references.mismatch" in _codes(YnvNetwork([left, right]))


def test_unilateral_one_to_many_links_are_rejected() -> None:
    source = _two_poly_cell(100)
    target = _cell(101)
    for edge in source.edges:
        edge.clear_neighbor()
    _connect(source, target, source_poly=0)
    _connect(source, target, source_poly=1)
    _connect(target, source, target_poly=0)

    report = YnvNetwork([source, target]).validate()
    missing = [
        issue
        for issue in report
        if issue.code == "ynv.network.edge.reciprocal.missing"
    ]

    assert len(missing) == 1
    assert missing[0].path == "polys[1].edges[0]"


def test_validation_supports_legacy_and_enhanced_cells() -> None:
    for game in (GameTarget.GTA5, GameTarget.GTA5_ENHANCED):
        left = _cell(100, game=game)
        right = _cell(101, game=game)
        _connect(left, right)
        _connect(right, left)
        assert YnvNetwork([left, right]).validate().valid


def test_synthetic_network_scale() -> None:
    template = _cell(0)
    cells = []
    for area_id in range(2_048):
        cell = copy.deepcopy(template)
        cell.area_id = area_id
        cell.polys[0].area_id = area_id
        cells.append(cell)

    assert YnvNetwork(cells).validate().valid
