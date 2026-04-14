from __future__ import annotations

import math
import struct

from ..binary import f32 as _f32, i32 as _i32, u16 as _u16
from .sequence_channels import (
    YcdAnimChannel,
    YcdAnimSequence,
    YcdCachedQuaternionChannel,
    YcdChannelType,
    YcdIndirectQuantizeFloatChannel,
    YcdLinearFloatChannel,
    YcdQuantizeFloatChannel,
    YcdRawFloatChannel,
    YcdSequenceRootChannelRef,
    YcdStaticFloatChannel,
    YcdStaticQuaternionChannel,
    YcdStaticVector3Channel,
    channel_frame_bits,
)
from .sequence_tracks import YcdAnimationTrack


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


class _ChannelDataWriter:
    def __init__(self, num_frames: int) -> None:
        self.position = 0
        self.frame = 0
        self.num_frames = int(num_frames)
        self.chunk_size = 0
        self.frame_length = 0
        self.channel_list_stream = bytearray()
        self.channel_item_stream = bytearray()
        self.main_stream = bytearray()
        self.channel_frame_stream: list[int] = []
        self.channel_frames: list[list[int]] = []
        self.bitstream: list[int] = []
        self.bitstream_pos = 0
        self.channel_frame_offset = 0

    def write_channel_list_data(self, value: int) -> None:
        self.channel_list_stream.extend(struct.pack("<H", int(value) & 0xFFFF))

    def write_channel_item_data(self, value: int) -> None:
        self.channel_item_stream.extend(struct.pack("<H", int(value) & 0xFFFF))

    def align_channel_item_data(self, channel_count: int, sequence_count: int) -> None:
        remainder = int(channel_count) % 4
        if remainder <= 0:
            return
        write_value = int(sequence_count) << 2
        for _ in range(4 - remainder):
            self.write_channel_item_data(write_value)

    def write_channel_item_data_bytes(self, data: bytes) -> None:
        if data:
            self.channel_item_stream.extend(bytes(data))

    def write_int32(self, value: int) -> None:
        self.main_stream.extend(struct.pack("<i", int(value)))
        self.position += 4

    def write_single(self, value: float) -> None:
        self.main_stream.extend(struct.pack("<f", float(value)))
        self.position += 4

    def write_vector3(self, value: tuple[float, float, float]) -> None:
        self.main_stream.extend(struct.pack("<3f", float(value[0]), float(value[1]), float(value[2])))
        self.position += 12

    def begin_frame(self, frame: int) -> None:
        self.frame = int(frame)
        self.channel_frame_stream = []
        self.channel_frame_offset = 0

    def write_frame_bits(self, bits: int, count: int) -> None:
        self._write_to_bitstream(self.channel_frame_stream, self.channel_frame_offset, bits, count)
        self.channel_frame_offset += int(count)

    def end_frame(self) -> None:
        self.frame_length = max(self.frame_length, len(self.channel_frame_stream) * 4)
        self.channel_frames.append(list(self.channel_frame_stream))
        self.channel_frame_stream = []

    def bit_count_scalar(self, bits: int) -> int:
        value = int(bits)
        if value <= 0:
            return 0
        return value.bit_length()

    def bit_count_values(self, values: list[int]) -> int:
        max_value = 0
        for value in values:
            max_value = max(max_value, int(value))
        return self.bit_count_scalar(max_value)

    def reset_bitstream(self) -> None:
        self.bitstream = []
        self.bitstream_pos = 0

    def write_bits(self, bits: int, count: int) -> None:
        self._write_to_bitstream(self.bitstream, self.bitstream_pos, bits, count)
        self.bitstream_pos += int(count)

    def write_bitstream(self) -> None:
        for value in self.bitstream:
            self.main_stream.extend(struct.pack("<I", int(value) & 0xFFFFFFFF))
            self.position += 4

    @staticmethod
    def _write_to_bitstream(stream: list[int], offset: int, bits: int, count: int) -> None:
        count = int(count)
        if count <= 0:
            return
        value = int(bits)
        mask = (1 << count) - 1
        masked = value & mask
        start_offset = int(offset) % 32
        start_index = int(offset) // 32
        while start_index >= len(stream):
            stream.append(0)
        stream[start_index] = (int(stream[start_index]) + ((masked << start_offset) & 0xFFFFFFFF)) & 0xFFFFFFFF
        end_bits = (start_offset + count) - 32
        if end_bits > 0:
            end_index = start_index + 1
            while end_index >= len(stream):
                stream.append(0)
            stream[end_index] = (int(stream[end_index]) + (masked >> (32 - start_offset))) & 0xFFFFFFFF

    def get_main_data_bytes(self) -> bytes:
        return bytes(self.main_stream)

    def get_frame_data_bytes(self) -> bytes:
        data = bytearray()
        frame_uint_count = self.frame_length // 4
        for frame_data in self.channel_frames:
            for index in range(frame_uint_count):
                value = frame_data[index] if index < len(frame_data) else 0
                data.extend(struct.pack("<I", int(value) & 0xFFFFFFFF))
        return bytes(data)

    def get_channel_list_data_bytes(self) -> bytes:
        return bytes(self.channel_list_stream)

    def get_channel_item_data_bytes(self) -> bytes:
        return bytes(self.channel_item_stream)


