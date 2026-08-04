from __future__ import annotations

import pytest

from fivefury import (
    CutAnimationManager,
    CutAssetManager,
    CutCamera,
    CutCameraCharacterLightPayload,
    CutCameraCutPayload,
    CutCameraDofModifierPayload,
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
    CutSceneValidationError,
    CutSubtitle,
    CutSubtitleCue,
    CutSubtitlePayload,
    build_cut_bytes,
    read_cut,
    scene_to_cut,
    validate_cut_scene,
)
from fivefury.cache.io import _decode_payload
from fivefury.gamefile import GameFileType
from fivefury.hashing import jenk_hash


def test_cut_scene_builder_writes_without_template() -> None:
    scene = CutScene.create(duration=15.0, face_dir="x:/gta5/assets_ng/cuts/test/faces")
    asset_manager = scene.add(CutAssetManager())
    camera = scene.add(CutCamera("cam_orbit"))
    actor = scene.add(CutPed("ped_sphere"))
    subtitle = scene.add(CutSubtitle("subtitle_track"))

    scene.load_scene(0.0, CutLoadScenePayload("intro_scene"), target=asset_manager)
    scene.load_models(0.0, [actor.object_id], target=asset_manager)
    camera_event = scene.camera_cut(0.0, camera, CutCameraCutPayload("cam_orbit"))
    subtitle_event = scene.show_subtitle(0.0, subtitle, CutSubtitlePayload("hola amigos", duration=15.0))

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
    camera_args = next(args for args in rebuilt.event_args if args.type_name == "rage__cutfCameraCutEventArgs")
    assert camera_args.fields["cName"].hash != 0


def test_cut_writer_preserves_fields_after_dynamic_structure_pointer() -> None:
    scene = CutScene.create(duration=5.0)
    asset_manager = scene.add_asset_manager()
    scene.load_scene(0.0, CutLoadScenePayload("nested_attributes"), target=asset_manager)
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
    vehicle = scene.add_vehicle("car", fields={"cRemoveBoneNameList": ["door_dside_f", "wheel_lf"]})

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    rebuilt_vehicle = next(node for node in rebuilt.objects if node.fields["iObjectId"] == vehicle.object_id)

    assert rebuilt_vehicle.fields["cRemoveBoneNameList"] == ["door_dside_f", "wheel_lf"]


def test_cut_decoder_uses_logical_pso_instead_of_stored_archive_bytes() -> None:
    logical = scene_to_cut(CutScene.create(duration=5.0)).to_bytes()

    parsed, kind = _decode_payload("example.cut", logical, raw=b"compressed archive payload")

    assert kind is GameFileType.CUT
    assert parsed.root.type_name == "rage__cutfCutsceneFile2"


def test_cut_scene_save_validation_allows_playable_minimal_scene() -> None:
    scene = CutScene.create(scene_name="playable", duration=5.0)
    asset_manager = scene.add_asset_manager()
    camera = scene.add_camera("cam_main")
    prop = scene.add_prop("prop_a", model_name="prop_a", ytyp_name="prop_pack")

    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.camera_cut(0.0, camera, CutCameraCutPayload("cam_main", near_draw_distance=0.05, far_draw_distance=1000.0))

    rebuilt = read_cut(scene.to_bytes())

    assert rebuilt.root.fields["fTotalDuration"] == pytest.approx(5.0)
    assert any(event.fields["iEventId"] == int(CutEventType.CAMERA_CUT) for event in rebuilt.events)


def test_cut_scene_save_validation_reports_missing_type_file() -> None:
    scene = CutScene.create(scene_name="bad_cut", duration=5.0)
    asset_manager = scene.add_asset_manager()
    camera = scene.add_camera("cam_main")
    prop = scene.add_prop("prop_a", model_name="prop_a")

    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.camera_cut(0.0, camera, CutCameraCutPayload("cam_main", near_draw_distance=0.05, far_draw_distance=1000.0))

    with pytest.raises(CutSceneValidationError) as excinfo:
        scene.to_bytes()

    assert any(issue.code == "object.type_file.missing" for issue in excinfo.value.issues)
    assert "object.type_file.missing" in str(excinfo.value)


def test_cut_scene_save_validation_reports_bad_animation_binding() -> None:
    scene = CutScene.create(scene_name="bad_anim", duration=5.0)
    asset_manager = scene.add_asset_manager()
    animation_manager = scene.add_animation_manager()
    camera = scene.add_camera("cam_main")
    prop = scene.add_prop("prop_a", model_name="prop_a", ytyp_name="prop_pack")

    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.load_anim_dict(0.0, "bad_anim", target=animation_manager)
    scene.set_anim(0.0, prop, target=animation_manager)
    scene.camera_cut(0.0, camera, CutCameraCutPayload("cam_main", near_draw_distance=0.05, far_draw_distance=1000.0))

    with pytest.raises(CutSceneValidationError) as excinfo:
        scene.to_bytes()

    assert any(issue.code == "set_anim.streaming_base.mismatch" for issue in excinfo.value.issues)


