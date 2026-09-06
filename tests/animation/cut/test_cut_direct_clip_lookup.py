from unittest.mock import patch

import pytest

from fivefury import CutScene, CutsceneAnimationDictionary, Vector3, YcdCutsceneBuilder
from fivefury.hashing import jenk_partial_hash


@pytest.mark.parametrize("reference", ["partial", "explicit", "missing"])
def test_exact_binding_lookup_does_not_build_name_maps(reference):
    builder = YcdCutsceneBuilder.create("lookup", duration=2, camera_cuts=[1])
    builder.prop("actor", mover_position=Vector3())
    scene = CutScene.create(duration=2)
    binding = (
        scene.prop("actor", animation_clip_base="actor")
        if reference == "explicit"
        else scene.object(
            "prop",
            name="shared_model",
            fields={
                "AnimStreamingBase": jenk_partial_hash(
                    "missing" if reference == "missing" else "actor"
                )
            },
        )
    )
    scene.animation_dictionary = CutsceneAnimationDictionary(
        sections=builder.build_ycds()
    )
    with patch.object(
        CutScene, "available_clips", side_effect=AssertionError("unexpected full map")
    ):
        for section in (0, 1):
            clip = scene.clip_for_binding(binding, cut_index=section)
            if reference == "missing":
                assert clip is None
            else:
                assert clip is scene.get_clip(f"actor-{section}")
        scene.animation_dictionary.sections.clear()
        if reference != "explicit":
            assert scene.clip_for_binding(binding) is None


def test_name_lookup_remains_available_without_streaming_base():
    builder = YcdCutsceneBuilder.create("lookup", duration=1)
    builder.prop("actor", mover_position=Vector3())
    scene = CutScene.create(duration=1)
    binding = scene.object("prop", name="actor")
    scene.animation_dictionary = CutsceneAnimationDictionary(
        sections=builder.build_ycds()
    )
    assert scene.clip_for_binding(binding) is scene.get_clip("actor-0")
