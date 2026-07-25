"""Runtime class headers used by legacy GTA V fragment resources."""

RESOURCE_STATE = 1

# Shared by the base-game breakable-prop fragments used as binary donors.
FRAG_PHYSICS_LOD_VFT = 0x406036D8
FRAG_PHYS_TRANSFORMS_VFT = 0x40600810
FRAG_PHYS_ARCHETYPE_DAMP_VFT = 0x4062A988
FRAG_TYPE_CHILD_VFT = 0x40604F10

# Euphoria body and joint classes are explicit and are never inferred for props.
PH_ARTICULATED_BODY_TYPE_EUPHORIA_VFT = 0x4062B8F8
PH_JOINT_1DOF_TYPE_VFT = 0x4062BCB0
PH_JOINT_3DOF_TYPE_VFT = 0x4062BC40

__all__ = [
    "FRAG_PHYSICS_LOD_VFT",
    "FRAG_PHYS_ARCHETYPE_DAMP_VFT",
    "FRAG_PHYS_TRANSFORMS_VFT",
    "FRAG_TYPE_CHILD_VFT",
    "PH_ARTICULATED_BODY_TYPE_EUPHORIA_VFT",
    "PH_JOINT_1DOF_TYPE_VFT",
    "PH_JOINT_3DOF_TYPE_VFT",
    "RESOURCE_STATE",
]
