from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from fivefury import Vector2, Vector3, Vector4, YdrMeshInput, create_ydr, read_ydr
from fivefury.mesh_math import generate_vertex_normals, generate_vertex_tangents
from fivefury.ydr.defs import VertexComponentType, VertexSemantic
from fivefury.ydr.prepare import channels
from fivefury.ydr.prepare import mesh as mesh_preparation
from fivefury.ydr.prepare.splitting import (
    _copy_vertex_channel,
    _split_mesh_by_vertex_limit,
)


@pytest.fixture(params=[165, 159], ids=["legacy", "enhanced"])
def version(request) -> int:
    return request.param


def _boundary_mesh() -> YdrMeshInput:
    # The last face shares vertex 0 with the first face, across the split boundary.
    return YdrMeshInput(
        positions=[Vector3(), Vector3(1, 0, 0), Vector3(0, 1, 0)]
        + [Vector3(10, 0, 0), Vector3(11, 0, 0), Vector3(10, 1, 0)] * 21844
        + [Vector3(0, 1, 1), Vector3(-1, 0, 0)],
        indices=list(range(65535)) + [0, 65535, 65536],
        texcoords=[
            [Vector2(), Vector2(1, 0), Vector2(0, 1)] * 21845
            + [Vector2(1, 0), Vector2(0, 1)]
        ],
    )


@pytest.mark.parametrize("authored_normals", [False, True])
def test_split_preserves_shared_normal_and_tangent_channels(
    tmp_path, version: int, authored_normals: bool
) -> None:
    mesh = _boundary_mesh()
    expected_normals = generate_vertex_normals(mesh.positions, mesh.indices)
    if authored_normals:
        mesh.normals = expected_normals
    expected_tangents = generate_vertex_tangents(
        mesh.positions, expected_normals, mesh.texcoords[0], mesh.indices
    )
    build = create_ydr(meshes=[mesh], shader="normal.sps", version=version)
    output = tmp_path / "split_channels.ydr"

    with (
        patch.object(
            channels, "generate_vertex_normals", wraps=generate_vertex_normals
        ) as normals,
        patch.object(
            channels, "generate_vertex_tangents", wraps=generate_vertex_tangents
        ) as tangents,
    ):
        build.save(output)
    assert normals.call_count == (0 if authored_normals else 1)
    assert tangents.call_count == 1

    parsed = read_ydr(output)
    assert parsed.version == version
    assert len(parsed.meshes) == 2
    assert all(len(chunk.positions) <= 65535 for chunk in parsed.meshes)
    assert sum(len(chunk.indices) for chunk in parsed.meshes) == len(mesh.indices)
    shared = [
        (chunk.normals[index], chunk.tangents[index])
        for chunk in parsed.meshes
        for index, position in enumerate(chunk.positions)
        if position == Vector3()
    ]
    assert len(shared) == 2
    assert shared[0] == shared[1]
    # Enhanced packs these channels, so allow its signed-normal quantization.
    assert tuple(shared[0][0]) == pytest.approx(tuple(expected_normals[0]), abs=0.002)
    assert tuple(shared[0][1]) == pytest.approx(tuple(expected_tangents[0]), abs=0.002)
    assert mesh.normals is (expected_normals if authored_normals else None)
    assert mesh.tangents is None
    assert len(mesh.positions) == 65537


@pytest.mark.parametrize("uv_channels", [[], [[]], [[], []]])
@pytest.mark.parametrize("populated_uv0", [False, True])
def test_split_optional_empty_channels_match_absent_channels(
    tmp_path, version: int, uv_channels: list[list[Vector2]], populated_uv0: bool
) -> None:
    mesh = _boundary_mesh()
    if not populated_uv0:
        mesh.texcoords = None
        # The default shader layout requires UV0; use an explicit UV-free declaration.
        mesh.declaration_flags = (1 << VertexSemantic.POSITION) | (
            1 << VertexSemantic.NORMAL
        )
        mesh.declaration_types = int(VertexComponentType.FLOAT3) | (
            int(VertexComponentType.FLOAT3) << (4 * VertexSemantic.NORMAL)
        )
    build = create_ydr(
        meshes=[mesh],
        shader="normal.sps" if populated_uv0 else "default.sps",
        version=version,
    )
    absent = build.to_bytes()
    for name in (
        "normals",
        "tangents",
        "colours0",
        "colours1",
        "blend_weights",
        "blend_indices",
        "bone_ids",
    ):
        setattr(mesh, name, [])
    mesh.texcoords = (mesh.texcoords or []) + uv_channels
    expected_texcoords = mesh.texcoords

    output = tmp_path / "empty_channels.ydr"
    build.save(output)
    assert output.read_bytes() == absent
    parsed = read_ydr(output)
    assert parsed.version == version
    assert len(parsed.meshes) == 2
    assert all(len(chunk.positions) <= 65535 for chunk in parsed.meshes)
    assert mesh.normals == []
    assert mesh.tangents == []
    assert mesh.texcoords == expected_texcoords


