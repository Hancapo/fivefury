from __future__ import annotations

import struct
from dataclasses import dataclass
from itertools import pairwise

from .mp3 import (
    MP3_SAMPLES_PER_FRAME,
    MP3_STREAMING_PACKET_SIZE,
    EncodedMp3Channel,
    Mp3Frame,
    parse_mp3_frames,
)


@dataclass(frozen=True, slots=True)
class Mp3StreamingChannel:
    packet_offsets: tuple[int, ...]
    sample_count: int
    frame_count: int
    encoded_size: int
    frames: tuple[Mp3Frame, ...]


@dataclass(frozen=True, slots=True)
class Mp3StreamingBlock:
    channels: tuple[Mp3StreamingChannel, ...]


def _align(value: int, alignment: int) -> int:
    return value + (-value % alignment)


def _frame_prefix(channel: EncodedMp3Channel) -> tuple[int, ...]:
    result = [0]
    for size in channel.frame_sizes:
        result.append(result[-1] + size)
    return tuple(result)


def _packet_offsets(sizes: tuple[int, ...], *, first_frame: int) -> tuple[int, ...]:
    offsets: list[int] = []
    packet_size = 0
    for index, frame_size in enumerate(sizes):
        if frame_size > MP3_STREAMING_PACKET_SIZE:
            raise ValueError("MP3 frame exceeds the AWC streaming packet size")
        if not offsets or packet_size + frame_size > MP3_STREAMING_PACKET_SIZE:
            offsets.append((first_frame + index) * MP3_SAMPLES_PER_FRAME)
            packet_size = 0
        packet_size += frame_size
    return tuple(offsets)


def _block_size(
    channels: tuple[EncodedMp3Channel, ...],
    prefixes: tuple[tuple[int, ...], ...],
    first_frame: int,
    end_frame: int,
) -> int:
    packet_count = sum(
        len(
            _packet_offsets(
                channel.frame_sizes[first_frame:end_frame], first_frame=first_frame
            )
        )
        for channel in channels
    )
    header_size = _align(
        24 * len(channels) + 4 * packet_count,
        MP3_STREAMING_PACKET_SIZE,
    )
    payload_size = sum(prefix[end_frame] - prefix[first_frame] for prefix in prefixes)
    return header_size + payload_size


def _block_end(
    channels: tuple[EncodedMp3Channel, ...],
    prefixes: tuple[tuple[int, ...], ...],
    first_frame: int,
    frame_count: int,
    block_size: int,
) -> int:
    low = first_frame + 1
    high = frame_count
    if _block_size(channels, prefixes, first_frame, low) > block_size:
        raise ValueError("AWC block size cannot hold one MP3 frame per channel")
    while low < high:
        middle = (low + high + 1) // 2
        if _block_size(channels, prefixes, first_frame, middle) <= block_size:
            low = middle
        else:
            high = middle - 1
    return low


def build_mp3_streaming_data(
    channels: tuple[EncodedMp3Channel, ...],
    *,
    block_size: int = 524_288,
) -> tuple[bytes, int]:
    if not channels:
        raise ValueError("MP3 streaming authoring requires at least one channel")
    if block_size <= 0 or block_size % MP3_STREAMING_PACKET_SIZE:
        raise ValueError("AWC MP3 block size must be a positive multiple of 2048")
    sample_counts = {channel.sample_count for channel in channels}
    sample_rates = {channel.sample_rate for channel in channels}
    frame_counts = {channel.frame_count for channel in channels}
    if len(sample_counts) != 1 or len(sample_rates) != 1 or len(frame_counts) != 1:
        raise ValueError("AWC MP3 channels must have equal duration and frame count")
    for channel in channels:
        if sum(channel.frame_sizes) != len(channel.data):
            raise ValueError("MP3 frame seek table does not cover its encoded channel")
        if channel.seek_table_entry_size != 2 or any(
            size <= 0 or size > 0xFFFF for size in channel.frame_sizes
        ):
            raise ValueError("MP3 frame sizes must fit the uint16 seek table")
        parsed = parse_mp3_frames(
            channel.data,
            require_independent=True,
            sample_rate=channel.sample_rate,
        )
        if tuple(frame.size for frame in parsed) != channel.frame_sizes:
            raise ValueError("MP3 frame seek table does not match the encoded payload")

    frame_count = frame_counts.pop()
    sample_count = sample_counts.pop()
    prefixes = tuple(_frame_prefix(channel) for channel in channels)
    blocks: list[bytes] = []
    first_frame = 0
    while first_frame < frame_count:
        end_frame = _block_end(
            channels,
            prefixes,
            first_frame,
            frame_count,
            block_size,
        )
        payloads: list[bytes] = []
        offsets_by_channel: list[tuple[int, ...]] = []
        block = bytearray()
        useful_samples = max(
            0,
            min(sample_count, end_frame * MP3_SAMPLES_PER_FRAME)
            - min(sample_count, first_frame * MP3_SAMPLES_PER_FRAME),
        )
        for channel, prefix in zip(channels, prefixes, strict=True):
            sizes = channel.frame_sizes[first_frame:end_frame]
            offsets = _packet_offsets(sizes, first_frame=first_frame)
            payload = channel.data[prefix[first_frame] : prefix[end_frame]]
            offsets_by_channel.append(offsets)
            payloads.append(payload)
            block += struct.pack(
                "<6i",
                -1,
                len(offsets),
                0,
                useful_samples,
                len(sizes),
                len(payload),
            )
        for offsets in offsets_by_channel:
            block += struct.pack(f"<{len(offsets)}i", *offsets)
        block += bytes(-len(block) % MP3_STREAMING_PACKET_SIZE)
        for payload in payloads:
            block += payload
        if len(block) > block_size:
            raise RuntimeError("AWC MP3 block planner exceeded the selected block size")
        block += bytes(block_size - len(block))
        blocks.append(bytes(block))
        first_frame = end_frame
    return b"".join(blocks), len(blocks)


