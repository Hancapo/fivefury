from __future__ import annotations

from math import isclose
from pathlib import Path

import pytest

from fivefury import (
    CutCameraCutPayload,
    CutCascadeShadowPayload,
    CutConcatMode,
    CutDecalPayload,
    CutEventType,
    CutFile,
    CutFinalNamePayload,
    CutFloatValuePayload,
    CutHashedString,
    CutLightFlag,
    CutLightProperty,
    CutLightType,
    CutLoadScenePayload,
    CutPropAnimationPreset,
    CutScene,
    CutsceneAnimationDictionary,
    CutSceneFlags,
    CutSceneSettings,
    CutSectioningMode,
    CutTypeFileStrategy,
    GameFileType,
    Quaternion,
    Vector3,
    YcdCutsceneBuilder,
    YdrLight,
    analyze_cut,
    build_cut_bytes,
    derive_cutscene_flags,
    get_cut_event_name,
    read_cut,
    read_cut_scene,
    scene_to_cut,
)
from fivefury.cut.events import CUT_EVENT_ID_TO_NAME, get_cut_event_spec
from fivefury.gamefile import guess_game_file_type
from fivefury.hashing import jenk_hash, jenk_partial_hash
from tests.helpers import reference_root

CUT_REFERENCE_DIR = reference_root() / "cut"
CUT_PATH = CUT_REFERENCE_DIR / "mp_int_mcs_18_a1.cut"
LAMAR_CUT_PATH = CUT_REFERENCE_DIR / "lamar_1_int.cut"
EF_CUT_PATH = CUT_REFERENCE_DIR / "ef_1_rcm.cut"


requires_cut = pytest.mark.skipif(
    not CUT_PATH.is_file(), reason="binary CUT sample not available"
)


def _counts(cut: CutFile) -> dict[str, int]:
    root = cut.root.fields
    return {
        "objects": len(root["pCutsceneObjects"]),
        "load_events": len(root["pCutsceneLoadEventList"]),
        "events": len(root["pCutsceneEventList"]),
        "event_args": len(root["pCutsceneEventArgsList"]),
        "concat": len(root["concatDataList"]),
        "discard": len(root["discardFrameList"]),
    }


@requires_cut
def test_read_cut_real_asset_shape() -> None:
    cut = read_cut(CUT_PATH)

    assert cut.root.type_name == "rage__cutfCutsceneFile2"
    assert isclose(
        cut.root.fields["fTotalDuration"], 64.36666870117188, rel_tol=0.0, abs_tol=1e-6
    )
    assert (
        cut.root.fields["cFaceDir"] == r"x:/gta5/assets_ng\cuts\MP_INT_MCS_18_A1\faces"
    )
    assert _counts(cut) == {
        "objects": 11,
        "load_events": 6,
        "events": 32,
        "event_args": 26,
        "concat": 1,
        "discard": 1,
    }
    assert cut.root.fields["concatDataList"][0].fields["cSceneName"] == CutHashedString(
        hash=972297886
    )


def test_cut_game_file_type_mapping() -> None:
    assert guess_game_file_type("foo.cut") is GameFileType.CUT
    assert guess_game_file_type("foo.cutxml") is GameFileType.UNKNOWN


@requires_cut
def test_cut_summary_and_resolution() -> None:
    cut = read_cut(CUT_PATH)
    summary = analyze_cut(cut)
    first_event = next(cut.iter_resolved_events(include_load_events=False))

    assert summary.root_type == "rage__cutfCutsceneFile2"
    assert summary.object_types["rage__cutfLightObject"] == 4
    assert summary.event_arg_types["rage__cutfSubtitleEventArgs"] == 16
    assert first_event.event.type_name == "rage__cutfObjectIdEvent"
    assert first_event.object is not None
    assert first_event.object.type_name == "rage__cutfAnimationManagerObject"
    assert first_event.event_args is not None
    assert first_event.event_args.type_name == "rage__cutfObjectIdEventArgs"


@requires_cut
def test_cut_roundtrip_binary_writer() -> None:
    cut = read_cut(CUT_PATH)
    cut.root.fields["fTotalDuration"] = 12.5
    cut.root.fields["cFaceDir"] = r"x:/gta5/assets_ng\cuts\TEST\faces"

    rebuilt = read_cut(build_cut_bytes(cut))

    assert isclose(
        rebuilt.root.fields["fTotalDuration"], 12.5, rel_tol=0.0, abs_tol=1e-6
    )
    assert rebuilt.root.fields["cFaceDir"] == r"x:/gta5/assets_ng\cuts\TEST\faces"
    assert _counts(rebuilt) == _counts(cut)
    assert (
        rebuilt.root.fields["pCutsceneObjects"][0].type_name
        == cut.root.fields["pCutsceneObjects"][0].type_name
    )


@pytest.mark.parametrize("path", [CUT_PATH, EF_CUT_PATH, LAMAR_CUT_PATH])
def test_cut_roundtrip_preserves_complex_real_templates(path: Path) -> None:
    if not path.is_file():
        pytest.skip(f"cut sample not available: {path.name}")
    cut = read_cut(path)

    rebuilt = read_cut(build_cut_bytes(cut, template=cut))

    assert rebuilt.root.type_name == cut.root.type_name
    assert _counts(rebuilt) == _counts(cut)
    assert len(rebuilt.objects) == len(cut.objects)
    assert len(rebuilt.events) == len(cut.events)
    assert len(rebuilt.event_args) == len(cut.event_args)


