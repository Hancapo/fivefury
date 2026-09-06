from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import (
    AssetSet,
    BuildContext,
    CutAnimationManager,
    CutAssetManager,
    CutCamera,
    CutCameraCharacterLightPayload,
    CutCameraCutPayload,
    CutCameraDofModifierPayload,
    CutConcatMode,
    CutDrawDistancePayload,
    CutEventBehavior,
    CutEventType,
    CutHashedString,
    CutLoadScenePayload,
    CutNode,
    CutPed,
    CutProp,
    CutPropAnimationPreset,
    CutScene,
    CutsceneAnimationDictionary,
    CutsceneAssets,
    CutsceneProject,
    CutSceneSettings,
    CutSectioningMode,
    CutSubtitle,
    CutSubtitleCue,
    CutSubtitlePayload,
    DiagnosticSeverity,
    GameFileCache,
    Quaternion,
    ValidationError,
    Vector2,
    Vector3,
    Ydr,
    YdrMeshInput,
    YdrSkeleton,
    Ytyp,
    build_cut_bytes,
    create_ydr,
    read_cut,
    read_cut_scene,
    read_ycd,
    scene_to_cut,
    validate_cut_scene,
)
from fivefury.cache.io import decode_game_file_payload
from fivefury.cut.limits import CUT_MAX_CONCATENATED_SCENES, CUT_MAX_PSO_ARRAY_ITEMS
from fivefury.gamefile import GameFileType
from fivefury.hashing import jenk_hash


def test_cut_scene_builder_writes_without_template() -> None:
    scene = CutScene.create(duration=15.0, face_dir="x:/gta5/assets_ng/cuts/test/faces")
    asset_manager = scene.binding(CutAssetManager())
    camera = scene.binding(CutCamera("cam_orbit"))
    actor = scene.binding(CutPed("ped_sphere"))
    subtitle = scene.binding(CutSubtitle("subtitle_track"))

    scene.load_scene(0.0, CutLoadScenePayload("intro_scene"), target=asset_manager)
    scene.load_models(0.0, [actor.object_id], target=asset_manager)
    camera_event = scene.camera_cut(0.0, camera, CutCameraCutPayload("cam_orbit"))
    subtitle_event = scene.show_subtitle(
        0.0, subtitle, CutSubtitlePayload("hola amigos", duration=15.0)
    )

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

    assert camera_event.behavior is CutEventBehavior.STATE
    assert camera_event.end is None
    assert subtitle_event.behavior is CutEventBehavior.DURATION
    assert subtitle_event.end == pytest.approx(15.0)
    assert rebuilt.root.type_name == "rage__cutfCutsceneFile2"
    assert rebuilt.root.fields["fTotalDuration"] == pytest.approx(15.0)
    assert rebuilt.root.fields["cFaceDir"] == "x:/gta5/assets_ng/cuts/test/faces"
    assert len(rebuilt.objects) == 4
    assert len(rebuilt.load_events) == 2
    assert len(rebuilt.events) == 2
    assert len(rebuilt.event_args) == 4
    assert rebuilt.objects[1].type_name == "rage__cutfCameraObject"
    assert any(event.fields["iEventId"] == 43 for event in rebuilt.events)
    camera_args = next(
        args
        for args in rebuilt.event_args
        if args.type_name == "rage__cutfCameraCutEventArgs"
    )
    assert camera_args.fields["cName"].hash != 0


def test_cut_writer_preserves_fields_after_dynamic_structure_pointer() -> None:
    scene = CutScene.create(duration=5.0)
    asset_manager = scene.asset_manager()
    scene.load_scene(
        0.0, CutLoadScenePayload("nested_attributes"), target=asset_manager
    )
    cut = scene_to_cut(scene)
    args = cut.event_args[0]
    args.fields["cutfAttributes"] = CutNode(
        type_name="rage__cutfEventArgs",
        fields={},
    )
    expected = args.fields["cName"]

    rebuilt = read_cut(build_cut_bytes(cut))
    actual = rebuilt.event_args[0].fields["cName"]

    assert isinstance(expected, CutHashedString)
    assert isinstance(actual, CutHashedString)
    assert actual.hash == expected.hash


