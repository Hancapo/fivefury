import pytest

from fivefury import Vector3
from fivefury.ydr import (
    ColorChannel,
    YdrMesh,
    YdrMeshInput,
    YdrModel,
    paint_mesh,
    paint_vertices,
)


@pytest.mark.parametrize("mesh_type", [YdrMesh, YdrMeshInput])
@pytest.mark.parametrize("channel", [0, 1])
def test_painting_preserves_unselected_vertices_and_components(
    mesh_type, channel
) -> None:
    mesh = mesh_type(positions=[Vector3()] * 3, indices=[0, 1, 2])
    paint_mesh(mesh, (0.1, 0.2, 0.3, 0.4), channel=channel)
    paint_vertices(mesh, [1], (0.7, 0.8), channel=channel, components=ColorChannel.GA)
    assert getattr(mesh, f"colours{channel}") == [
        (0.1, 0.2, 0.3, 0.4),
        (0.1, 0.7, 0.3, 0.8),
        (0.1, 0.2, 0.3, 0.4),
    ]
    assert not getattr(mesh, f"colours{1 - channel}")


def test_painting_model_traverses_all_meshes() -> None:
    meshes = [YdrMesh(positions=[Vector3()] * count) for count in (1, 3)]
    model = YdrModel(lod="high", meshes=meshes)
    paint_mesh(model, "red")
    paint_vertices(model, [0], 0.5, components=ColorChannel.A)
    for mesh in meshes:
        assert mesh.colours0[0] == (1.0, 0.0, 0.0, 0.5)
        assert mesh.colours0[1:] == [(1.0, 0.0, 0.0, 1.0)] * (len(mesh.positions) - 1)
