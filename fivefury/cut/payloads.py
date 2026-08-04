from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..colors import CssColor, parse_css_argb


@dataclass(slots=True)
class CutEventPayload:
    def to_fields(self) -> dict[str, Any]:
        return {}

    @property
    def event_label(self) -> str | None:
        return None

    @property
    def event_duration(self) -> float | None:
        return None


@dataclass(slots=True)
class CutLoadScenePayload(CutEventPayload):
    name: str
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0

    def to_fields(self) -> dict[str, Any]:
        return {
            "cName": self.name,
            "vOffset": self.offset,
            "fRotation": self.rotation,
            "fPitch": self.pitch,
            "fRoll": self.roll,
        }


@dataclass(slots=True)
class CutObjectIdListPayload(CutEventPayload):
    object_ids: list[int]

    def to_fields(self) -> dict[str, Any]:
        return {"iObjectIdList": list(self.object_ids)}


@dataclass(slots=True)
class CutNamePayload(CutEventPayload):
    name: str

    def to_fields(self) -> dict[str, Any]:
        return {"cName": self.name}

    @property
    def event_label(self) -> str | None:
        return self.name


@dataclass(slots=True)
class CutAnimationDictPayload(CutNamePayload):
    pass


@dataclass(slots=True)
class CutFinalNamePayload(CutEventPayload):
    name: str

    def to_fields(self) -> dict[str, Any]:
        return {"cName": str(self.name)}

    @property
    def event_label(self) -> str | None:
        return self.name


@dataclass(slots=True)
class CutAnimationTargetPayload(CutEventPayload):
    object_id: int
    clip_name: str | None = None

    def to_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {"iObjectId": int(self.object_id)}
        if self.clip_name is not None:
            fields["cName"] = self.clip_name
        return fields

    @property
    def event_label(self) -> str | None:
        return self.clip_name


@dataclass(slots=True)
class CutFloatValuePayload(CutEventPayload):
    value: float

    def to_fields(self) -> dict[str, Any]:
        return {"fValue": float(self.value)}


@dataclass(slots=True)
class CutDrawDistancePayload(CutEventPayload):
    near_distance: float
    far_distance: float

    def to_fields(self) -> dict[str, Any]:
        return {
            "fValue": float(self.near_distance),
            "fValue2": float(self.far_distance),
        }


@dataclass(slots=True)
class CutAttachmentPayload(CutEventPayload):
    parent_object_id: int
    bone_name: str

    def to_fields(self) -> dict[str, Any]:
        return {
            "iObjectId": int(self.parent_object_id),
            "cBoneName": self.bone_name,
        }


@dataclass(slots=True)
class CutBoolValuePayload(CutEventPayload):
    value: bool

    def to_fields(self) -> dict[str, Any]:
        return {"bValue": bool(self.value)}


@dataclass(slots=True)
class CutObjectVariationPayload(CutEventPayload):
    object_id: int
    component: int
    drawable: int
    texture: int

    def to_fields(self) -> dict[str, Any]:
        return {
            "iObjectId": int(self.object_id),
            "iComponent": int(self.component),
            "iDrawable": int(self.drawable),
            "iTexture": int(self.texture),
        }


@dataclass(slots=True)
class CutObjectTargetPayload(CutEventPayload):
    object_id: int

    def to_fields(self) -> dict[str, Any]:
        return {"iObjectId": int(self.object_id)}


@dataclass(slots=True)
class CutObjectNamePayload(CutEventPayload):
    object_id: int
    name: str

    def to_fields(self) -> dict[str, Any]:
        return {
            "iObjectId": int(self.object_id),
            "cName": self.name,
        }

    @property
    def event_label(self) -> str | None:
        return self.name


