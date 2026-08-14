from fivefury import (
    CutScene,
    CutsceneProject,
    YcdCutsceneBuilder,
    build_ycd_cutscene_clip_hash,
    read_ycd,
)
from fivefury.cut.scene.io import read_cut_scene
from fivefury.hashing import jenk_hash, jenk_partial_hash


def _duplicate_prop_project(
    *, camera_cuts: list[float] | None = None
) -> tuple[CutsceneProject, dict[str, int]]:
    duration = 2.0 if camera_cuts else 1.0
    project = CutsceneProject.create(
        "duplicate_props",
        duration=duration,
        fps=30.0,
        camera_cuts=camera_cuts,
    )
    project.camera(
        "camera",
        position={0.0: (0.0, 0.0, 0.0), duration: (1.0, 0.0, 0.0)},
        rotation=(0.0, 0.0, 0.0, 1.0),
        field_of_view=60.0,
    )
    object_ids: dict[str, int] = {}
    for instance_name in ("prop_box", "prop_box.001"):
        binding = project.scene.prop(
            instance_name,
            cutscene_name=instance_name,
            streaming_name="prop_box",
            animation_clip_base=instance_name,
            type_file="props",
        )
        object_ids[instance_name] = binding.object_id
        project.animate(
            binding,
            mover_position={
                0.0: (0.0, 0.0, 0.0),
                duration: (1.0, 0.0, 0.0),
            },
            mover_rotation=(0.0, 0.0, 0.0, 1.0),
        )
    return project, object_ids


def _roundtrip_project(project: CutsceneProject) -> CutScene:
    files = project.build(cut_name="duplicate_props.cut").build_files()
    scene = read_cut_scene(files["duplicate_props.cut"])
    for name, data in files.items():
        if not name.endswith(".ycd"):
            continue
        ycd = read_ycd(data)
        ycd.path = name
        ycd.build()
        scene.clip_dictionary(ycd)
    return scene


def test_clip_for_binding_distinguishes_shared_model_animation_bases() -> None:
    builder = YcdCutsceneBuilder.create("shared_model", duration=1.0)
    builder.ped("actor_a", mover_position=(0.0, 0.0, 0.0))
    builder.ped("actor_b", mover_position=(1.0, 0.0, 0.0))

    scene = CutScene.create(duration=1.0)
    actor_a = scene.object(
        "ped",
        name="shared_model",
        fields={"AnimStreamingBase": jenk_partial_hash("actor_a")},
    )
    actor_b = scene.object(
        "ped",
        name="shared_model",
        fields={"AnimStreamingBase": jenk_partial_hash("actor_b")},
    )
    for ycd in builder.build_ycds():
        scene.clip_dictionary(ycd)

    clip_a = scene.clip_for_binding(actor_a)
    clip_b = scene.clip_for_binding(actor_b)

    assert clip_a is not None
    assert clip_b is not None
    assert clip_a is not clip_b
    assert clip_a.name.startswith("actor_a-")
    assert clip_b.name.startswith("actor_b-")


def test_clip_for_binding_does_not_fall_back_from_unresolved_stream_base() -> None:
    builder = YcdCutsceneBuilder.create("shared_model", duration=1.0)
    builder.ped("shared_model", mover_position=(0.0, 0.0, 0.0))
    scene = CutScene.create(duration=1.0)
    actor = scene.object(
        "ped",
        name="shared_model",
        fields={"AnimStreamingBase": jenk_partial_hash("missing_actor")},
    )
    for ycd in builder.build_ycds():
        scene.clip_dictionary(ycd)

    assert scene.clip_for_binding(actor) is None


def test_clip_for_binding_reads_animation_base_from_generic_camera_fields() -> None:
    builder = YcdCutsceneBuilder.create("camera_scene", duration=1.0)
    builder.camera(
        "exportcamera",
        position=(0.0, 0.0, 1.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
    )
    scene = CutScene.create(duration=1.0)
    camera = scene.object(
        "camera",
        name="0x39662FB2",
        fields={"AnimStreamingBase": jenk_partial_hash("exportcamera")},
    )
    for ycd in builder.build_ycds():
        scene.clip_dictionary(ycd)

    clip = scene.clip_for_binding(camera)

    assert clip is not None
    assert clip.name.startswith("exportcamera-")


def test_duplicate_model_instances_survive_strict_cut_ycd_roundtrip() -> None:
    project, object_ids = _duplicate_prop_project()

    scene = _roundtrip_project(project)
    available = scene.available_clips(cut_index=0)
    assert not any(
        "no matching clip" in warning for warning in scene.validate_animations()
    )

    for clip_base, object_id in object_ids.items():
        binding = scene.get_binding(object_id)
        assert binding is not None
        assert binding.fields["StreamingName"].hash == jenk_hash("prop_box")
        clip = scene.clip_for_binding(binding, cut_index=0)
        assert clip is not None
        assert clip.hash == build_ycd_cutscene_clip_hash(
            jenk_partial_hash(clip_base),
            0,
        )
        assert clip.name == f"{clip_base}-0"
        assert available[jenk_hash(clip_base)] is clip


def test_cutscene_clip_hash_continues_merged_facial_suffix() -> None:
    clip_hash = build_ycd_cutscene_clip_hash(
        jenk_partial_hash("actor"),
        2,
        combined_facial=True,
    )

    assert clip_hash.uint == jenk_hash("actor_dual-2")


def test_duplicate_model_instances_resolve_each_technical_segment() -> None:
    project, object_ids = _duplicate_prop_project(camera_cuts=[1.0])

    scene = _roundtrip_project(project)

    for cut_index in (0, 1):
        resolved = []
        for clip_base, object_id in object_ids.items():
            clip = scene.clip_for_binding(object_id, cut_index=cut_index)
            assert clip is not None
            assert clip.hash == build_ycd_cutscene_clip_hash(
                jenk_partial_hash(clip_base),
                cut_index,
            )
            assert clip.name == f"{clip_base}-{cut_index}"
            resolved.append(clip.hash.uint)
        assert len(set(resolved)) == 2