def test_cut_writer_roundtrips_atstring_arrays() -> None:
    scene = CutScene.create(duration=5.0)
    vehicle = scene.vehicle(
        "car", fields={"cRemoveBoneNameList": ["door_dside_f", "wheel_lf"]}
    )

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    rebuilt_vehicle = next(
        node
        for node in rebuilt.objects
        if node.fields["iObjectId"] == vehicle.object_id
    )

    assert rebuilt_vehicle.fields["cRemoveBoneNameList"] == ["door_dside_f", "wheel_lf"]


def test_cut_decoder_uses_logical_pso_instead_of_stored_archive_bytes() -> None:
    logical = scene_to_cut(CutScene.create(duration=5.0)).to_bytes()

    parsed, kind = decode_game_file_payload(
        "example.cut", logical, raw=b"compressed archive payload"
    )

    assert kind is GameFileType.CUT
    assert parsed.root.type_name == "rage__cutfCutsceneFile2"


def test_cut_scene_save_validation_allows_playable_minimal_scene() -> None:
    scene = CutScene.create(scene_name="playable", duration=5.0)
    asset_manager = scene.asset_manager()
    camera = scene.camera("cam_main")
    prop = scene.prop("prop_a", model_name="prop_a", ytyp_name="prop_pack")

    scene.load_scene(0.0, CutLoadScenePayload("playable"), target=asset_manager)
    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.camera_cut(
        0.0,
        camera,
        CutCameraCutPayload(
            "cam_main", near_draw_distance=0.05, far_draw_distance=1000.0
        ),
    )

    rebuilt = read_cut(scene.to_bytes())

    assert rebuilt.root.fields["fTotalDuration"] == pytest.approx(5.0)
    assert any(
        event.fields["iEventId"] == int(CutEventType.CAMERA_CUT)
        for event in rebuilt.events
    )


def test_cut_scene_save_validation_reports_missing_type_file() -> None:
    scene = CutScene.create(scene_name="bad_cut", duration=5.0)
    asset_manager = scene.asset_manager()
    camera = scene.camera("cam_main")
    prop = scene.prop("prop_a", model_name="prop_a")

    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.camera_cut(
        0.0,
        camera,
        CutCameraCutPayload(
            "cam_main", near_draw_distance=0.05, far_draw_distance=1000.0
        ),
    )

    with pytest.raises(ValidationError) as excinfo:
        scene.to_bytes()

    assert any(
        issue.code == "object.type_file.missing"
        for issue in excinfo.value.report.errors
    )
    assert "object.type_file.missing" in str(excinfo.value)


def test_cut_scene_save_validation_reports_bad_animation_binding() -> None:
    scene = CutScene.create(scene_name="bad_anim", duration=5.0)
    asset_manager = scene.asset_manager()
    animation_manager = scene.animation_manager()
    camera = scene.camera("cam_main")
    prop = scene.prop("prop_a", model_name="prop_a", ytyp_name="prop_pack")

    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.load_anim_dict(0.0, "bad_anim", target=animation_manager)
    scene.set_anim(0.0, prop, target=animation_manager)
    scene.camera_cut(
        0.0,
        camera,
        CutCameraCutPayload(
            "cam_main", near_draw_distance=0.05, far_draw_distance=1000.0
        ),
    )

    with pytest.raises(ValidationError) as excinfo:
        scene.to_bytes()

    assert any(
        issue.code == "set_anim.streaming_base.mismatch"
        for issue in excinfo.value.report.errors
    )