@requires_cut
def test_cut_scene_abstraction_reads_like_timeline() -> None:
    scene = read_cut_scene(CUT_PATH)

    assert scene.duration == pytest.approx(64.36666870117188)
    assert len(scene.cameras) == 1
    assert len(scene.actors) == 1
    assert len(scene.peds) == 1
    assert len(scene.entities) == 1
    assert len(scene.lights) == 4
    assert len(scene.audio) == 1
    assert len(scene.subtitles) == 1
    assert scene.camera_track is not None
    assert scene.subtitle_track is not None
    assert scene.load_track is not None
    assert scene.camera_track.events[0].event_name == "camera_cut"
    assert any(track.kind == "camera_cut" for track in scene.tracks)
    assert any(track.kind == "subtitle" for track in scene.tracks)
    assert scene.timeline[0].start == pytest.approx(0.0)


@requires_cut
def test_cut_scene_roundtrip() -> None:
    scene = read_cut_scene(CUT_PATH)
    scene.duration = 33.0
    scene.cameras[0].name = "cam_test"
    scene.timeline[0].start = 1.25

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

    assert rebuilt.root.fields["fTotalDuration"] == pytest.approx(33.0)
    assert _counts(rebuilt) == _counts(scene.raw)


def test_cut_event_name_lookup() -> None:
    assert get_cut_event_name(0) == "load_scene"
    assert get_cut_event_name(30) == "show_subtitle"
    assert get_cut_event_name(43) == "camera_cut"
    assert get_cut_event_name(74) == "set_light"


def test_cut_scene_builder_from_scratch() -> None:
    scene = CutScene.create(duration=15.0, face_dir="x:/gta5/assets_ng/cuts/test/faces")
    asset_manager = scene.asset_manager()
    camera = scene.camera("cam_orbit")
    actor = scene.ped("ped_sphere")
    subtitle = scene.subtitle("subtitle_track")

    scene.event("load_scene", start=0.0, target=asset_manager)
    scene.event(
        "load_models",
        start=0.0,
        target=asset_manager,
        payload={"iObjectIdList": [actor.object_id]},
    )
    scene.event("camera_cut", start=0.0, target=camera, label="cam_orbit")
    scene.event(
        "show_subtitle",
        start=0.0,
        target=subtitle,
        label="hola amigos",
        duration=15.0,
        payload={"iLanguageID": 0},
    )

    cut = scene_to_cut(scene)
    rebuilt = read_cut(build_cut_bytes(cut))

    assert rebuilt.root.fields["fTotalDuration"] == pytest.approx(15.0)
    assert rebuilt.root.fields["cFaceDir"] == "x:/gta5/assets_ng/cuts/test/faces"
    assert len(rebuilt.objects) == 4
    assert len(rebuilt.load_events) == 2
    assert len(rebuilt.events) == 2
    assert len(rebuilt.event_args) == 4


def test_cut_scene_builder_defaults_to_playable_root_metadata() -> None:
    scene = CutScene.create(scene_name="sample_scene", duration=2.5)
    asset_manager = scene.asset_manager()
    camera = scene.camera("cam_main")

    scene.load_scene(0.0, payload={"cName": "sample_scene"}, target=asset_manager)
    scene.event("camera_cut", start=1.0, target=camera, label="cam_main")

    cut = scene_to_cut(scene)
    root = cut.root.fields
    flags = CutSceneFlags(root["iCutsceneFlags"][0])

    assert root["cFaceDir"] == "x:/gta5/assets_ng/cuts/SAMPLE_SCENE/faces"
    assert root["iRangeStart"] == 0
    assert root["iRangeEnd"] == 75
    assert root["iAltRangeEnd"] == 0
    assert root["fSectionByTimeSliceDuration"] == pytest.approx(4.0)
    assert root["cameraCutList"] == []
    assert len(root["concatDataList"]) == 1
    assert root["concatDataList"][0].fields["cSceneName"].hash == jenk_hash(
        "sample_scene"
    )
    load_scene = next(
        event
        for event in cut.load_events
        if event.fields["iEventId"] == int(CutEventType.LOAD_SCENE)
    )
    load_scene_args = cut.event_args[load_scene.fields["iEventArgsIndex"]]
    assert load_scene_args.fields["cName"].hash == 0
    assert flags & CutSceneFlags.IS_SECTIONED
    assert not flags & CutSceneFlags.USE_ONE_AUDIO
    assert flags & CutSceneFlags.USE_STORY_MODE
    assert flags & CutSceneFlags.USE_IN_GAME_DOF_START
    assert flags & CutSceneFlags.EXTERNAL_CONCAT
    assert not flags & CutSceneFlags.INTERNAL_CONCAT
    assert not flags & CutSceneFlags.SECTION_BY_CAMERA_CUTS

    rebuilt = read_cut(build_cut_bytes(cut))
    rebuilt_flags = CutSceneFlags(rebuilt.root.fields["iCutsceneFlags"][0])

    assert rebuilt.root.fields["iCutsceneFlags"] == root["iCutsceneFlags"]
    assert rebuilt_flags & CutSceneFlags.IS_SECTIONED
    assert not rebuilt_flags & CutSceneFlags.SECTION_BY_CAMERA_CUTS


