from __future__ import annotations

from typing import Iterable

from ..events import CutEventType
from ..payloads import (
    CutAnimationDictPayload,
    CutAnimationTargetPayload,
    CutCameraCutPayload,
    CutCascadeShadowPayload,
    CutDecalPayload,
    CutFinalNamePayload,
    CutFloatValuePayload,
    CutHashBoolPayload,
    CutHashFloatPayload,
    CutLoadScenePayload,
    CutNamePayload,
    CutObjectNamePayload,
    CutObjectIdListPayload,
    CutObjectTargetPayload,
    CutObjectVariationPayload,
    CutPlayParticleEffectPayload,
    CutScreenFadePayload,
    CutSubtitlePayload,
)
from .base import CutScene
from .bindings import CutBinding
from .shared import _coerce_object_id, _coerce_object_ids
from .timeline import CutTimelineEvent


def load_scene(self: CutScene, start: float, payload: CutLoadScenePayload, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.LOAD_SCENE, start=start, target=target, payload=payload)


def unload_scene(self: CutScene, start: float, payload: CutLoadScenePayload, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.UNLOAD_SCENE, start=start, target=target, payload=payload)


def load_models(self: CutScene, start: float, object_ids: list[int], *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.LOAD_MODELS, start=start, target=target, payload=CutObjectIdListPayload(object_ids))


def unload_models(self: CutScene, start: float, object_ids: list[int], *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.UNLOAD_MODELS, start=start, target=target, payload=CutObjectIdListPayload(object_ids))


def load_particle_effects(self: CutScene, start: float, particle_effects: Iterable[CutBinding | int], *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.LOAD_PARTICLE_EFFECTS, start=start, target=target, track="load", payload=CutObjectIdListPayload(_coerce_object_ids(particle_effects)))


def unload_particle_effects(self: CutScene, start: float, particle_effects: Iterable[CutBinding | int], *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.UNLOAD_PARTICLE_EFFECTS, start=start, target=target, track="load", payload=CutObjectIdListPayload(_coerce_object_ids(particle_effects)))


def load_overlays(self: CutScene, start: float, overlays: Iterable[CutBinding | int], *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.LOAD_OVERLAYS, start=start, target=target, track="load", payload=CutObjectIdListPayload(_coerce_object_ids(overlays)))


def unload_overlays(self: CutScene, start: float, overlays: Iterable[CutBinding | int], *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.UNLOAD_OVERLAYS, start=start, target=target, track="load", payload=CutObjectIdListPayload(_coerce_object_ids(overlays)))