def test_cut_scene_installs_subtitle_track_and_gxt2() -> None:
    scene = CutScene.create(duration=6.0)
    asset_manager = scene.asset_manager()
    track = scene.install_subtitles(
        "TEST_SUBS",
        [
            CutSubtitleCue("TEST_SUB_001", "First line", start=0.0, duration=2.0),
            CutSubtitleCue("TEST_SUB_002", "Second line", start=2.5, duration=2.0),
        ],
        asset_manager=asset_manager,
    )

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    gxt = track.to_gxt2()

    assert gxt.get("TEST_SUB_001") == "First line"
    assert gxt.get("TEST_SUB_002") == "Second line"
    assert (
        sum(1 for obj in rebuilt.objects if obj.type_name == "rage__cutfSubtitleObject")
        == 1
    )
    assert (
        sum(1 for event in rebuilt.load_events if event.fields["iEventId"] == 12) == 1
    )
    show_events = [event for event in rebuilt.events if event.fields["iEventId"] == 30]
    assert len(show_events) == 2
    args = rebuilt.get_event_args(show_events[0].fields["iEventArgsIndex"])
    assert args is not None and args.type_name == "rage__cutfSubtitleEventArgs"
    assert args.fields["iLanguageID"] == -1
    assert args.fields["iTransitionIn"] == -1
    assert args.fields["iTransitionOut"] == -1


def test_cut_scene_load_order_is_stable_with_subtitles() -> None:
    scene = CutScene.create(duration=6.0)
    asset_manager = scene.asset_manager()
    animation_manager = scene.animation_manager()
    prop = scene.prop("prop_a")

    scene.load_scene(0.0, CutLoadScenePayload("scene"), target=asset_manager)
    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.load_anim_dict(0.0, "scene", target=animation_manager)
    scene.install_subtitles(
        "TEST_SUBS",
        [CutSubtitleCue("TEST_SUB_001", "First line", start=1.0, duration=2.0)],
        asset_manager=asset_manager,
        load_dictionary=False,
    )

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

    assert [event.fields["iEventId"] for event in rebuilt.load_events] == [0, 6, 2]


def test_cut_scene_preserves_authored_order_for_simultaneous_events() -> None:
    scene = CutScene.create(duration=2.0)
    asset_manager = scene.asset_manager()
    animation_manager = scene.animation_manager()
    prop = scene.prop("prop_a")

    scene.load_anim_dict(0.0, "scene", target=animation_manager)
    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.load_scene(0.0, CutLoadScenePayload("scene"), target=asset_manager)

    first = read_cut(build_cut_bytes(scene_to_cut(scene)))
    second = read_cut(build_cut_bytes(scene_to_cut(read_cut_scene(first))))

    expected = [
        int(CutEventType.LOAD_ANIM_DICT),
        int(CutEventType.LOAD_MODELS),
        int(CutEventType.LOAD_SCENE),
    ]
    assert [event.fields["iEventId"] for event in first.load_events] == expected
    assert [event.fields["iEventId"] for event in second.load_events] == expected


def test_cut_scene_animation_manager_writes_without_template() -> None:
    scene = CutScene.create(duration=8.0)
    animation_manager = scene.binding(CutAnimationManager())
    actor = scene.binding(CutPed("ped_actor"))

    load_event = scene.load_anim_dict(0.0, "intro_dict", target=animation_manager)
    set_event = scene.set_anim(0.0, actor, target=animation_manager)
    clear_event = scene.clear_anim(6.0, actor, target=animation_manager)
    unload_event = scene.unload_anim_dict(7.5, "intro_dict", target=animation_manager)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

    assert load_event.behavior is CutEventBehavior.STATE
    assert set_event.behavior is CutEventBehavior.STATE
    assert clear_event.behavior is CutEventBehavior.STATE
    assert unload_event.behavior is CutEventBehavior.STATE
    assert len(rebuilt.objects) == 2
    assert len(rebuilt.load_events) == 2
    assert len(rebuilt.events) == 2
    assert len(rebuilt.event_args) == 4
    animation_object = next(
        node
        for node in rebuilt.objects
        if node.type_name == "rage__cutfAnimationManagerObject"
    )
    assert animation_object.fields["iObjectId"] == animation_manager.object_id
    name_args = [
        args
        for args in rebuilt.event_args
        if args.type_name == "rage__cutfNameEventArgs"
    ]
    object_args = [
        args
        for args in rebuilt.event_args
        if args.type_name == "rage__cutfObjectIdEventArgs"
    ]
    assert len(name_args) == 2
    assert len(object_args) == 2
    assert all(
        args.fields["cName"].hash == jenk_hash("intro_dict") for args in name_args
    )
    assert all(args.fields["iObjectId"] == actor.object_id for args in object_args)
    assert {
        event.fields["iEventId"] for event in rebuilt.load_events + rebuilt.events
    } == {
        int(CutEventType.LOAD_ANIM_DICT),
        int(CutEventType.SET_ANIM),
        int(CutEventType.CLEAR_ANIM),
        int(CutEventType.UNLOAD_ANIM_DICT),
    }