def test_cut_scene_builder_propagates_relocation_offset() -> None:
    scene = CutScene.create(
        scene_name="offset_scene", duration=2.5, offset=Vector3(10.0, 20.0, 100.0)
    )
    asset_manager = scene.asset_manager()

    scene.load_scene(0.0, payload={"cName": "offset_scene"}, target=asset_manager)

    cut = scene_to_cut(scene)
    root = cut.root.fields
    load_scene = next(
        event
        for event in cut.load_events
        if event.fields["iEventId"] == int(CutEventType.LOAD_SCENE)
    )
    load_scene_args = cut.event_args[load_scene.fields["iEventArgsIndex"]]

    assert root["vOffset"] == Vector3(10.0, 20.0, 100.0)
    assert root["vTriggerOffset"] == Vector3()
    assert root["concatDataList"][0].fields["vOffset"] == Vector3(10.0, 20.0, 100.0)
    assert load_scene_args.fields["vOffset"] == Vector3(10.0, 20.0, 100.0)


def test_cut_scene_builder_only_sections_by_camera_cuts_when_explicit() -> None:
    scene = CutScene.create(
        scene_name="sample_scene", duration=2.5, camera_cut_list=[1.0]
    )
    asset_manager = scene.asset_manager()
    camera = scene.camera("cam_main")

    scene.load_scene(0.0, payload={"cName": "sample_scene"}, target=asset_manager)
    scene.event("camera_cut", start=1.0, target=camera, label="cam_main")

    cut = scene_to_cut(scene)
    root = cut.root.fields
    flags = CutSceneFlags(root["iCutsceneFlags"][0])

    assert root["cameraCutList"] == [1.0]
    assert flags & CutSceneFlags.SECTION_BY_CAMERA_CUTS


def test_cut_scene_builder_keeps_explicit_streaming_cuts_separate_from_shots() -> None:
    scene = CutScene.create(
        scene_name="sample_scene",
        duration=6.0,
        camera_cut_list=[2.0, 4.0],
    )
    camera = scene.camera("exportcamera")
    scene.camera_cut(1.0, camera, CutCameraCutPayload("shot_0"))
    scene.camera_cut(3.0, camera, CutCameraCutPayload("shot_1"))

    cut = scene_to_cut(scene)

    assert cut.root.fields["cameraCutList"] == [2.0, 4.0]


def test_cut_scene_builder_derives_observable_flags() -> None:
    scene = CutScene.create(scene_name="sample_scene", duration=2.5)
    scene.audio("dialogue")
    scene.camera_cut_list = [1.0]
    scene.blend_out_cutscene_duration = 15

    flags = derive_cutscene_flags(scene)

    assert flags & CutSceneFlags.USE_ONE_AUDIO
    assert flags & CutSceneFlags.SECTION_BY_CAMERA_CUTS
    assert flags & CutSceneFlags.USE_BLENDOUT_CAMERA


def test_cut_scene_builder_concat_mode_is_explicit_and_not_prop_dependent() -> None:
    scene = CutScene.create(
        scene_name="sample_scene",
        duration=2.5,
        settings=CutSceneSettings(concat=CutConcatMode.INTERNAL),
    )
    scene.prop("prop_a")

    flags = derive_cutscene_flags(scene)

    assert flags & CutSceneFlags.INTERNAL_CONCAT
    assert not flags & CutSceneFlags.EXTERNAL_CONCAT


def test_cut_scene_settings_reproduce_every_serialized_flag() -> None:
    for index in range(32):
        expected = CutSceneFlags(1 << index)
        scene = CutScene.create(
            duration=2.5,
            settings=CutSceneSettings.from_flags(expected),
        )

        assert derive_cutscene_flags(scene) == expected

    expected = CutSceneFlags(0xFFFFFFFF)
    scene = CutScene.create(
        duration=2.5,
        settings=CutSceneSettings.from_flags(expected),
    )

    assert derive_cutscene_flags(scene) == expected


def test_cut_scene_settings_preserve_root_fade_metadata() -> None:
    scene = CutScene.create(
        duration=2.5,
        settings=CutSceneSettings(
            fade_in_game=True,
            fade_out_cutscene=True,
            sectioning=CutSectioningMode.NONE,
        ),
    )
    scene.fade_in_game_duration = 1.25
    scene.fade_out_cutscene_duration = 0.5
    scene.fade_in_color = 0xFF102030
    scene.fade_out_color = 0xFF405060

    rebuilt = read_cut_scene(build_cut_bytes(scene_to_cut(scene)))

    assert rebuilt.settings.fade_in_game
    assert rebuilt.settings.fade_out_cutscene
    assert rebuilt.fade_in_game_duration == pytest.approx(1.25)
    assert rebuilt.fade_out_cutscene_duration == pytest.approx(0.5)
    assert rebuilt.fade_in_color == 0xFF102030
    assert rebuilt.fade_out_color == 0xFF405060


def test_cut_scene_builder_preserves_authored_loader_order() -> None:
    scene = CutScene.create(scene_name="sample_scene", duration=2.5)
    asset_manager = scene.asset_manager()
    animation_manager = scene.animation_manager()
    prop = scene.prop("prop_a")

    scene.load_anim_dict(0.0, "sample_scene", target=animation_manager)
    scene.load_scene(0.0, payload={"cName": "sample_scene"}, target=asset_manager)
    scene.load_models(0.0, [prop.object_id], target=asset_manager)

    cut = scene_to_cut(scene)

    assert [event.fields["iEventId"] for event in cut.load_events] == [
        int(CutEventType.LOAD_ANIM_DICT),
        int(CutEventType.LOAD_SCENE),
        int(CutEventType.LOAD_MODELS),
    ]


