from __future__ import annotations

import numpy as np
import pytest

from fivefury.mesh_math import (
    generate_vertex_normals,
    generate_vertex_tangents,
    triangle_array,
)


def test_triangle_array_accepts_flat_and_matrix_indices() -> None:
    flat = triangle_array((0, 1, 2, 2, 1, 3), 4)
    matrix = triangle_array(np.asarray(((0, 1, 2), (2, 1, 3))), 4)

    assert flat.tolist() == matrix.tolist() == [[0, 1, 2], [2, 1, 3]]


@pytest.mark.parametrize("indices", [(-1, 1, 2), (0, 1, 4), (0.0, 1.5, 2.0)])
def test_triangle_array_rejects_invalid_indices(indices: tuple[float, ...]) -> None:
    with pytest.raises(ValueError):
        triangle_array(indices, 4)


def test_generate_vertex_normals_accumulates_shared_vertices() -> None:
    positions = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0))

    normals = generate_vertex_normals(positions, (0, 1, 2, 2, 1, 3))

    assert normals == pytest.approx([(0.0, 0.0, 1.0)] * 4)


def test_generate_vertex_tangents_matches_uv_axes() -> None:
    positions = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    normals = ((0.0, 0.0, 1.0),) * 3
    texcoords = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))

    tangents = generate_vertex_tangents(
        positions,
        normals,
        texcoords,
        (0, 1, 2),
    )

    assert tangents == pytest.approx([(1.0, 0.0, 0.0, 1.0)] * 3)