def test_cut_scene_preserves_authored_prop_startup_time() -> None:
    scene = CutScene.create(duration=8.0)
    asset_manager = scene.binding(CutAssetManager())
    animation_manager = scene.binding(CutAnimationManager())
    camera = scene.binding(CutCamera("cam"))
    prop = scene.binding(
        CutProp("prop_local")
        .configure_model_asset(
            streaming_name="prop_stream",
            animation_clip_base="prop_stream",
            type_file="prop_pack",
        )
        .apply_animation_preset(CutPropAnimationPreset.COMMON_PROP)
    )

    scene.load_anim_dict(0.0, "scene-0", target=animation_manager)
    scene.load_scene(0.0, CutLoadScenePayload("scene"), target=asset_manager)
    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.camera_cut(0.0, camera, CutCameraCutPayload("cam"))
    scene.set_anim(1.0 / 240.0, prop, target=animation_manager)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

    assert [event.fields["iEventId"] for event in rebuilt.load_events] == [
        int(CutEventType.LOAD_ANIM_DICT),
        int(CutEventType.LOAD_SCENE),
        int(CutEventType.LOAD_MODELS),
    ]
    assert [
        (event.fields["fTime"], event.fields["iEventId"])
        for event in rebuilt.events[:2]
    ] == [
        (0.0, int(CutEventType.CAMERA_CUT)),
        (pytest.approx(1.0 / 240.0), int(CutEventType.SET_ANIM)),
    ]
    rebuilt_prop = next(
        node
        for node in rebuilt.objects
        if node.type_name == "rage__cutfPropModelObject"
    )
    assert rebuilt_prop.fields["cHandle"].hash == 0


def test_cut_event_args_use_complete_runtime_layouts() -> None:
    scene = CutScene.create(duration=5.0)
    animation_manager = scene.animation_manager()
    camera = scene.camera("cam")
    parent = scene.prop("parent")
    child = scene.prop("child")

    scene.set_anim(0.0, child, clip_name="child_clip", target=animation_manager)
    scene.set_draw_distance(0.0, camera, CutDrawDistancePayload(0.1, 1500.0))
    scene.set_attachment(0.0, child, parent, "SKEL_R_Hand")
    scene.camera_cut(
        0.0,
        camera,
        CutCameraCutPayload(
            "cam",
            character_light=CutCameraCharacterLightPayload(intensity=0.25),
            time_of_day_dof_modifiers=[CutCameraDofModifierPayload(0x3F, 4)],
        ),
    )

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    args_by_type = {args.type_name: args for args in rebuilt.event_args}

    named_anim = args_by_type["rage__cutfObjectIdNameEventArgs"]
    assert named_anim.fields["iObjectId"] == child.object_id
    assert named_anim.fields["cName"].hash == jenk_hash("child_clip")
    draw_distance = args_by_type["rage__cutfTwoFloatValuesEventArgs"]
    assert draw_distance.fields["fValue"] == pytest.approx(0.1)
    assert draw_distance.fields["fValue2"] == pytest.approx(1500.0)
    attachment = args_by_type["rage__cutfAttachmentEventArgs"]
    assert attachment.fields["iObjectId"] == parent.object_id
    assert attachment.fields["cBoneName"].hash == jenk_hash("SKEL_R_Hand")
    camera_args = args_by_type["rage__cutfCameraCutEventArgs"]
    assert camera_args.fields["fNearDrawDistance"] == pytest.approx(-1.0)
    assert camera_args.fields["AbsoluteIntensityEnabled"] is True
    assert camera_args.fields["CharacterLight"].fields["fIntensity"] == pytest.approx(
        0.25
    )
    dof_modifier = camera_args.fields["TimeOfDayDofModifers"][0]
    assert dof_modifier.fields["TimeOfDayFlags"] == 0x3F
    assert dof_modifier.fields["DofStrengthModifier"] == 4


