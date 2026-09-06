import random

import pytest

from fivefury import _native_abi3 as native


def test_small_mesh_does_not_need_remapping():
    assert native.ydr_split_mesh_indices([0, 1, 2] * 20000, 3, 65535) is None
    assert native.ydr_split_mesh_indices([], 0, 65535) is None


def test_small_mesh_still_validates_indices():
    with pytest.raises(ValueError, match="outside positions"):
        native.ydr_split_mesh_indices([0, 1, 3], 3, 65535)
    with pytest.raises(ValueError, match="triangle list"):
        native.ydr_split_mesh_indices([0, 1], 3, 65535)


def test_high_indices_are_remapped_even_with_few_referenced_vertices():
    assert native.ydr_split_mesh_indices([65536, 70000, 80000], 80001, 65535) == [
        ([65536, 70000, 80000], [0, 1, 2])
    ]


def test_split_partition_and_vertex_order_match_reference():
    rng = random.Random(123)
    indices = [v for _ in range(400) for v in rng.sample(range(100), 3)]
    expected = []
    vertices, remapped, lookup = [], [], {}
    for start in range(0, len(indices), 3):
        triangle = indices[start : start + 3]
        if remapped and len(vertices) + sum(v not in lookup for v in triangle) > 17:
            expected.append((vertices, remapped))
            vertices, remapped, lookup = [], [], {}
        for vertex in triangle:
            if vertex not in lookup:
                lookup[vertex] = len(vertices)
                vertices.append(vertex)
            remapped.append(lookup[vertex])
    expected.append((vertices, remapped))
    assert native.ydr_split_mesh_indices(indices, 100, 17) == expected
