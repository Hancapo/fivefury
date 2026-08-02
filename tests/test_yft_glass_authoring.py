from __future__ import annotations

import math

import pytest

from fivefury.yft.glass import YftGlassPaneFlag
from fivefury.yft.glass_authoring import (
    YftGlassOrthonormalTransform,
    YftGlassPaneMesh,
    build_yft_glass_pane,
    compute_glass_bounds_offsets,
)


def _rectangle_mesh(*, back_depth: float = 0.0) -> YftGlassPaneMesh:
    positions = [
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.0),
        (2.0, 3.0, 0.0),
        (0.0, 3.0, 0.0),
    ]
    uv0 = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    if back_depth:
        positions += [(x, y, back_depth) for x, y, _ in positions]
        uv0 += list(uv0)
    return YftGlassPaneMesh.declare(
        positions,
        (0, 1, 2, 0, 2, 3),
        uv0,
        [(2.0, 0.0, 0.0)] * len(positions),
    )


def test_planar_pane_uses_uv_basis_and_range():
    geometry = _rectangle_mesh().compute()

    assert geometry.position_base == pytest.approx((0.0, 0.0, 0.0))
    assert geometry.position_width == pytest.approx((2.0, 0.0, 0.0))
    assert geometry.position_height == pytest.approx((0.0, 3.0, 0.0))
    assert geometry.uv_min == pytest.approx((0.0, 0.0))
    assert geometry.uv_max == pytest.approx((1.0, 1.0))
    assert geometry.thickness == pytest.approx(0.0)


def test_thick_pane_measures_depth_across_all_vertices():
    geometry = _rectangle_mesh(back_depth=0.25).compute()

    assert geometry.thickness == pytest.approx(0.25)
    assert geometry.bounds_offset_front == pytest.approx(0.125)
    assert geometry.bounds_offset_back == pytest.approx(0.125)


def test_largest_valid_triangle_ignores_degenerate_uv_triangle():
    mesh = YftGlassPaneMesh.declare(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (2, 0, 0), (2, 2, 0)],
        (0, 1, 2, 0, 3, 4),
        [(0, 0), (0, 0), (0, 0), (1, 0), (1, 1)],
        [(1, 0, 0)] * 5,
    )

    geometry = mesh.compute()

    assert geometry.position_width == pytest.approx((2.0, 0.0, 0.0))
    assert geometry.position_height == pytest.approx((0.0, 2.0, 0.0))


def test_all_degenerate_uv_triangles_are_rejected():
    mesh = YftGlassPaneMesh.declare(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        (0, 1, 2),
        [(0, 0), (0.5, 0), (1, 0)],
        [(1, 0, 0)] * 3,
    )

    with pytest.raises(ValueError, match="UV0 coordinates are degenerate"):
        mesh.compute()


def test_average_tangent_is_normalized():
    mesh = YftGlassPaneMesh.declare(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        (0, 1, 2),
        [(0, 0), (1, 0), (0, 1)],
        [(2, 0, 0), (0, 2, 0), (2, 0, 0)],
    )

    tangent = mesh.compute().tangent

    assert tangent == pytest.approx((2 / math.sqrt(5), 1 / math.sqrt(5), 0.0))


def test_bounds_offsets_match_identity_aabb_support_points():
    geometry = _rectangle_mesh(back_depth=0.25).compute()

    front, back = compute_glass_bounds_offsets(
        geometry,
        (-1.0, -1.0, -0.25),
        (3.0, 4.0, 0.5),
    )

    assert front == pytest.approx(0.25)
    assert back == pytest.approx(0.5)


def test_bounds_offsets_untransform_plane_into_bound_space():
    geometry = _rectangle_mesh().compute()
    transform = YftGlassOrthonormalTransform(
        x_axis=(0.0, 1.0, 0.0),
        y_axis=(-1.0, 0.0, 0.0),
        z_axis=(0.0, 0.0, 1.0),
        translation=(0.0, 0.0, 2.0),
    )

    front, back = compute_glass_bounds_offsets(
        geometry,
        (-1.0, -1.0, -3.0),
        (3.0, 4.0, 1.0),
        transform=transform,
    )

    assert front == pytest.approx(1.0)
    assert back == pytest.approx(3.0)


def test_bone_filter_matches_major_triangle_and_first_binding_vertices():
    mesh = YftGlassPaneMesh.declare(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 0.2)],
        (0, 1, 2),
        [(0, 0), (1, 0), (0, 1), (0, 0)],
        [(2, 0, 0)] * 4,
        blend_indices=[(7, 1, 0, 0), (7, 0, 0, 0), (1, 7, 0, 0), (1, 7, 0, 0)],
        blend_weights=[(1, 0, 0, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 1, 0, 0)],
    )

    geometry = mesh.compute(bone_index=7)

    assert geometry.uv_min == pytest.approx((0.0, 0.0))
    assert geometry.uv_max == pytest.approx((1.0, 0.0))
    assert geometry.thickness == pytest.approx(0.0)


def test_declarative_builder_returns_serializable_pane():
    pane = build_yft_glass_pane(
        _rectangle_mesh(back_depth=0.25),
        glass_type=2,
        shader_index=4,
        bounds_minimum=(-1.0, -1.0, -0.25),
        bounds_maximum=(3.0, 4.0, 0.5),
    )

    assert pane.glass_type == 2
    assert pane.shader_index == 4
    assert pane.flags == YftGlassPaneFlag.TANGENT
    assert pane.bounds_offset_front == pytest.approx(0.25)
    assert pane.bounds_offset_back == pytest.approx(0.5)