def _float_to_bits(value: float) -> int:
    return int.from_bytes(struct.pack("<f", float(value)), "little", signed=False)


def _sample_channel_value(values: list[float], index: int, default: float) -> float:
    if not values:
        return float(default)
    frame = int(index)
    if 0 <= frame < len(values):
        return float(values[frame])
    return float(values[frame % len(values)])


def _sample_frame_index(frames: list[int], index: int) -> int:
    if not frames:
        return 0
    frame = int(index)
    if 0 <= frame < len(frames):
        return int(frames[frame])
    return int(frames[frame % len(frames)])


def _quantize_to_bits(value: float, quantum: float, offset: float) -> int:
    quantum_value = float(quantum)
    if abs(quantum_value) <= 1e-12:
        return 0
    return int(((float(value) - float(offset)) / quantum_value) + 0.5)


def _channel_reference_index(channel: YcdAnimChannel) -> int:
    if isinstance(channel, YcdCachedQuaternionChannel):
        return int(channel.quat_index)
    return int(channel.channel_index)


def _write_channel(channel: YcdAnimChannel, writer: _ChannelDataWriter) -> None:
    if isinstance(channel, YcdStaticFloatChannel):
        writer.write_single(channel.value)
        return
    if isinstance(channel, YcdStaticVector3Channel):
        writer.write_vector3(channel.value)
        return
    if isinstance(channel, YcdStaticQuaternionChannel):
        writer.write_vector3((float(channel.value[0]), float(channel.value[1]), float(channel.value[2])))
        return
    if isinstance(channel, YcdRawFloatChannel):
        return
    if isinstance(channel, YcdQuantizeFloatChannel):
        values = [
            _quantize_to_bits(_sample_channel_value(channel.values, index, channel.offset), channel.quantum, channel.offset)
            for index in range(writer.num_frames)
        ]
        channel.value_list = values
        channel.value_bits = max(writer.bit_count_values(values), 1)
        writer.write_int32(channel.value_bits)
        writer.write_single(channel.quantum)
        writer.write_single(channel.offset)
        return
    if isinstance(channel, YcdIndirectQuantizeFloatChannel):
        source_values = list(channel.values) if channel.values else [float(channel.offset)]
        value_list = [_quantize_to_bits(value, channel.quantum, channel.offset) for value in source_values]
        channel.value_list = value_list
        channel.frame_bits = max(writer.bit_count_scalar(max(len(source_values), 1)), 2)
        channel.value_bits = max(writer.bit_count_values(value_list), 3)
        writer.reset_bitstream()
        for value in value_list:
            writer.write_bits(value, channel.value_bits)
        channel.num_ints = len(writer.bitstream)
        writer.write_int32(channel.frame_bits)
        writer.write_int32(channel.value_bits)
        writer.write_int32(channel.num_ints)
        writer.write_single(channel.quantum)
        writer.write_single(channel.offset)
        writer.write_bitstream()
        if not channel.frames:
            channel.frames = [0] * writer.num_frames
        return
    if isinstance(channel, YcdLinearFloatChannel):
        num_frames = max(writer.num_frames, 0)
        chunk_size = 64
        if writer.chunk_size != chunk_size:
            writer.chunk_size = chunk_size
        source_values = list(channel.values) if channel.values else [float(channel.offset)] * max(num_frames, 1)
        value_list = [_quantize_to_bits(value, channel.quantum, channel.offset) for value in source_values]
        channel.value_list = value_list
        num_chunks = (chunk_size + num_frames - 1) // chunk_size if num_frames > 0 else 0
        chunk_offsets = [0] * num_chunks
        chunk_values = [0] * num_chunks
        chunk_deltas: list[list[int]] = [[0] * chunk_size for _ in range(num_chunks)]
        chunk_delta_bits = [0] * max(num_frames, 0)
        default_value = value_list[0] if value_list else 0
        for chunk_index in range(num_chunks):
            chunk_frame = chunk_index * chunk_size
            current_value = value_list[chunk_frame] if chunk_frame < len(value_list) else default_value
            current_increment = 0
            chunk_values[chunk_index] = current_value
            deltas = chunk_deltas[chunk_index]
            for local_frame in range(1, chunk_size):
                frame_index = chunk_frame + local_frame
                if frame_index >= num_frames:
                    break
                value = value_list[frame_index] if frame_index < len(value_list) else current_value
                increment = value - current_value
                delta = increment - current_increment
                current_increment = increment
                current_value = value
                deltas[local_frame] = delta
                chunk_delta_bits[frame_index] = abs(delta)
        count3 = writer.bit_count_values(chunk_delta_bits)
        bit_offset = 0
        for chunk_index in range(num_chunks):
            chunk_offsets[chunk_index] = bit_offset
            for local_frame in range(1, chunk_size):
                frame_index = (chunk_index * chunk_size) + local_frame
                if frame_index >= num_frames:
                    break
                delta = chunk_deltas[chunk_index][local_frame]
                bit_offset += count3 + (2 if delta < 0 else 1)
        count1 = writer.bit_count_values(chunk_offsets)
        count2 = writer.bit_count_values(chunk_values)
        writer.reset_bitstream()
        if count1 > 0:
            for value in chunk_offsets:
                writer.write_bits(value, count1)
        if count2 > 0:
            for value in chunk_values:
                writer.write_bits(value, count2)
        for chunk_index in range(num_chunks):
            for local_frame in range(1, chunk_size):
                frame_index = (chunk_index * chunk_size) + local_frame
                if frame_index >= num_frames:
                    break
                delta = chunk_deltas[chunk_index][local_frame]
                writer.write_bits(abs(delta), count3)
                writer.write_bits(1, 1)
                if delta < 0:
                    writer.write_bits(1, 1)
        channel.num_ints = 4 + len(writer.bitstream)
        channel.counts = (count1 & 0xFF) | ((count2 & 0xFF) << 8) | ((count3 & 0xFF) << 16)
        writer.write_int32(channel.num_ints)
        writer.write_int32(channel.counts)
        writer.write_single(channel.quantum)
        writer.write_single(channel.offset)
        writer.write_bitstream()
        return
    if isinstance(channel, YcdCachedQuaternionChannel):
        return
    raise TypeError(f"Unsupported YCD channel instance: {type(channel)!r}")


