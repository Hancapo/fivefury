import pytest

from fivefury import (
    AssetSet,
    BuildContext,
    CutsceneProject,
    GameTarget,
    Quaternion,
    Vector3,
    read_cut_scene,
    read_ycd,
)


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_loose_ycd_context_survives_export_without_mutating_source(game):
    project = CutsceneProject.create(
        "loose_camera", duration=2, camera_cuts=[1], game=game
    )
    project.camera(position=Vector3(), rotation=Quaternion())
    authored = project.build()
    assets = AssetSet()
    for ycd in authored.scene.animation_dictionary.sections:
        assets[f"stream/{ycd.path}"] = ycd
    authored.scene.animation_dictionary.sections.clear()
    context = BuildContext(assets=assets, game=game, strict=True)
    assert authored.validate(context=context).valid
    files = authored.build_files(context=context)
    assert set(files) == {
        "loose_camera.cut",
        "loose_camera-0.ycd",
        "loose_camera-1.ycd",
    }
    assert authored.scene.animation_dictionary.sections == []
    assert read_cut_scene(files["loose_camera.cut"]).cameras
    for name, data in files.items():
        if name.endswith(".ycd"):
            assert read_ycd(data).clips


def test_missing_loose_section_does_not_write_partial_files(tmp_path):
    project = CutsceneProject.create("missing", duration=2, camera_cuts=[1])
    project.camera(position=Vector3(), rotation=Quaternion())
    authored = project.build()
    assets = AssetSet()
    assets["missing-0.ycd"] = authored.scene.animation_dictionary.sections[0]
    authored.scene.animation_dictionary.sections.clear()
    context = BuildContext(assets=assets, strict=True)
    with pytest.raises(ValueError, match="section"):
        authored.save(tmp_path, context=context)
    assert list(tmp_path.iterdir()) == []