def test_cut_camera_validation_accepts_minus_one_overrides() -> None:
    scene = CutScene.create(duration=1.0)
    camera = scene.camera("cam")
    scene.camera_cut(0.0, camera, CutCameraCutPayload("cam"))

    issues = validate_cut_scene(scene, strict=True)

    assert not any(
        issue.code.startswith("camera_cut.clip")
        and issue.severity == DiagnosticSeverity.ERROR
        for issue in issues
    )


def test_cut_validation_rejects_runtime_duration_and_range_errors() -> None:
    too_short = CutScene.create(duration=0.5)
    bad_range = CutScene.create(duration=5.0, range_start=30, range_end=150)

    assert any(
        issue.code == "cut.duration.too_short"
        for issue in validate_cut_scene(too_short)
    )
    assert any(
        issue.code == "cut.range.duration_mismatch"
        for issue in validate_cut_scene(bad_range)
    )


def test_cut_validation_rejects_unsafe_section_layouts() -> None:
    duration_sections = CutScene.create(
        duration=5.0,
        settings=CutSceneSettings(sectioning=CutSectioningMode.DURATION),
        section_by_time_slice_duration=0.5,
    )
    split_sections = CutScene.create(
        duration=5.0,
        settings=CutSceneSettings(sectioning=CutSectioningMode.SPLIT),
        section_split_list=[2.0, 1.0],
    )
    conflicting_modes = CutScene.create(
        duration=5.0,
        settings=CutSceneSettings(
            sectioning=(CutSectioningMode.CAMERA_CUTS | CutSectioningMode.SPLIT)
        ),
    )

    assert any(
        issue.code == "cut.section.duration.too_short"
        for issue in validate_cut_scene(duration_sections)
    )
    assert any(
        issue.code == "cut.section.split.order"
        for issue in validate_cut_scene(split_sections)
    )
    assert any(
        issue.code == "cut.section.mode.multiple"
        for issue in validate_cut_scene(conflicting_modes)
    )


def test_cut_validation_rejects_conflicting_concat_modes() -> None:
    scene = CutScene.create(
        duration=5.0,
        settings=CutSceneSettings(
            concat=CutConcatMode.INTERNAL | CutConcatMode.EXTERNAL
        ),
    )

    assert any(
        issue.code == "cut.concat.mode.multiple" for issue in validate_cut_scene(scene)
    )


def test_cut_validation_accepts_retail_camera_cut_precision() -> None:
    scene = CutScene.create(
        duration=2.0,
        settings=CutSceneSettings(sectioning=CutSectioningMode.CAMERA_CUTS),
        camera_cut_list=[0.9999964],
    )

    assert not any(
        issue.code == "cut.section.interval.too_short"
        for issue in validate_cut_scene(scene)
    )


def test_cut_writer_rejects_fixed_and_dynamic_array_overflow() -> None:
    cut = scene_to_cut(CutScene.create(duration=1.0))
    concat_item = cut.root.fields["concatDataList"][0]
    cut.root.fields["concatDataList"] = [concat_item] * (
        CUT_MAX_CONCATENATED_SCENES + 1
    )

    with pytest.raises(ValueError, match="concatDataList"):
        build_cut_bytes(cut)

    cut.root.fields["concatDataList"] = [concat_item]
    cut.root.fields["cameraCutList"] = [0.0] * (CUT_MAX_PSO_ARRAY_ITEMS + 1)

    with pytest.raises(ValueError, match="cameraCutList"):
        build_cut_bytes(cut)