def _write_channel_frame(channel: YcdAnimChannel, writer: _ChannelDataWriter) -> None:
    if isinstance(channel, YcdRawFloatChannel):
        writer.write_frame_bits(_float_to_bits(_sample_channel_value(channel.values, writer.frame, 0.0)), 32)
        return
    if isinstance(channel, YcdQuantizeFloatChannel):
        value = _sample_channel_value(channel.values, writer.frame, channel.offset)
        writer.write_frame_bits(_quantize_to_bits(value, channel.quantum, channel.offset), channel.value_bits)
        return
    if isinstance(channel, YcdIndirectQuantizeFloatChannel):
        writer.write_frame_bits(_sample_frame_index(channel.frames, writer.frame), channel.frame_bits)
        return
    if isinstance(channel, YcdLinearFloatChannel):
        return
    if isinstance(channel, (YcdStaticFloatChannel, YcdStaticVector3Channel, YcdStaticQuaternionChannel, YcdCachedQuaternionChannel)):
        return
    raise TypeError(f"Unsupported YCD channel instance: {type(channel)!r}")


def _build_root_motion_refs(anim_sequences: list[YcdAnimSequence]) -> tuple[list[YcdSequenceRootChannelRef], list[YcdSequenceRootChannelRef]]:
    root_position_refs: list[YcdSequenceRootChannelRef] = []
    root_rotation_refs: list[YcdSequenceRootChannelRef] = []
    for anim_sequence in anim_sequences:
        track = getattr(getattr(anim_sequence, "bone_id", None), "track", None)
        if track is None:
            continue
        if int(track) == int(YcdAnimationTrack.MOVER_TRANSLATION):
            target = root_position_refs
        elif int(track) == int(YcdAnimationTrack.MOVER_ROTATION):
            target = root_rotation_refs
        else:
            continue
        for channel in anim_sequence.channels:
            target.append(
                YcdSequenceRootChannelRef.build(
                    channel.channel_type,
                    _channel_reference_index(channel),
                    channel.data_offset,
                    channel.frame_offset,
                )
            )
    root_position_refs.sort(key=lambda item: (item.channel_type, item.channel_index))
    root_rotation_refs.sort(key=lambda item: (item.channel_type, item.channel_index))
    return root_position_refs, root_rotation_refs


