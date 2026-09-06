from __future__ import annotations

import dataclasses
import math

from ...vector import Vector3


@dataclasses.dataclass(slots=True)
class YdrJointControlPoint:
    max_swing: float = 0.0
    min_twist: float = 0.0
    max_twist: float = 0.0


@dataclasses.dataclass(slots=True)
class YdrJointRotationLimit:
    bone_id: int = 0
    unknown_ah: int = 0
    unknown_0h: int = 0
    unknown_4h: int = 0
    unknown_14h: int = 0
    unknown_18h: int = 0
    unknown_1ch: int = 0
    unknown_20h: int = 0
    unknown_24h: int = 0
    unknown_28h: int = 0
    unknown_30h: int = 0
    unknown_34h: int = 0
    unknown_38h: int = 0
    unknown_3ch: int = 0
    unknown_44h: int = 0
    unknown_48h: int = 0
    unknown_4ch: int = 0
    unknown_bch: int = 0x100
    num_control_points: int = 1
    joint_dofs: int = 3
    unknown_2ch: float = 1.0
    unknown_40h: float = 1.0
    soft_limit_scale: float = 1.0
    min: Vector3 = dataclasses.field(default_factory=Vector3)
    max: Vector3 = dataclasses.field(default_factory=Vector3)
    twist_limit_min: float = -math.pi
    twist_limit_max: float = math.pi
    unknown_74h: float = math.pi
    unknown_78h: float = -math.pi
    unknown_7ch: float = math.pi
    unknown_80h: float = math.pi
    unknown_84h: float = -math.pi
    unknown_88h: float = math.pi
    unknown_8ch: float = math.pi
    unknown_90h: float = -math.pi
    unknown_94h: float = math.pi
    unknown_98h: float = math.pi
    unknown_9ch: float = -math.pi
    unknown_a0h: float = math.pi
    unknown_a4h: float = math.pi
    unknown_a8h: float = -math.pi
    unknown_ach: float = math.pi
    unknown_b0h: float = math.pi
    unknown_b4h: float = -math.pi
    unknown_b8h: float = math.pi

    def build(self) -> YdrJointRotationLimit:
        if not isinstance(self.min, Vector3) or not isinstance(self.max, Vector3):
            raise TypeError("joint limit bounds must be Vector3 values")
        self.num_control_points = int(self.num_control_points)
        self.joint_dofs = int(self.joint_dofs)
        return self


@dataclasses.dataclass(slots=True)
class YdrJointTranslationLimit:
    bone_id: int = 0
    min: Vector3 = dataclasses.field(default_factory=Vector3)
    max: Vector3 = dataclasses.field(default_factory=Vector3)
    unknown_0h: int = 0
    unknown_4h: int = 0
    unknown_ch: int = 0
    unknown_10h: int = 0
    unknown_14h: int = 0
    unknown_18h: int = 0
    unknown_1ch: int = 0
    unknown_2ch: int = 0
    unknown_3ch: int = 0

    def build(self) -> YdrJointTranslationLimit:
        if not isinstance(self.min, Vector3) or not isinstance(self.max, Vector3):
            raise TypeError("joint limit bounds must be Vector3 values")
        return self


@dataclasses.dataclass(slots=True)
class YdrJoints:
    rotation_limits: list[YdrJointRotationLimit] = dataclasses.field(
        default_factory=list
    )
    translation_limits: list[YdrJointTranslationLimit] = dataclasses.field(
        default_factory=list
    )
    vft: int = 0x40617800
    unknown_4h: int = 1
    unknown_8h: int = 0
    unknown_20h: int = 0
    unknown_28h: int = 0
    unknown_34h: int = 0
    unknown_36h: int = 1
    unknown_38h: int = 0

    @property
    def has_limits(self) -> bool:
        return bool(self.rotation_limits or self.translation_limits)

    def build(self) -> YdrJoints:
        self.vft = int(self.vft)
        self.unknown_4h = int(self.unknown_4h)
        self.unknown_8h = int(self.unknown_8h)
        self.unknown_20h = int(self.unknown_20h)
        self.unknown_28h = int(self.unknown_28h)
        self.unknown_34h = int(self.unknown_34h)
        self.unknown_36h = int(self.unknown_36h)
        self.unknown_38h = int(self.unknown_38h)
        for limit in self.rotation_limits:
            limit.build()
        for limit in self.translation_limits:
            limit.build()
        return self

    def rotation_limit(
        self,
        *,
        bone_id: int,
        min: Vector3 = Vector3(),
        max: Vector3 = Vector3(),
        unknown_ah: int = 0,
        num_control_points: int = 1,
        joint_dofs: int = 3,
    ) -> YdrJointRotationLimit:
        limit = YdrJointRotationLimit(
            bone_id=int(bone_id),
            min=min,
            max=max,
            unknown_ah=int(unknown_ah) & 0xFFFF,
            num_control_points=int(num_control_points),
            joint_dofs=int(joint_dofs),
        )
        self.rotation_limits.append(limit)
        return limit

    def translation_limit(
        self,
        *,
        bone_id: int,
        min: Vector3 = Vector3(),
        max: Vector3 = Vector3(),
    ) -> YdrJointTranslationLimit:
        limit = YdrJointTranslationLimit(
            bone_id=int(bone_id),
            min=min,
            max=max,
        )
        self.translation_limits.append(limit)
        return limit
