from __future__ import annotations

import pytest

from fivefury import (
    CutAnimatedLight,
    CutAnimatedParticleEffect,
    CutBlockingBounds,
    CutEventObject,
    CutLightEffectPayload,
    CutParticleEffect,
    CutPlayParticleEffectPayload,
    CutRayfire,
    CutRemovalBounds,
    CutScene,
    CutVehicleExtraPayload,
    CutVehicleVariationPayload,
    CutWeapon,
    build_cut_bytes,
    read_cut,
    scene_to_cut,
)
from fivefury.cut.names import CUT_NAME_VALUES
from fivefury.cut.schema import BUILTIN_CUT_STRUCTS


def test_cut_scene_writes_complete_object_model_without_template() -> None:
    scene = CutScene.create(duration=5.0)

    weapon = CutWeapon("weapon_stream")
    weapon.cutscene_name = "weapon_actor"
    weapon.generic_weapon_type = 3
    scene.binding(weapon)

    animated_light = CutAnimatedLight("animated_light")
    animated_light.anim_streaming_base = 7
    scene.binding(animated_light)

    particle = CutParticleEffect("particle_stream")
    particle.cutscene_name = "particle_actor"
    particle.effect_list = "core"
    scene.binding(particle)

    animated_particle = CutAnimatedParticleEffect("animated_particle_stream")
    animated_particle.cutscene_name = "animated_particle_actor"
    animated_particle.anim_streaming_base = 12
    animated_particle.effect_list = "scr_rcbarry2"
    scene.binding(animated_particle)

    blocking = CutBlockingBounds("blocking")
    blocking.corners = ((-1.0, -2.0, 0.0), (1.0, -2.0, 0.0), (1.0, 2.0, 0.0), (-1.0, 2.0, 0.0))
    blocking.height = 4.5
    scene.binding(blocking)

    removal = CutRemovalBounds("removal")
    removal.corners = ((-3.0, -4.0, 1.0), (3.0, -4.0, 1.0), (3.0, 4.0, 1.0), (-3.0, 4.0, 1.0))
    removal.height = 8.0
    scene.binding(removal)

    rayfire = CutRayfire("rayfire_stream")
    rayfire.cutscene_name = "rayfire_actor"
    rayfire.start_position = (10.0, 20.0, 30.0)
    scene.binding(rayfire)
    scene.binding(CutEventObject())

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    objects = {node.type_name: node for node in rebuilt.objects}

    assert objects["rage__cutfWeaponModelObject"].fields["GenericWeaponType"] == 3
    assert objects["rage__cutfAnimatedLightObject"].fields["AnimStreamingBase"] == 7
    assert objects["rage__cutfParticleEffectObject"].fields["athFxListHash"].hash != 0
    assert objects["rage__cutfAnimatedParticleEffectObject"].fields["AnimStreamingBase"] == 12
    assert objects["rage__cutfBlockingBoundsObject"].fields["vCorners"] == [
        pytest.approx(corner) for corner in blocking.corners
    ]
    assert objects["rage__cutfBlockingBoundsObject"].fields["fHeight"] == pytest.approx(4.5)
    assert objects["rage__cutfRemovalBoundsObject"].fields["vCorners"] == [
        pytest.approx(corner) for corner in removal.corners
    ]
    assert objects["rage__cutfRayfireObject"].fields["vStartPosition"] == pytest.approx((10.0, 20.0, 30.0))
    assert objects["rage__cutfEventObject"].fields["iObjectId"] >= 0


def test_cut_scene_writes_vehicle_variation_layouts_without_template() -> None:
    scene = CutScene.create(duration=5.0)
    vehicle = scene.vehicle("vehicle")
    scene.set_variation(
        0.0,
        vehicle,
        CutVehicleVariationPayload(
            vehicle.object_id,
            main_body_colour=1,
            second_body_colour=2,
            specular_colour=3,
            wheel_trim_colour=4,
            body_colour_5=5,
            livery=6,
            livery_2=7,
            dirt_level=0.25,
        ),
    )
    scene.set_variation(1.0, vehicle, CutVehicleExtraPayload(vehicle.object_id, [11, 12]))

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    args = {node.type_name: node.fields for node in rebuilt.event_args}

    variation = args["rage__cutfVehicleVariationEventArgs"]
    assert variation["iMainBodyColour"] == 1
    assert variation["iBodyColour5"] == 5
    assert variation["iLivery"] == 6
    assert variation["iLivery2"] == 7
    assert variation["fDirtLevel"] == pytest.approx(0.25)
    assert args["rage__cutfVehicleExtraEventArgs"]["pExtraBoneIds"] == [11, 12]


