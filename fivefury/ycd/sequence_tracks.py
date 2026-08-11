from __future__ import annotations

from enum import IntEnum


class YcdTrackFormat(IntEnum):
    VECTOR3 = 0
    QUATERNION = 1
    FLOAT = 2


class YcdAnimationTrack(IntEnum):
    BONE_TRANSLATION = 0
    BONE_ROTATION = 1
    BONE_SCALE = 2
    BONE_CONSTRAINT = 3
    VISIBILITY = 4
    MOVER_TRANSLATION = 5
    MOVER_ROTATION = 6
    CAMERA_TRANSLATION = 7
    CAMERA_ROTATION = 8
    CAMERA_SCALE = 9
    CAMERA_FOCAL_LENGTH = 10
    CAMERA_HORIZONTAL_FILM_APERTURE = 11
    CAMERA_APERTURE = 12
    CAMERA_FOCAL_POINT = 13
    CAMERA_F_STOP = 14
    CAMERA_FOCUS_DISTANCE = 15
    SHADER_FRAME_INDEX = 16
    SHADER_SLIDE_U = 17
    SHADER_SLIDE_V = 18
    SHADER_ROTATE_UV = 19
    MOVER_SCALE = 20
    BLEND_SHAPE = 21
    VISEMES = 22
    UNKNOWN_22 = 22
    ANIMATED_NORMAL_MAPS = 23
    FACIAL_CONTROL = 24
    FACIAL_TRANSLATION = 25
    FACIAL_ROTATION = 26
    CAMERA_FIELD_OF_VIEW = 27
    CAMERA_DEPTH_OF_FIELD = 28
    COLOR = 29
    UNKNOWN_29 = 29
    LIGHT_INTENSITY = 30
    UNKNOWN_30 = 30
    LIGHT_FALLOFF = 31
    UNKNOWN_31 = 31
    LIGHT_CONE_ANGLE = 32
    UNKNOWN_32 = 32
    GENERIC_CONTROL = 33
    UNKNOWN_33 = 33
    GENERIC_TRANSLATION = 34
    UNKNOWN_34 = 34
    GENERIC_ROTATION = 35
    CAMERA_DEPTH_OF_FIELD_STRENGTH = 36
    FACIAL_SCALE = 37
    GENERIC_SCALE = 38
    CAMERA_SHALLOW_DEPTH_OF_FIELD = 39
    UNKNOWN_39 = 39
    CAMERA_MOTION_BLUR = 40
    PARTICLE_DATA = 41
    UNKNOWN_41 = 41
    LIGHT_DIRECTION = 42
    UNKNOWN_42 = 42
    CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE = 43
    CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE = 44
    CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE = 45
    CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE = 46
    LIGHT_EXP_FALLOFF = 47
    UNKNOWN_47 = 47
    CAMERA_SIMPLE_DEPTH_OF_FIELD = 48
    UNKNOWN_48 = 48
    CAMERA_COC = 49
    FACIAL_TINTING = 50
    UNKNOWN_50 = 50
    CAMERA_FOCUS = 51
    CAMERA_NIGHT_COC = 52
    CAMERA_LIMIT = 53
    UNKNOWN_53 = 53
    UNKNOWN_134 = 134
    UNKNOWN_136 = 136
    UNKNOWN_137 = 137
    UNKNOWN_138 = 138
    UNKNOWN_139 = 139
    UNKNOWN_140 = 140