def inspect_mp3_streaming_data(
    data: bytes | bytearray | memoryview,
    *,
    block_count: int,
    block_size: int,
    channel_count: int,
    sample_rate: int,
) -> tuple[Mp3StreamingBlock, ...]:
    source = bytes(data)
    if block_count <= 0 or block_size <= 0 or channel_count <= 0:
        raise ValueError("Invalid AWC MP3 streaming dimensions")
    if len(source) != block_count * block_size:
        raise ValueError("AWC MP3 streaming data does not match its block table")
    result: list[Mp3StreamingBlock] = []
    for block_index in range(block_count):
        block = source[block_index * block_size : (block_index + 1) * block_size]
        cursor = channel_count * 24
        headers: list[tuple[int, int, int, int, int, int]] = []
        offsets_by_channel: list[tuple[int, ...]] = []
        for channel_index in range(channel_count):
            header = struct.unpack_from("<6i", block, channel_index * 24)
            if header[0] != -1 or any(value < 0 for value in header[1:]):
                raise ValueError("AWC MP3 channel block header is invalid")
            headers.append(header)
        for header in headers:
            packet_count = header[1]
            table_size = packet_count * 4
            if cursor + table_size > block_size:
                raise ValueError("AWC MP3 packet table is truncated")
            offsets = (
                struct.unpack_from(f"<{packet_count}i", block, cursor)
                if packet_count
                else ()
            )
            if any(value < 0 for value in offsets) or any(
                right <= left for left, right in pairwise(offsets)
            ):
                raise ValueError("AWC MP3 packet offsets must be monotonic")
            offsets_by_channel.append(tuple(offsets))
            cursor += table_size
        cursor = _align(cursor, MP3_STREAMING_PACKET_SIZE)
        parsed_channels: list[Mp3StreamingChannel] = []
        for header, packet_offsets in zip(headers, offsets_by_channel, strict=True):
            encoded_size = header[5]
            if cursor + encoded_size > block_size:
                raise ValueError("AWC MP3 channel payload is truncated")
            payload = block[cursor : cursor + encoded_size]
            frames = parse_mp3_frames(
                payload,
                require_independent=True,
                sample_rate=sample_rate,
            )
            if len(frames) != header[4]:
                raise ValueError("AWC MP3 frame count does not match its payload")
            expected_offsets = _packet_offsets(
                tuple(frame.size for frame in frames),
                first_frame=(
                    packet_offsets[0] // MP3_SAMPLES_PER_FRAME if packet_offsets else 0
                ),
            )
            if expected_offsets != packet_offsets:
                raise ValueError("AWC MP3 packet table does not match its frame layout")
            parsed_channels.append(
                Mp3StreamingChannel(
                    packet_offsets,
                    header[3],
                    header[4],
                    encoded_size,
                    frames,
                )
            )
            cursor += encoded_size
        result.append(Mp3StreamingBlock(tuple(parsed_channels)))
    return tuple(result)


__all__ = [
    "Mp3StreamingBlock",
    "Mp3StreamingChannel",
    "build_mp3_streaming_data",
    "inspect_mp3_streaming_data",
]