def test_cut_scene_builder_preserves_authored_simultaneous_event_order() -> None:
    scene = CutScene.create(scene_name="sample_scene", duration=2.5)
    animation_manager = scene.animation_manager()
    camera = scene.camera("cam_main")
    prop = scene.prop("prop_a")

    scene.event("camera_cut", start=0.0, target=camera, label="cam_main")
    scene.set_anim(0.0, prop, target=animation_manager)

    cut = scene_to_cut(scene)

    assert [event.fields["iEventId"] for event in cut.events[:2]] == [
        int(CutEventType.CAMERA_CUT),
        int(CutEventType.SET_ANIM),
    ]


def test_cut_scene_builder_supports_real_asset_group_and_overlay_events() -> None:
    scene = CutScene.create(
        duration=20.0, face_dir="x:/gta5/assets_ng/cuts/test_plus/faces"
    )
    asset_manager = scene.asset_manager()
    overlay = scene.object("overlay", name="overlay_track")
    particle_fx = scene.object("rage__cutfParticleEffectObject", name="core_fx")

    scene.load_scene(0.0, payload={"cName": "test_plus"})
    scene.load_particle_effects(0.0, [particle_fx], target=asset_manager)
    scene.load_overlays(0.0, [overlay], target=asset_manager)
    scene.load_subtitles(0.0, CutFinalNamePayload("TEST_PLUS"), target=asset_manager)
    scene.show_overlay(0.0, overlay)
    scene.hide_overlay(1.0, overlay)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

    assert rebuilt.root.fields["fTotalDuration"] == pytest.approx(20.0)
    assert len(rebuilt.load_events) == 4
    assert len(rebuilt.events) == 2
    assert any(
        event.fields["iEventId"] == 8 for event in rebuilt.load_events
    )  # load_particle_effects
    assert any(
        event.fields["iEventId"] == 10 for event in rebuilt.load_events
    )  # load_overlays
    assert any(
        event.fields["iEventId"] == 12 for event in rebuilt.load_events
    )  # load_subtitles
    assert any(
        event.fields["iEventId"] == 26 for event in rebuilt.events
    )  # show_overlay
    assert any(
        event.fields["iEventId"] == 27 for event in rebuilt.events
    )  # hide_overlay
    load_fx_args = next(
        rebuilt.get_event_args(event.fields["iEventArgsIndex"])
        for event in rebuilt.load_events
        if event.fields["iEventId"] == 8
    )
    load_overlay_args = next(
        rebuilt.get_event_args(event.fields["iEventArgsIndex"])
        for event in rebuilt.load_events
        if event.fields["iEventId"] == 10
    )
    subtitle_args = next(
        rebuilt.get_event_args(event.fields["iEventArgsIndex"])
        for event in rebuilt.load_events
        if event.fields["iEventId"] == 12
    )
    show_overlay_args = next(
        rebuilt.get_event_args(event.fields["iEventArgsIndex"])
        for event in rebuilt.events
        if event.fields["iEventId"] == 26
    )
    hide_overlay_event = next(
        event for event in rebuilt.events if event.fields["iEventId"] == 27
    )
    assert (
        load_fx_args is not None
        and load_fx_args.type_name == "rage__cutfObjectIdListEventArgs"
    )
    assert load_fx_args.fields["iObjectIdList"] == [particle_fx.object_id]
    assert (
        load_overlay_args is not None
        and load_overlay_args.type_name == "rage__cutfObjectIdListEventArgs"
    )
    assert load_overlay_args.fields["iObjectIdList"] == [overlay.object_id]
    assert (
        subtitle_args is not None
        and subtitle_args.type_name == "rage__cutfFinalNameEventArgs"
    )
    assert subtitle_args.fields["cName"] == "TEST_PLUS"
    assert (
        show_overlay_args is not None
        and show_overlay_args.type_name == "rage__cutfEventArgs"
    )
    assert hide_overlay_event.fields["iEventArgsIndex"] == -1


def test_cut_scene_builder_supports_variation_events_with_real_template() -> None:
    scene = CutScene.create(
        duration=8.0, face_dir="x:/gta5/assets_ng/cuts/test_variation/faces"
    )
    asset_manager = scene.asset_manager()
    ped = scene.ped("ped_plus")

    scene.load_scene(0.0, payload={"cName": "test_variation"})
    scene.load_models(0.0, [ped.object_id], target=asset_manager)
    scene.set_variation(0.0, ped, component=3, drawable=1, texture=2)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

    assert len(rebuilt.load_events) == 2
    assert len(rebuilt.events) == 1
    assert rebuilt.events[0].fields["iEventId"] == 34
    args = rebuilt.get_event_args(rebuilt.events[0].fields["iEventArgsIndex"])
    assert args is not None
    assert args.type_name == "rage__cutfObjectVariationEventArgs"
    assert args.fields["iObjectId"] == ped.object_id
    assert args.fields["iComponent"] == 3
    assert args.fields["iDrawable"] == 1
    assert args.fields["iTexture"] == 2