def test_cutscene_project_builds_valid_cut_and_segmented_ycds() -> None:
    project = CutsceneProject.create("demo_scene", duration=2.0, camera_cuts=[1.0])
    prop = project.scene.prop("box", model_name="prop_box", ytyp_name="demo_props")
    project.animate(
        prop,
        mover_position={0.0: Vector3(), 2.0: Vector3(1.0, 0.0, 0.0)},
        mover_rotation=Quaternion(),
    )
    project.camera(
        position={0.0: Vector3(0.0, -4.0, 1.0), 2.0: Vector3(0.0, -3.0, 1.0)},
        rotation=Quaternion(),
        field_of_view=45.0,
    )

    files = project.build().build_files()

    assert set(files) == {
        "demo_scene.cut",
        "demo_scene-0.ycd",
        "demo_scene-1.ycd",
    }
    rebuilt_ycds = []
    for name in ("demo_scene-0.ycd", "demo_scene-1.ycd"):
        ycd = read_ycd(files[name])
        ycd.path = name
        rebuilt_ycds.append(ycd)
    rebuilt = read_cut_scene(files["demo_scene.cut"])
    rebuilt.animation_dictionary = CutsceneAnimationDictionary(sections=rebuilt_ycds)
    rebuilt.validate(strict=True).raise_for_errors()


def test_cutscene_assets_do_not_write_files_when_validation_fails(tmp_path) -> None:
    project = CutsceneProject.create("broken_scene", duration=1.0)

    with pytest.raises(ValidationError) as excinfo:
        project.build().save(tmp_path)

    assert any(
        issue.code == "camera_cut.missing" for issue in excinfo.value.report.errors
    )
    assert list(tmp_path.iterdir()) == []


def test_cutscene_high_level_save_cannot_skip_validation() -> None:
    scene = CutScene.create(scene_name="broken_scene", duration=1.0)

    with pytest.raises(TypeError):
        scene.to_bytes(validate=False)  # type: ignore[call-arg]


def test_cutscene_rejects_wrong_event_target_role() -> None:
    scene = CutScene.create(scene_name="wrong_target", duration=1.0)
    asset_manager = scene.asset_manager()
    camera = scene.camera("camera")
    scene.load_scene(0.0, {"cName": "wrong_target"}, target=asset_manager)
    scene.camera_cut(0.0, camera, CutCameraCutPayload("camera"))
    scene.load_models(0.0, [], target=camera)

    with pytest.raises(ValidationError) as excinfo:
        scene.to_bytes()

    assert any(
        issue.code == "event.target.role" for issue in excinfo.value.report.errors
    )


def test_cutscene_rejects_attachment_cycles() -> None:
    scene = CutScene.create(scene_name="attachment_cycle", duration=1.0)
    first = scene.prop("first", model_name="first", ytyp_name="props")
    second = scene.prop("second", model_name="second", ytyp_name="props")
    scene.set_attachment(0.0, first, second, "root")
    scene.set_attachment(0.0, second, first, "root")

    issues = scene.validate(strict=True)

    assert any(issue.code == "attachment.cycle" for issue in issues)


def test_cutscene_rejects_animation_dictionary_that_does_not_match_ycd() -> None:
    project = CutsceneProject.create("dict_mismatch", duration=1.0)
    prop = project.scene.prop("box", model_name="prop_box", ytyp_name="demo_props")
    project.animate(
        prop,
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
    )
    project.camera()
    load_event = next(
        event
        for event in project.scene.timeline
        if event.event_name == "load_anim_dict"
    )
    load_event.label = "wrong_dictionary"
    load_event.payload["cName"] = "wrong_dictionary"

    with pytest.raises(ValidationError) as excinfo:
        project.build().build_files()

    assert any(
        issue.code == "set_anim.dict.mismatch" for issue in excinfo.value.report.errors
    )


def test_cutscene_rejects_animation_after_model_was_unloaded() -> None:
    project = CutsceneProject.create("unloaded_model", duration=1.0)
    prop = project.scene.prop("box", model_name="prop_box", ytyp_name="demo_props")
    project.animate(
        prop,
        start=0.5,
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
    )
    project.camera()
    project.scene.unload_models(0.25, [prop.object_id], target=project.asset_manager)

    with pytest.raises(ValidationError) as excinfo:
        project.build().build_files()

    assert any(
        issue.code == "set_anim.model.not_loaded"
        for issue in excinfo.value.report.errors
    )


