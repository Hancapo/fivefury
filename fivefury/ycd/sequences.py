from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum

from ..binary import f32 as _f32, i32 as _i32, u16 as _u16, u32 as _u32


class YcdAnimationTrack(IntEnum):
    POSITION = 0
    ROTATION = 1
    ROOT_POSITION = 5
    ROOT_ROTATION = 6
    CAMERA_POSITION = 7
    CAMERA_ROTATION = 8
    UV0 = 17
    UV1 = 18
    BONE_SCALE = 24
    BONE_POSITION = 25
    BONE_ROTATION = 26
    CAMERA_TRACK_27 = 27
    CAMERA_TRACK_28 = 28
    CAMERA_TRACK_36 = 36
    CAMERA_TRACK_40 = 40
    CAMERA_TRACK_43 = 43
    CAMERA_TRACK_44 = 44
    CAMERA_TRACK_45 = 45
    CAMERA_TRACK_46 = 46
    CAMERA_TRACK_49 = 49
    CAMERA_TRACK_51 = 51
    CAMERA_TRACK_52 = 52


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


TRACK_NAME_BY_ID = {
    YcdAnimationTrack.POSITION: "POSITION",
    YcdAnimationTrack.ROTATION: "ROTATION",
    YcdAnimationTrack.ROOT_POSITION: "ROOT_POSITION",
    YcdAnimationTrack.ROOT_ROTATION: "ROOT_ROTATION",
    YcdAnimationTrack.CAMERA_POSITION: "CAMERA_POSITION",
    YcdAnimationTrack.CAMERA_ROTATION: "CAMERA_ROTATION",
    YcdAnimationTrack.UV0: "UV0",
    YcdAnimationTrack.UV1: "UV1",
    YcdAnimationTrack.BONE_SCALE: "BONE_SCALE",
    YcdAnimationTrack.BONE_POSITION: "BONE_POSITION",
    YcdAnimationTrack.BONE_ROTATION: "BONE_ROTATION",
    YcdAnimationTrack.CAMERA_TRACK_27: "CAMERA_TRACK_27",
    YcdAnimationTrack.CAMERA_TRACK_28: "CAMERA_TRACK_28",
    YcdAnimationTrack.CAMERA_TRACK_36: "CAMERA_TRACK_36",
    YcdAnimationTrack.CAMERA_TRACK_40: "CAMERA_TRACK_40",
    YcdAnimationTrack.CAMERA_TRACK_43: "CAMERA_TRACK_43",
    YcdAnimationTrack.CAMERA_TRACK_44: "CAMERA_TRACK_44",
    YcdAnimationTrack.CAMERA_TRACK_45: "CAMERA_TRACK_45",
    YcdAnimationTrack.CAMERA_TRACK_46: "CAMERA_TRACK_46",
    YcdAnimationTrack.CAMERA_TRACK_49: "CAMERA_TRACK_49",
    YcdAnimationTrack.CAMERA_TRACK_51: "CAMERA_TRACK_51",
    YcdAnimationTrack.CAMERA_TRACK_52: "CAMERA_TRACK_52",
}


CAMERA_TRACK_IDS = frozenset(
    {
        int(YcdAnimationTrack.CAMERA_POSITION),
        int(YcdAnimationTrack.CAMERA_ROTATION),
        int(YcdAnimationTrack.CAMERA_TRACK_27),
        int(YcdAnimationTrack.CAMERA_TRACK_28),
        int(YcdAnimationTrack.CAMERA_TRACK_36),
        int(YcdAnimationTrack.CAMERA_TRACK_40),
        int(YcdAnimationTrack.CAMERA_TRACK_43),
        int(YcdAnimationTrack.CAMERA_TRACK_44),
        int(YcdAnimationTrack.CAMERA_TRACK_45),
        int(YcdAnimationTrack.CAMERA_TRACK_46),
        int(YcdAnimationTrack.CAMERA_TRACK_49),
        int(YcdAnimationTrack.CAMERA_TRACK_51),
        int(YcdAnimationTrack.CAMERA_TRACK_52),
    }
)

