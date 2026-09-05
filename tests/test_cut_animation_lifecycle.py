import pytest

from fivefury import CutsceneProject, GameTarget, Quaternion, Vector3


def camera_assets(game=GameTarget.GTA5):
    project = CutsceneProject.create("lifecycle", duration=2, game=game)
    camera = project.camera(position=Vector3(), rotation=Quaternion())
    return project, camera, project.build()


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_clear_before_set_cannot_be_exported(game, tmp_path):
    project, _camera, assets = camera_assets(game)
    for event in project.scene.timeline:
        if event.event_name == "set_anim":
            event.start = 1
        elif event.event_name == "clear_anim":
            event.start = 0.5
    codes = {issue.code for issue in assets.validate().errors}
    assert {"clear_anim.lifecycle.inactive", "clear_anim.lifecycle.unbalanced"} <= codes
    with pytest.raises(ValueError, match="CLEAR_ANIM"):
        assets.save(tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("clear_first", [False, True])
def test_equal_time_events_preserve_reference_order(clear_first):
    project, _camera, assets = camera_assets()
    events = {
        event.event_name: event
        for event in project.scene.timeline
        if event.event_name in {"set_anim", "clear_anim"}
    }
    events["set_anim"].start = events["clear_anim"].start = 1
    if clear_first:
        events["set_anim"].order, events["clear_anim"].order = (
            events["clear_anim"].order,
            events["set_anim"].order,
        )
    codes = {issue.code for issue in assets.validate().errors}
    assert ("clear_anim.lifecycle.inactive" in codes) == clear_first


def test_repeated_set_uses_reference_count_and_allows_semantic_rebinding():
    project, camera, assets = camera_assets()
    project.scene.set_anim(0.25, camera, target=project.animation_manager)
    project.scene.clear_anim(0.5, camera, target=project.animation_manager)
    project.scene.clear_anim(0.75, camera, target=project.animation_manager)
    project.scene.set_anim(1, camera, target=project.animation_manager)
    assert assets.validate().valid
    assert assets.build_files()["lifecycle.cut"]
    project.scene.clear_anim(1.5, camera, target=project.animation_manager)
    assert "clear_anim.lifecycle.inactive" in {
        issue.code for issue in assets.validate().errors
    }
