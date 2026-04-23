from __future__ import annotations

from math import isclose
from pathlib import Path

import pytest

from fivefury.hashing import jenk_hash
from fivefury import (
    CutCascadeShadowPayload,
    CutDecalPayload,
    CutFile,
    CutHashedString,
    CutFinalNamePayload,
    CutHashFloatPayload,
    CutPlayParticleEffectPayload,
    CutPropAnimationPreset,
    CutTypeFileStrategy,
    CutScreenFadePayload,
    CutScene,
    GameFileType,
    analyze_cut,
    build_cut_bytes,
    get_cut_event_name,
    read_cut,
    read_cut_scene,
    read_cutxml,
    scene_to_cut,
)
from fivefury.gamefile import guess_game_file_type


TESTS_DIR = Path(__file__).resolve().parent
CUT_PATH = TESTS_DIR / "mp_int_mcs_18_a1.cut"
CUTXML_PATH = TESTS_DIR / "mp_int_mcs_18_a1.cutxml"
LAMAR_CUT_PATH = TESTS_DIR.parent / "references" / "lamar_1_int.cut"
EF_CUT_PATH = TESTS_DIR / "ef_1_rcm.cut"
MAUDE_CUT_PATH = TESTS_DIR / "maude_mcs_1.cut"


pytestmark = pytest.mark.skipif(not CUT_PATH.is_file() or not CUTXML_PATH.is_file(), reason="cut samples not available")


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


def test_read_cutxml_smoke() -> None:
    cutxml = read_cutxml(CUTXML_PATH)

    assert cutxml.root.type_name == "rage__cutfCutsceneFile2"
    assert _counts(cutxml) == {
        "objects": 11,
        "load_events": 6,
        "events": 32,
        "event_args": 26,
        "concat": 1,
        "discard": 1,
    }


def test_read_cut_matches_cutxml_shape() -> None:
    cut = read_cut(CUT_PATH)
    cutxml = read_cutxml(CUTXML_PATH)

    assert cut.root.type_name == cutxml.root.type_name
    assert isclose(cut.root.fields["fTotalDuration"], 64.36666870117188, rel_tol=0.0, abs_tol=1e-6)
    assert cut.root.fields["cFaceDir"] == r"x:/gta5/assets_ng\cuts\MP_INT_MCS_18_A1\faces"
    assert _counts(cut) == _counts(cutxml)
    assert cut.root.fields["pCutsceneObjects"][0].type_name == cutxml.root.fields["pCutsceneObjects"][0].type_name
    assert cut.root.fields["concatDataList"][0].fields["cSceneName"] == CutHashedString(hash=972297886)


def test_cut_game_file_type_mapping() -> None:
    assert guess_game_file_type("foo.cut") is GameFileType.CUT
    assert guess_game_file_type("foo.cutxml") is GameFileType.CUT


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


def test_cut_roundtrip_binary_writer() -> None:
    cut = read_cut(CUT_PATH)
    cut.root.fields["fTotalDuration"] = 12.5
    cut.root.fields["cFaceDir"] = r"x:/gta5/assets_ng\cuts\TEST\faces"

    rebuilt = read_cut(build_cut_bytes(cut))

    assert isclose(rebuilt.root.fields["fTotalDuration"], 12.5, rel_tol=0.0, abs_tol=1e-6)
    assert rebuilt.root.fields["cFaceDir"] == r"x:/gta5/assets_ng\cuts\TEST\faces"
    assert _counts(rebuilt) == _counts(cut)
    assert rebuilt.root.fields["pCutsceneObjects"][0].type_name == cut.root.fields["pCutsceneObjects"][0].type_name


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
    asset_manager = scene.add_asset_manager()
    camera = scene.add_camera("cam_orbit")
    actor = scene.add_ped("ped_sphere")
    subtitle = scene.add_subtitle("subtitle_track")

    scene.create_event("load_scene", start=0.0, target=asset_manager)
    scene.create_event("load_models", start=0.0, target=asset_manager, payload={"iObjectIdList": [actor.object_id]})
    scene.create_event("camera_cut", start=0.0, target=camera, label="cam_orbit")
    scene.create_event("show_subtitle", start=0.0, target=subtitle, label="hola amigos", duration=15.0, payload={"iLanguageID": 0})

    cut = scene_to_cut(scene)
    rebuilt = read_cut(build_cut_bytes(cut, template=CUT_PATH))

    assert rebuilt.root.fields["fTotalDuration"] == pytest.approx(15.0)
    assert rebuilt.root.fields["cFaceDir"] == "x:/gta5/assets_ng/cuts/test/faces"
    assert len(rebuilt.objects) == 4
    assert len(rebuilt.load_events) == 2
    assert len(rebuilt.events) == 2
    assert len(rebuilt.event_args) == 4