ROOT_MOTION_TRACK_IDS = frozenset(
    {
        int(YcdAnimationTrack.ROOT_POSITION),
        int(YcdAnimationTrack.ROOT_ROTATION),
    }
)

BONE_TRACK_IDS = frozenset(
    {
        int(YcdAnimationTrack.BONE_SCALE),
        int(YcdAnimationTrack.BONE_POSITION),
        int(YcdAnimationTrack.BONE_ROTATION),
    }
)


def get_ycd_track_name(track: int) -> str:
    try:
        return TRACK_NAME_BY_ID[YcdAnimationTrack(int(track))]
    except ValueError:
        return f"TRACK_{int(track)}"


def is_ycd_uv_track(track: int) -> bool:
    return int(track) in (int(YcdAnimationTrack.UV0), int(YcdAnimationTrack.UV1))


def is_ycd_object_track(track: int) -> bool:
    return int(track) in (int(YcdAnimationTrack.POSITION), int(YcdAnimationTrack.ROTATION))


def is_ycd_camera_track(track: int) -> bool:
    return int(track) in CAMERA_TRACK_IDS


def is_ycd_root_motion_track(track: int) -> bool:
    return int(track) in ROOT_MOTION_TRACK_IDS


def is_ycd_bone_track(track: int) -> bool:
    return int(track) in BONE_TRACK_IDS


def is_ycd_position_track(track: int) -> bool:
    return int(track) in (int(YcdAnimationTrack.POSITION), int(YcdAnimationTrack.ROOT_POSITION))


def is_ycd_rotation_track(track: int) -> bool:
    return int(track) in (int(YcdAnimationTrack.ROTATION), int(YcdAnimationTrack.ROOT_ROTATION))


@dataclass(slots=True)
class YcdSequenceRootChannelRef:
    raw_bytes: bytes

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
    def is_bone_animation(self) -> bool:
        return self.track is not None and is_ycd_bone_track(self.track)

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


class _ChannelDataReader:
    def __init__(self, data: bytes, num_frames: int, chunk_size: int, frame_offset: int, frame_length: int) -> None:
        self.data = data
        self.num_frames = int(num_frames)
        self.chunk_size = int(chunk_size)
        self.position = 0
        self.frame = 0
        self.frame_offset = int(frame_offset)
        self.frame_length = int(frame_length)
        self.channel_list_offset = self.frame_offset + (self.frame_length * self.num_frames)
        self.channel_data_offset = self.channel_list_offset + (9 * 2)
        self.channel_frame_offset = 0
        self.bit_position = 0

    def read_int32(self) -> int:
        value = _i32(self.data, self.position)
        self.position += 4
        return value

    def read_single(self) -> float:
        value = _f32(self.data, self.position)
        self.position += 4
        return value

    def read_vector3(self) -> tuple[float, float, float]:
        value = (
            _f32(self.data, self.position),
            _f32(self.data, self.position + 4),
            _f32(self.data, self.position + 8),
        )
        self.position += 12
        return value

    def get_bits(self, start_bit: int, length: int) -> int:
        if start_bit < 0:
            return 0
        start_byte = start_bit // 8
        bit_offset = start_bit % 8
        result = 0
        shift = -bit_offset
        cur_byte = start_byte
        bits_remaining = int(length)
        while bits_remaining > 0:
            byte = int(self.data[cur_byte]) if cur_byte < len(self.data) else 0
            cur_byte += 1
            shifted_byte = (byte >> -shift) if shift < 0 else (byte << shift)
            bit_mask = ((1 << min(bits_remaining, 8)) - 1) << max(shift, 0)
            result += shifted_byte & bit_mask
            bits_remaining -= 8 + min(shift, 0)
            shift += 8
        return int(result)

    def read_bits(self, length: int) -> int:
        value = self.get_bits(self.bit_position, length)
        self.bit_position += int(length)
        return int(value)

    def read_channel_count(self) -> int:
        value = _u16(self.data, self.channel_list_offset)
        self.channel_list_offset += 2
        return int(value)

    def read_channel_data_bits(self) -> int:
        value = _u16(self.data, self.channel_data_offset)
        self.channel_data_offset += 2
        return int(value)

    def read_channel_data_bytes(self, count: int) -> bytes:
        result = bytes(self.data[self.channel_data_offset : self.channel_data_offset + count])
        self.channel_data_offset += int(count)
        return result

    def align_channel_data_offset(self, channel_count: int) -> None:
        remainder = int(channel_count) % 4
        if remainder > 0:
            self.channel_data_offset += (4 - remainder) * 2

    def begin_frame(self, frame: int) -> None:
        self.frame = int(frame)
        self.channel_frame_offset = (self.frame_offset + (self.frame_length * self.frame)) * 8

    def read_frame_bits(self, count: int) -> int:
        value = self.get_bits(self.channel_frame_offset, count)
        self.channel_frame_offset += int(count)
        return int(value)