def load_subtitles(self: CutScene, start: float, name: str | CutFinalNamePayload, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    payload = name if isinstance(name, CutFinalNamePayload) else CutFinalNamePayload(str(name))
    return self.create_event(CutEventType.LOAD_SUBTITLES, start=start, target=target, track="load", payload=payload)


def unload_subtitles(self: CutScene, start: float, name: str | CutFinalNamePayload, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    payload = name if isinstance(name, CutFinalNamePayload) else CutFinalNamePayload(str(name))
    return self.create_event(CutEventType.UNLOAD_SUBTITLES, start=start, target=target, track="load", payload=payload)


def load_anim_dict(self: CutScene, start: float, name: str | CutAnimationDictPayload, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    payload = name if isinstance(name, CutAnimationDictPayload) else CutAnimationDictPayload(str(name))
    return self.create_event(CutEventType.LOAD_ANIM_DICT, start=start, target=target, track="animation_state", payload=payload)


def unload_anim_dict(self: CutScene, start: float, name: str | CutAnimationDictPayload, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    payload = name if isinstance(name, CutAnimationDictPayload) else CutAnimationDictPayload(str(name))
    return self.create_event(CutEventType.UNLOAD_ANIM_DICT, start=start, target=target, track="animation_state", payload=payload)


def load_audio(self: CutScene, start: float, name: str | CutNamePayload, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    payload = name if isinstance(name, CutNamePayload) else CutNamePayload(str(name))
    return self.create_event(CutEventType.LOAD_AUDIO, start=start, target=target, track="audio_cue", payload=payload)


def unload_audio(self: CutScene, start: float, name: str | CutNamePayload, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    payload = name if isinstance(name, CutNamePayload) else CutNamePayload(str(name))
    return self.create_event(CutEventType.UNLOAD_AUDIO, start=start, target=target, track="audio_cue", payload=payload)


def set_anim(self: CutScene, start: float, animated: CutBinding | int, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    object_id = animated.object_id if isinstance(animated, CutBinding) else int(animated)
    return self.create_event(CutEventType.SET_ANIM, start=start, target=target, track="animation_binding", payload=CutAnimationTargetPayload(object_id))


def clear_anim(self: CutScene, start: float, animated: CutBinding | int, *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    object_id = animated.object_id if isinstance(animated, CutBinding) else int(animated)
    return self.create_event(CutEventType.CLEAR_ANIM, start=start, target=target, track="animation_binding", payload=CutAnimationTargetPayload(object_id))


def play_animation(
    self: CutScene,
    start: float,
    animated: CutBinding | int,
    dict_name: str,
    *,
    end: float | None = None,
    target: CutBinding | int | None = None,
) -> list[CutTimelineEvent]:
    events: list[CutTimelineEvent] = [self.load_anim_dict(start, dict_name, target=target), self.set_anim(start, animated, target=target)]
    if end is not None:
        events.append(self.clear_anim(end, animated, target=target))
        events.append(self.unload_anim_dict(end, dict_name, target=target))
    return events


def camera_cut(self: CutScene, start: float, camera: CutBinding | int | None, payload: CutCameraCutPayload) -> CutTimelineEvent:
    return self.create_event(CutEventType.CAMERA_CUT, start=start, target=camera, payload=payload)


def fade_out(self: CutScene, start: float, fade: CutBinding | int | None, payload: CutScreenFadePayload) -> CutTimelineEvent:
    return self.create_event(CutEventType.FADE_OUT, start=start, target=fade, payload=payload)


def fade_in(self: CutScene, start: float, fade: CutBinding | int | None, payload: CutScreenFadePayload) -> CutTimelineEvent:
    return self.create_event(CutEventType.FADE_IN, start=start, target=fade, payload=payload)


def set_draw_distance(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutFloatValuePayload) -> CutTimelineEvent:
    payload = value if isinstance(value, CutFloatValuePayload) else CutFloatValuePayload(float(value))
    return self.create_event(CutEventType.SET_DRAW_DISTANCE, start=start, target=camera, payload=payload)


def hide_objects(self: CutScene, start: float, target: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(target)
    return self.create_event(CutEventType.HIDE_OBJECTS, start=start, target=target, payload=CutObjectTargetPayload(object_id))


def show_objects(self: CutScene, start: float, target: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(target)
    return self.create_event(CutEventType.SHOW_OBJECTS, start=start, target=target, payload=CutObjectTargetPayload(object_id))


def fixup_objects(self: CutScene, start: float, objects: Iterable[CutBinding | int], *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.FIXUP_OBJECTS, start=start, target=target, payload=CutObjectIdListPayload(_coerce_object_ids(objects)))


def revert_fixup_objects(self: CutScene, start: float, objects: Iterable[CutBinding | int], *, target: CutBinding | int | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.REVERT_FIXUP_OBJECTS, start=start, target=target, payload=CutObjectIdListPayload(_coerce_object_ids(objects)))


def set_attachment(self: CutScene, start: float, target: CutBinding | int, name: str) -> CutTimelineEvent:
    object_id = _coerce_object_id(target)
    return self.create_event(CutEventType.SET_ATTACHMENT, start=start, target=target, payload=CutObjectNamePayload(object_id, str(name)))


def add_blocking_bounds(self: CutScene, start: float, bounds: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(bounds)
    return self.create_event(CutEventType.ADD_BLOCKING_BOUNDS, start=start, target=bounds, payload=CutObjectTargetPayload(object_id))


def remove_blocking_bounds(self: CutScene, start: float, bounds: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(bounds)
    return self.create_event(CutEventType.REMOVE_BLOCKING_BOUNDS, start=start, target=bounds, payload=CutObjectTargetPayload(object_id))


def activate_blocking_bounds(self: CutScene, start: float, bounds: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(bounds)
    return self.create_event(CutEventType.ACTIVATE_BLOCKING_BOUNDS, start=start, target=bounds, payload=CutObjectTargetPayload(object_id))


def deactivate_blocking_bounds(self: CutScene, start: float, bounds: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(bounds)
    return self.create_event(CutEventType.DEACTIVATE_BLOCKING_BOUNDS, start=start, target=bounds, payload=CutObjectTargetPayload(object_id))


def fix_fixup_object(self: CutScene, start: float, fixup: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(fixup)
    return self.create_event(CutEventType.FIX_FIXUP_OBJECT, start=start, target=fixup, payload=CutObjectTargetPayload(object_id))


def revert_fixup_object(self: CutScene, start: float, fixup: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(fixup)
    return self.create_event(CutEventType.REVERT_FIXUP_OBJECT, start=start, target=fixup, payload=CutObjectTargetPayload(object_id))


def add_removal_bounds(self: CutScene, start: float, bounds: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(bounds)
    return self.create_event(CutEventType.ADD_REMOVAL_BOUNDS, start=start, target=bounds, payload=CutObjectTargetPayload(object_id))


def remove_removal_bounds(self: CutScene, start: float, bounds: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(bounds)
    return self.create_event(CutEventType.REMOVE_REMOVAL_BOUNDS, start=start, target=bounds, payload=CutObjectTargetPayload(object_id))


def activate_removal_bounds(self: CutScene, start: float, bounds: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(bounds)
    return self.create_event(CutEventType.ACTIVATE_REMOVAL_BOUNDS, start=start, target=bounds, payload=CutObjectTargetPayload(object_id))


def deactivate_removal_bounds(self: CutScene, start: float, bounds: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(bounds)
    return self.create_event(CutEventType.DEACTIVATE_REMOVAL_BOUNDS, start=start, target=bounds, payload=CutObjectTargetPayload(object_id))


def enable_dof(self: CutScene, start: float, camera: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(camera)
    return self.create_event(CutEventType.ENABLE_DOF, start=start, target=camera, payload=CutObjectTargetPayload(object_id))


def disable_dof(self: CutScene, start: float, camera: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(camera)
    return self.create_event(CutEventType.DISABLE_DOF, start=start, target=camera, payload=CutObjectTargetPayload(object_id))


def set_variation(self: CutScene, start: float, target: CutBinding | int, *, component: int, drawable: int, texture: int) -> CutTimelineEvent:
    object_id = target.object_id if isinstance(target, CutBinding) else int(target)
    return self.create_event(
        CutEventType.SET_VARIATION,
        start=start,
        target=target,
        payload=CutObjectVariationPayload(object_id=object_id, component=component, drawable=drawable, texture=texture),
    )


def hide_hidden_object(self: CutScene, start: float, target: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(target)
    return self.create_event(CutEventType.HIDE_HIDDEN_OBJECT, start=start, target=target, payload=CutObjectTargetPayload(object_id))


def show_hidden_object(self: CutScene, start: float, target: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(target)
    return self.create_event(CutEventType.SHOW_HIDDEN_OBJECT, start=start, target=target, payload=CutObjectTargetPayload(object_id))


def show_overlay(self: CutScene, start: float, overlay: CutBinding | int | None) -> CutTimelineEvent:
    return self.create_event(CutEventType.SHOW_OVERLAY, start=start, target=overlay)


def hide_overlay(self: CutScene, start: float, overlay: CutBinding | int | None) -> CutTimelineEvent:
    return self.create_event(CutEventType.HIDE_OVERLAY, start=start, target=overlay)


def blendout_camera(self: CutScene, start: float, camera: CutBinding | int | None) -> CutTimelineEvent:
    return self.create_event(CutEventType.BLENDOUT_CAMERA, start=start, target=camera)


def catchup_camera(self: CutScene, start: float, camera: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(camera)
    return self.create_event(CutEventType.CATCHUP_CAMERA, start=start, target=camera, payload=CutObjectTargetPayload(object_id))


def first_person_blendout_camera(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload = 1.0) -> CutTimelineEvent:
    payload = value if isinstance(value, CutHashFloatPayload) else CutHashFloatPayload(float(value))
    return self.create_event(CutEventType.FIRST_PERSON_BLENDOUT_CAMERA, start=start, target=camera, payload=payload)


def first_person_catchup_camera(self: CutScene, start: float, camera: CutBinding | int) -> CutTimelineEvent:
    object_id = _coerce_object_id(camera)
    return self.create_event(CutEventType.FIRST_PERSON_CATCHUP_CAMERA, start=start, target=camera, payload=CutObjectTargetPayload(object_id))


def enable_cascade_shadow_bounds(self: CutScene, start: float, camera: CutBinding | int | None, payload: CutCascadeShadowPayload) -> CutTimelineEvent:
    return self.create_event(CutEventType.ENABLE_CASCADE_SHADOW_BOUNDS, start=start, target=camera, payload=payload)


def cascade_shadows_bool(self: CutScene, event: str | int | CutEventType, start: float, camera: CutBinding | int | None, enabled: bool) -> CutTimelineEvent:
    return self.create_event(event, start=start, target=camera, payload=CutHashBoolPayload(bool(enabled)))


def cascade_shadows_float(self: CutScene, event: str | int | CutEventType, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    payload = value if isinstance(value, CutHashFloatPayload) else CutHashFloatPayload(float(value))
    return self.create_event(event, start=start, target=camera, payload=payload)


def cascade_shadows_enable_entity_tracker(self: CutScene, start: float, camera: CutBinding | int | None, *, enabled: bool = True) -> CutTimelineEvent:
    return cascade_shadows_bool(self, CutEventType.CASCADE_SHADOWS_ENABLE_ENTITY_TRACKER, start, camera, enabled)


def cascade_shadows_set_world_height_update(self: CutScene, start: float, camera: CutBinding | int | None, *, enabled: bool = True) -> CutTimelineEvent:
    return cascade_shadows_bool(self, CutEventType.CASCADE_SHADOWS_SET_WORLD_HEIGHT_UPDATE, start, camera, enabled)


def cascade_shadows_set_receiver_height_update(self: CutScene, start: float, camera: CutBinding | int | None, *, enabled: bool = True) -> CutTimelineEvent:
    return cascade_shadows_bool(self, CutEventType.CASCADE_SHADOWS_SET_RECEIVER_HEIGHT_UPDATE, start, camera, enabled)


def cascade_shadows_set_aircraft_mode(self: CutScene, start: float, camera: CutBinding | int | None, *, enabled: bool = True) -> CutTimelineEvent:
    return cascade_shadows_bool(self, CutEventType.CASCADE_SHADOWS_SET_AIRCRAFT_MODE, start, camera, enabled)


def cascade_shadows_set_dynamic_depth_value(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    payload = value if isinstance(value, CutHashFloatPayload) else CutHashFloatPayload(float(value))
    return self.create_event(CutEventType.CASCADE_SHADOWS_SET_DYNAMIC_DEPTH_VALUE, start=start, target=camera, payload=payload)


def cascade_shadows_set_dynamic_depth_mode(self: CutScene, start: float, camera: CutBinding | int | None, *, enabled: bool = True) -> CutTimelineEvent:
    return cascade_shadows_bool(self, CutEventType.CASCADE_SHADOWS_SET_DYNAMIC_DEPTH_MODE, start, camera, enabled)


def cascade_shadows_set_fly_camera_mode(self: CutScene, start: float, camera: CutBinding | int | None, *, enabled: bool = True) -> CutTimelineEvent:
    return cascade_shadows_bool(self, CutEventType.CASCADE_SHADOWS_SET_FLY_CAMERA_MODE, start, camera, enabled)


def cascade_shadows_set_cascade_bounds_hfov(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    return cascade_shadows_float(self, CutEventType.CASCADE_SHADOWS_SET_CASCADE_BOUNDS_HFOV, start, camera, value)


def cascade_shadows_set_cascade_bounds_vfov(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    return cascade_shadows_float(self, CutEventType.CASCADE_SHADOWS_SET_CASCADE_BOUNDS_VFOV, start, camera, value)


def cascade_shadows_set_cascade_bounds_scale(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    return cascade_shadows_float(self, CutEventType.CASCADE_SHADOWS_SET_CASCADE_BOUNDS_SCALE, start, camera, value)


def cascade_shadows_set_entity_tracker_scale(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    return cascade_shadows_float(self, CutEventType.CASCADE_SHADOWS_SET_ENTITY_TRACKER_SCALE, start, camera, value)


def cascade_shadows_set_split_z_exp_weight(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    return cascade_shadows_float(self, CutEventType.CASCADE_SHADOWS_SET_SPLIT_Z_EXP_WEIGHT, start, camera, value)


def cascade_shadows_set_dither_radius_scale(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    return cascade_shadows_float(self, CutEventType.CASCADE_SHADOWS_SET_DITHER_RADIUS_SCALE, start, camera, value)


def cascade_shadows_set_depth_bias(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    return cascade_shadows_float(self, CutEventType.CASCADE_SHADOWS_SET_DEPTH_BIAS, start, camera, value)


def cascade_shadows_set_slope_bias(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    return cascade_shadows_float(self, CutEventType.CASCADE_SHADOWS_SET_SLOPE_BIAS, start, camera, value)


def cascade_shadows_set_shadow_sample_type(self: CutScene, start: float, camera: CutBinding | int | None, value: float | CutHashFloatPayload) -> CutTimelineEvent:
    return cascade_shadows_float(self, CutEventType.CASCADE_SHADOWS_SET_SHADOW_SAMPLE_TYPE, start, camera, value)


def cascade_shadows_set_world_height_minmax(self: CutScene, start: float, camera: CutBinding | int | None) -> CutTimelineEvent:
    return self.create_event(CutEventType.CASCADE_SHADOWS_SET_WORLD_HEIGHT_MINMAX, start=start, target=camera)


def cascade_shadows_set_receiver_height_minmax(self: CutScene, start: float, camera: CutBinding | int | None) -> CutTimelineEvent:
    return self.create_event(CutEventType.CASCADE_SHADOWS_SET_RECEIVER_HEIGHT_MINMAX, start=start, target=camera)


def cascade_shadows_reset_cascade_shadows(self: CutScene, start: float, camera: CutBinding | int | None, *, enabled: bool = True) -> CutTimelineEvent:
    return self.create_event(
        CutEventType.CASCADE_SHADOWS_RESET_CASCADE_SHADOWS,
        start=start,
        target=camera,
        payload=CutHashBoolPayload(bool(enabled)),
    )


def reset_adaption(self: CutScene, start: float) -> CutTimelineEvent:
    return self.create_event(CutEventType.RESET_ADAPTION, start=start)


def play_particle_effect(self: CutScene, start: float, particle_fx: CutBinding | int | None, payload: CutPlayParticleEffectPayload | None = None) -> CutTimelineEvent:
    return self.create_event(CutEventType.PLAY_PARTICLE_EFFECT, start=start, target=particle_fx, payload=payload or CutPlayParticleEffectPayload())


def stop_particle_effect(self: CutScene, start: float, particle_fx: CutBinding | int | None) -> CutTimelineEvent:
    return self.create_event(CutEventType.STOP_PARTICLE_EFFECT, start=start, target=particle_fx)


def trigger_decal(self: CutScene, start: float, decal: CutBinding | int | None, payload: CutDecalPayload) -> CutTimelineEvent:
    return self.create_event(CutEventType.TRIGGER_DECAL, start=start, target=decal, payload=payload)


def remove_decal(self: CutScene, start: float, decal: CutBinding | int | None) -> CutTimelineEvent:
    return self.create_event(CutEventType.REMOVE_DECAL, start=start, target=decal)


def set_light(self: CutScene, start: float, light: CutBinding | int | None) -> CutTimelineEvent:
    return self.create_event(CutEventType.SET_LIGHT, start=start, target=light)


def clear_light(self: CutScene, start: float, light: CutBinding | int | None) -> CutTimelineEvent:
    return self.create_event(CutEventType.CLEAR_LIGHT, start=start, target=light)


def show_subtitle(self: CutScene, start: float, subtitle: CutBinding | int | None, payload: CutSubtitlePayload) -> CutTimelineEvent:
    return self.create_event(CutEventType.SHOW_SUBTITLE, start=start, target=subtitle, payload=payload)


def hide_subtitle(self: CutScene, start: float, subtitle: CutBinding | int | None, text: str = "") -> CutTimelineEvent:
    return self.create_event(CutEventType.HIDE_SUBTITLE, start=start, target=subtitle, payload=CutSubtitlePayload(text, duration=0.0))


def play_audio(self: CutScene, start: float, audio: CutBinding | int | None, name: str) -> CutTimelineEvent:
    return self.create_event(CutEventType.PLAY_AUDIO, start=start, target=audio, payload=CutNamePayload(name))


def stop_audio(self: CutScene, start: float, audio: CutBinding | int | None, name: str) -> CutTimelineEvent:
    return self.create_event(CutEventType.STOP_AUDIO, start=start, target=audio, payload=CutNamePayload(name))


def load_rayfire(self: CutScene, start: float, target: CutBinding | int, name: str) -> CutTimelineEvent:
    object_id = _coerce_object_id(target)
    return self.create_event(CutEventType.LOAD_RAYFIRE, start=start, target=target, payload=CutObjectNamePayload(object_id, str(name)))


def unload_rayfire(self: CutScene, start: float, target: CutBinding | int, name: str) -> CutTimelineEvent:
    object_id = _coerce_object_id(target)
    return self.create_event(CutEventType.UNLOAD_RAYFIRE, start=start, target=target, payload=CutObjectNamePayload(object_id, str(name)))


def start_replay_record(self: CutScene, start: float) -> CutTimelineEvent:
    return self.create_event(CutEventType.START_REPLAY_RECORD, start=start)


def stop_replay_record(self: CutScene, start: float) -> CutTimelineEvent:
    return self.create_event(CutEventType.STOP_REPLAY_RECORD, start=start)


for _name in (
    "load_scene",
    "unload_scene",
    "load_models",
    "unload_models",
    "load_particle_effects",
    "unload_particle_effects",
    "load_overlays",
    "unload_overlays",
    "load_subtitles",
    "unload_subtitles",
    "load_anim_dict",
    "unload_anim_dict",
    "load_audio",
    "unload_audio",
    "set_anim",
    "clear_anim",
    "play_animation",
    "camera_cut",
    "fade_out",
    "fade_in",
    "set_draw_distance",
    "hide_objects",
    "show_objects",
    "fixup_objects",
    "revert_fixup_objects",
    "set_attachment",
    "add_blocking_bounds",
    "remove_blocking_bounds",
    "activate_blocking_bounds",
    "deactivate_blocking_bounds",
    "fix_fixup_object",
    "revert_fixup_object",
    "add_removal_bounds",
    "remove_removal_bounds",
    "activate_removal_bounds",
    "deactivate_removal_bounds",
    "enable_dof",
    "disable_dof",
    "set_variation",
    "hide_hidden_object",
    "show_hidden_object",
    "show_overlay",
    "hide_overlay",
    "catchup_camera",
    "blendout_camera",
    "first_person_blendout_camera",
    "first_person_catchup_camera",
    "enable_cascade_shadow_bounds",
    "cascade_shadows_bool",
    "cascade_shadows_float",
    "cascade_shadows_enable_entity_tracker",
    "cascade_shadows_set_world_height_update",
    "cascade_shadows_set_receiver_height_update",
    "cascade_shadows_set_aircraft_mode",
    "cascade_shadows_set_dynamic_depth_mode",
    "cascade_shadows_set_fly_camera_mode",
    "cascade_shadows_set_cascade_bounds_hfov",
    "cascade_shadows_set_cascade_bounds_vfov",
    "cascade_shadows_set_cascade_bounds_scale",
    "cascade_shadows_set_entity_tracker_scale",
    "cascade_shadows_set_split_z_exp_weight",
    "cascade_shadows_set_dither_radius_scale",
    "cascade_shadows_set_world_height_minmax",
    "cascade_shadows_set_receiver_height_minmax",
    "cascade_shadows_set_depth_bias",
    "cascade_shadows_set_slope_bias",
    "cascade_shadows_set_shadow_sample_type",
    "cascade_shadows_set_dynamic_depth_value",
    "cascade_shadows_reset_cascade_shadows",
    "reset_adaption",
    "play_particle_effect",
    "stop_particle_effect",
    "trigger_decal",
    "remove_decal",
    "set_light",
    "clear_light",
    "show_subtitle",
    "hide_subtitle",
    "play_audio",
    "stop_audio",
    "load_rayfire",
    "unload_rayfire",
    "start_replay_record",
    "stop_replay_record",
):
    setattr(CutScene, _name, globals()[_name])
