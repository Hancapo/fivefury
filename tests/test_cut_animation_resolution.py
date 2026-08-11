from fivefury import CutScene, YcdCutsceneBuilder
from fivefury.hashing import jenk_partial_hash


def test_clip_for_binding_distinguishes_shared_model_animation_bases() -> None:
    builder = YcdCutsceneBuilder.create("shared_model", duration=1.0)
    builder.add_ped("actor_a", mover_position=(0.0, 0.0, 0.0))
    builder.add_ped("actor_b", mover_position=(1.0, 0.0, 0.0))

    scene = CutScene.create(duration=1.0)
    actor_a = scene.add_object(
        "ped",
        name="shared_model",
        fields={"AnimStreamingBase": jenk_partial_hash("actor_a")},
    )
    actor_b = scene.add_object(
        "ped",
        name="shared_model",
        fields={"AnimStreamingBase": jenk_partial_hash("actor_b")},
    )
    for ycd in builder.build_ycds():
        scene.attach_clip_dict(ycd)

    clip_a = scene.clip_for_binding(actor_a)
    clip_b = scene.clip_for_binding(actor_b)

    assert clip_a is not None
    assert clip_b is not None
    assert clip_a is not clip_b
    assert clip_a.name.startswith("actor_a-")
    assert clip_b.name.startswith("actor_b-")


def test_clip_for_binding_does_not_fall_back_from_unresolved_stream_base() -> None:
    builder = YcdCutsceneBuilder.create("shared_model", duration=1.0)
    builder.add_ped("shared_model", mover_position=(0.0, 0.0, 0.0))
    scene = CutScene.create(duration=1.0)
    actor = scene.add_object(
        "ped",
        name="shared_model",
        fields={"AnimStreamingBase": jenk_partial_hash("missing_actor")},
    )
    for ycd in builder.build_ycds():
        scene.attach_clip_dict(ycd)

    assert scene.clip_for_binding(actor) is None


def test_clip_for_binding_reads_animation_base_from_generic_camera_fields() -> None:
    builder = YcdCutsceneBuilder.create("camera_scene", duration=1.0)
    builder.add_camera(
        "exportcamera",
        position=(0.0, 0.0, 1.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
    )
    scene = CutScene.create(duration=1.0)
    camera = scene.add_object(
        "camera",
        name="0x39662FB2",
        fields={"AnimStreamingBase": jenk_partial_hash("exportcamera")},
    )
    for ycd in builder.build_ycds():
        scene.attach_clip_dict(ycd)

    clip = scene.clip_for_binding(camera)

    assert clip is not None
    assert clip.name.startswith("exportcamera-")