def _cutscene_prop_project(*, bones: dict[int, object] | None = None):
    project = CutsceneProject.create("context_scene", duration=1.0)
    prop = project.scene.prop("box", model_name="prop_box", ytyp_name="demo_props")
    project.animate(
        prop,
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
        bones=bones,
    )
    project.camera()
    return project


def _cutscene_prop_context(drawable: Ydr | None = None) -> BuildContext:
    ytyp = Ytyp(name="demo_props")
    ytyp.archetype("prop_box")
    assets = AssetSet()
    assets["stream/prop_box.ydr"] = drawable or Ydr(version=165)
    assets["stream/demo_props.ytyp"] = ytyp
    return BuildContext(assets=assets)


def _write_cutscene_prop_assets(directory: Path) -> None:
    mesh = YdrMeshInput(
        positions=[Vector3(), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0)],
        indices=[0, 1, 2],
        material="default",
        texcoords=[[Vector2(), Vector2(1.0, 0.0), Vector2(0.0, 1.0)]],
    )
    create_ydr(meshes=[mesh], name="prop_box").save(directory / "prop_box.ydr")
    ytyp = Ytyp(name="demo_props")
    ytyp.archetype("prop_box")
    ytyp.save(directory / "demo_props.ytyp")


def test_cutscene_asset_validation_is_non_mutating() -> None:
    assets = _cutscene_prop_project().build()

    report = assets.validate(context=_cutscene_prop_context())

    assert report.valid
    assert assets.scene.animation_dictionary is not None
    assert assets.scene.animation_dictionary.sections


def test_cutscene_asset_validation_reports_missing_context_dependencies() -> None:
    assets = _cutscene_prop_project().build()

    report = assets.validate(context=BuildContext(assets=AssetSet()))

    assert {issue.code for issue in report.errors} == {
        "cut.binding.model.unresolved",
        "cut.binding.ytyp.unresolved",
    }


def test_cutscene_asset_validation_rejects_invalid_decoded_model() -> None:
    context = _cutscene_prop_context()
    context.assets.replace("stream/prop_box.ydr", object())

    report = _cutscene_prop_project().build().validate(context=context)

    assert any(issue.code == "cut.binding.model.invalid" for issue in report.errors)


def test_cutscene_asset_validation_checks_animation_bones() -> None:
    skeleton = YdrSkeleton()
    skeleton.bone("root", tag=0)
    assets = _cutscene_prop_project(bones={42: {"position": Vector3()}}).build()

    report = assets.validate(
        context=_cutscene_prop_context(Ydr(version=165, skeleton=skeleton))
    )

    issue = next(
        issue
        for issue in report.errors
        if issue.code == "cut.binding.skeleton.bone_unresolved"
    )
    assert issue.path == "bindings[2].animation.bones[42]"


def test_cutscene_asset_validation_resolves_serialized_loose_assets(tmp_path) -> None:
    _write_cutscene_prop_assets(tmp_path)
    context = BuildContext(assets=AssetSet.from_directory(tmp_path))

    report = _cutscene_prop_project().build().validate(context=context)

    assert report.valid


def test_cutscene_asset_validation_resolves_loose_ycd() -> None:
    authored = _cutscene_prop_project().build()
    context = _cutscene_prop_context()
    assert authored.scene.animation_dictionary is not None
    for ycd in authored.scene.animation_dictionary.sections:
        context.assets[f"stream/{ycd.path}"] = ycd

    report = CutsceneAssets(authored.scene).validate(context=context)

    assert report.valid


def test_cutscene_asset_validation_resolves_game_file_cache(tmp_path) -> None:
    _write_cutscene_prop_assets(tmp_path)

    with GameFileCache(tmp_path, use_index_cache=False) as cache:
        cache.scan(load_keys=False)
        report = (
            _cutscene_prop_project().build().validate(context=BuildContext(cache=cache))
        )

    assert report.valid