def test_cut_builtin_vehicle_variation_uses_current_runtime_layout() -> None:
    schema = BUILTIN_CUT_STRUCTS[CUT_NAME_VALUES["rage__cutfVehicleVariationEventArgs"]]
    fields = {entry.name_hash: entry.data_offset for entry in schema.entries}

    assert schema.length == 72
    assert fields[CUT_NAME_VALUES["iBodyColour5"]] == 56
    assert fields[CUT_NAME_VALUES["iLivery2"]] == 64
    assert fields[CUT_NAME_VALUES["fDirtLevel"]] == 68


def test_cut_animation_validation_accepts_runtime_animatable_objects() -> None:
    scene = CutScene.create(duration=1.0)
    manager = scene.animation_manager()
    weapon = scene.binding(CutWeapon("weapon"))
    weapon.anim_streaming_base = 1
    light = scene.binding(CutAnimatedLight("light"))
    light.anim_streaming_base = 2
    particle = scene.binding(CutAnimatedParticleEffect("particle"))
    particle.anim_streaming_base = 3
    for binding in (weapon, light, particle):
        scene.set_anim(0.0, binding, target=manager)

    codes = {issue.code for issue in scene.validate(strict=False).errors}

    assert "set_anim.object.invalid" not in codes


def test_cut_animation_validation_rejects_static_particle_objects() -> None:
    scene = CutScene.create(duration=1.0)
    manager = scene.animation_manager()
    particle = scene.binding(CutParticleEffect("particle"))
    scene.set_anim(0.0, particle, target=manager)

    codes = {issue.code for issue in scene.validate(strict=False).errors}

    assert "set_anim.object.invalid" in codes


def test_cut_particle_and_attached_light_payloads_roundtrip() -> None:
    scene = CutScene.create(duration=2.0)
    particle = scene.binding(CutParticleEffect("particle"))
    light = scene.binding(CutAnimatedLight("light"))
    play_payload = CutPlayParticleEffectPayload(
        initial_bone_offset=(1.0, 2.0, 3.0),
        attach_parent_id=4,
        attach_bone_hash=5,
    )
    stop_payload = CutPlayParticleEffectPayload(
        initial_bone_offset=(6.0, 7.0, 8.0),
        attach_parent_id=9,
        attach_bone_hash=10,
    )
    scene.play_particle_effect(0.0, particle, play_payload)
    scene.stop_particle_effect(0.5, particle, stop_payload)
    scene.set_light(
        1.0,
        light,
        CutLightEffectPayload(
            attach_parent_id=11,
            attach_bone_hash=12,
            attached_parent_name="parent",
        ),
    )
    scene.set_light(1.5, light)

    rebuilt = read_cut(build_cut_bytes(scene_to_cut(scene)))
    events = list(rebuilt.iter_resolved_events())
    by_time = {event.event.fields["fTime"]: event for event in events}

    assert by_time[0.0].event_args is not None
    assert by_time[0.0].event_args.type_name == "rage__cutfPlayParticleEffectEventArgs"
    assert by_time[0.0].event_args.fields["iAttachParentId"] == 4
    assert by_time[0.5].event_args is not None
    assert by_time[0.5].event_args.type_name == "rage__cutfPlayParticleEffectEventArgs"
    assert by_time[0.5].event_args.fields["iAttachParentId"] == 9
    assert by_time[1.0].event_args is not None
    assert by_time[1.0].event_args.type_name == "rage__cutfTriggerLightEffectEventArgs"
    assert by_time[1.0].event_args.fields["iAttachParentId"] == 11
    assert by_time[1.5].event_args is None
