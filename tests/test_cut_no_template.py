from __future__ import annotations

import pytest

from fivefury import (
    CutAssetManager,
    CutAnimationManager,
    CutCamera,
    CutCameraCutPayload,
    CutEventBehavior,
    CutEventType,
    CutLoadScenePayload,
    CutPed,
    CutProp,
    CutPropAnimationPreset,
    CutScene,
    CutSubtitle,
    CutSubtitlePayload,
    build_cut_bytes,
    read_cut,
    scene_to_cut,
)
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


def test_cut_scene_normalizes_retail_prop_startup_order() -> None:
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
        int(CutEventType.LOAD_ANIM_DICT),
        int(CutEventType.LOAD_MODELS),
    ]
    assert [(event.fields["fTime"], event.fields["iEventId"]) for event in rebuilt.events[:2]] == [
        (0.0, int(CutEventType.SET_ANIM)),
        (0.0, int(CutEventType.CAMERA_CUT)),
    ]
    rebuilt_prop = next(node for node in rebuilt.objects if node.type_name == "rage__cutfPropModelObject")
    assert rebuilt_prop.fields["cHandle"].hash == 0