def test_cut_scene_builder_supports_real_asset_group_and_overlay_events() -> None:
    scene = CutScene.create(duration=20.0, face_dir="x:/gta5/assets_ng/cuts/test_plus/faces")
    asset_manager = scene.add_asset_manager()
    overlay = scene.add_object("overlay", name="overlay_track")
    particle_fx = scene.add_object("rage__cutfParticleEffectObject", name="core_fx")

    scene.load_scene(0.0, payload={"cName": "test_plus"})
    scene.load_particle_effects(0.0, [particle_fx], target=asset_manager)
    scene.load_overlays(0.0, [overlay], target=asset_manager)
    scene.load_subtitles(0.0, CutFinalNamePayload("TEST_PLUS"), target=asset_manager)
    scene.show_overlay(0.0, overlay)
    scene.hide_overlay(1.0, overlay)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene), template=MAUDE_CUT_PATH))

    assert rebuilt.root.fields["fTotalDuration"] == pytest.approx(20.0)
    assert len(rebuilt.load_events) == 4
    assert len(rebuilt.events) == 2
    assert any(event.fields["iEventId"] == 8 for event in rebuilt.load_events)  # load_particle_effects
    assert any(event.fields["iEventId"] == 10 for event in rebuilt.load_events)  # load_overlays
    assert any(event.fields["iEventId"] == 12 for event in rebuilt.load_events)  # load_subtitles
    assert any(event.fields["iEventId"] == 26 for event in rebuilt.events)  # show_overlay
    assert any(event.fields["iEventId"] == 27 for event in rebuilt.events)  # hide_overlay
    load_fx_args = next(rebuilt.get_event_args(event.fields["iEventArgsIndex"]) for event in rebuilt.load_events if event.fields["iEventId"] == 8)
    load_overlay_args = next(rebuilt.get_event_args(event.fields["iEventArgsIndex"]) for event in rebuilt.load_events if event.fields["iEventId"] == 10)
    subtitle_args = next(rebuilt.get_event_args(event.fields["iEventArgsIndex"]) for event in rebuilt.load_events if event.fields["iEventId"] == 12)
    show_overlay_args = next(rebuilt.get_event_args(event.fields["iEventArgsIndex"]) for event in rebuilt.events if event.fields["iEventId"] == 26)
    hide_overlay_event = next(event for event in rebuilt.events if event.fields["iEventId"] == 27)
    assert load_fx_args is not None and load_fx_args.type_name == "rage__cutfObjectIdListEventArgs"
    assert load_fx_args.fields["iObjectIdList"] == [particle_fx.object_id]
    assert load_overlay_args is not None and load_overlay_args.type_name == "rage__cutfObjectIdListEventArgs"
    assert load_overlay_args.fields["iObjectIdList"] == [overlay.object_id]
    assert subtitle_args is not None and subtitle_args.type_name == "rage__cutfFinalNameEventArgs"
    assert subtitle_args.fields["cName"] == "TEST_PLUS"
    assert show_overlay_args is not None and show_overlay_args.type_name == "rage__cutfEventArgs"
    assert hide_overlay_event.fields["iEventArgsIndex"] == -1


def test_cut_scene_builder_supports_variation_events_with_real_template() -> None:
    scene = CutScene.create(duration=8.0, face_dir="x:/gta5/assets_ng/cuts/test_variation/faces")
    asset_manager = scene.add_asset_manager()
    ped = scene.add_ped("ped_plus")

    scene.load_scene(0.0, payload={"cName": "test_variation"})
    scene.load_models(0.0, [ped.object_id], target=asset_manager)
    scene.set_variation(0.0, ped, component=3, drawable=1, texture=2)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene), template=LAMAR_CUT_PATH))

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


