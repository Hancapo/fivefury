from __future__ import annotations

import pytest

from fivefury import (
    CutAssetManager,
    CutCamera,
    CutCameraCutPayload,
    CutEventBehavior,
    CutLoadScenePayload,
    CutPed,
    CutScene,
    CutSubtitle,
    CutSubtitlePayload,
    build_cut_bytes,
    read_cut,
    scene_to_cut,
)


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
