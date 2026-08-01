"""Runtime class headers used by GTA V fragment resources."""

from __future__ import annotations

import dataclasses

from ..ydr.resource_headers import (
    GEN9_FRAGMENT_DRAWABLE_HEADERS,
    LEGACY_FRAGMENT_DRAWABLE_HEADERS,
    DrawableRuntimeHeaders,
)

RESOURCE_STATE = 1

FRAGMENT_TYPE_VFT = 0x40571138
FRAG_PHYSICS_LOD_GROUP_VFT = 0x406036B0
FRAG_PHYSICS_LOD_VFT = 0x406036D8
FRAG_PHYS_TRANSFORMS_VFT = 0x40600810
FRAG_PHYS_ARCHETYPE_DAMP_VFT = 0x4062A988
FRAG_TYPE_CHILD_VFT = 0x40604F10
PH_ARTICULATED_BODY_TYPE_EUPHORIA_VFT = 0x4062B8F8
PH_JOINT_1DOF_TYPE_VFT = 0x4062BCB0
PH_JOINT_3DOF_TYPE_VFT = 0x4062BC40


@dataclasses.dataclass(frozen=True, slots=True)
class YftRuntimeHeaders:
    fragment_type: int
    physics_lod_group: int
    physics_lod: int
    physics_transforms: int
    damp_archetype: int
    physics_child: int
    articulated_body: int
    joint_1dof: int
    joint_3dof: int
    drawable: DrawableRuntimeHeaders
    enhanced: bool = False


LEGACY_YFT_RUNTIME_HEADERS = YftRuntimeHeaders(
    fragment_type=FRAGMENT_TYPE_VFT,
    physics_lod_group=FRAG_PHYSICS_LOD_GROUP_VFT,
    physics_lod=FRAG_PHYSICS_LOD_VFT,
    physics_transforms=FRAG_PHYS_TRANSFORMS_VFT,
    damp_archetype=FRAG_PHYS_ARCHETYPE_DAMP_VFT,
    physics_child=FRAG_TYPE_CHILD_VFT,
    articulated_body=PH_ARTICULATED_BODY_TYPE_EUPHORIA_VFT,
    joint_1dof=PH_JOINT_1DOF_TYPE_VFT,
    joint_3dof=PH_JOINT_3DOF_TYPE_VFT,
    drawable=LEGACY_FRAGMENT_DRAWABLE_HEADERS,
)

GEN9_YFT_RUNTIME_HEADERS = YftRuntimeHeaders(
    fragment_type=0x4068C7A0,
    physics_lod_group=0x406E02B0,
    physics_lod=0x406E02F8,
    physics_transforms=0x4069B018,
    damp_archetype=0x406B4908,
    physics_child=0x406E4D68,
    articulated_body=0x406B1750,
    joint_1dof=0x406B1628,
    joint_3dof=0x406B1690,
    drawable=GEN9_FRAGMENT_DRAWABLE_HEADERS,
    enhanced=True,
)


def yft_runtime_headers(version: int) -> YftRuntimeHeaders:
    return GEN9_YFT_RUNTIME_HEADERS if int(version) == 171 else LEGACY_YFT_RUNTIME_HEADERS


__all__ = [
    "FRAGMENT_TYPE_VFT",
    "FRAG_PHYSICS_LOD_GROUP_VFT",
    "FRAG_PHYSICS_LOD_VFT",
    "FRAG_PHYS_ARCHETYPE_DAMP_VFT",
    "FRAG_PHYS_TRANSFORMS_VFT",
    "FRAG_TYPE_CHILD_VFT",
    "GEN9_YFT_RUNTIME_HEADERS",
    "LEGACY_YFT_RUNTIME_HEADERS",
    "PH_ARTICULATED_BODY_TYPE_EUPHORIA_VFT",
    "PH_JOINT_1DOF_TYPE_VFT",
    "PH_JOINT_3DOF_TYPE_VFT",
    "RESOURCE_STATE",
    "YftRuntimeHeaders",
    "yft_runtime_headers",
]