@pytest.mark.skipif(
    not LAMAR_CUT_PATH.is_file(), reason="blocking-bounds CUT template not available"
)
def test_cut_scene_builder_supports_camera_and_blocking_events_with_real_templates() -> (
    None
):
    scene = CutScene.create(
        duration=12.0, face_dir="x:/gta5/assets_ng/cuts/test_fx/faces"
    )
    asset_manager = scene.asset_manager()
    camera = scene.camera("cam_fx")
    hidden = scene.object("hidden_object", name="hidden_target")
    bounds = scene.object("blocking_bounds", name="blocker")

    scene.load_scene(0.0, payload={"cName": "test_fx"})
    scene.load_models(0.0, [hidden.object_id, bounds.object_id], target=asset_manager)
    scene.install_blocking_bounds(0.0, bounds)
    scene.hide_objects(0.0, hidden)
    scene.enable_dof(0.0, camera)
    scene.enable_cascade_shadow_bounds(
        0.0,
        camera,
        CutCascadeShadowPayload(
            camera_cut_hash="cam_fx",
            position=Vector3(1.0, 2.0, 3.0),
            radius=5.0,
            interp_time=0.25,
            cascade_index=2,
            enabled=True,
            interpolate_to_disabled=False,
        ),
    )
    scene.cascade_shadows_set_dynamic_depth_value(0.5, camera, 0.75)
    scene.blendout_camera(1.0, camera)
    scene.first_person_blendout_camera(2.0, camera, CutFloatValuePayload(1.0))

    rebuilt = read_cut(
        build_cut_bytes(scene_to_cut(scene), template=read_cut(LAMAR_CUT_PATH))
    )

    event_ids = [event.fields["iEventId"] for event in rebuilt.events]
    assert 18 in event_ids  # add_blocking_bounds
    assert 14 in event_ids  # hide_objects
    assert 48 in event_ids  # enable_dof
    assert 54 in event_ids  # enable_cascade_shadow_bounds
    assert 73 in event_ids  # cascade_shadows_set_dynamic_depth_value
    assert 51 in event_ids  # blendout_camera
    assert 79 in event_ids  # first_person_blendout_camera

    cascade_event = next(
        event for event in rebuilt.events if event.fields["iEventId"] == 54
    )
    cascade_args = rebuilt.get_event_args(cascade_event.fields["iEventArgsIndex"])
    assert cascade_args is not None
    assert cascade_args.type_name == "rage__cutfCascadeShadowEventArgs"
    assert cascade_args.fields["cameraCutHashName"].hash == jenk_hash("cam_fx")
    assert cascade_args.fields["position"] == Vector3(1.0, 2.0, 3.0)
    assert cascade_args.fields["radius"] == pytest.approx(5.0)
    assert cascade_args.fields["interpTime"] == pytest.approx(0.25)
    assert cascade_args.fields["cascadeIndex"] == 2
    assert cascade_args.fields["enabled"] is True
    assert cascade_args.fields["interpolateToDisabled"] is False

    depth_event = next(
        event for event in rebuilt.events if event.fields["iEventId"] == 73
    )
    depth_args = rebuilt.get_event_args(depth_event.fields["iEventArgsIndex"])
    assert depth_args is not None
    assert depth_args.type_name == "rage__cutfFloatValueEventArgs"
    assert depth_args.fields["fValue"] == pytest.approx(0.75)


def test_cut_scene_builder_supports_decal_light_and_hidden_object_events() -> None:
    scene = CutScene.create(
        duration=6.0, face_dir="x:/gta5/assets_ng/cuts/test_decal/faces"
    )
    decal = scene.decal("blood_mark")
    light = scene.light("fx_light")
    hidden = scene.object(
        "hidden_object",
        name="hidden_target",
        fields={"vPosition": Vector3(), "fRadius": 1.5},
    )

    decal_payload = CutDecalPayload(
        position=Vector3(1.0, 2.0, 3.0),
        rotation=Quaternion(),
        width=0.75,
        height=1.25,
        colour=0xFFAA5500,
        lifetime=10.0,
    )
    scene.trigger_decal(0.0, decal, decal_payload)
    scene.remove_decal(1.0, decal, decal_payload)
    scene.set_light(0.0, light)
    scene.clear_light(2.0, light)
    scene.hide_hidden_object(0.0, hidden)
    scene.show_hidden_object(1.0, hidden)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

    event_names = [
        get_cut_event_name(event.fields["iEventId"]) for event in rebuilt.events
    ]
    assert "trigger_decal" in event_names
    assert "remove_decal" in event_names
    assert "set_light" in event_names
    assert "clear_light" in event_names
    assert "hide_hidden_object" in event_names
    assert "show_hidden_object" in event_names

    trigger_decal_event = next(
        event
        for event in rebuilt.events
        if get_cut_event_name(event.fields["iEventId"]) == "trigger_decal"
    )
    decal_args = rebuilt.get_event_args(trigger_decal_event.fields["iEventArgsIndex"])
    assert decal_args is not None
    assert decal_args.type_name == "rage__cutfDecalEventArgs"
    assert decal_args.fields["vPosition"] == Vector3(1.0, 2.0, 3.0)
    assert decal_args.fields["fWidth"] == pytest.approx(0.75)
    remove_decal_event = next(
        event
        for event in rebuilt.events
        if get_cut_event_name(event.fields["iEventId"]) == "remove_decal"
    )
    remove_decal_args = rebuilt.get_event_args(
        remove_decal_event.fields["iEventArgsIndex"]
    )
    assert remove_decal_args is not None
    assert remove_decal_args.type_name == "rage__cutfDecalEventArgs"
    assert decal_args.fields["fHeight"] == pytest.approx(1.25)
    assert decal_args.fields["Colour"] == 0xFFAA5500
    assert decal_args.fields["fLifeTime"] == pytest.approx(10.0)


