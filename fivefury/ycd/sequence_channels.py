from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum

from .sequence_tracks import (
    get_ycd_track_name,
    is_ycd_camera_track,
    is_ycd_facial_track,
    is_ycd_object_track,
    is_ycd_position_track,
    is_ycd_root_motion_track,
    is_ycd_rotation_track,
    is_ycd_uv_track,
)


class YcdChannelType(IntEnum):
    STATIC_QUATERNION = 0
    STATIC_VECTOR3 = 1
    STATIC_FLOAT = 2
    RAW_FLOAT = 3
    QUANTIZE_FLOAT = 4
    INDIRECT_QUANTIZE_FLOAT = 5
    LINEAR_FLOAT = 6
    CACHED_QUATERNION1 = 7
    CACHED_QUATERNION2 = 8


@dataclass(slots=True)
class YcdSequenceRootChannelRef:
    raw_bytes: bytes

    @classmethod
    def build(
        cls,
        channel_type: int | YcdChannelType,
        channel_index: int,
        data_int_offset: int,
        frame_bit_offset: int,
    ) -> YcdSequenceRootChannelRef:
        return cls(
            bytes(
                (
                    int(channel_type) & 0xFF,
                    int(channel_index) & 0xFF,
                    int(data_int_offset) & 0xFF,
                    (int(data_int_offset) >> 8) & 0xFF,
                    int(frame_bit_offset) & 0xFF,
                    (int(frame_bit_offset) >> 8) & 0xFF,
                )
            )
        )

    @property
    def channel_type(self) -> int:
        return int(self.raw_bytes[0]) if self.raw_bytes else 0

    @property
    def channel_index(self) -> int:
        return int(self.raw_bytes[1]) if len(self.raw_bytes) >= 2 else 0

    @property
    def data_int_offset(self) -> int:
        if len(self.raw_bytes) < 4:
            return 0
        return int(self.raw_bytes[2] | (self.raw_bytes[3] << 8))

    @property
    def frame_bit_offset(self) -> int:
        if len(self.raw_bytes) < 6:
            return 0
        return int(self.raw_bytes[4] | (self.raw_bytes[5] << 8))


@dataclass(slots=True)
class YcdAnimChannel:
    channel_type: YcdChannelType
    sequence_index: int = 0
    channel_index: int = 0
    data_offset: int = 0
    frame_offset: int = 0

    @property
    def component_count(self) -> int:
        return 1

    def evaluate_float(self, frame: int) -> float:
        return 0.0

    def evaluate_components(self, frame: int) -> tuple[float, ...]:
        return (self.evaluate_float(frame),)


@dataclass(slots=True)
class YcdStaticFloatChannel(YcdAnimChannel):
    value: float = 0.0

    def evaluate_float(self, frame: int) -> float:
        return float(self.value)


@dataclass(slots=True)
class YcdStaticVector3Channel(YcdAnimChannel):
    value: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def component_count(self) -> int:
        return 3

    def evaluate_components(self, frame: int) -> tuple[float, ...]:
        return self.value


@dataclass(slots=True)
class YcdStaticQuaternionChannel(YcdAnimChannel):
    value: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

    @property
    def component_count(self) -> int:
        return 4

    def evaluate_components(self, frame: int) -> tuple[float, ...]:
        return self.value


@dataclass(slots=True)
class YcdRawFloatChannel(YcdAnimChannel):
    values: list[float] = field(default_factory=list)

    def evaluate_float(self, frame: int) -> float:
        if not self.values:
            return 0.0
        return float(self.values[int(frame) % len(self.values)])


@dataclass(slots=True)
class YcdQuantizeFloatChannel(YcdAnimChannel):
    value_bits: int = 0
    quantum: float = 0.0
    offset: float = 0.0
    values: list[float] = field(default_factory=list)
    value_list: list[int] = field(default_factory=list)

    def evaluate_float(self, frame: int) -> float:
        if not self.values:
            return float(self.offset)
        return float(self.values[int(frame) % len(self.values)])


@dataclass(slots=True)
class YcdIndirectQuantizeFloatChannel(YcdAnimChannel):
    frame_bits: int = 0
    value_bits: int = 0
    num_ints: int = 0
    quantum: float = 0.0
    offset: float = 0.0
    values: list[float] = field(default_factory=list)
    value_list: list[int] = field(default_factory=list)
    frames: list[int] = field(default_factory=list)

    def evaluate_float(self, frame: int) -> float:
        if not self.frames or not self.values:
            return float(self.offset)
        value_index = self.frames[int(frame) % len(self.frames)]
        if value_index >= len(self.values):
            return float(self.offset)
        return float(self.values[value_index])