def test_cut_scene_installs_subtitle_track_and_gxt2() -> None:
    scene = CutScene.create(duration=6.0)
    asset_manager = scene.add_asset_manager()
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
    assert sum(1 for obj in rebuilt.objects if obj.type_name == "rage__cutfSubtitleObject") == 1
    assert sum(1 for event in rebuilt.load_events if event.fields["iEventId"] == 12) == 1
    show_events = [event for event in rebuilt.events if event.fields["iEventId"] == 30]
    assert len(show_events) == 2
    args = rebuilt.get_event_args(show_events[0].fields["iEventArgsIndex"])
    assert args is not None and args.type_name == "rage__cutfSubtitleEventArgs"
    assert args.fields["iLanguageID"] == -1
    assert args.fields["iTransitionIn"] == -1
    assert args.fields["iTransitionOut"] == -1


def test_cut_scene_load_order_is_stable_with_subtitles() -> None:
    scene = CutScene.create(duration=6.0)
    asset_manager = scene.add_asset_manager()
    animation_manager = scene.add_animation_manager()
    prop = scene.add_prop("prop_a")

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


def test_cut_scene_animation_manager_writes_without_template() -> None:
    scene = CutScene.create(duration=8.0)
    animation_manager = scene.add(CutAnimationManager())
    actor = scene.add(CutPed("ped_actor"))

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
    animation_object = next(node for node in rebuilt.objects if node.type_name == "rage__cutfAnimationManagerObject")
    assert animation_object.fields["iObjectId"] == animation_manager.object_id
    name_args = [args for args in rebuilt.event_args if args.type_name == "rage__cutfNameEventArgs"]
    object_args = [args for args in rebuilt.event_args if args.type_name == "rage__cutfObjectIdEventArgs"]
    assert len(name_args) == 2
    assert len(object_args) == 2
    assert all(args.fields["cName"].hash == jenk_hash("intro_dict") for args in name_args)
    assert all(args.fields["iObjectId"] == actor.object_id for args in object_args)
    assert {event.fields["iEventId"] for event in rebuilt.load_events + rebuilt.events} == {
        int(CutEventType.LOAD_ANIM_DICT),
        int(CutEventType.SET_ANIM),
        int(CutEventType.CLEAR_ANIM),
        int(CutEventType.UNLOAD_ANIM_DICT),
    }


def test_cut_scene_preserves_authored_prop_startup_time() -> None:
    scene = CutScene.create(duration=8.0)
    asset_manager = scene.add(CutAssetManager())
    animation_manager = scene.add(CutAnimationManager())
    camera = scene.add(CutCamera("cam"))
    prop = scene.add(
        CutProp("prop_local").configure_model_asset(
            streaming_name="prop_stream",
            animation_clip_base="prop_stream",
            type_file="prop_pack",
        ).apply_animation_preset(CutPropAnimationPreset.COMMON_PROP)
    )

    scene.load_anim_dict(0.0, "scene-0", target=animation_manager)
    scene.load_scene(0.0, CutLoadScenePayload("scene"), target=asset_manager)
    scene.load_models(0.0, [prop.object_id], target=asset_manager)
    scene.camera_cut(0.0, camera, CutCameraCutPayload("cam"))
    scene.set_anim(1.0 / 240.0, prop, target=animation_manager)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

    assert [event.fields["iEventId"] for event in rebuilt.load_events] == [
        int(CutEventType.LOAD_SCENE),
        int(CutEventType.LOAD_MODELS),
        int(CutEventType.LOAD_ANIM_DICT),
    ]
    assert [(event.fields["fTime"], event.fields["iEventId"]) for event in rebuilt.events[:2]] == [
        (0.0, int(CutEventType.CAMERA_CUT)),
        (pytest.approx(1.0 / 240.0), int(CutEventType.SET_ANIM)),
    ]
    rebuilt_prop = next(node for node in rebuilt.objects if node.type_name == "rage__cutfPropModelObject")
    assert rebuilt_prop.fields["cHandle"].hash == 0


def test_cut_event_args_use_complete_runtime_layouts() -> None:
    scene = CutScene.create(duration=5.0)
    animation_manager = scene.add_animation_manager()
    camera = scene.add_camera("cam")
    parent = scene.add_prop("parent")
    child = scene.add_prop("child")

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
    assert camera_args.fields["CharacterLight"].fields["fIntensity"] == pytest.approx(0.25)
    dof_modifier = camera_args.fields["TimeOfDayDofModifers"][0]
    assert dof_modifier.fields["TimeOfDayFlags"] == 0x3F
    assert dof_modifier.fields["DofStrengthModifier"] == 4


def test_cut_camera_validation_accepts_minus_one_overrides() -> None:
    scene = CutScene.create(duration=1.0)
    camera = scene.add_camera("cam")
    scene.camera_cut(0.0, camera, CutCameraCutPayload("cam"))

    issues = validate_cut_scene(scene, strict=True)

    assert not any(issue.code.startswith("camera_cut.clip") and issue.severity == "error" for issue in issues)