def test_cut_scene_builder_supports_camera_and_blocking_events_with_real_templates() -> None:
    scene = CutScene.create(duration=12.0, face_dir="x:/gta5/assets_ng/cuts/test_fx/faces")
    asset_manager = scene.add_asset_manager()
    camera = scene.add_camera("cam_fx")
    hidden = scene.add_object("hidden_object", name="hidden_target")
    bounds = scene.add_object("blocking_bounds", name="blocker")

    scene.load_scene(0.0, payload={"cName": "test_fx"})
    scene.load_models(0.0, [hidden.object_id, bounds.object_id], target=asset_manager)
    scene.add_blocking_bounds(0.0, bounds)
    scene.hide_objects(0.0, hidden)
    scene.enable_dof(0.0, camera)
    scene.enable_cascade_shadow_bounds(
        0.0,
        camera,
        CutCascadeShadowPayload(
            camera_cut_hash="cam_fx",
            position=(1.0, 2.0, 3.0),
            radius=5.0,
            interp_time=0.25,
            cascade_index=2,
            enabled=True,
            interpolate_to_disabled=False,
        ),
    )
    scene.cascade_shadows_set_dynamic_depth_value(0.5, camera, 0.75)
    scene.blendout_camera(1.0, camera)
    scene.first_person_blendout_camera(2.0, camera, CutHashFloatPayload(1.0))

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene), template=LAMAR_CUT_PATH))

    event_ids = [event.fields["iEventId"] for event in rebuilt.events]
    assert 18 in event_ids  # add_blocking_bounds
    assert 14 in event_ids  # hide_objects
    assert 48 in event_ids  # enable_dof
    assert 54 in event_ids  # enable_cascade_shadow_bounds
    assert 73 in event_ids  # cascade_shadows_set_dynamic_depth_value
    assert 51 in event_ids  # blendout_camera
    assert 79 in event_ids  # first_person_blendout_camera

    cascade_event = next(event for event in rebuilt.events if event.fields["iEventId"] == 54)
    cascade_args = rebuilt.get_event_args(cascade_event.fields["iEventArgsIndex"])
    assert cascade_args is not None
    assert cascade_args.type_name == "rage__cutfCascadeShadowEventArgs"
    assert cascade_args.fields["cameraCutHashTag"].hash == jenk_hash("cam_fx")
    assert cascade_args.fields["position"] == pytest.approx((1.0, 2.0, 3.0))
    assert cascade_args.fields["radius"] == pytest.approx(5.0)
    assert cascade_args.fields["interpTimeTag"] == pytest.approx(0.25)
    assert cascade_args.fields["cascadeIndexTag"] == 2
    assert cascade_args.fields["enabled"] is True
    assert cascade_args.fields["interpolateToDisabledTag"] is False

    depth_event = next(event for event in rebuilt.events if event.fields["iEventId"] == 73)
    depth_args = rebuilt.get_event_args(depth_event.fields["iEventArgsIndex"])
    assert depth_args is not None
    assert depth_args.type_name == "hash_5FF00EA5"
    assert depth_args.fields["hash_0BD8B46C"] == pytest.approx(0.75)