@dataclass(slots=True)
class CutSubtitlePayload(CutEventPayload):
    text: str
    duration: float
    language_id: int = 0
    transition_in: int = 0
    transition_in_duration: float = 0.0
    transition_out: int = 0
    transition_out_duration: float = 0.0

    def to_fields(self) -> dict[str, Any]:
        return {
            "cName": self.text,
            "iLanguageID": self.language_id,
            "iTransitionIn": self.transition_in,
            "fTransitionInDuration": self.transition_in_duration,
            "iTransitionOut": self.transition_out,
            "fTransitionOutDuration": self.transition_out_duration,
            "fSubtitleDuration": self.duration,
        }

    @property
    def event_label(self) -> str | None:
        return self.text

    @property
    def event_duration(self) -> float | None:
        return self.duration


@dataclass(slots=True)
class CutCameraCharacterLightPayload:
    use_timecycle_values: bool = True
    direction: tuple[float, float, float] = (0.0, 1.0, 0.0)
    colour: tuple[float, float, float] = (0.0, 0.0, 0.0)
    intensity: float = 0.0

    def to_fields(self) -> dict[str, Any]:
        return {
            "bUseTimeCycleValues": bool(self.use_timecycle_values),
            "vDirection": self.direction,
            "vColour": self.colour,
            "fIntensity": float(self.intensity),
        }


@dataclass(slots=True)
class CutCameraDofModifierPayload:
    hour_flags: int
    strength: int

    def to_fields(self) -> dict[str, Any]:
        return {
            "TimeOfDayFlags": int(self.hour_flags),
            "DofStrengthModifier": int(self.strength),
        }


@dataclass(slots=True)
class CutCameraCutPayload(CutEventPayload):
    name: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_quaternion: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    near_draw_distance: float = -1.0
    far_draw_distance: float = -1.0
    map_lod_scale: float = -1.0
    reflection_lod_range_start: float = -1.0
    reflection_lod_range_end: float = -1.0
    reflection_slod_range_start: float = -1.0
    reflection_slod_range_end: float = -1.0
    lod_mult_hd: float = -1.0
    lod_mult_orphaned_hd: float = -1.0
    lod_mult_lod: float = -1.0
    lod_mult_slod1: float = -1.0
    lod_mult_slod2: float = -1.0
    lod_mult_slod3: float = -1.0
    lod_mult_slod4: float = -1.0
    water_reflection_far_clip: float = -1.0
    ssao_light_intensity: float = -1.0
    exposure_push: float = 0.0
    light_fade_distance_mult: float = 1.0
    light_shadow_fade_distance_mult: float = 1.0
    light_specular_fade_distance_mult: float = 1.0
    light_volumetric_fade_distance_mult: float = 1.0
    directional_light_multiplier: float = -1.0
    lens_artefact_multiplier: float = -1.0
    bloom_max: float = -1.0
    disable_high_quality_dof: bool = False
    freeze_reflection_map: bool = False
    disable_directional_lighting: bool = False
    absolute_intensity_enabled: bool = True
    character_light: CutCameraCharacterLightPayload = field(
        default_factory=CutCameraCharacterLightPayload
    )
    time_of_day_dof_modifiers: list[CutCameraDofModifierPayload] = field(
        default_factory=list
    )

    def to_fields(self) -> dict[str, Any]:
        return {
            "cName": self.name,
            "vPosition": self.position,
            "vRotationQuaternion": self.rotation_quaternion,
            "fNearDrawDistance": self.near_draw_distance,
            "fFarDrawDistance": self.far_draw_distance,
            "fMapLodScale": self.map_lod_scale,
            "ReflectionLodRangeStart": self.reflection_lod_range_start,
            "ReflectionLodRangeEnd": self.reflection_lod_range_end,
            "ReflectionSLodRangeStart": self.reflection_slod_range_start,
            "ReflectionSLodRangeEnd": self.reflection_slod_range_end,
            "LodMultHD": self.lod_mult_hd,
            "LodMultOrphanedHD": self.lod_mult_orphaned_hd,
            "LodMultLod": self.lod_mult_lod,
            "LodMultSLod1": self.lod_mult_slod1,
            "LodMultSLod2": self.lod_mult_slod2,
            "LodMultSLod3": self.lod_mult_slod3,
            "LodMultSLod4": self.lod_mult_slod4,
            "WaterReflectionFarClip": self.water_reflection_far_clip,
            "SSAOLightInten": self.ssao_light_intensity,
            "ExposurePush": self.exposure_push,
            "LightFadeDistanceMult": self.light_fade_distance_mult,
            "LightShadowFadeDistanceMult": self.light_shadow_fade_distance_mult,
            "LightSpecularFadeDistMult": self.light_specular_fade_distance_mult,
            "LightVolumetricFadeDistanceMult": self.light_volumetric_fade_distance_mult,
            "DirectionalLightMultiplier": self.directional_light_multiplier,
            "LensArtefactMultiplier": self.lens_artefact_multiplier,
            "BloomMax": self.bloom_max,
            "DisableHighQualityDof": self.disable_high_quality_dof,
            "FreezeReflectionMap": self.freeze_reflection_map,
            "DisableDirectionalLighting": self.disable_directional_lighting,
            "AbsoluteIntensityEnabled": self.absolute_intensity_enabled,
            "CharacterLight": self.character_light.to_fields(),
            "TimeOfDayDofModifers": [
                item.to_fields() for item in self.time_of_day_dof_modifiers
            ],
        }

    @property
    def event_label(self) -> str | None:
        return self.name


