from __future__ import annotations

from math import isclose
from pathlib import Path

import pytest

from fivefury import (
    CutFile,
    CutHashedString,
    CutPlayParticleEffectPayload,
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


def test_cut_scene_builder_supports_overlay_and_load_name_events() -> None:
    scene = CutScene.create(duration=20.0, face_dir="x:/gta5/assets_ng/cuts/test_plus/faces")
    asset_manager = scene.add_asset_manager()
    overlay = scene.add_object("overlay", name="overlay_track")

    scene.load_scene(0.0, payload={"cName": "test_plus"})
    scene.load_particle_effects(0.0, "core_fx", target=asset_manager)
    scene.load_overlays(0.0, "ui_overlays", target=asset_manager)
    scene.show_overlay(0.0, overlay, "overlay_track")
    scene.hide_overlay(1.0, overlay, "overlay_track")

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene), template=MAUDE_CUT_PATH))

    assert rebuilt.root.fields["fTotalDuration"] == pytest.approx(20.0)
    assert len(rebuilt.load_events) == 3
    assert len(rebuilt.events) == 2
    assert any(event.fields["iEventId"] == 8 for event in rebuilt.load_events)  # load_particle_effects
    assert any(event.fields["iEventId"] == 10 for event in rebuilt.load_events)  # load_overlays
    assert any(event.fields["iEventId"] == 26 for event in rebuilt.events)  # show_overlay
    assert any(event.fields["iEventId"] == 27 for event in rebuilt.events)  # hide_overlay


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