@pytest.mark.parametrize("vertex_count", [3, 65538], ids=["small", "oversized"])
@pytest.mark.parametrize("empty", [False, True])
def test_numpy_numeric_channels_match_lists(
    tmp_path, version: int, vertex_count: int, empty: bool
) -> None:
    count = 0 if empty else vertex_count
    channels = {
        "colours0": np.tile([1.0, 0.0, 0.0, 1.0], (count, 1)),
        "colours1": np.tile([0.0, 1.0, 0.0, 1.0], (count, 1)),
        "blend_weights": np.tile([1.0, 0.0, 0.0, 0.0], (count, 1)),
        "blend_indices": np.zeros((count, 4), dtype=np.uint8),
    }
    mesh = YdrMeshInput(
        positions=[Vector3()] * vertex_count,
        indices=list(range(vertex_count)),
        texcoords=[[Vector2()] * vertex_count],
        **{name: values.tolist() for name, values in channels.items()},
    )
    build = create_ydr(meshes=[mesh], version=version)
    expected = build.to_bytes()
    for name, values in channels.items():
        setattr(mesh, name, values)
        copied = _copy_vertex_channel(values, [2, 0])
        if empty:
            assert copied is None
        else:
            np.testing.assert_array_equal(copied, values[[2, 0]])

    output = tmp_path / "numpy_channels.ydr"
    build.save(output)

    assert output.read_bytes() == expected
    parsed = read_ydr(output)
    assert parsed.version == version
    assert len(parsed.meshes) == (1 if vertex_count <= 65535 else 2)
    for name, values in channels.items():
        assert getattr(mesh, name) is values


def test_split_copy_preserves_uv_channel_slots() -> None:
    mesh = _boundary_mesh()
    populated = mesh.texcoords[0]
    mesh.texcoords = [[], populated, []]
    mesh.normals = []
    mesh.tangents = []
    mesh.colours0 = []
    mesh.colours1 = []
    mesh.blend_weights = []
    mesh.blend_indices = []

    chunks = _split_mesh_by_vertex_limit(mesh)

    assert len(chunks) == 2
    for chunk in chunks:
        assert chunk.texcoords[0] == []
        assert chunk.texcoords[2] == []
        assert len(chunk.texcoords[1]) == len(chunk.positions)
        for name in (
            "normals",
            "tangents",
            "colours0",
            "colours1",
            "blend_weights",
            "blend_indices",
        ):
            assert getattr(chunk, name) is None
    assert chunks[0].texcoords[1] == populated[:65535]
    assert chunks[1].texcoords[1] == [populated[0], populated[65535], populated[65536]]


@pytest.mark.parametrize("vertex_count", [3, 65538], ids=["small", "oversized"])
@pytest.mark.parametrize("length_delta", [-1, 1], ids=["short", "long"])
@pytest.mark.parametrize(
    ("channel_name", "value", "diagnostic_name"),
    [
        ("normals", Vector3(0, 0, 1), "normals"),
        ("tangents", Vector4(1, 0, 0, 1), "tangents"),
        ("colours0", (1, 1, 1, 1), "colours0"),
        ("colours1", (1, 1, 1, 1), "colours1"),
        ("blend_weights", (1, 0, 0, 0), "blend_weights"),
        ("blend_indices", (0, 0, 0, 0), "blend_indices"),
        ("texcoords", Vector2(), "UV channel 1"),
    ],
)
def test_channel_mismatches_fail_before_generation_or_splitting(
    version: int,
    vertex_count: int,
    length_delta: int,
    channel_name: str,
    value,
    diagnostic_name: str,
) -> None:
    mesh = YdrMeshInput(
        positions=[Vector3()] * vertex_count,
        indices=list(range(vertex_count)),
    )
    channel = [value] * (vertex_count + length_delta)
    setattr(
        mesh, channel_name, [[], channel] if channel_name == "texcoords" else channel
    )
    build = create_ydr(meshes=[mesh], version=version)

    with (
        patch.object(
            channels,
            "generate_vertex_normals",
            side_effect=AssertionError("generated normals"),
        ),
        patch.object(
            channels,
            "generate_vertex_tangents",
            side_effect=AssertionError("generated tangents"),
        ),
        patch.object(
            mesh_preparation,
            "_split_mesh_by_vertex_limit",
            side_effect=AssertionError("split mesh"),
        ),
        pytest.raises(
            ValueError,
            match=f"Mesh {diagnostic_name} length must match positions length",
        ),
    ):
        build.to_bytes()
