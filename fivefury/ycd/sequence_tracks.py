from __future__ import annotations

from enum import IntEnum


class YcdAnimationTrack(IntEnum):
    BONE_TRANSLATION = 0
    BONE_ROTATION = 1
    MOVER_TRANSLATION = 5
    MOVER_ROTATION = 6
    CAMERA_TRANSLATION = 7
    CAMERA_ROTATION = 8
    SHADER_SLIDE_U = 17
    SHADER_SLIDE_V = 18
    FACIAL_CONTROL = 24
    FACIAL_TRANSLATION = 25
    FACIAL_ROTATION = 26
    CAMERA_FIELD_OF_VIEW = 27
    CAMERA_DEPTH_OF_FIELD = 28
    CAMERA_DEPTH_OF_FIELD_STRENGTH = 36
    CAMERA_MOTION_BLUR = 40
    CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE = 43
    CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE = 44
    CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE = 45
    CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE = 46
    CAMERA_COC = 49
    CAMERA_FOCUS = 51
    CAMERA_NIGHT_COC = 52


TRACK_NAME_BY_ID = {
    YcdAnimationTrack.BONE_TRANSLATION: "kTrackBoneTranslation",
    YcdAnimationTrack.BONE_ROTATION: "kTrackBoneRotation",
    YcdAnimationTrack.MOVER_TRANSLATION: "kTrackMoverTranslation",
    YcdAnimationTrack.MOVER_ROTATION: "kTrackMoverRotation",
    YcdAnimationTrack.CAMERA_TRANSLATION: "kTrackCameraTranslation",
    YcdAnimationTrack.CAMERA_ROTATION: "kTrackCameraRotation",
    YcdAnimationTrack.SHADER_SLIDE_U: "kTrackShaderSlideU",
    YcdAnimationTrack.SHADER_SLIDE_V: "kTrackShaderSlideV",
    YcdAnimationTrack.FACIAL_CONTROL: "kTrackFacialControl",
    YcdAnimationTrack.FACIAL_TRANSLATION: "kTrackFacialTranslation",
    YcdAnimationTrack.FACIAL_ROTATION: "kTrackFacialRotation",
    YcdAnimationTrack.CAMERA_FIELD_OF_VIEW: "kTrackCameraFieldOfView",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD: "kTrackCameraDepthOfField",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_STRENGTH: "kTrackCameraDepthOfFieldStrength",
    YcdAnimationTrack.CAMERA_MOTION_BLUR: "kTrackCameraMotionBlur",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_OUT_OF_FOCUS_PLANE: "kTrackCameraDepthOfFieldNearOutOfFocusPlane",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_NEAR_IN_FOCUS_PLANE: "kTrackCameraDepthOfFieldNearInFocusPlane",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_OUT_OF_FOCUS_PLANE: "kTrackCameraDepthOfFieldFarOutOfFocusPlane",
    YcdAnimationTrack.CAMERA_DEPTH_OF_FIELD_FAR_IN_FOCUS_PLANE: "kTrackCameraDepthOfFieldFarInFocusPlane",
    YcdAnimationTrack.CAMERA_COC: "kTrackCameraCoC",
    YcdAnimationTrack.CAMERA_FOCUS: "kTrackCameraFocus",
    YcdAnimationTrack.CAMERA_NIGHT_COC: "kTrackCameraNightCoC",
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


def get_ycd_track_name(track: int) -> str:
    try:
        return TRACK_NAME_BY_ID[YcdAnimationTrack(int(track))]
    except ValueError:
        return f"TRACK_{int(track)}"


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
    "CAMERA_TRACK_IDS",
    "FACIAL_TRACK_IDS",
    "ROOT_MOTION_TRACK_IDS",
    "get_ycd_track_name",
    "is_ycd_camera_track",
    "is_ycd_facial_track",
    "is_ycd_object_track",
    "is_ycd_position_track",
    "is_ycd_rotation_track",
    "is_ycd_root_motion_track",
    "is_ycd_uv_track",
]
