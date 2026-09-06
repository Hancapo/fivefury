from ...drawable.model import NumericParameterValue
from ...matrix import Matrix4
from .asset import Ydr
from .geometry import YdrMesh, YdrModel
from .joints import (
    YdrJointControlPoint,
    YdrJointRotationLimit,
    YdrJoints,
    YdrJointTranslationLimit,
)
from .lights import YdrLight, YdrLightFlags, YdrLightType
from .material import YdrMaterial, YdrMaterialParameterRef, YdrTextureRef
from .painting import Color4, ColorChannel, paint_mesh, paint_vertices
from .skeleton import (
    YDR_BONE_ANIMATABLE_FLAGS,
    YdrBone,
    YdrBoneFlagName,
    YdrBoneFlags,
    YdrSkeleton,
    calculate_bone_tag,
    calculate_skeleton_unknown_hashes,
    skeleton_bone_flag_names,
)

__all__ = [
    "YDR_BONE_ANIMATABLE_FLAGS",
    "Color4",
    "ColorChannel",
    "Matrix4",
    "NumericParameterValue",
    "Ydr",
    "YdrBone",
    "YdrBoneFlagName",
    "YdrBoneFlags",
    "YdrJointControlPoint",
    "YdrJointRotationLimit",
    "YdrJointTranslationLimit",
    "YdrJoints",
    "YdrLight",
    "YdrLightFlags",
    "YdrLightType",
    "YdrMaterial",
    "YdrMaterialParameterRef",
    "YdrMesh",
    "YdrModel",
    "YdrSkeleton",
    "YdrTextureRef",
    "calculate_bone_tag",
    "calculate_skeleton_unknown_hashes",
    "paint_mesh",
    "paint_vertices",
    "skeleton_bone_flag_names",
]
