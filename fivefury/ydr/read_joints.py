from __future__ import annotations

from typing import Callable

from .model import (
    YdrJointRotationLimit,
    YdrJointTranslationLimit,
    YdrJoints,
)

_ROTATION_LIMIT_SIZE = 0xC0
_TRANSLATION_LIMIT_SIZE = 0x40


def _read_rotation_limit(
    system_data: bytes,
    offset: int,
    *,
    u16: Callable[[bytes, int], int],
    u32: Callable[[bytes, int], int],
    f32: Callable[[bytes, int], float],
    vec3: Callable[[bytes, int], tuple[float, float, float]],
) -> YdrJointRotationLimit:
    return YdrJointRotationLimit(
        bone_id=u16(system_data, offset + 0x08),
        unknown_ah=u16(system_data, offset + 0x0A),
        unknown_0h=u32(system_data, offset + 0x00),
        unknown_4h=u32(system_data, offset + 0x04),
        num_control_points=u32(system_data, offset + 0x0C),
        joint_dofs=u32(system_data, offset + 0x10),
        unknown_14h=u32(system_data, offset + 0x14),
        unknown_18h=u32(system_data, offset + 0x18),
        unknown_1ch=u32(system_data, offset + 0x1C),
        unknown_20h=u32(system_data, offset + 0x20),
        unknown_24h=u32(system_data, offset + 0x24),
        unknown_28h=u32(system_data, offset + 0x28),
        unknown_2ch=f32(system_data, offset + 0x2C),
        unknown_30h=u32(system_data, offset + 0x30),
        unknown_34h=u32(system_data, offset + 0x34),
        unknown_38h=u32(system_data, offset + 0x38),
        unknown_3ch=u32(system_data, offset + 0x3C),
        unknown_40h=f32(system_data, offset + 0x40),
        unknown_44h=u32(system_data, offset + 0x44),
        unknown_48h=u32(system_data, offset + 0x48),
        unknown_4ch=u32(system_data, offset + 0x4C),
        twist_limit_min=f32(system_data, offset + 0x50),
        twist_limit_max=f32(system_data, offset + 0x54),
        soft_limit_scale=f32(system_data, offset + 0x58),
        min=vec3(system_data, offset + 0x5C),
        max=vec3(system_data, offset + 0x68),
        unknown_74h=f32(system_data, offset + 0x74),
        unknown_78h=f32(system_data, offset + 0x78),
        unknown_7ch=f32(system_data, offset + 0x7C),
        unknown_80h=f32(system_data, offset + 0x80),
        unknown_84h=f32(system_data, offset + 0x84),
        unknown_88h=f32(system_data, offset + 0x88),
        unknown_8ch=f32(system_data, offset + 0x8C),
        unknown_90h=f32(system_data, offset + 0x90),
        unknown_94h=f32(system_data, offset + 0x94),
        unknown_98h=f32(system_data, offset + 0x98),
        unknown_9ch=f32(system_data, offset + 0x9C),
        unknown_a0h=f32(system_data, offset + 0xA0),
        unknown_a4h=f32(system_data, offset + 0xA4),
        unknown_a8h=f32(system_data, offset + 0xA8),
        unknown_ach=f32(system_data, offset + 0xAC),
        unknown_b0h=f32(system_data, offset + 0xB0),
        unknown_b4h=f32(system_data, offset + 0xB4),
        unknown_b8h=f32(system_data, offset + 0xB8),
        unknown_bch=u32(system_data, offset + 0xBC),
    )


def _read_translation_limit(
    system_data: bytes,
    offset: int,
    *,
    u32: Callable[[bytes, int], int],
    vec3: Callable[[bytes, int], tuple[float, float, float]],
) -> YdrJointTranslationLimit:
    return YdrJointTranslationLimit(
        bone_id=u32(system_data, offset + 0x08),
        min=vec3(system_data, offset + 0x20),
        max=vec3(system_data, offset + 0x30),
        unknown_0h=u32(system_data, offset + 0x00),
        unknown_4h=u32(system_data, offset + 0x04),
        unknown_ch=u32(system_data, offset + 0x0C),
        unknown_10h=u32(system_data, offset + 0x10),
        unknown_14h=u32(system_data, offset + 0x14),
        unknown_18h=u32(system_data, offset + 0x18),
        unknown_1ch=u32(system_data, offset + 0x1C),
        unknown_2ch=u32(system_data, offset + 0x2C),
        unknown_3ch=u32(system_data, offset + 0x3C),
    )


def parse_joints(
    system_data: bytes,
    pointer: int,
    *,
    virtual_offset: Callable[[int, bytes], int],
    u16: Callable[[bytes, int], int],
    u32: Callable[[bytes, int], int],
    u64: Callable[[bytes, int], int],
    f32: Callable[[bytes, int], float],
    vec3: Callable[[bytes, int], tuple[float, float, float]],
) -> YdrJoints | None:
    if not pointer:
        return None
    joints_off = virtual_offset(pointer, system_data)
    rotation_limits_pointer = u64(system_data, joints_off + 0x10)
    translation_limits_pointer = u64(system_data, joints_off + 0x18)
    rotation_limits_count = u16(system_data, joints_off + 0x30)
    translation_limits_count = u16(system_data, joints_off + 0x32)

    rotation_limits: list[YdrJointRotationLimit] = []
    if rotation_limits_pointer and rotation_limits_count:
        rotation_limits_off = virtual_offset(rotation_limits_pointer, system_data)
        for index in range(rotation_limits_count):
            rotation_limits.append(
                _read_rotation_limit(
                    system_data,
                    rotation_limits_off + (index * _ROTATION_LIMIT_SIZE),
                    u16=u16,
                    u32=u32,
                    f32=f32,
                    vec3=vec3,
                )
            )

    translation_limits: list[YdrJointTranslationLimit] = []
    if translation_limits_pointer and translation_limits_count:
        translation_limits_off = virtual_offset(translation_limits_pointer, system_data)
        for index in range(translation_limits_count):
            translation_limits.append(
                _read_translation_limit(
                    system_data,
                    translation_limits_off + (index * _TRANSLATION_LIMIT_SIZE),
                    u32=u32,
                    vec3=vec3,
                )
            )

    return YdrJoints(
        rotation_limits=rotation_limits,
        translation_limits=translation_limits,
        vft=u32(system_data, joints_off + 0x00),
        unknown_4h=u32(system_data, joints_off + 0x04),
        unknown_8h=u64(system_data, joints_off + 0x08),
        unknown_20h=u64(system_data, joints_off + 0x20),
        unknown_28h=u64(system_data, joints_off + 0x28),
        unknown_34h=u16(system_data, joints_off + 0x34),
        unknown_36h=u16(system_data, joints_off + 0x36),
        unknown_38h=u64(system_data, joints_off + 0x38),
    )


__all__ = ["parse_joints"]
