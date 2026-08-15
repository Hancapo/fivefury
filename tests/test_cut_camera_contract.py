from __future__ import annotations

import pytest

from fivefury import CutCamera, CutsceneProject, read_ycd
from fivefury.cut.scene.io import read_cut_scene
from fivefury.hashing import jenk_partial_hash


def _animated_camera_project() -> tuple[CutsceneProject, CutCamera]:
    project = CutsceneProject.create(
        "camera_contract",
        duration=2.0,
        camera_cuts=[1.0],
        fps=30.0,
    )
    camera = project.camera(
        "exportcamera",
        start=0.25,
        cut_name="opening_shot",
        position={0.0: (0.0, 0.0, 1.0), 2.0: (20.0, 0.0, 1.0)},
        rotation=(0.0, 0.0, 0.0, 1.0),
        field_of_view=45.0,
        near_clip=0.1,
        far_clip=2000.0,
    )
    return project, camera


def test_project_camera_authors_runtime_binding_and_sampled_cut_pose() -> None:
    project, camera = _animated_camera_project()
    event = next(
        item for item in project.scene.timeline if item.event_name == "camera_cut"
    )

    assert camera.animation_streaming_base == jenk_partial_hash("exportcamera")
    assert camera.near_draw_distance == pytest.approx(0.1)
    assert camera.far_draw_distance == pytest.approx(2000.0)
    assert event.target_id == camera.object_id
    assert event.label == "opening_shot"
    assert event.payload["vPosition"] == pytest.approx((2.5, 0.0, 1.0))
    assert event.payload["vRotationQuaternion"] == pytest.approx(
        (0.0, 0.0, 0.0, 1.0)
    )


def test_one_runtime_camera_drives_multiple_named_cuts() -> None:
    project, camera = _animated_camera_project()
    project.camera_cut(camera, start=1.5, name="closing_shot")

    events = [
        item for item in project.scene.timeline if item.event_name == "camera_cut"
    ]
    assert project.scene.cameras == [camera]
    assert [event.target_id for event in events] == [camera.object_id, camera.object_id]
    assert [event.label for event in events] == ["opening_shot", "closing_shot"]
    assert events[1].payload["vPosition"] == pytest.approx((15.0, 0.0, 1.0))


def test_camera_contract_survives_cut_and_segmented_ycd_roundtrip() -> None:
    project, camera = _animated_camera_project()
    files = project.build().build_files()
    scene = read_cut_scene(files["camera_contract.cut"])
    rebuilt_camera = scene.cameras[0]

    assert isinstance(rebuilt_camera, CutCamera)
    assert rebuilt_camera.animation_streaming_base == camera.animation_streaming_base
    assert rebuilt_camera.near_draw_distance == pytest.approx(0.1)
    assert rebuilt_camera.far_draw_distance == pytest.approx(2000.0)
    for index in range(2):
        ycd = read_ycd(files[f"camera_contract-{index}.ycd"])
        assert ycd.get_clip(f"exportcamera-{index}") is not None


def test_animated_camera_requires_a_complete_cut_pose() -> None:
    project = CutsceneProject.create("incomplete_camera", duration=1.0)

    with pytest.raises(ValueError, match="position and rotation"):
        project.camera(
            position=(0.0, 0.0, 0.0),
            field_of_view=45.0,
        )


def test_project_rejects_a_second_runtime_camera() -> None:
    project, _camera = _animated_camera_project()

    with pytest.raises(ValueError, match="one runtime camera"):
        project.camera("second_camera")