def build_sequence_data(sequence: object) -> bytes:
    anim_sequences = list(getattr(sequence, "anim_sequences", []) or [])
    if not anim_sequences:
        raw_data = bytes(getattr(sequence, "raw_data", b""))
        if hasattr(sequence, "data_length"):
            sequence.data_length = len(raw_data)
        return raw_data

    num_frames = int(getattr(sequence, "num_frames", 0))
    writer = _ChannelDataWriter(num_frames)
    channel_lists: list[list[YcdAnimChannel] | None] = [None] * 9

    for sequence_index, anim_sequence in enumerate(anim_sequences):
        if not anim_sequence.channels:
            continue
        anim_sequence.is_cached_quaternion = any(isinstance(channel, YcdCachedQuaternionChannel) for channel in anim_sequence.channels)
        for channel in anim_sequence.channels:
            type_index = int(channel.channel_type)
            if type_index < 0 or type_index >= len(channel_lists):
                continue
            channel.sequence_index = sequence_index
            if isinstance(channel, YcdCachedQuaternionChannel):
                channel.channel_index = 3 if channel.channel_type is YcdChannelType.CACHED_QUATERNION1 else 4
                channel.quat_index = int(channel.quat_index) & 0x3
                channel.parent_sequence = anim_sequence
            channel_list = channel_lists[type_index]
            if channel_list is None:
                channel_list = []
                channel_lists[type_index] = channel_list
            channel_list.append(channel)

    for channel_list in channel_lists:
        channels = channel_list or []
        writer.write_channel_list_data(len(channels))
        for channel in channels:
            encoded_index = channel.quat_index if isinstance(channel, YcdCachedQuaternionChannel) else int(channel.channel_index)
            channel_data_bits = int(encoded_index) + (int(channel.sequence_index) << 2)
            writer.write_channel_item_data(channel_data_bits)
            channel.data_offset = writer.position // 4
            _write_channel(channel, writer)
        writer.align_channel_item_data(len(channels), len(anim_sequences))

    for frame in range(num_frames):
        writer.begin_frame(frame)
        for channel_list in channel_lists:
            for channel in channel_list or []:
                _write_channel_frame(channel, writer)
        writer.end_frame()

    frame_bit_offset = 0
    for channel_list in channel_lists:
        for channel in channel_list or []:
            channel.frame_offset = frame_bit_offset
            frame_bit_offset += channel_frame_bits(channel)

    root_position_refs, root_rotation_refs = _build_root_motion_refs(anim_sequences)
    for root_ref in root_position_refs:
        writer.write_channel_item_data_bytes(root_ref.raw_bytes)
    for root_ref in root_rotation_refs:
        writer.write_channel_item_data_bytes(root_ref.raw_bytes)

    main_data = writer.get_main_data_bytes()
    frame_data = writer.get_frame_data_bytes()
    channel_list_data = writer.get_channel_list_data_bytes()
    channel_item_data = writer.get_channel_item_data_bytes()
    raw_data = main_data + frame_data + channel_list_data + channel_item_data

    if hasattr(sequence, "raw_data"):
        sequence.raw_data = raw_data
    if hasattr(sequence, "data_length"):
        sequence.data_length = len(raw_data)
    if hasattr(sequence, "frame_offset"):
        sequence.frame_offset = len(main_data)
    if hasattr(sequence, "frame_length"):
        sequence.frame_length = writer.frame_length
    if hasattr(sequence, "chunk_size"):
        sequence.chunk_size = writer.chunk_size if writer.chunk_size > 0 else 0xFF
    if hasattr(sequence, "quantize_float_value_bits"):
        sequence.quantize_float_value_bits = sum(
            int(channel.value_bits)
            for anim_sequence in anim_sequences
            for channel in anim_sequence.channels
            if isinstance(channel, YcdQuantizeFloatChannel)
        )
    if hasattr(sequence, "indirect_quantize_float_num_ints"):
        sequence.indirect_quantize_float_num_ints = sum(
            int(channel.num_ints) + 5
            for anim_sequence in anim_sequences
            for channel in anim_sequence.channels
            if isinstance(channel, YcdIndirectQuantizeFloatChannel)
        )
    if hasattr(sequence, "root_position_refs"):
        sequence.root_position_refs = root_position_refs
    if hasattr(sequence, "root_rotation_refs"):
        sequence.root_rotation_refs = root_rotation_refs
    if hasattr(sequence, "root_motion_ref_counts"):
        sequence.root_motion_ref_counts = (len(root_position_refs) << 4) | len(root_rotation_refs)
    if hasattr(sequence, "root_motion_refs_offset"):
        sequence.root_motion_refs_offset = (0x20 + len(raw_data)) - ((len(root_position_refs) + len(root_rotation_refs)) * 6)
    return raw_data


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
        chunk_size = max(reader.chunk_size, 1)
        num_chunks = (chunk_size + reader.num_frames - 1) // chunk_size
        delta_offset = bit + (num_chunks * (count1 + count2))
        reader.bit_position = bit
        chunk_offsets = [reader.read_bits(count1) if count1 > 0 else 0 for _ in range(num_chunks)]
        chunk_values = [reader.read_bits(count2) if count2 > 0 else 0 for _ in range(num_chunks)]
        frame_values = [0.0] * reader.num_frames
        frame_bits = [0] * reader.num_frames
        for chunk_index in range(num_chunks):
            doffs = chunk_offsets[chunk_index] + delta_offset
            value = chunk_values[chunk_index]
            chunk_start = chunk_index * chunk_size
            reader.bit_position = doffs
            increment = 0
            for local_frame in range(chunk_size):
                frame_index = chunk_start + local_frame
                if frame_index >= reader.num_frames:
                    break
                frame_values[frame_index] = (value * channel.quantum) + channel.offset
                frame_bits[frame_index] = value
                if (local_frame + 1) >= chunk_size:
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
            frame_bit_offset += channel_frame_bits(channel)
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


__all__ = [
    "build_sequence_data",
    "parse_sequence_data",
]
