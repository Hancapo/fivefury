from __future__ import annotations

from typing import TYPE_CHECKING

from ..binary import align
from .constants import AwcCodecType
from .streaming import _iter_streaming_blocks, _read_block_tables

if TYPE_CHECKING:
    from .structures import AwcStream

PCM_WIDTHS = {
    AwcCodecType.PCM: 2,
    AwcCodecType.PCM_BIG_ENDIAN: 2,
    AwcCodecType.FLOAT: 4,
    AwcCodecType.FLOAT_BIG_ENDIAN: 4,
}


def sample_capacity(data: bytes | memoryview, codec: AwcCodecType) -> int:
    if codec in PCM_WIDTHS:
        width = PCM_WIDTHS[codec]
        if len(data) % width:
            raise ValueError("PCM payload is not aligned to its sample width")
        return len(data) // width
    if codec is AwcCodecType.ADPCM:
        if not data or len(data) % 2048:
            raise ValueError("ADPCM data requires complete 2048-byte blocks")
        if any(data[index] > 88 for index in range(0, len(data), 2048)):
            raise ValueError("ADPCM predictor step index is out of range")
        return len(data) // 2048 * 4088
    raise ValueError("Unsupported fixed-block audio codec")


def validate_fixed_stream(stream: AwcStream) -> None:
    layout = stream.stream_format_chunk
    data = stream.data_chunk.data
    positions = [0] * len(layout.channels)
    expected_seek = []
    for block in _iter_streaming_blocks(
        data, block_count=layout.block_count, block_size=layout.block_size
    ):
        headers, offsets, cursor = _read_block_tables(block, len(layout.channels))
        starts = []
        for index, (channel, header, packets) in enumerate(
            zip(layout.channels, headers, offsets, strict=True)
        ):
            count, skip, samples = header[1:4]
            size = header[5] or count * 2048
            if cursor + size > len(block):
                raise ValueError("Streaming channel payload is truncated")
            capacity = sample_capacity(block[cursor : cursor + size], channel.codec)
            if not 0 <= skip < samples <= capacity:
                raise ValueError(
                    "Streaming samples or skipped prefix exceed payload capacity"
                )
            packet_samples = (
                4088
                if channel.codec is AwcCodecType.ADPCM
                else 2048 // PCM_WIDTHS[channel.codec]
            )
            if not packets or packets[0] + skip != positions[index]:
                raise ValueError(
                    "Streaming packets do not match the absolute sample position"
                )
            if tuple(packets) != tuple(
                packets[0] + i * packet_samples for i in range(count)
            ):
                raise ValueError("Streaming packet sample offsets are inconsistent")
            if count != (capacity + packet_samples - 1) // packet_samples:
                raise ValueError("Streaming packet count does not cover its payload")
            starts.append(positions[index])
            positions[index] += samples - skip
            cursor += align(size, 16)
        if len(set(starts)) != 1:
            raise ValueError("Streaming channels do not share a block start")
        expected_seek.append(starts[0])
    if positions != [channel.samples for channel in layout.channels]:
        raise ValueError("Streaming samples do not match the format duration")
    seek = stream.seek_table_chunk
    if (
        seek is None
        or seek.seek_table_entry_size != 4
        or seek.seek_table != expected_seek
    ):
        raise ValueError("Streaming seek table does not match its blocks")
