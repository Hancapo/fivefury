import pytest

from fivefury import (
    AssetSet,
    BuildContext,
    CutsceneAnimationDictionary,
    CutsceneAssets,
    CutsceneProject,
    GameTarget,
    Quaternion,
    Vector3,
    read_cut_scene,
    read_ycd,
)


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_cutscene_project_keeps_logical_animation_across_technical_ycds(
    game: GameTarget,
) -> None:
    boundaries = [1.0, 2.0, 3.0, 4.0]
    project = CutsceneProject.create(
        "bobei_shape",
        duration=5.0,
        camera_cuts=boundaries,
        game=game,
    )
    actor = project.scene.prop(
        "actor",
        model_name="actor",
        ytyp_name="actors",
    )
    project.animate(
        actor,
        mover_position={0.0: Vector3(), 5.0: Vector3(5.0, 0.0, 0.0)},
        mover_rotation=Quaternion(),
    )
    camera = project.camera(
        position={0.0: Vector3(0.0, -5.0, 1.0), 5.0: Vector3(5.0, -5.0, 1.0)},
        rotation=Quaternion(),
    )
    for index, start in enumerate(boundaries, 1):
        project.camera_cut(camera, start=start, name=f"shot_{index}")

    assets = project.build()
    assert assets.scene.animation_dictionary is not None
    assert assets.scene.animation_dictionary.reference == "dict"
    assert [ycd.path for ycd in assets.scene.animation_dictionary.sections] == [
        f"bobei_shape-{index}.ycd" for index in range(5)
    ]

    timeline = assets.scene.timeline
    loads = [event for event in timeline if event.event_name == "load_anim_dict"]
    sets = [event for event in timeline if event.event_name == "set_anim"]
    clears = [event for event in timeline if event.event_name == "clear_anim"]
    unloads = [event for event in timeline if event.event_name == "unload_anim_dict"]
    camera_cuts = [event for event in timeline if event.event_name == "camera_cut"]

    assert len(loads) == 1
    assert loads[0].start == 0.0
    assert loads[0].label == "dict"
    assert len(sets) == 2
    assert {event.start for event in sets} == {0.0}
    assert {event.payload["iObjectId"] for event in sets} == {
        actor.object_id,
        camera.object_id,
    }
    assert not [
        event
        for event in timeline
        if event.start in boundaries
        and event.event_name
        in {"load_anim_dict", "unload_anim_dict", "set_anim", "clear_anim"}
    ]
    assert len(camera_cuts) == 5
    assert [event.start for event in camera_cuts] == [0.0, *boundaries]
    assert len(clears) == 2
    assert {event.start for event in clears} == {5.0}
    assert len(unloads) == 1
    assert unloads[0].start == 5.0

    files = assets.build_files()
    rebuilt = read_cut_scene(files["bobei_shape.cut"])
    rebuilt.animation_dictionary = CutsceneAnimationDictionary(
        sections=[read_ycd(files[f"bobei_shape-{index}.ycd"]) for index in range(5)]
    )
    rebuilt.validate(strict=True).raise_for_errors()


def test_single_ycd_project_uses_the_same_logical_animation_lifecycle() -> None:
    project = CutsceneProject.create("single_section", duration=1.0)
    camera = project.camera(position=Vector3(), rotation=Quaternion())

    assets = project.build()
    assert assets.scene.animation_dictionary is not None
    assert [ycd.path for ycd in assets.scene.animation_dictionary.sections] == [
        "single_section-0.ycd"
    ]
    assert [
        event.event_name
        for event in assets.scene.timeline
        if event.event_name
        in {"load_anim_dict", "set_anim", "clear_anim", "unload_anim_dict"}
    ] == ["load_anim_dict", "set_anim", "clear_anim", "unload_anim_dict"]
    assert camera.object_id in {
        event.payload.get("iObjectId")
        for event in assets.scene.timeline
        if event.event_name in {"set_anim", "clear_anim"}
    }


def test_validation_checks_every_active_technical_ycd_section() -> None:
    project = CutsceneProject.create(
        "section_validation",
        duration=3.0,
        camera_cuts=[1.0, 2.0],
    )
    actor = project.scene.prop("actor", model_name="actor", ytyp_name="actors")
    project.animate(
        actor,
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
    )
    project.camera(position=Vector3(), rotation=Quaternion())
    assets = project.build()
    assert assets.scene.animation_dictionary is not None
    assets.scene.animation_dictionary.sections[2].clips = [
        clip
        for clip in assets.scene.animation_dictionary.sections[2].clips
        if clip.short_name != "actor-2"
    ]

    report = assets.validate()

    issue = next(
        issue for issue in report.errors if issue.code == "set_anim.clip.missing"
    )
    assert "segment 2" in issue.message


def test_validation_rejects_physical_loads_and_boundary_rebinds() -> None:
    project = CutsceneProject.create(
        "redundant_sections",
        duration=2.0,
        camera_cuts=[1.0],
    )
    actor = project.scene.prop("actor", model_name="actor", ytyp_name="actors")
    project.animate(actor, mover_position=Vector3(), mover_rotation=Quaternion())
    project.camera(position=Vector3(), rotation=Quaternion())
    project.scene.load_anim_dict(
        1.0,
        "redundant_sections-1",
        target=project.animation_manager,
    )
    project.scene.set_anim(1.0, actor, target=project.animation_manager)

    codes = {issue.code for issue in project.build().validate().errors}

    assert "load_anim_dict.physical_section" in codes
    assert "load_anim_dict.redundant" in codes
    assert "set_anim.section_rebind.redundant" in codes


def test_semantic_clear_allows_a_new_binding_at_a_section_boundary() -> None:
    project = CutsceneProject.create(
        "semantic_rebind",
        duration=2.0,
        camera_cuts=[1.0],
    )
    actor = project.scene.prop("actor", model_name="actor", ytyp_name="actors")
    project.animate(actor, mover_position=Vector3(), mover_rotation=Quaternion())
    project.camera(position=Vector3(), rotation=Quaternion())
    project.scene.clear_anim(1.0, actor, target=project.animation_manager)
    project.scene.set_anim(1.0, actor, target=project.animation_manager)

    codes = {issue.code for issue in project.build().validate().errors}

    assert "set_anim.section_rebind.redundant" not in codes
    assert "clear_anim.lifecycle.unbalanced" not in codes


def test_loose_ycd_resolution_uses_physical_section_names() -> None:
    project = CutsceneProject.create(
        "loose_sections",
        duration=2.0,
        camera_cuts=[1.0],
    )
    project.camera(position=Vector3(), rotation=Quaternion())
    authored = project.build()
    assert authored.scene.animation_dictionary is not None
    assets = AssetSet()
    for ycd in authored.scene.animation_dictionary.sections:
        assets[f"stream/{ycd.path}"] = ycd
    authored.scene.animation_dictionary.sections = []

    report = CutsceneAssets(authored.scene).validate(
        context=BuildContext(assets=assets)
    )

    assert "cut.ycd.section_unresolved" not in {issue.code for issue in report.errors}
    assert report.valid
