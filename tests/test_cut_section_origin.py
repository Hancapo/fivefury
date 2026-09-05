import pytest

from fivefury import CutScene, CutSceneSettings, CutSectioningMode
from fivefury.cut.scene.io import read_cut_scene, scene_to_cut
from fivefury.cut.scene.shared import (
    _runtime_animation_section_index,
    _runtime_animation_section_starts,
)


@pytest.mark.parametrize(
    "mode", [CutSectioningMode.CAMERA_CUTS, CutSectioningMode.SPLIT]
)
@pytest.mark.parametrize("origin", [0, 300])
def test_runtime_section_times_are_relative_to_source_frame_range(mode, origin):
    cuts = [origin / 30 + value for value in (0, 3, 6, 10)]
    scene = CutScene.create(
        duration=10,
        range_start=origin,
        range_end=origin + 300,
        settings=CutSceneSettings(sectioning=mode),
        camera_cut_list=cuts if mode == CutSectioningMode.CAMERA_CUTS else [],
        section_split_list=cuts if mode == CutSectioningMode.SPLIT else [],
    )
    rebuilt = read_cut_scene(scene_to_cut(scene).to_bytes())
    assert _runtime_animation_section_starts(rebuilt) == (0, 3, 6)
    assert [
        _runtime_animation_section_index(rebuilt, time) for time in (0, 2.9, 3, 6, 9)
    ] == [0, 0, 1, 2, 2]


def test_duration_sections_do_not_subtract_source_origin():
    scene = CutScene.create(
        duration=10,
        range_start=300,
        range_end=600,
        settings=CutSceneSettings(sectioning=CutSectioningMode.DURATION),
        section_by_time_slice_duration=3,
    )
    assert _runtime_animation_section_starts(scene) == (0, 3, 6, 9)
    scene.settings.sectioned = False
    assert _runtime_animation_section_starts(scene) == (0,)