def _construct_channel(channel_type: YcdChannelType) -> YcdAnimChannel:
    if channel_type is YcdChannelType.STATIC_QUATERNION:
        return YcdStaticQuaternionChannel(channel_type=channel_type)
    if channel_type is YcdChannelType.STATIC_VECTOR3:
        return YcdStaticVector3Channel(channel_type=channel_type)
    if channel_type is YcdChannelType.STATIC_FLOAT:
        return YcdStaticFloatChannel(channel_type=channel_type)
    if channel_type is YcdChannelType.RAW_FLOAT:
        return YcdRawFloatChannel(channel_type=channel_type)
    if channel_type is YcdChannelType.QUANTIZE_FLOAT:
        return YcdQuantizeFloatChannel(channel_type=channel_type)
    if channel_type is YcdChannelType.INDIRECT_QUANTIZE_FLOAT:
        return YcdIndirectQuantizeFloatChannel(channel_type=channel_type)
    if channel_type is YcdChannelType.LINEAR_FLOAT:
        return YcdLinearFloatChannel(channel_type=channel_type)
    if channel_type is YcdChannelType.CACHED_QUATERNION1:
        return YcdCachedQuaternionChannel(channel_type=channel_type)
    if channel_type is YcdChannelType.CACHED_QUATERNION2:
        return YcdCachedQuaternionChannel(channel_type=channel_type)
    raise ValueError(f"Unsupported YCD channel type: {channel_type}")