TRACK_NAME_BY_ID = {
    YcdAnimationTrack.BONE_TRANSLATION: "kTrackBoneTranslation",
    YcdAnimationTrack.BONE_ROTATION: "kTrackBoneRotation",
    YcdAnimationTrack.BONE_SCALE: "kTrackBoneScale",
    YcdAnimationTrack.BONE_CONSTRAINT: "kTrackBoneConstraint",
    YcdAnimationTrack.VISIBILITY: "kTrackVisibility",
    YcdAnimationTrack.MOVER_TRANSLATION: "kTrackMoverTranslation",
    YcdAnimationTrack.MOVER_ROTATION: "kTrackMoverRotation",
    YcdAnimationTrack.MOVER_SCALE: "kTrackMoverScale",
    YcdAnimationTrack.CAMERA_TRANSLATION: "kTrackCameraTranslation",
    YcdAnimationTrack.CAMERA_ROTATION: "kTrackCameraRotation",
    YcdAnimationTrack.CAMERA_SCALE: "kTrackCameraScale",
    YcdAnimationTrack.CAMERA_FOCAL_LENGTH: "kTrackCameraFocalLength",
    YcdAnimationTrack.CAMERA_HORIZONTAL_FILM_APERTURE: "kTrackCameraHorizontalFilmAperture",
    YcdAnimationTrack.CAMERA_APERTURE: "kTrackCameraAperture",
    YcdAnimationTrack.CAMERA_FOCAL_POINT: "kTrackCameraFocalPoint",
    YcdAnimationTrack.CAMERA_F_STOP: "kTrackCameraFStop",
    YcdAnimationTrack.CAMERA_FOCUS_DISTANCE: "kTrackCameraFocusDistance",
    YcdAnimationTrack.SHADER_FRAME_INDEX: "kTrackShaderFrameIndex",
    YcdAnimationTrack.SHADER_SLIDE_U: "kTrackShaderSlideU",
    YcdAnimationTrack.SHADER_SLIDE_V: "kTrackShaderSlideV",
    YcdAnimationTrack.SHADER_ROTATE_UV: "kTrackShaderRotateUV",
    YcdAnimationTrack.BLEND_SHAPE: "kTrackBlendShape",
    YcdAnimationTrack.VISEMES: "kTrackVisemes",
    YcdAnimationTrack.ANIMATED_NORMAL_MAPS: "kTrackAnimatedNormalMaps",
    YcdAnimationTrack.FACIAL_CONTROL: "kTrackFacialControl",
    YcdAnimationTrack.FACIAL_TRANSLATION: "kTrackFacialTranslation",
    YcdAnimationTrack.FACIAL_ROTATION: "kTrackFacialRotation",
    YcdAnimationTrack.CAMERA_FIELD_OF_VIEW: "kTrackCameraFieldOfView",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD: "kTrackCameraDepthOfField",
    YcdAnimationTrack.COLOR: "kTrackColor",
    YcdAnimationTrack.LIGHT_INTENSITY: "kTrackLightIntensity",
    YcdAnimationTrack.LIGHT_FALLOFF: "kTrackLightFallOff",
    YcdAnimationTrack.LIGHT_CONE_ANGLE: "kTrackLightConeAngle",
    YcdAnimationTrack.GENERIC_CONTROL: "kTrackGenericControl",
    YcdAnimationTrack.GENERIC_TRANSLATION: "kTrackGenericTranslation",
    YcdAnimationTrack.GENERIC_ROTATION: "kTrackGenericRotation",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH: "kTrackCameraDepthOfFieldStrength",
    YcdAnimationTrack.FACIAL_SCALE: "kTrackFacialScale",
    YcdAnimationTrack.GENERIC_SCALE: "kTrackGenericScale",
    YcdAnimationTrack.CAMERA_SHALLOW_DEPTH_OF_FIELD: "kTrackCameraShallowDepthOfField",
    YcdAnimationTrack.CAMERA_MOTION_BLUR: "kTrackCameraMotionBlur",
    YcdAnimationTrack.PARTICLE_DATA: "kTrackParticleData",
    YcdAnimationTrack.LIGHT_DIRECTION: "kTrackLightDirection",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE: "kTrackCameraDepthOfFieldNearOutOfFocusPlane",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE: "kTrackCameraDepthOfFieldNearInFocusPlane",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE: "kTrackCameraDepthOfFieldFarOutOfFocusPlane",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE: "kTrackCameraDepthOfFieldFarInFocusPlane",
    YcdAnimationTrack.LIGHT_EXP_FALLOFF: "kTrackLightExpFallOff",
    YcdAnimationTrack.CAMERA_SIMPLE_DEPTH_OF_FIELD: "kTrackCameraSimpleDepthOfField",
    YcdAnimationTrack.CAMERA_COC: "kTrackCameraCoC",
    YcdAnimationTrack.FACIAL_TINTING: "kTrackFacialTinting",
    YcdAnimationTrack.CAMERA_FOCUS: "kTrackCameraFocus",
    YcdAnimationTrack.CAMERA_NIGHT_COC: "kTrackCameraNightCoC",
    YcdAnimationTrack.CAMERA_LIMIT: "kTrackCameraLimit",
    YcdAnimationTrack.UNKNOWN_134: "kTrackUnk134",
    YcdAnimationTrack.UNKNOWN_136: "kTrackUnk136",
    YcdAnimationTrack.UNKNOWN_137: "kTrackUnk137",
    YcdAnimationTrack.UNKNOWN_138: "kTrackUnk138",
    YcdAnimationTrack.UNKNOWN_139: "kTrackUnk139",
    YcdAnimationTrack.UNKNOWN_140: "kTrackUnk140",
}


CAMERA_TRACK_IDS = frozenset(
    {
        int(YcdAnimationTrack.CAMERA_TRANSLATION),
        int(YcdAnimationTrack.CAMERA_ROTATION),
        int(YcdAnimationTrack.CAMERA_FIELD_OF_VIEW),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH),
        int(YcdAnimationTrack.CAMERA_MOTION_BLUR),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE),
        int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE),
        int(YcdAnimationTrack.CAMERA_COC),
        int(YcdAnimationTrack.CAMERA_FOCUS),
        int(YcdAnimationTrack.CAMERA_NIGHT_COC),
    }
)

