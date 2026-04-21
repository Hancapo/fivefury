from __future__ import annotations

from pathlib import Path

from fivefury import AssimpScene, YdrMeshInput, obj_to_nav, read_ynv
import fivefury.ynv.assimp as ynv_assimp


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