def test_cut_scene_can_materialize_ydr_embedded_lights() -> None:
    scene = CutScene.create(
        duration=2.0, face_dir="x:/gta5/assets_ng/cuts/test_lights/faces"
    )
    ydr = type(
        "FakeYdr",
        (),
        {
            "lights": [
                YdrLight.spot(
                    position=Vector3(1.0, 2.0, 3.0),
                    direction=Vector3(0.0, 0.0, -1.0),
                    color=(255, 128, 0),
                    intensity=5.0,
                    falloff=40.0,
                    cone_inner_angle=25.0,
                    cone_outer_angle=55.0,
                    flags=(1 << 7) | (1 << 8) | (1 << 12) | (1 << 23),
                    volume_intensity=1.0,
                    volume_size_scale=1.0,
                    corona_intensity=1.0,
                    corona_z_bias=0.1,
                    falloff_exponent=2.0,
                    time_flags=0xFFFFFF,
                )
            ]
        },
    )()

    lights = scene.ensure_ydr_embedded_lights(ydr, name_prefix="stage01")

    assert len(lights) == 1
    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    cut_light = next(
        obj for obj in rebuilt.objects if obj.type_name == "rage__cutfLightObject"
    )
    assert cut_light.fields["iLightType"] == int(CutLightType.SPOT)
    assert cut_light.fields["iLightProperty"] == int(CutLightProperty.CASTS_SHADOWS)
    assert cut_light.fields["uLightFlags"] == int(
        CutLightFlag.CAST_STATIC_GEOM_SHADOWS
        | CutLightFlag.CAST_DYNAMIC_GEOM_SHADOWS
        | CutLightFlag.DRAW_VOLUME
        | CutLightFlag.DONT_LIGHT_ALPHA
    )
    colour = cut_light.fields["vColour"]
    assert isinstance(colour, Vector3)
    assert colour.x == pytest.approx(1.0)
    assert colour.y == pytest.approx(128.0 / 255.0)
    assert colour.z == pytest.approx(0.0)
    assert cut_light.fields["vPosition"] == Vector3(1.0, 2.0, 3.0)
    assert cut_light.fields["fFallOff"] == pytest.approx(40.0)
    assert any(
        event.fields["iEventId"] == 74
        and event.fields["iObjectId"] == cut_light.fields["iObjectId"]
        for event in rebuilt.events
    )


def test_cut_prop_binding_exposes_real_streaming_fields() -> None:
    scene = CutScene.create(
        duration=4.0, face_dir="x:/gta5/assets_ng/cuts/test_prop/faces"
    )
    prop = scene.prop(
        "prop_stream",
        cutscene_name="prop_local",
        anim_streaming_base=0x1234,
        anim_export_ctrl_spec_file="anim_ctrl",
        face_export_ctrl_spec_file="face_ctrl",
        anim_compression_file="anim_comp",
        handle="prop_handle",
        type_file="prop_type",
    )

    assert prop.streaming_name == "prop_stream"
    assert prop.cutscene_name == "prop_local"
    assert prop.anim_streaming_base == 0x1234
    assert prop.anim_export_ctrl_spec_file == "anim_ctrl"
    assert prop.face_export_ctrl_spec_file == "face_ctrl"
    assert prop.anim_compression_file == "anim_comp"
    assert prop.handle == "prop_handle"
    assert prop.type_file == "prop_type"

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    rebuilt_prop = rebuilt.objects[0]

    assert rebuilt_prop.type_name == "rage__cutfPropModelObject"
    assert rebuilt_prop.fields["StreamingName"].hash == jenk_hash("prop_stream")
    assert rebuilt_prop.fields["cName"].hash == jenk_hash("prop_local")
    assert rebuilt_prop.fields["AnimStreamingBase"] == 0x1234
    assert rebuilt_prop.fields["cAnimExportCtrlSpecFile"].hash == jenk_hash("anim_ctrl")
    assert rebuilt_prop.fields["cFaceExportCtrlSpecFile"].hash == jenk_hash("face_ctrl")
    assert rebuilt_prop.fields["cAnimCompressionFile"].hash == jenk_hash("anim_comp")
    assert rebuilt_prop.fields["cHandle"].hash == jenk_hash("prop_handle")
    assert rebuilt_prop.fields["typeFile"].hash == jenk_hash("prop_type")

    roundtrip_scene = read_cut_scene(scene_to_cut(scene))
    roundtrip_prop = roundtrip_scene.props[0]
    assert roundtrip_prop.streaming_name == "prop_stream"
    assert roundtrip_prop.cutscene_name == "prop_local"
    assert roundtrip_prop.anim_streaming_base == 0x1234
    assert roundtrip_prop.anim_export_ctrl_spec_file == "anim_ctrl"
    assert roundtrip_prop.face_export_ctrl_spec_file == "face_ctrl"
    assert roundtrip_prop.anim_compression_file == "anim_comp"
    assert roundtrip_prop.handle == "prop_handle"
    assert roundtrip_prop.type_file == "prop_type"