ROOT_MOTION_TRACK_IDS = frozenset(
    {
        int(YcdAnimationTrack.MOVER_TRANSLATION),
        int(YcdAnimationTrack.MOVER_ROTATION),
    }
)

FACIAL_TRACK_IDS = frozenset(
    {
        int(YcdAnimationTrack.FACIAL_CONTROL),
        int(YcdAnimationTrack.FACIAL_TRANSLATION),
        int(YcdAnimationTrack.FACIAL_ROTATION),
        int(YcdAnimationTrack.FACIAL_SCALE),
        int(YcdAnimationTrack.BLEND_SHAPE),
        int(YcdAnimationTrack.VISEMES),
        int(YcdAnimationTrack.ANIMATED_NORMAL_MAPS),
        int(YcdAnimationTrack.FACIAL_TINTING),
    }
)

TRACK_FORMAT_BY_ID = {
    int(YcdAnimationTrack.BONE_TRANSLATION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.BONE_ROTATION): YcdTrackFormat.QUATERNION,
    int(YcdAnimationTrack.BONE_SCALE): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.VISIBILITY): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.MOVER_TRANSLATION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.MOVER_ROTATION): YcdTrackFormat.QUATERNION,
    int(YcdAnimationTrack.MOVER_SCALE): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.CAMERA_TRANSLATION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.CAMERA_ROTATION): YcdTrackFormat.QUATERNION,
    int(YcdAnimationTrack.SHADER_SLIDE_U): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.SHADER_SLIDE_V): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.BLEND_SHAPE): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.VISEMES): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.ANIMATED_NORMAL_MAPS): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.FACIAL_CONTROL): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.FACIAL_TRANSLATION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.FACIAL_ROTATION): YcdTrackFormat.QUATERNION,
    int(YcdAnimationTrack.FACIAL_SCALE): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.FACIAL_TINTING): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_FIELD_OF_VIEW): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.COLOR): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.UNKNOWN_30): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_31): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_32): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.GENERIC_CONTROL): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.GENERIC_TRANSLATION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.GENERIC_ROTATION): YcdTrackFormat.QUATERNION,
    int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_39): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_MOTION_BLUR): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_41): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.LIGHT_DIRECTION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_47): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_48): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_COC): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_50): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_FOCUS): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_NIGHT_COC): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_53): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_134): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_136): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_137): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_138): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_139): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_140): YcdTrackFormat.FLOAT,
}


def get_ycd_track_name(track: int) -> str:
    try:
        return TRACK_NAME_BY_ID[YcdAnimationTrack(int(track))]
    except ValueError:
        return f"TRACK_{int(track)}"


def get_ycd_track_format(track: int) -> YcdTrackFormat:
    try:
        return TRACK_FORMAT_BY_ID[int(track)]
    except KeyError as exc:
        raise ValueError(f"Unsupported YCD track format mapping for track {int(track)}") from exc


def is_ycd_uv_track(track: int) -> bool:
    return int(track) in (int(YcdAnimationTrack.SHADER_SLIDE_U), int(YcdAnimationTrack.SHADER_SLIDE_V))


def is_ycd_object_track(track: int) -> bool:
    return int(track) in (
        int(YcdAnimationTrack.BONE_TRANSLATION),
        int(YcdAnimationTrack.BONE_ROTATION),
        int(YcdAnimationTrack.BONE_SCALE),
    )


def is_ycd_camera_track(track: int) -> bool:
    return int(track) in CAMERA_TRACK_IDS


def is_ycd_root_motion_track(track: int) -> bool:
    return int(track) in ROOT_MOTION_TRACK_IDS


def is_ycd_facial_track(track: int) -> bool:
    return int(track) in FACIAL_TRACK_IDS


def is_ycd_position_track(track: int) -> bool:
    return int(track) in (int(YcdAnimationTrack.BONE_TRANSLATION), int(YcdAnimationTrack.MOVER_TRANSLATION))


def is_ycd_rotation_track(track: int) -> bool:
    return TRACK_FORMAT_BY_ID.get(int(track)) is YcdTrackFormat.QUATERNION


__all__ = [
    "CAMERA_TRACK_IDS",
    "FACIAL_TRACK_IDS",
    "ROOT_MOTION_TRACK_IDS",
    "YcdAnimationTrack",
    "YcdTrackFormat",
    "get_ycd_track_format",
    "get_ycd_track_name",
    "is_ycd_camera_track",
    "is_ycd_facial_track",
    "is_ycd_object_track",
    "is_ycd_position_track",
    "is_ycd_root_motion_track",
    "is_ycd_rotation_track",
    "is_ycd_uv_track",
]
