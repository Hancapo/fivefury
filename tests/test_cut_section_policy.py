from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fivefury import (
    CutCameraCutPayload,
    CutScene,
    CutSceneSettings,
    CutSectioningMode,
    YcdCutsceneBuilder,
)
from fivefury.cut.resolution.animations import _resolve_ycds
from fivefury.cut.scene.io import scene_to_cut


@pytest.mark.parametrize(
    "mode, expected", [(CutSectioningMode.SPLIT, 3), (CutSectioningMode.DURATION, 4)]
)
@pytest.mark.parametrize("source_kind", ["scene", "cut", "path"])
def test_builder_and_resolver_use_technical_sections(
    mode, expected, source_kind, tmp_path
):
    scene = CutScene.create(
        scene_name="sections",
        duration=10,
        range_start=300,
        range_end=600,
        settings=CutSceneSettings(sectioning=mode),
        section_split_list=[13, 16],
        section_by_time_slice_duration=3,
        camera_cut_list=[],
    )
    source = scene
    if source_kind != "scene":
        source = scene_to_cut(scene)
        if source_kind == "path":
            path = tmp_path / "sections.cut"
            path.write_bytes(source.to_bytes())
            source = path
    builder = YcdCutsceneBuilder.from_cut(source)
    assert len(builder.sections) == expected
    cache = Mock()
    cache.find_path.return_value = None
    _resolve_ycds(cache, SimpleNamespace(path="sections.cut"), scene, [])
    paths = [call.args[0] for call in cache.find_path.call_args_list]
    assert paths == [
        "sections-0.ycd",
        "sections.ycd",
        *[f"sections-{i}.ycd" for i in range(1, expected)],
    ]


def test_shot_events_do_not_create_technical_sections():
    scene = CutScene.create(scene_name="shots", duration=3)
    camera = scene.camera()
    scene.camera_cut(1, camera, CutCameraCutPayload("shot"))
    assert len(scene.animation_builder().sections) == 1
    scene.camera_cut_list = [1, 2]
    scene.settings.sectioned = False
    assert len(scene.animation_builder().sections) == 1