def test_cut_ped_does_not_require_type_file() -> None:
    scene = CutScene.create(duration=4.0)
    scene.ped("cs_test")

    issues = scene.validate(strict=True)

    assert not [issue for issue in issues if issue.code == "object.type_file.missing"]
    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    ped = next(
        obj for obj in rebuilt.objects if obj.type_name == "rage__cutfPedModelObject"
    )
    assert ped.fields["typeFile"].hash == 0


def test_cut_prop_binding_supports_clear_aliases_for_real_fields() -> None:
    scene = CutScene.create(duration=1.0)
    prop = scene.prop(
        model_name="prop_npc_phone",
        scene_name="phone_local",
        animation_streaming_base=0xE99D162E,
        animation_export_spec_file="anim_ctrl",
        face_animation_export_spec_file="face_ctrl",
        animation_compression_filename="anim_comp",
        object_handle="phone_handle",
        ytyp_name="xm4_props_phone",
    )

    assert prop.model_name == "prop_npc_phone"
    assert prop.streaming_name == "prop_npc_phone"
    assert prop.scene_name == "phone_local"
    assert prop.cutscene_name == "phone_local"
    assert prop.animation_streaming_base == 0xE99D162E
    assert prop.animation_export_spec_file == "anim_ctrl"
    assert prop.face_animation_export_spec_file == "face_ctrl"
    assert prop.animation_compression_filename == "anim_comp"
    assert prop.object_handle == "phone_handle"
    assert prop.ytyp_name == "xm4_props_phone"


def test_cut_prop_animation_presets_are_selectable() -> None:
    scene = CutScene.create(duration=1.0)
    prop = scene.prop(
        model_name="prop_npc_phone",
        animation_preset=CutPropAnimationPreset.COMMON_PROP,
    )

    assert prop.anim_export_ctrl_spec_file == "0x7097694E"
    assert prop.face_export_ctrl_spec_file == "0x00000000"
    assert prop.anim_compression_file == "0x47FB8D46"
    assert prop.fields["cAnimExportCtrlSpecFile"].hash == 1888971086
    assert prop.fields["cFaceExportCtrlSpecFile"].hash == 0
    assert prop.fields["cAnimCompressionFile"].hash == 1207668038

    prop.apply_animation_preset(CutPropAnimationPreset.NONE)
    assert "cAnimExportCtrlSpecFile" not in prop.fields
    assert "cFaceExportCtrlSpecFile" not in prop.fields
    assert "cAnimCompressionFile" not in prop.fields


def test_cut_prop_animation_clip_base_defaults_to_model_name() -> None:
    prop = CutScene.create().prop(
        name="mmd_model_001",
        model=r"assets/miku_hatsune_metal.ydr",
        scene_name="mmd_model_001",
        animation_preset=CutPropAnimationPreset.COMMON_PROP,
    )

    assert prop.model_name == "miku_hatsune_metal"
    assert prop.animation_clip_base == "miku_hatsune_metal"
    assert prop.animation_streaming_base == jenk_partial_hash("miku_hatsune_metal")
    assert prop.animation_streaming_base != jenk_partial_hash("mmd_model_001")


def test_cut_scene_validate_matches_set_anim_against_model_clip_base() -> None:
    scene = CutScene.create(duration=1.0)
    manager = scene.animation_manager()
    prop = scene.prop(
        name="mmd_model_001",
        model=r"assets/miku_hatsune_metal.ydr",
        scene_name="mmd_model_001",
        animation_preset=CutPropAnimationPreset.COMMON_PROP,
    )
    builder = YcdCutsceneBuilder.create("sample", duration=1.0, fps=30.0)
    builder.prop(
        "miku_hatsune_metal",
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
    )
    scene.animation_dictionary = CutsceneAnimationDictionary(
        sections=[builder.build_ycds()[0]]
    )
    scene.set_anim(0.0, prop, target=manager)

    assert not scene.validate_animations()


def test_cut_scene_does_not_reject_unresolved_dictionary_hash() -> None:
    scene = CutScene.create(duration=1.0)
    manager = scene.animation_manager()
    prop = scene.prop(
        name="target",
        model="target.ydr",
        animation_preset=CutPropAnimationPreset.COMMON_PROP,
    )
    builder = YcdCutsceneBuilder.create("sample", duration=1.0)
    builder.prop(
        "target",
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
    )
    scene.animation_dictionary = CutsceneAnimationDictionary(
        reference="0xDEADBEEF",
        sections=[builder.build_ycds()[0]],
    )
    scene.load_anim_dict(0.0, "0xDEADBEEF", target=manager)
    scene.set_anim(0.0, prop, target=manager)

    assert "set_anim.dict.mismatch" not in {
        issue.code for issue in scene.validate(strict=False).errors
    }


