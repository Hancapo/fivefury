from __future__ import annotations

from ..resource import ResourceWriter
from .model import YdrJoints

_JOINTS_VFT = 0x40617800
_ROTATION_LIMIT_SIZE = 0xC0
_TRANSLATION_LIMIT_SIZE = 0x40


def _write_rotation_limits(system: ResourceWriter, joints: YdrJoints) -> int:
    if not joints.rotation_limits:
        return 0
    base_off = system.alloc(len(joints.rotation_limits) * _ROTATION_LIMIT_SIZE, 16)
    for index, limit in enumerate(joints.rotation_limits):
        off = base_off + (index * _ROTATION_LIMIT_SIZE)
        system.pack_into("I", off + 0x00, int(limit.unknown_0h))
        system.pack_into("I", off + 0x04, int(limit.unknown_4h))
        system.pack_into("H", off + 0x08, int(limit.bone_id) & 0xFFFF)
        system.pack_into("H", off + 0x0A, int(limit.unknown_ah) & 0xFFFF)
        system.pack_into("I", off + 0x0C, int(limit.num_control_points))
        system.pack_into("I", off + 0x10, int(limit.joint_dofs))
        system.pack_into("I", off + 0x14, int(limit.unknown_14h))
        system.pack_into("I", off + 0x18, int(limit.unknown_18h))
        system.pack_into("I", off + 0x1C, int(limit.unknown_1ch))
        system.pack_into("I", off + 0x20, int(limit.unknown_20h))
        system.pack_into("I", off + 0x24, int(limit.unknown_24h))
        system.pack_into("I", off + 0x28, int(limit.unknown_28h))
        system.pack_into("f", off + 0x2C, float(limit.unknown_2ch))
        system.pack_into("I", off + 0x30, int(limit.unknown_30h))
        system.pack_into("I", off + 0x34, int(limit.unknown_34h))
        system.pack_into("I", off + 0x38, int(limit.unknown_38h))
        system.pack_into("I", off + 0x3C, int(limit.unknown_3ch))
        system.pack_into("f", off + 0x40, float(limit.unknown_40h))
        system.pack_into("I", off + 0x44, int(limit.unknown_44h))
        system.pack_into("I", off + 0x48, int(limit.unknown_48h))
        system.pack_into("I", off + 0x4C, int(limit.unknown_4ch))
        system.pack_into("f", off + 0x50, float(limit.twist_limit_min))
        system.pack_into("f", off + 0x54, float(limit.twist_limit_max))
        system.pack_into("f", off + 0x58, float(limit.soft_limit_scale))
        system.pack_into("3f", off + 0x5C, *[float(v) for v in limit.min])
        system.pack_into("3f", off + 0x68, *[float(v) for v in limit.max])
        system.pack_into("f", off + 0x74, float(limit.unknown_74h))
        system.pack_into("f", off + 0x78, float(limit.unknown_78h))
        system.pack_into("f", off + 0x7C, float(limit.unknown_7ch))
        system.pack_into("f", off + 0x80, float(limit.unknown_80h))
        system.pack_into("f", off + 0x84, float(limit.unknown_84h))
        system.pack_into("f", off + 0x88, float(limit.unknown_88h))
        system.pack_into("f", off + 0x8C, float(limit.unknown_8ch))
        system.pack_into("f", off + 0x90, float(limit.unknown_90h))
        system.pack_into("f", off + 0x94, float(limit.unknown_94h))
        system.pack_into("f", off + 0x98, float(limit.unknown_98h))
        system.pack_into("f", off + 0x9C, float(limit.unknown_9ch))
        system.pack_into("f", off + 0xA0, float(limit.unknown_a0h))
        system.pack_into("f", off + 0xA4, float(limit.unknown_a4h))
        system.pack_into("f", off + 0xA8, float(limit.unknown_a8h))
        system.pack_into("f", off + 0xAC, float(limit.unknown_ach))
        system.pack_into("f", off + 0xB0, float(limit.unknown_b0h))
        system.pack_into("f", off + 0xB4, float(limit.unknown_b4h))
        system.pack_into("f", off + 0xB8, float(limit.unknown_b8h))
        system.pack_into("I", off + 0xBC, int(limit.unknown_bch))
    return base_off


def _write_translation_limits(system: ResourceWriter, joints: YdrJoints) -> int:
    if not joints.translation_limits:
        return 0
    base_off = system.alloc(len(joints.translation_limits) * _TRANSLATION_LIMIT_SIZE, 16)
    for index, limit in enumerate(joints.translation_limits):
        off = base_off + (index * _TRANSLATION_LIMIT_SIZE)
        system.pack_into("I", off + 0x00, int(limit.unknown_0h))
        system.pack_into("I", off + 0x04, int(limit.unknown_4h))
        system.pack_into("I", off + 0x08, int(limit.bone_id))
        system.pack_into("I", off + 0x0C, int(limit.unknown_ch))
        system.pack_into("I", off + 0x10, int(limit.unknown_10h))
        system.pack_into("I", off + 0x14, int(limit.unknown_14h))
        system.pack_into("I", off + 0x18, int(limit.unknown_18h))
        system.pack_into("I", off + 0x1C, int(limit.unknown_1ch))
        system.pack_into("3f", off + 0x20, *[float(v) for v in limit.min])
        system.pack_into("I", off + 0x2C, int(limit.unknown_2ch))
        system.pack_into("3f", off + 0x30, *[float(v) for v in limit.max])
        system.pack_into("I", off + 0x3C, int(limit.unknown_3ch))
    return base_off


def write_joints(system: ResourceWriter, joints: YdrJoints | None, *, virtual) -> int:
    if joints is None or not joints.has_limits:
        return 0
    joints = joints.build()
    rotation_limits_off = _write_rotation_limits(system, joints)
    translation_limits_off = _write_translation_limits(system, joints)
    joints_off = system.alloc(0x40, 16)
    system.pack_into("I", joints_off + 0x00, int(joints.vft or _JOINTS_VFT))
    system.pack_into("I", joints_off + 0x04, int(joints.unknown_4h))
    system.pack_into("Q", joints_off + 0x08, int(joints.unknown_8h))
    system.pack_into("Q", joints_off + 0x10, virtual(rotation_limits_off) if rotation_limits_off else 0)
    system.pack_into("Q", joints_off + 0x18, virtual(translation_limits_off) if translation_limits_off else 0)
    system.pack_into("Q", joints_off + 0x20, int(joints.unknown_20h))
    system.pack_into("Q", joints_off + 0x28, int(joints.unknown_28h))
    system.pack_into("H", joints_off + 0x30, len(joints.rotation_limits))
    system.pack_into("H", joints_off + 0x32, len(joints.translation_limits))
    system.pack_into("H", joints_off + 0x34, int(joints.unknown_34h))
    system.pack_into("H", joints_off + 0x36, int(joints.unknown_36h))
    system.pack_into("Q", joints_off + 0x38, int(joints.unknown_38h))
    return joints_off


__all__ = ["write_joints"]