@dataclass(slots=True)
class YcdLinearFloatChannel(YcdAnimChannel):
    num_ints: int = 0
    counts: int = 0
    quantum: float = 0.0
    offset: float = 0.0
    values: list[float] = field(default_factory=list)
    value_list: list[int] = field(default_factory=list)

    def evaluate_float(self, frame: int) -> float:
        if not self.values:
            return float(self.offset)
        return float(self.values[int(frame) % len(self.values)])


@dataclass(slots=True)
class YcdCachedQuaternionChannel(YcdAnimChannel):
    quat_index: int = 3
    parent_sequence: YcdAnimSequence | None = None

    def evaluate_float(self, frame: int) -> float:
        sequence = self.parent_sequence
        if sequence is None:
            return 0.0
        xyz: list[float] = []
        for channel in sequence.channels:
            if channel is self:
                continue
            components = channel.evaluate_components(frame)
            xyz.extend(float(value) for value in components)
            if len(xyz) >= 3:
                break
        if len(xyz) < 3:
            return 0.0
        x, y, z = xyz[:3]
        return float(math.sqrt(max(1.0 - ((x * x) + (y * y) + (z * z)), 0.0)))


@dataclass(slots=True)
class YcdAnimSequence:
    channels: list[YcdAnimChannel] = field(default_factory=list)
    bone_id: object | None = None
    is_cached_quaternion: bool = False

    @property
    def track(self) -> int | None:
        return getattr(self.bone_id, "track", None)

    @property
    def track_name(self) -> str | None:
        if self.track is None:
            return None
        return get_ycd_track_name(self.track)

    @property
    def is_uv_animation(self) -> bool:
        return self.track is not None and is_ycd_uv_track(self.track)

    @property
    def is_object_animation(self) -> bool:
        return self.track is not None and is_ycd_object_track(self.track)

    @property
    def is_camera_animation(self) -> bool:
        return self.track is not None and is_ycd_camera_track(self.track)

    @property
    def is_root_motion(self) -> bool:
        return self.track is not None and is_ycd_root_motion_track(self.track)

    @property
    def is_facial_animation(self) -> bool:
        return self.track is not None and is_ycd_facial_track(self.track)

    @property
    def is_position_track(self) -> bool:
        return self.track is not None and is_ycd_position_track(self.track)

    @property
    def is_rotation_track(self) -> bool:
        return self.track is not None and is_ycd_rotation_track(self.track)

    def evaluate_components(self, frame: int) -> tuple[float, ...]:
        values: list[float] = []
        for channel in self.channels:
            values.extend(float(value) for value in channel.evaluate_components(frame))
            if len(values) >= 4:
                break
        while len(values) < 4:
            values.append(0.0)
        return tuple(values[:4])

    def evaluate_vector4(self, frame: int) -> tuple[float, float, float, float]:
        values = self.evaluate_components(frame)
        return (float(values[0]), float(values[1]), float(values[2]), float(values[3]))

    def evaluate_vector3(self, frame: int) -> tuple[float, float, float]:
        values = self.evaluate_components(frame)
        return (float(values[0]), float(values[1]), float(values[2]))

    def evaluate_quaternion(self, frame: int) -> tuple[float, float, float, float]:
        if not self.is_cached_quaternion:
            return self.evaluate_vector4(frame)

        xyz: list[float] = []
        normalized = 0.0
        quat_index = 3
        for channel in self.channels:
            if isinstance(channel, YcdCachedQuaternionChannel):
                normalized = channel.evaluate_float(frame)
                quat_index = int(channel.quat_index)
                continue
            xyz.extend(float(value) for value in channel.evaluate_components(frame))
            if len(xyz) >= 3:
                xyz = xyz[:3]
                break
        while len(xyz) < 3:
            xyz.append(0.0)
        x, y, z = xyz[:3]
        if quat_index == 0:
            return (normalized, x, y, z)
        if quat_index == 1:
            return (x, normalized, y, z)
        if quat_index == 2:
            return (x, y, normalized, z)
        return (x, y, z, normalized)


def channel_frame_bits(channel: YcdAnimChannel) -> int:
    if isinstance(channel, YcdRawFloatChannel):
        return 32
    if isinstance(channel, YcdQuantizeFloatChannel):
        return int(channel.value_bits)
    if isinstance(channel, YcdIndirectQuantizeFloatChannel):
        return int(channel.frame_bits)
    return 0


__all__ = [
    "YcdAnimChannel",
    "YcdAnimSequence",
    "YcdCachedQuaternionChannel",
    "YcdChannelType",
    "YcdIndirectQuantizeFloatChannel",
    "YcdLinearFloatChannel",
    "YcdQuantizeFloatChannel",
    "YcdRawFloatChannel",
    "YcdSequenceRootChannelRef",
    "YcdStaticFloatChannel",
    "YcdStaticQuaternionChannel",
    "YcdStaticVector3Channel",
    "channel_frame_bits",
]