def _read_channel(channel: YcdAnimChannel, reader: _ChannelDataReader) -> None:
    if isinstance(channel, YcdStaticFloatChannel):
        channel.value = reader.read_single()
        return
    if isinstance(channel, YcdStaticVector3Channel):
        channel.value = reader.read_vector3()
        return
    if isinstance(channel, YcdStaticQuaternionChannel):
        x, y, z = reader.read_vector3()
        w = math.sqrt(max(1.0 - ((x * x) + (y * y) + (z * z)), 0.0))
        channel.value = (x, y, z, float(w))
        return
    if isinstance(channel, YcdRawFloatChannel):
        channel.values = [0.0] * reader.num_frames
        return
    if isinstance(channel, YcdQuantizeFloatChannel):
        channel.value_bits = reader.read_int32()
        channel.quantum = reader.read_single()
        channel.offset = reader.read_single()
        channel.values = [0.0] * reader.num_frames
        channel.value_list = [0] * reader.num_frames
        return
    if isinstance(channel, YcdIndirectQuantizeFloatChannel):
        channel.frame_bits = reader.read_int32()
        channel.value_bits = reader.read_int32()
        channel.num_ints = reader.read_int32()
        channel.quantum = reader.read_single()
        channel.offset = reader.read_single()
        channel.frames = [0] * reader.num_frames
        num_values0 = (channel.num_ints * 32) // max(channel.value_bits, 1)
        num_values1 = (1 << max(channel.frame_bits, 0)) - 1
        num_values = min(num_values0, num_values1) if channel.value_bits > 0 else 0
        channel.values = [0.0] * num_values
        channel.value_list = [0] * num_values
        reader.bit_position = reader.position * 8
        for index in range(num_values):
            bits = reader.read_bits(channel.value_bits)
            channel.values[index] = (bits * channel.quantum) + channel.offset
            channel.value_list[index] = bits
        reader.position += channel.num_ints * 4
        return
    if isinstance(channel, YcdLinearFloatChannel):
        channel.num_ints = reader.read_int32()
        channel.counts = reader.read_int32()
        channel.quantum = reader.read_single()
        channel.offset = reader.read_single()
        bit = reader.position * 8
        count1 = channel.counts & 0xFF
        count2 = (channel.counts >> 8) & 0xFF
        count3 = (channel.counts >> 16) & 0xFF
        stream_length = len(reader.data) * 8
        num_chunks = (max(reader.chunk_size, 1) + reader.num_frames - 1) // max(reader.chunk_size, 1)
        delta_offset = bit + (num_chunks * (count1 + count2))
        reader.bit_position = bit
        chunk_offsets = [reader.read_bits(count1) if count1 > 0 else 0 for _ in range(num_chunks)]
        chunk_values = [reader.read_bits(count2) if count2 > 0 else 0 for _ in range(num_chunks)]
        frame_values = [0.0] * reader.num_frames
        frame_bits = [0] * reader.num_frames
        for chunk_index in range(num_chunks):
            doffs = chunk_offsets[chunk_index] + delta_offset
            value = chunk_values[chunk_index]
            chunk_start = chunk_index * max(reader.chunk_size, 1)
            reader.bit_position = doffs
            increment = 0
            for local_frame in range(max(reader.chunk_size, 1)):
                frame_index = chunk_start + local_frame
                if frame_index >= reader.num_frames:
                    break
                frame_values[frame_index] = (value * channel.quantum) + channel.offset
                frame_bits[frame_index] = value
                if (local_frame + 1) >= max(reader.chunk_size, 1):
                    break
                delta = reader.read_bits(count3) if count3 != 0 else 0
                start_offset = reader.bit_position
                max_offset = stream_length
                bit_found = 0
                while bit_found == 0:
                    bit_found = reader.read_bits(1)
                    if reader.bit_position >= max_offset:
                        break
                delta |= (reader.bit_position - start_offset - 1) << count3
                if delta != 0 and reader.read_bits(1) == 1:
                    delta = -delta
                increment += delta
                value += increment
        channel.values = frame_values
        channel.value_list = frame_bits
        reader.position -= 16
        reader.position += channel.num_ints * 4
        return
    if isinstance(channel, YcdCachedQuaternionChannel):
        return
    raise TypeError(f"Unsupported YCD channel instance: {type(channel)!r}")


def _read_channel_frame(channel: YcdAnimChannel, reader: _ChannelDataReader) -> None:
    if isinstance(channel, YcdRawFloatChannel):
        bits = reader.read_frame_bits(32)
        channel.values[reader.frame] = _f32(bits.to_bytes(4, "little"), 0)
        return
    if isinstance(channel, YcdQuantizeFloatChannel):
        bits = reader.read_frame_bits(channel.value_bits)
        channel.values[reader.frame] = (bits * channel.quantum) + channel.offset
        channel.value_list[reader.frame] = bits
        return
    if isinstance(channel, YcdIndirectQuantizeFloatChannel):
        channel.frames[reader.frame] = reader.read_frame_bits(channel.frame_bits)
        return
    if isinstance(channel, YcdLinearFloatChannel):
        return
    if isinstance(channel, (YcdStaticFloatChannel, YcdStaticVector3Channel, YcdStaticQuaternionChannel, YcdCachedQuaternionChannel)):
        return
    raise TypeError(f"Unsupported YCD channel instance: {type(channel)!r}")


