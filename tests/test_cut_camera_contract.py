from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

import pytest

from fivefury import (
    GEN9_YCD_RUNTIME_PROFILE,
    LEGACY_YCD_RUNTIME_PROFILE,
    CutCamera,
    CutScene,
    CutsceneProject,
    GameFileCache,
    GameFileType,
    GameTarget,
    Quaternion,
    Vector3,
    read_ycd,
    validate_cut_scene,
)
from fivefury.cut.scene.io import read_cut_scene
from fivefury.hashing import jenk_partial_hash


def _configured_retail_game_paths() -> list[tuple[str, Path, GameTarget]]:
    result = []
    for edition, variable, game in (
        ("legacy", "FIVEFURY_GTA5_LEGACY_PATH", GameTarget.GTA5),
        ("enhanced", "FIVEFURY_GTA5_ENHANCED_PATH", GameTarget.GTA5_ENHANCED),
    ):
        value = os.environ.get(variable)
        if value and Path(value).is_dir():
            result.append((edition, Path(value), game))
    return result


_RETAIL_GAME_PATHS = _configured_retail_game_paths()


@pytest.mark.parametrize(
    ("_edition", "game_path", "game"),
    _RETAIL_GAME_PATHS,
    ids=[entry[0] for entry in _RETAIL_GAME_PATHS],
)
def test_retail_cut_flags_roundtrip_through_semantic_settings(
    _edition: str,
    game_path: Path,
    game: GameTarget,
) -> None:
    mismatches: list[str] = []
    with GameFileCache(
        game_path,
        game=game,
        exclude_folders=["mods"],
        load_audio=False,
        load_peds=False,
        load_vehicles=False,
        use_index_cache=True,
    ) as cache:
        cache.scan(exclude_folders=["mods"])
        for asset in cache.iter_assets(GameFileType.CUT):
            game_file = cache.load_asset(asset)
            assert game_file is not None
            cut = game_file.parsed
            stored = int(cut.root.fields.get("iCutsceneFlags", [0])[0])
            derived = int(read_cut_scene(cut).flags)
            if stored != derived:
                mismatches.append(f"{asset.path}: 0x{stored:08X} != 0x{derived:08X}")

    assert not mismatches


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
        position={0.0: Vector3(0.0, 0.0, 1.0), 2.0: Vector3(20.0, 0.0, 1.0)},
        rotation=Quaternion(),
        field_of_view=45.0,
        near_clip=0.1,
        far_clip=2000.0,
    )
    return project, camera


def _remove_camera_set_anim(
    project: CutsceneProject,
    camera: CutCamera,
    *,
    start: float | None = None,
) -> None:
    for track in project.scene.tracks:
        track.events[:] = [
            event
            for event in track.events
            if not (
                event.event_name == "set_anim"
                and event.payload["iObjectId"] == camera.object_id
                and (start is None or event.start == start)
            )
        ]


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
    assert event.payload["vPosition"] == Vector3(2.5, 0.0, 1.0)
    assert event.payload["vRotationQuaternion"] == Quaternion()
    set_anim_events = [
        item for item in project.scene.timeline if item.event_name == "set_anim"
    ]
    assert [item.start for item in set_anim_events] == pytest.approx([0.25, 1.0])
    assert [item.payload["iObjectId"] for item in set_anim_events] == [
        camera.object_id,
        camera.object_id,
    ]
    assert [item.target_id for item in set_anim_events] == [
        project.animation_manager.object_id,
        project.animation_manager.object_id,
    ]


def test_one_runtime_camera_drives_multiple_named_cuts() -> None:
    project, camera = _animated_camera_project()
    project.camera_cut(camera, start=1.5, name="closing_shot")

    events = [
        item for item in project.scene.timeline if item.event_name == "camera_cut"
    ]
    assert project.scene.cameras == [camera]
    assert [event.target_id for event in events] == [camera.object_id, camera.object_id]
    assert [event.label for event in events] == ["opening_shot", "closing_shot"]
    assert events[1].payload["vPosition"] == Vector3(15.0, 0.0, 1.0)


