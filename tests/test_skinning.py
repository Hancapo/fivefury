from __future__ import annotations

import numpy as np
import pytest

from fivefury import compose_skeleton_matrices, skin_vertices


def test_compose_skeleton_matrices_supports_out_of_order_hierarchies() -> None:
    local = np.repeat(np.eye(4, dtype=np.float32)[None, :, :], 3, axis=0)
    local[0, 3, :3] = (1.0, 0.0, 0.0)
    local[1, 3, :3] = (0.0, 2.0, 0.0)
    local[2, 3, :3] = (0.0, 0.0, 3.0)

    absolute = compose_skeleton_matrices(local, np.asarray((2, -1, 1)))

    np.testing.assert_allclose(absolute[1, 3, :3], (0.0, 2.0, 0.0))
    np.testing.assert_allclose(absolute[2, 3, :3], (0.0, 2.0, 3.0))
    np.testing.assert_allclose(absolute[0, 3, :3], (1.0, 2.0, 3.0))


def test_compose_skeleton_matrices_rejects_cycles() -> None:
    local = np.repeat(np.eye(4, dtype=np.float32)[None, :, :], 2, axis=0)

    with pytest.raises(ValueError, match="contains a cycle"):
        compose_skeleton_matrices(local, (1, 0))


def test_skin_vertices_blends_positions_and_normalizes_normals() -> None:
    matrices = np.repeat(np.eye(4, dtype=np.float32)[None, :, :], 2, axis=0)
    matrices[0, 3, :3] = (2.0, 0.0, 0.0)
    matrices[1, 3, :3] = (0.0, 4.0, 0.0)
    result = skin_vertices(
        [(1.0, 1.0, 1.0), (3.0, 2.0, 1.0)],
        matrices,
        [(0, 1), (1, 0)],
        [(1.0, 1.0), (0.0, 0.0)],
        normals=[(0.0, 0.0, 2.0), (0.0, 3.0, 0.0)],
    )

    np.testing.assert_allclose(result.positions[0], (2.0, 3.0, 1.0))
    np.testing.assert_allclose(result.positions[1], (3.0, 2.0, 1.0))
    assert result.normals is not None
    np.testing.assert_allclose(result.normals[0], (0.0, 0.0, 1.0))
    np.testing.assert_allclose(result.normals[1], (0.0, 3.0, 0.0))


def test_skin_vertices_can_preserve_non_normalized_weights() -> None:
    matrices = np.eye(4, dtype=np.float32)[None, :, :]

    result = skin_vertices(
        [(2.0, 0.0, 0.0)],
        matrices,
        [(0,)],
        [(0.5,)],
        normalize_weights=False,
    )

    np.testing.assert_allclose(result.positions[0], (1.0, 0.0, 0.0))


def test_skin_vertices_rejects_invalid_weighted_bone_indices() -> None:
    with pytest.raises(ValueError, match="outside the 1 available matrices"):
        skin_vertices(
            [(0.0, 0.0, 0.0)],
            np.eye(4, dtype=np.float32)[None, :, :],
            [(4,)],
            [(1.0,)],
        )


@pytest.mark.parametrize(
    ("indices", "weights", "message"),
    [
        ([(0, -1)], [(1.0, 0.0)], "exact non-negative integers"),
        ([(0, 0)], [(1.0, -0.1)], "finite non-negative values"),
        ([(0, 0)], [(1.0,)], "match the blend_indices shape"),
    ],
)
def test_skin_vertices_validates_influence_data(
    indices: object,
    weights: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        skin_vertices(
            [(0.0, 0.0, 0.0)],
            np.eye(4, dtype=np.float32)[None, :, :],
            indices,
            weights,
        )
