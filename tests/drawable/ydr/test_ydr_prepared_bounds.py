from __future__ import annotations

import copy
import math
import struct
from unittest.mock import patch

import pytest

from fivefury import Vector2, Vector3
from fivefury.resource import split_rsc7_sections
from fivefury.ydr import (
    YdrBone,
    YdrMeshInput,
    YdrSkeleton,
    YdrSkeletonBinding,
    create_ydr,
)
from fivefury.ydr.prepare import (
    bounds,
    compute_bounds,
    compute_model_collection_bounds,
    prepare_build,
)
from fivefury.ydr.shaders import load_shader_library
from fivefury.ydr.write_materials import prepare_materials


def _rigid_build(matrix, *, version=165):
    skeleton = YdrSkeleton(
        bones=[YdrBone(name="root", tag=0)],
        transformations=[matrix],
    )
    return create_ydr(
        meshes=[
            YdrMeshInput(
                positions=[Vector3(), Vector3(1, 0, 0), Vector3(0, 1, 0)],
                indices=[0, 1, 2],
                texcoords=[[Vector2(), Vector2(1, 0), Vector2(0, 1)]],
            )
        ],
        skeleton=skeleton,
        skeleton_binding=YdrSkeletonBinding.rigid(bone_index=0),
        version=version,
    )


@pytest.mark.parametrize("version", [165, 159], ids=["legacy", "enhanced"])
def test_transformed_rigid_bounds_match_expected_float32_bytes(version: int) -> None:
    # Row-vector quarter turn, nonuniform scale/reflection, and translation.
    # The fourth column is metadata, not a perspective divide. Object-space
    # vertices are exactly (10,20,30), (10,22,30), and (7,20,30).
    matrix = (
        (0.0, 2.0, 0.0, 91.0),
        (-3.0, 0.0, 0.0, 92.0),
        (0.0, 0.0, -4.0, 93.0),
        (10.0, 20.0, 30.0, 94.0),
    )
    build = _rigid_build(matrix, version=version)
    _, system, _ = split_rsc7_sections(build.to_bytes())
    expected = struct.pack(
        "<4f3fI3fI",
        8.5,
        21.0,
        30.0,
        math.sqrt(3.25),
        7.0,
        20.0,
        30.0,
        0x7F800001,
        10.0,
        22.0,
        30.0,
        0x7F800001,
    )
    assert system[0x20:0x50] == expected
    assert build.skeleton.transformations == [matrix]


@pytest.mark.parametrize(
    "matrix",
    [
        (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
        (
            (0.0, 2.0, 0.0, 0.0),
            (-3.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, -4.0, 0.0),
            (10.0, 20.0, 30.0, 1.0),
        ),
        (
            (0.13, 0.27, 0.39, 17.0),
            (-0.42, 0.56, 0.68, 18.0),
            (0.71, 0.83, -0.97, 19.0),
            (0.11, -0.23, 0.37, 20.0),
        ),
    ],
)
def test_row_adapter_numerical_parity_and_input_preservation(matrix) -> None:
    build = _rigid_build(matrix)
    build.lods[next(iter(build.lods))][0].meshes[0].positions = [
        Vector3(0.17, -0.31, 0.43),
        Vector3(-1.29, 2.41, 3.53),
        Vector3(4.67, -5.79, 6.81),
    ]
    _, lods = prepare_build(
        build,
        load_shader_library(),
        prepare_materials=prepare_materials,
        generate_normals=True,
        generate_tangents=True,
        fill_vertex_colours=True,
    )
    models = next(iter(lods.values()))
    before = copy.deepcopy(models)
    # Independent scalar oracle for the removed helper. Non-exact sums need
    # numerical parity, not a promise of identical float32 rounding everywhere.
    expected_positions = [
        Vector3(
            *(
                point.x * matrix[0][axis]
                + point.y * matrix[1][axis]
                + point.z * matrix[2][axis]
                + matrix[3][axis]
                for axis in range(3)
            )
        )
        for point in models[0].meshes[0].positions
    ]
    with patch.object(
        bounds, "transform_positions", wraps=bounds.transform_positions
    ) as transform:
        actual = compute_model_collection_bounds(models, skeleton=build.skeleton)
    expected = compute_bounds(expected_positions)
    for value, reference in zip(actual[:3], expected[:3], strict=True):
        assert value.components == pytest.approx(
            reference.components, rel=1e-12, abs=1e-12
        )
    assert actual[3] == pytest.approx(expected[3], rel=1e-12, abs=1e-12)
    assert transform.call_count == 1
    assert models == before
    assert build.skeleton.transformations == [matrix]