def parse_sequence_data(
    raw_data: bytes,
    *,
    num_frames: int,
    chunk_size: int,
    frame_offset: int,
    frame_length: int,
    root_motion_ref_counts: int,
) -> tuple[list[YcdAnimSequence], list[YcdSequenceRootChannelRef], list[YcdSequenceRootChannelRef]]:
    if not raw_data:
        return [], [], []

    reader = _ChannelDataReader(
        raw_data,
        num_frames=num_frames,
        chunk_size=chunk_size,
        frame_offset=frame_offset,
        frame_length=frame_length,
    )
    channel_list: list[tuple[int, int, YcdAnimChannel]] = []
    channel_groups: list[list[YcdAnimChannel]] = [[] for _ in range(9)]
    frame_bit_offset = 0

    for channel_type_index in range(9):
        channel_type = YcdChannelType(channel_type_index)
        channel_count = reader.read_channel_count()
        for _ in range(channel_count):
            channel = _construct_channel(channel_type)
            channel_data_bits = reader.read_channel_data_bits()
            channel.sequence_index = channel_data_bits >> 2
            channel.channel_index = channel_data_bits & 3
            if isinstance(channel, YcdCachedQuaternionChannel):
                channel.quat_index = channel.channel_index
                channel.channel_index = 3 if channel.channel_type is YcdChannelType.CACHED_QUATERNION1 else 4
            channel.data_offset = reader.position // 4
            _read_channel(channel, reader)
            channel.frame_offset = frame_bit_offset
            frame_bit_offset += int(getattr(channel, "value_bits", 0) or 0) if False else channel_frame_bits(channel)
            channel_groups[channel_type_index].append(channel)
            channel_list.append((channel.sequence_index, channel.channel_index, channel))
        reader.align_channel_data_offset(channel_count)

    for frame in range(num_frames):
        reader.begin_frame(frame)
        for channels in channel_groups:
            for channel in channels:
                _read_channel_frame(channel, reader)

    if channel_list:
        sequence_count = max(sequence_index for sequence_index, _, _ in channel_list) + 1
    else:
        sequence_count = 0
    anim_sequences: list[YcdAnimSequence] = []
    for sequence_index in range(sequence_count):
        items = [(index, channel) for seq, index, channel in channel_list if seq == sequence_index]
        items.sort(key=lambda item: item[0])
        sequence = YcdAnimSequence(
            channels=[channel for _, channel in items],
            is_cached_quaternion=any(isinstance(channel, YcdCachedQuaternionChannel) for _, channel in items),
        )
        for channel in sequence.channels:
            if isinstance(channel, YcdCachedQuaternionChannel):
                channel.parent_sequence = sequence
        anim_sequences.append(sequence)

    root_position_ref_count = (int(root_motion_ref_counts) >> 4) & 0xF
    root_rotation_ref_count = int(root_motion_ref_counts) & 0xF
    root_position_refs = [YcdSequenceRootChannelRef(reader.read_channel_data_bytes(6)) for _ in range(root_position_ref_count)]
    root_rotation_refs = [YcdSequenceRootChannelRef(reader.read_channel_data_bytes(6)) for _ in range(root_rotation_ref_count)]

    return anim_sequences, root_position_refs, root_rotation_refs


def channel_frame_bits(channel: YcdAnimChannel) -> int:
    if isinstance(channel, YcdRawFloatChannel):
        return 32
    if isinstance(channel, YcdQuantizeFloatChannel):
        return int(channel.value_bits)
    if isinstance(channel, YcdIndirectQuantizeFloatChannel):
        return int(channel.frame_bits)
    return 0


__all__ = [
    "YcdAnimationTrack",
    "YcdChannelType",
    "CAMERA_TRACK_IDS",
    "ROOT_MOTION_TRACK_IDS",
    "BONE_TRACK_IDS",
    "YcdAnimChannel",
    "YcdAnimSequence",
    "YcdCachedQuaternionChannel",
    "YcdIndirectQuantizeFloatChannel",
    "YcdLinearFloatChannel",
    "YcdQuantizeFloatChannel",
    "YcdRawFloatChannel",
    "YcdSequenceRootChannelRef",
    "YcdStaticFloatChannel",
    "YcdStaticQuaternionChannel",
    "YcdStaticVector3Channel",
    "channel_frame_bits",
    "get_ycd_track_name",
    "is_ycd_bone_track",
    "is_ycd_camera_track",
    "is_ycd_object_track",
    "is_ycd_position_track",
    "is_ycd_rotation_track",
    "is_ycd_root_motion_track",
    "is_ycd_uv_track",
    "parse_sequence_data",
]