@dataclass(slots=True)
class CutScreenFadePayload(CutEventPayload):
    value: float
    color: int | CssColor = 0xFF000000

    def to_fields(self) -> dict[str, Any]:
        return {
            "fValue": float(self.value),
            "color": parse_css_argb(self.color),
        }


@dataclass(slots=True)
class CutCascadeShadowPayload(CutEventPayload):
    camera_cut_hash: int | str
    position: tuple[float, float, float]
    radius: float
    interp_time: float = 0.0
    cascade_index: int = 0
    enabled: bool = True
    interpolate_to_disabled: bool = True

    def to_fields(self) -> dict[str, Any]:
        return {
            "cameraCutHashTag": self.camera_cut_hash,
            "position": self.position,
            "radius": float(self.radius),
            "interpTimeTag": float(self.interp_time),
            "cascadeIndexTag": int(self.cascade_index),
            "enabled": bool(self.enabled),
            "interpolateToDisabledTag": bool(self.interpolate_to_disabled),
        }


@dataclass(slots=True)
class CutHashFloatPayload(CutEventPayload):
    value: float

    def to_fields(self) -> dict[str, Any]:
        return {"hash_0BD8B46C": float(self.value)}


@dataclass(slots=True)
class CutHashBoolPayload(CutEventPayload):
    value: bool

    def to_fields(self) -> dict[str, Any]:
        return {"hash_0C74B449": bool(self.value)}


@dataclass(slots=True)
class CutPlayParticleEffectPayload(CutEventPayload):
    initial_bone_rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    initial_bone_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    attach_parent_id: int = -1
    attach_bone_hash: int = 0

    def to_fields(self) -> dict[str, Any]:
        return {
            "vParticleInitialBoneRotation": self.initial_bone_rotation,
            "vParticleInitialBoneOffset": self.initial_bone_offset,
            "hash_33B52A22": int(self.attach_parent_id),
            "hash_EAA4CB67": int(self.attach_bone_hash),
        }


@dataclass(slots=True)
class CutDecalPayload(CutEventPayload):
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    width: float = 1.0
    height: float = 1.0
    colour: int | CssColor = 0xFFFFFFFF
    lifetime: float = 0.0

    def to_fields(self) -> dict[str, Any]:
        return {
            "vPosition": self.position,
            "vRotation": self.rotation,
            "fWidth": float(self.width),
            "fHeight": float(self.height),
            "Colour": parse_css_argb(self.colour),
            "fLifeTime": float(self.lifetime),
        }


@dataclass(slots=True)
class CutLightEffectPayload(CutEventPayload):
    attach_parent_id: int = -1
    attach_bone_hash: int = 0
    attached_parent_name: str | None = None

    def to_fields(self) -> dict[str, Any]:
        fields = {
            "iAttachParentId": int(self.attach_parent_id),
            "iAttachBoneHash": int(self.attach_bone_hash),
        }
        if self.attached_parent_name is not None:
            fields["AttachedParentName"] = self.attached_parent_name
        return fields
