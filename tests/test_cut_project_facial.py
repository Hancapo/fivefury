import pytest

from fivefury import (
    CutFacialAnimationMode,
    CutsceneAnimationDictionary,
    CutsceneProject,
    GameTarget,
    Quaternion,
    Vector3,
    YcdAnimationTrack,
    YcdFacialTrackSet,
    read_cut_scene,
    read_ycd,
)
from fivefury.hashing import jenk_partial_hash


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize("with_body", [False, True])
@pytest.mark.parametrize("clip", ["actor", "custom_dual"])
def test_facial_project_roundtrip_and_rebuild(game, with_body, clip):
    project = CutsceneProject.create("face", duration=2, camera_cuts=[1], game=game)
    project.scene.range_start = 300
    project.scene.range_end = 360
    project.scene.camera_cut_list = [11]
    ped = project.scene.ped("actor", model_name="ped_face", ytyp_name="ped_pack")
    project.camera(position=Vector3(), rotation=Quaternion())
    project.animate(
        ped,
        clip=clip,
        mover_position=Vector3() if with_body else None,
        facial=YcdFacialTrackSet(controls={7: {0.0: 0.0, 2.0: 0.75}}),
    )
    files = project.build().build_files()
    assert files == project.build().build_files()
    scene = read_cut_scene(files["face.cut"])
    scene.animation_dictionary = CutsceneAnimationDictionary(
        sections=[read_ycd(files[f"face-{i}.ycd"]) for i in range(2)]
    )
    actor = scene.peds[0]
    base = clip.removesuffix("_dual")
    assert actor.facial_animation_mode is CutFacialAnimationMode.MERGED
    assert actor.anim_streaming_base == jenk_partial_hash(base)
    for section in range(2):
        resolved = scene.clip_for_binding(actor, cut_index=section)
        assert resolved.short_name == f"{base}_dual-{section}"
        tracks = {bone.track for bone in resolved.animation.bone_ids}
        assert YcdAnimationTrack.FACIAL_CONTROL in tracks
        assert (YcdAnimationTrack.MOVER_TRANSLATION in tracks) == with_body
    assert scene.validate(strict=True).valid


@pytest.mark.parametrize("role", ["prop", "vehicle"])
def test_facial_input_rejects_non_peds_without_authoring_events(role):
    project = CutsceneProject.create("invalid", duration=1)
    binding = getattr(project.scene, role)("actor")
    before = list(project.scene.timeline)
    with pytest.raises(ValueError, match="ped"):
        project.animate(binding, facial=YcdFacialTrackSet(controls={1: 0.5}))
    assert project.scene.timeline == before


def test_body_only_ped_does_not_gain_facial_flags_or_dual_suffix():
    project = CutsceneProject.create("body", duration=1)
    ped = project.scene.ped("actor")
    project.animate(ped, mover_position=Vector3())
    project.camera()
    assets = project.build()
    assert ped.facial_animation_mode is CutFacialAnimationMode.NONE
    assert assets.scene.clip_for_binding(ped).short_name == "actor-0"