def test_cut_scene_validates_set_anim_against_active_technical_segment() -> None:
    scene = CutScene.create(duration=2.0, camera_cut_list=[1.0])
    manager = scene.animation_manager()
    prop = scene.prop(
        name="target",
        model=r"assets/target.ydr",
        scene_name="target",
        animation_preset=CutPropAnimationPreset.COMMON_PROP,
    )

    first = YcdCutsceneBuilder.create("sample", duration=1.0, section_index_start=0)
    first.prop("decoy", mover_position=Vector3(), mover_rotation=Quaternion())
    second = YcdCutsceneBuilder.create("sample", duration=1.0, section_index_start=1)
    second.prop("target", mover_position=Vector3(), mover_rotation=Quaternion())
    scene.animation_dictionary = CutsceneAnimationDictionary(
        sections=[first.build_ycds()[0], second.build_ycds()[0]]
    )
    scene.set_anim(1.0, prop, target=manager)

    assert not scene.validate_animations()
    assert not any(issue.code == "set_anim.clip.missing" for issue in scene.validate())

    scene.timeline[-1].start = 0.0
    assert any(
        "target-0" in issue.message for issue in scene.validate_animations().warnings
    )
    assert any(issue.code == "set_anim.clip.missing" for issue in scene.validate())


def test_cut_scene_validate_warns_on_binding_name_clip_mismatch() -> None:
    scene = CutScene.create(duration=1.0)
    manager = scene.animation_manager()
    prop = scene.prop(
        name="mmd_model_001",
        model=r"assets/miku_hatsune_metal.ydr",
        scene_name="mmd_model_001",
        animation_preset=CutPropAnimationPreset.COMMON_PROP,
    )
    builder = YcdCutsceneBuilder.create("sample", duration=1.0, fps=30.0)
    builder.prop(
        "mmd_model_001",
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
    )
    scene.animation_dictionary = CutsceneAnimationDictionary(
        sections=[builder.build_ycds()[0]]
    )
    scene.set_anim(0.0, prop, target=manager)

    assert any(
        "miku_hatsune_metal-0" in issue.message
        for issue in scene.validate_animations().warnings
    )


@pytest.mark.parametrize(
    ("preset", "expected_export", "expected_comp"),
    [
        (CutPropAnimationPreset.COMMON_PROP_ALT_COMPRESSION, 1888971086, 4002728289),
        (CutPropAnimationPreset.ALT_EXPORT_A, 2678174446, 1207668038),
        (CutPropAnimationPreset.ALT_EXPORT_B, 2700143237, 1207668038),
    ],
)
def test_cut_prop_animation_alternative_presets_match_real_cut_patterns(
    preset: CutPropAnimationPreset,
    expected_export: int,
    expected_comp: int,
) -> None:
    prop = CutScene.create().prop(model_name="prop_test", animation_preset=preset)
    assert prop.fields["cAnimExportCtrlSpecFile"].hash == expected_export
    assert prop.fields["cFaceExportCtrlSpecFile"].hash == 0
    assert prop.fields["cAnimCompressionFile"].hash == expected_comp


def test_cut_prop_can_be_built_from_runtime_sources_with_explicit_ytyp() -> None:
    scene = CutScene.create(duration=1.0)
    prop = scene.prop(
        model=r"update/x64/dlcpacks/mpchristmas2018/dlc.rpf/x64/levels/gta5/props/prop_arena_cutscene.rpf/xs_prop_arena_clipboard_01a.ydr",
        ytyp=r"update/x64/dlcpacks/mpchristmas2018/dlc.rpf/x64/levels/gta5/props/prop_arena_cutscene.rpf/xs_prop_arena_cutscene.ytyp",
        scene_name="clipboard_local",
    )

    assert prop.model_name == "xs_prop_arena_clipboard_01a"
    assert prop.ytyp_name == "xs_prop_arena_cutscene"
    assert prop.scene_name == "clipboard_local"


def test_cut_prop_runtime_source_auto_falls_back_to_container_stem() -> None:
    scene = CutScene.create(duration=1.0)
    prop = scene.prop(
        model=r"update/x64/dlcpacks/mpgunrunning/dlc.rpf/x64/levels/gta5/props/prop_gr_crates.rpf/gr_prop_gr_torque_wrench_01a.ydr",
        scene_name="wrench_local",
    )

    assert prop.model_name == "gr_prop_gr_torque_wrench_01a"
    assert prop.type_file == "prop_gr_crates"
    assert prop.scene_name == "wrench_local"


def test_cut_prop_runtime_source_can_disable_type_file_inference() -> None:
    prop = CutScene.create().prop(
        model=r"x64c.rpf/levels/gta5/props/lev_des/lev_des.rpf/prop_npc_phone.ydr",
        type_file_strategy=CutTypeFileStrategy.NONE,
    )

    assert prop.model_name == "prop_npc_phone"
    assert prop.type_file is None


def test_cut_all_event_ids_have_serializable_specs() -> None:
    scene = CutScene.create(scene_name="all_events_smoke", duration=1.0)
    scene.asset_manager()
    scene.animation_manager()
    scene.camera("camera")
    scene.fade("fade")
    scene.light("light")
    scene.object("subtitle", name="subtitle")
    scene.prop("prop", model_name="prop")

    missing_specs = [
        name
        for name in CUT_EVENT_ID_TO_NAME.values()
        if get_cut_event_spec(name) is None
    ]
    assert missing_specs == []

    for name in CUT_EVENT_ID_TO_NAME.values():
        if name == "load_scene":
            scene.load_scene(0.0, CutLoadScenePayload("all_events_smoke"))
        elif name == "unload_scene":
            scene.unload_scene(0.0, CutLoadScenePayload("all_events_smoke"))
        else:
            scene.event(name, start=0.0)

    summary = read_cut(build_cut_bytes(scene_to_cut(scene))).summary()
    assert summary.load_event_count + summary.event_count == len(CUT_EVENT_ID_TO_NAME)