def test_cut_scene_builder_supports_decal_light_and_hidden_object_events() -> None:
    scene = CutScene.create(duration=6.0, face_dir="x:/gta5/assets_ng/cuts/test_decal/faces")
    decal = scene.add_decal("blood_mark")
    light = scene.add_light("fx_light")
    hidden = scene.add_object("hidden_object", name="hidden_target", fields={"vPosition": (0.0, 0.0, 0.0), "fRadius": 1.5})

    scene.trigger_decal(
        0.0,
        decal,
        CutDecalPayload(
            position=(1.0, 2.0, 3.0),
            rotation=(0.0, 0.0, 0.0, 1.0),
            width=0.75,
            height=1.25,
            colour=0xFFAA5500,
            lifetime=10.0,
        ),
    )
    scene.remove_decal(1.0, decal)
    scene.set_light(0.0, light)
    scene.clear_light(2.0, light)
    scene.hide_hidden_object(0.0, hidden)
    scene.show_hidden_object(1.0, hidden)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene), template=MAUDE_CUT_PATH))

    event_names = [get_cut_event_name(event.fields["iEventId"]) for event in rebuilt.events]
    assert "trigger_decal" in event_names
    assert "remove_decal" in event_names
    assert "set_light" in event_names
    assert "clear_light" in event_names
    assert "hide_hidden_object" in event_names
    assert "show_hidden_object" in event_names

    trigger_decal_event = next(event for event in rebuilt.events if get_cut_event_name(event.fields["iEventId"]) == "trigger_decal")
    decal_args = rebuilt.get_event_args(trigger_decal_event.fields["iEventArgsIndex"])
    assert decal_args is not None
    assert decal_args.type_name == "rage__cutfDecalEventArgs"
    assert decal_args.fields["vPosition"] == pytest.approx((1.0, 2.0, 3.0))
    assert decal_args.fields["fWidth"] == pytest.approx(0.75)
    assert decal_args.fields["fHeight"] == pytest.approx(1.25)
    assert decal_args.fields["Colour"] == 0xFFAA5500
    assert decal_args.fields["fLifeTime"] == pytest.approx(10.0)


def test_cut_prop_binding_exposes_real_streaming_fields() -> None:
    scene = CutScene.create(duration=4.0, face_dir="x:/gta5/assets_ng/cuts/test_prop/faces")
    prop = scene.add_prop(
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

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene), template=MAUDE_CUT_PATH))
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


def test_cut_prop_binding_supports_clear_aliases_for_real_fields() -> None:
    scene = CutScene.create(duration=1.0)
    prop = scene.add_prop(
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
    prop = scene.add_prop(
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
    prop = CutScene.create().add_prop(model_name="prop_test", animation_preset=preset)
    assert prop.fields["cAnimExportCtrlSpecFile"].hash == expected_export
    assert prop.fields["cFaceExportCtrlSpecFile"].hash == 0
    assert prop.fields["cAnimCompressionFile"].hash == expected_comp


def test_cut_prop_can_be_built_from_runtime_sources_with_explicit_ytyp() -> None:
    scene = CutScene.create(duration=1.0)
    prop = scene.add_prop(
        model=r"update/x64/dlcpacks/mpchristmas2018/dlc.rpf/x64/levels/gta5/props/prop_arena_cutscene.rpf/xs_prop_arena_clipboard_01a.ydr",
        ytyp=r"update/x64/dlcpacks/mpchristmas2018/dlc.rpf/x64/levels/gta5/props/prop_arena_cutscene.rpf/xs_prop_arena_cutscene.ytyp",
        scene_name="clipboard_local",
    )

    assert prop.model_name == "xs_prop_arena_clipboard_01a"
    assert prop.ytyp_name == "xs_prop_arena_cutscene"
    assert prop.scene_name == "clipboard_local"


def test_cut_prop_runtime_source_auto_falls_back_to_container_stem() -> None:
    scene = CutScene.create(duration=1.0)
    prop = scene.add_prop_from_runtime_asset(
        model=r"update/x64/dlcpacks/mpgunrunning/dlc.rpf/x64/levels/gta5/props/prop_gr_crates.rpf/gr_prop_gr_torque_wrench_01a.ydr",
        scene_name="wrench_local",
    )

    assert prop.model_name == "gr_prop_gr_torque_wrench_01a"
    assert prop.type_file == "prop_gr_crates"
    assert prop.scene_name == "wrench_local"


def test_cut_prop_runtime_source_can_disable_type_file_inference() -> None:
    prop = CutScene.create().add_prop(
        model=r"x64c.rpf/levels/gta5/props/lev_des/lev_des.rpf/prop_npc_phone.ydr",
        type_file_strategy=CutTypeFileStrategy.NONE,
    )

    assert prop.model_name == "prop_npc_phone"
    assert prop.type_file is None
