import pytest

from fivefury import (
    CutsceneAnimationDictionary,
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
