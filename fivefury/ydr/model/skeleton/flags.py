from __future__ import annotations

import enum


class YdrBoneFlags(enum.IntFlag):
    NONE = 0
    ROT_X = 0x1
    ROT_Y = 0x2
    ROT_Z = 0x4
    LIMIT_ROTATION = 0x8
    TRANS_X = 0x10
    TRANS_Y = 0x20
    TRANS_Z = 0x40
    LIMIT_TRANSLATION = 0x80
    SCALE_X = 0x100
    SCALE_Y = 0x200
    SCALE_Z = 0x400
    LIMIT_SCALE = 0x800
    HAS_CHILD = 0x1000
    IS_SKINNED = 0x2000
    UNKNOWN_2 = 0x4000
    UNKNOWN_3 = 0x8000


YDR_BONE_ANIMATABLE_FLAGS = (
    YdrBoneFlags.ROT_X
    | YdrBoneFlags.ROT_Y
    | YdrBoneFlags.ROT_Z
    | YdrBoneFlags.TRANS_X
    | YdrBoneFlags.TRANS_Y
    | YdrBoneFlags.TRANS_Z
)


class YdrBoneFlagName(enum.StrEnum):
    ROT_X = "RotX"
    ROT_Y = "RotY"
    ROT_Z = "RotZ"
    LIMIT_ROTATION = "LimitRotation"
    TRANS_X = "TransX"
    TRANS_Y = "TransY"
    TRANS_Z = "TransZ"
    LIMIT_TRANSLATION = "LimitTranslation"
    SCALE_X = "ScaleX"
    SCALE_Y = "ScaleY"
    SCALE_Z = "ScaleZ"
    HAS_CHILD = "HasChild"
    IS_SKINNED = "IsSkinned"


_SKELETON_HASH_FLAG_NAMES = (
    (YdrBoneFlags.ROT_X, YdrBoneFlagName.ROT_X),
    (YdrBoneFlags.ROT_Y, YdrBoneFlagName.ROT_Y),
    (YdrBoneFlags.ROT_Z, YdrBoneFlagName.ROT_Z),
    (YdrBoneFlags.LIMIT_ROTATION, YdrBoneFlagName.LIMIT_ROTATION),
    (YdrBoneFlags.TRANS_X, YdrBoneFlagName.TRANS_X),
    (YdrBoneFlags.TRANS_Y, YdrBoneFlagName.TRANS_Y),
    (YdrBoneFlags.TRANS_Z, YdrBoneFlagName.TRANS_Z),
    (YdrBoneFlags.LIMIT_TRANSLATION, YdrBoneFlagName.LIMIT_TRANSLATION),
    (YdrBoneFlags.SCALE_X, YdrBoneFlagName.SCALE_X),
    (YdrBoneFlags.SCALE_Y, YdrBoneFlagName.SCALE_Y),
    (YdrBoneFlags.SCALE_Z, YdrBoneFlagName.SCALE_Z),
    (YdrBoneFlags.HAS_CHILD, YdrBoneFlagName.HAS_CHILD),
    (YdrBoneFlags.IS_SKINNED, YdrBoneFlagName.IS_SKINNED),
)


def skeleton_bone_flag_names(flags: YdrBoneFlags | int) -> tuple[YdrBoneFlagName, ...]:
    value = YdrBoneFlags(flags)
    return tuple(name for flag, name in _SKELETON_HASH_FLAG_NAMES if value & flag)
