from __future__ import annotations

import pytest

from fivefury import CutScene, build_cut_bytes, read_cut, scene_to_cut


def test_cut_scene_builder_writes_without_template() -> None:
    scene = CutScene.create(duration=15.0, face_dir="x:/gta5/assets_ng/cuts/test/faces")
    asset_manager = scene.add_asset_manager()
    camera = scene.add_camera("cam_orbit")
    actor = scene.add_ped("ped_sphere")
    subtitle = scene.add_subtitle("subtitle_track")

    scene.create_event("load_scene", start=0.0, target=asset_manager, payload={"cName": "intro_scene"})
    scene.create_event("load_models", start=0.0, target=asset_manager, payload={"iObjectIdList": [actor.object_id]})
    scene.create_event("camera_cut", start=0.0, target=camera, label="cam_orbit")
    scene.create_event("show_subtitle", start=0.0, target=subtitle, label="hola amigos", duration=15.0, payload={"iLanguageID": 0})

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))

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