def test_camera_contract_survives_cut_and_segmented_ycd_roundtrip() -> None:
    project, camera = _animated_camera_project()
    files = project.build().build_files()
    scene = read_cut_scene(files["camera_contract.cut"])
    rebuilt_camera = scene.cameras[0]

    assert isinstance(rebuilt_camera, CutCamera)
    assert rebuilt_camera.animation_streaming_base == camera.animation_streaming_base
    assert rebuilt_camera.near_draw_distance == pytest.approx(0.1)
    assert rebuilt_camera.far_draw_distance == pytest.approx(2000.0)
    set_anim_events = [item for item in scene.timeline if item.event_name == "set_anim"]
    assert [item.start for item in set_anim_events] == pytest.approx([0.25, 1.0])
    assert [item.payload["iObjectId"] for item in set_anim_events] == [
        rebuilt_camera.object_id,
        rebuilt_camera.object_id,
    ]
    assert [item.target_id for item in set_anim_events] == [1, 1]
    for index in range(2):
        ycd = read_ycd(files[f"camera_contract-{index}.ycd"])
        assert ycd.get_clip(f"exportcamera-{index}") is not None


def test_static_camera_has_no_runtime_animation_binding() -> None:
    project = CutsceneProject.create("static_camera", duration=1.0)
    project.camera(cut_position=Vector3(), cut_rotation=Quaternion())

    assert not [
        item for item in project.scene.timeline if item.event_name == "set_anim"
    ]


def test_camera_and_prop_keep_independent_runtime_animation_bindings() -> None:
    project = CutsceneProject.create("mixed_animation", duration=1.0)
    prop = project.scene.prop("box", model_name="prop_box", ytyp_name="demo_props")
    project.animate(
        prop,
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
    )
    camera = project.camera(
        position=Vector3(0.0, 0.0, 1.0),
        rotation=Quaternion(),
    )

    events = [item for item in project.scene.timeline if item.event_name == "set_anim"]
    assert [item.payload["iObjectId"] for item in events] == [
        prop.object_id,
        camera.object_id,
    ]
    assert {item.target_id for item in events} == {project.animation_manager.object_id}


def test_animated_camera_requires_a_complete_cut_pose() -> None:
    project = CutsceneProject.create("incomplete_camera", duration=1.0)

    with pytest.raises(ValueError, match="position and rotation"):
        project.camera(
            position=Vector3(),
            field_of_view=45.0,
        )


def test_project_rejects_a_second_runtime_camera() -> None:
    project, _camera = _animated_camera_project()

    with pytest.raises(ValueError, match="one runtime camera"):
        project.camera("second_camera")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    (
        (
            "animation_streaming_base",
            None,
            "camera.binding.streaming_base.missing",
        ),
        (
            "animation_streaming_base",
            1,
            "camera.binding.streaming_base.mismatch",
        ),
        (
            "near_draw_distance",
            0.0,
            "camera.binding.near_draw_distance.invalid",
        ),
        (
            "far_draw_distance",
            0.0,
            "camera.binding.far_draw_distance.invalid",
        ),
    ),
)
def test_camera_binding_contract_reports_invalid_runtime_fields(
    field: str,
    value: object,
    code: str,
) -> None:
    project, camera = _animated_camera_project()
    setattr(camera, field, value)

    report = project.build().validate()

    assert code in {issue.code for issue in report.errors}


def test_camera_contract_reports_missing_section_clip() -> None:
    project, _camera = _animated_camera_project()
    assets = project.build()
    assets.ycds[1].clips.clear()
    assets.ycds[1].animations.clear()

    report = assets.validate()

    assert "camera.binding.clip.missing" in {issue.code for issue in report.errors}


def test_camera_contract_reports_missing_runtime_animation_binding() -> None:
    project, camera = _animated_camera_project()
    _remove_camera_set_anim(project, camera, start=1.0)

    report = project.build().validate()

    assert "camera.animation_binding.missing" in {issue.code for issue in report.errors}


def test_camera_binding_validation_is_inspection_only() -> None:
    project, camera = _animated_camera_project()
    _remove_camera_set_anim(project, camera)
    timeline = list(project.scene.timeline)

    report = project.build().validate()

    assert "camera.animation_binding.missing" in {issue.code for issue in report.errors}
    assert project.scene.timeline == timeline


