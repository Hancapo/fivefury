from __future__ import annotations

from enum import IntEnum


class YcdTrackFormat(IntEnum):
    VECTOR3 = 0
    QUATERNION = 1
    FLOAT = 2


class YcdAnimationTrack(IntEnum):
    BONE_TRANSLATION = 0
    BONE_ROTATION = 1
    UNKNOWN_22 = 22
    FACIAL_CONTROL = 24
    FACIAL_TRANSLATION = 25
    FACIAL_ROTATION = 26
    MOVER_TRANSLATION = 5
    MOVER_ROTATION = 6
    CAMERA_TRANSLATION = 7
    CAMERA_ROTATION = 8
    SHADER_SLIDE_U = 17
    SHADER_SLIDE_V = 18
    CAMERA_FIELD_OF_VIEW = 27
    CAMERA_DEPTH_OF_FIELD = 28
    UNKNOWN_29 = 29
    UNKNOWN_30 = 30
    UNKNOWN_31 = 31
    UNKNOWN_32 = 32
    UNKNOWN_33 = 33
    UNKNOWN_34 = 34
    CAMERA_DEPTH_OF_FIELD_STRENGTH = 36
    UNKNOWN_39 = 39
    CAMERA_MOTION_BLUR = 40
    UNKNOWN_41 = 41
    UNKNOWN_42 = 42
    CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE = 43
    CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE = 44
    CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE = 45
    CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE = 46
    UNKNOWN_47 = 47
    UNKNOWN_48 = 48
    CAMERA_COC = 49
    UNKNOWN_50 = 50
    CAMERA_FOCUS = 51
    CAMERA_NIGHT_COC = 52
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
    YcdAnimationTrack.MOVER_TRANSLATION: "kTrackMoverTranslation",
    YcdAnimationTrack.MOVER_ROTATION: "kTrackMoverRotation",
    YcdAnimationTrack.CAMERA_TRANSLATION: "kTrackCameraTranslation",
    YcdAnimationTrack.CAMERA_ROTATION: "kTrackCameraRotation",
    YcdAnimationTrack.SHADER_SLIDE_U: "kTrackShaderSlideU",
    YcdAnimationTrack.SHADER_SLIDE_V: "kTrackShaderSlideV",
    YcdAnimationTrack.UNKNOWN_22: "kTrackUnk22",
    YcdAnimationTrack.FACIAL_CONTROL: "kTrackFacialControl",
    YcdAnimationTrack.FACIAL_TRANSLATION: "kTrackFacialTranslation",
    YcdAnimationTrack.FACIAL_ROTATION: "kTrackFacialRotation",
    YcdAnimationTrack.CAMERA_FIELD_OF_VIEW: "kTrackCameraFieldOfView",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD: "kTrackCameraDepthOfField",
    YcdAnimationTrack.UNKNOWN_29: "kTrackUnk29",
    YcdAnimationTrack.UNKNOWN_30: "kTrackUnk30",
    YcdAnimationTrack.UNKNOWN_31: "kTrackUnk31",
    YcdAnimationTrack.UNKNOWN_32: "kTrackUnk32",
    YcdAnimationTrack.UNKNOWN_33: "kTrackUnk33",
    YcdAnimationTrack.UNKNOWN_34: "kTrackUnk34",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH: "kTrackCameraDepthOfFieldStrength",
    YcdAnimationTrack.UNKNOWN_39: "kTrackCameraUnk39",
    YcdAnimationTrack.CAMERA_MOTION_BLUR: "kTrackCameraMotionBlur",
    YcdAnimationTrack.UNKNOWN_41: "kTrackUnk41",
    YcdAnimationTrack.UNKNOWN_42: "kTrackUnk42",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE: "kTrackCameraDepthOfFieldNearOutOfFocusPlane",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE: "kTrackCameraDepthOfFieldNearInFocusPlane",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE: "kTrackCameraDepthOfFieldFarOutOfFocusPlane",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE: "kTrackCameraDepthOfFieldFarInFocusPlane",
    YcdAnimationTrack.UNKNOWN_47: "kTrackUnk47",
    YcdAnimationTrack.UNKNOWN_48: "kTrackCameraUnk48",
    YcdAnimationTrack.CAMERA_COC: "kTrackCameraCoC",
    YcdAnimationTrack.UNKNOWN_50: "kTrackUnk50",
    YcdAnimationTrack.CAMERA_FOCUS: "kTrackCameraFocus",
    YcdAnimationTrack.CAMERA_NIGHT_COC: "kTrackCameraNightCoC",
    YcdAnimationTrack.UNKNOWN_53: "kTrackUnk53",
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
    }
)

TRACK_FORMAT_BY_ID = {
    int(YcdAnimationTrack.BONE_TRANSLATION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.BONE_ROTATION): YcdTrackFormat.QUATERNION,
    int(YcdAnimationTrack.MOVER_TRANSLATION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.MOVER_ROTATION): YcdTrackFormat.QUATERNION,
    int(YcdAnimationTrack.CAMERA_TRANSLATION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.CAMERA_ROTATION): YcdTrackFormat.QUATERNION,
    int(YcdAnimationTrack.SHADER_SLIDE_U): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.SHADER_SLIDE_V): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.UNKNOWN_22): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.FACIAL_CONTROL): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.FACIAL_TRANSLATION): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.FACIAL_ROTATION): YcdTrackFormat.QUATERNION,
    int(YcdAnimationTrack.CAMERA_FIELD_OF_VIEW): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.UNKNOWN_29): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.UNKNOWN_30): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_31): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_32): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_33): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_34): YcdTrackFormat.VECTOR3,
    int(YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_39): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.CAMERA_MOTION_BLUR): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_41): YcdTrackFormat.FLOAT,
    int(YcdAnimationTrack.UNKNOWN_42): YcdTrackFormat.VECTOR3,
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
    return int(track) in (int(YcdAnimationTrack.BONE_TRANSLATION), int(YcdAnimationTrack.BONE_ROTATION))


def is_ycd_camera_track(track: int) -> bool:
    return int(track) in CAMERA_TRACK_IDS


def is_ycd_root_motion_track(track: int) -> bool:
    return int(track) in ROOT_MOTION_TRACK_IDS


def is_ycd_facial_track(track: int) -> bool:
    return int(track) in FACIAL_TRACK_IDS


def is_ycd_position_track(track: int) -> bool:
    return int(track) in (int(YcdAnimationTrack.BONE_TRANSLATION), int(YcdAnimationTrack.MOVER_TRANSLATION))


def is_ycd_rotation_track(track: int) -> bool:
    return int(track) in (int(YcdAnimationTrack.BONE_ROTATION), int(YcdAnimationTrack.MOVER_ROTATION))


__all__ = [
    "YcdAnimationTrack",
    "YcdTrackFormat",
    "CAMERA_TRACK_IDS",
    "FACIAL_TRACK_IDS",
    "ROOT_MOTION_TRACK_IDS",
    "get_ycd_track_format",
    "get_ycd_track_name",
    "is_ycd_camera_track",
    "is_ycd_facial_track",
    "is_ycd_object_track",
    "is_ycd_position_track",
    "is_ycd_rotation_track",
    "is_ycd_root_motion_track",
    "is_ycd_uv_track",
]