def test_camera_binding_validation_uses_external_concat_boundaries() -> None:
    project = CutsceneProject.create(
        "external_concat_camera",
        duration=2.0,
        camera_cuts=[1.0],
    )
    camera = project.camera(
        position=Vector3(0.0, 0.0, 1.0),
        rotation=Quaternion(),
    )
    assets = project.build().build()
    raw = project.scene.to_cut()
    camera_events = [
        event
        for event in project.scene.timeline
        if event.event_name == "set_anim"
        and event.payload["iObjectId"] == camera.object_id
    ]
    camera_events[1].start = 0.5
    first_section = raw.root.fields["concatDataList"][0]
    second_section = deepcopy(first_section)
    second_section.fields["fStartTime"] = 0.5
    raw.root.fields["concatDataList"] = [first_section, second_section]
    project.scene.raw = raw

    report = assets.validate()

    assert "camera.animation_binding.missing" not in {
        issue.code for issue in report.errors
    }


def test_camera_cut_contract_reports_target_and_pose_failures() -> None:
    project, _camera = _animated_camera_project()
    event = next(
        item for item in project.scene.timeline if item.event_name == "camera_cut"
    )
    event.target_id = None
    event.payload["vPosition"] = Vector3(float("nan"), 0.0, 0.0)

    report = project.build().validate()
    codes = {issue.code for issue in report.errors}

    assert "camera_cut.target.missing" in codes
    assert "camera_cut.pose.non_finite" in codes


def test_camera_cut_contract_reports_missing_pose() -> None:
    project, _camera = _animated_camera_project()
    event = next(
        item for item in project.scene.timeline if item.event_name == "camera_cut"
    )
    event.payload.pop("vPosition")

    report = project.build().validate()

    assert "camera_cut.pose.missing" in {issue.code for issue in report.errors}


def test_camera_contract_reports_multiple_runtime_bindings() -> None:
    project, _camera = _animated_camera_project()
    project.scene.camera("second_camera")

    report = project.build().validate()

    assert "camera.binding.multiple" in {issue.code for issue in report.errors}


def test_cut_validation_does_not_build_or_repair_the_source_scene() -> None:
    scene = CutScene(scene_name="inspection_only", duration=1.0)
    settings = deepcopy(scene.settings)

    validate_cut_scene(scene, strict=True)

    assert scene.settings == settings
    assert scene.range_start is None
    assert scene.range_end is None
    assert scene.camera_cut_list is None
    assert not scene.bindings
    assert not scene.tracks


@pytest.mark.parametrize(
    ("game", "animation_vft"),
    (
        (GameTarget.GTA5, LEGACY_YCD_RUNTIME_PROFILE.animation_vft),
        (GameTarget.GTA5_ENHANCED, GEN9_YCD_RUNTIME_PROFILE.animation_vft),
    ),
)
def test_project_camera_preserves_explicit_ycd_runtime_profile(
    game: GameTarget,
    animation_vft: int,
) -> None:
    project = CutsceneProject.create("camera_target", duration=1.0, game=game)
    project.camera(
        position=Vector3(),
        rotation=Quaternion(),
    )

    files = project.build().build_files()
    ycd = read_ycd(files["camera_target-0.ycd"])

    assert ycd.game is game
    assert {animation.vft for animation in ycd.animations} == {animation_vft}


@pytest.mark.parametrize(
    ("_edition", "game_path", "game"),
    _RETAIL_GAME_PATHS,
    ids=[entry[0] for entry in _RETAIL_GAME_PATHS],
)
def test_retail_prologue_cuts_follow_runtime_camera_contract(
    _edition: str,
    game_path: Path,
    game: GameTarget,
) -> None:
    with GameFileCache(
        game_path,
        game=game,
        load_audio=False,
        load_peds=False,
        load_vehicles=False,
        use_index_cache=True,
    ) as cache:
        cache.scan()
        bundles = tuple(
            cache.resolve_cutscene(name) for name in ("pro_mcs_1.cut", "pro_mcs_5.cut")
        )

    for bundle in bundles:
        assert len(bundle.scene.cameras) == 1
        camera = bundle.scene.cameras[0]
        assert camera.animation_streaming_base == jenk_partial_hash("exportcamera")
        assert camera.near_draw_distance is not None
        assert camera.near_draw_distance > 0.0
        assert camera.far_draw_distance is not None
        assert camera.far_draw_distance > camera.near_draw_distance
        assert not [
            issue
            for issue in bundle.scene.validate(strict=True)
            if issue.severity == "error" and issue.code.startswith("camera")
        ]
