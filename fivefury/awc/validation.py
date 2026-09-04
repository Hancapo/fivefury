from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

from ..authoring import DiagnosticSeverity, ValidationReport
from ..authoring.invariants import check_unsigned
from .constants import AWC_STREAM_ID_MASK, AwcCodecType

if TYPE_CHECKING:
    from .structures import Awc, AwcStream


def validate_awc_format(value: object) -> ValidationReport:
    from .structures import AwcFormat, AwcStreamFormat

    report = ValidationReport()
    if isinstance(value, AwcFormat):
        fields = (("samples", 32), ("sample_rate", 16), ("loop_begin", 16),
                  ("loop_end", 16), ("play_end", 16), ("play_begin", 8), ("codec", 8))
        if value.peak is not None:
            fields += (("peak", 32),)
    elif isinstance(value, AwcStreamFormat):
        fields = (("id", 32), ("samples", 32), ("sample_rate", 16),
                  ("codec", 8), ("unused1", 8), ("unused2", 16))
    else:
        raise TypeError("Expected an AWC format")
    for name, bits in fields:
        check_unsigned(report, getattr(value, name), bits,
                       code="awc.format.field.range", path=name)
    return report


def validate_awc_binary_fields(awc: Awc) -> ValidationReport:
    report = ValidationReport()
    for stream_index, stream in enumerate(awc.streams):
        path = f"streams[{stream_index}]"
        check_unsigned(report, len(stream.chunks), 3,
                       code="awc.stream.chunk_count.range", path=f"{path}.chunks")
        for chunk_index, chunk in enumerate(stream.chunks):
            chunk_path = f"{path}.chunks[{chunk_index}]"
            if chunk.format is not None:
                report.extend(validate_awc_format(chunk.format), path=f"{chunk_path}.format")
            if chunk.stream_format is not None:
                layout = chunk.stream_format
                for field in ("block_count", "block_size"):
                    check_unsigned(report, getattr(layout, field), 32,
                                   code="awc.layout.field.range", path=f"{chunk_path}.{field}")
                for channel_index, channel in enumerate(layout.channels):
                    report.extend(validate_awc_format(channel),
                                  path=f"{chunk_path}.channels[{channel_index}]")
    if awc.chunk_indices_flag:
        start = 0
        for stream_index, stream in enumerate(awc.streams):
            check_unsigned(report, start, 16, code="awc.stream.chunk_index.range",
                           path=f"streams[{stream_index}].chunk_index")
            start += len(stream.chunks)
    return report


def awc_playback_streams(awc: Awc) -> tuple[AwcStream, ...]:
    if awc.multi_channel_flag:
        return tuple(
            stream
            for stream in awc.streams
            if stream.stream_format_chunk is not None and stream.data_chunk is not None
        )
    return tuple(
        stream
        for stream in awc.streams
        if stream.data_chunk is not None and stream.codec is not None
    )


def awc_channel_codecs(awc: Awc) -> tuple[AwcCodecType, ...]:
    """Return one codec for each logical playback channel."""
    streams = awc_playback_streams(awc)
    if awc.multi_channel_flag:
        if len(streams) != 1 or streams[0].stream_format_chunk is None:
            return ()
        return tuple(channel.codec for channel in streams[0].stream_format_chunk.channels)
    return tuple(stream.codec for stream in streams if stream.codec is not None)


def resolve_awc_playback_stream(
    awc: Awc,
    *,
    stream_hash: int = 0,
    fallback_hash: int = 0,
) -> AwcStream | None:
    candidates = awc_playback_streams(awc)
    values = (stream_hash,) if stream_hash else (fallback_hash,)
    for value in values:
        target = int(value) & AWC_STREAM_ID_MASK
        if not target:
            continue
        direct = [stream for stream in candidates if stream.hash == target]
        if len(direct) == 1:
            return direct[0]
        if awc.multi_channel_flag:
            owners = [
                stream
                for stream in candidates
                if any(
                    (channel.id & AWC_STREAM_ID_MASK) == target
                    for channel in stream.stream_format_chunk.channels
                )
            ]
            if len(owners) == 1:
                return owners[0]
        if stream_hash:
            return None
    return candidates[0] if len(candidates) == 1 else None


def _validate_mp3_seek_table(
    report: ValidationReport,
    stream: AwcStream,
    expected: tuple[int, ...] | None,
    *,
    block_count: int,
    path: str,
) -> None:
    seek_chunk = stream.seek_table_chunk
    if seek_chunk is None or seek_chunk.seek_table is None:
        report.issue(
            "awc.stream.mp3.seek_table.missing",
            "Multichannel MP3 streams require a block seek table",
            path=path,
        )
        return
    seek_table = tuple(int(value) for value in seek_chunk.seek_table)
    if seek_chunk.seek_table_entry_size != 4:
        report.issue(
            "awc.stream.mp3.seek_table.width.invalid",
            "The MP3 block seek table must use uint32 entries",
            path=f"{path}.entry_size",
        )
    if len(seek_table) != block_count:
        report.issue(
            "awc.stream.mp3.seek_table.count.invalid",
            "The MP3 block seek table must contain one entry per block",
            path=path,
        )
    if seek_table and seek_table[0] != 0:
        report.issue(
            "awc.stream.mp3.seek_table.origin.invalid",
            "The MP3 block seek table must begin at sample zero",
            path=f"{path}[0]",
        )
    if any(right < left for left, right in pairwise(seek_table)):
        report.issue(
            "awc.stream.mp3.seek_table.order.invalid",
            "MP3 block seek offsets must be monotonic",
            path=path,
        )
    if any(value < 0 or value > 0xFFFFFFFF for value in seek_table):
        report.issue(
            "awc.stream.mp3.seek_table.range.invalid",
            "MP3 block seek offsets must fit uint32",
            path=path,
        )
    if expected is not None and seek_table != expected:
        report.issue(
            "awc.stream.mp3.seek_table.values.invalid",
            "MP3 block seek offsets do not match the streaming packet tables",
            path=path,
        )


def _validate_stream(report: ValidationReport, awc: Awc, stream: AwcStream) -> None:
    path = f"streams[0x{stream.hash:08X}]"
    if stream.data_chunk is None:
        report.issue(
            "awc.stream.data.missing",
            "Audio stream has no data chunk",
            path=path,
        )
    if awc.multi_channel_flag:
        layout = stream.stream_format_chunk
        if layout is None:
            report.issue(
                "awc.stream.layout.missing",
                "Multichannel stream has no stream-format chunk",
                path=path,
            )
            return
        if layout.block_count <= 0 or layout.block_size <= 0:
            report.issue(
                "awc.stream.layout.invalid",
                "Multichannel block count and block size must be positive",
                path=path,
            )
        if not layout.channels:
            report.issue(
                "awc.stream.channels.invalid",
                "A multichannel stream must describe at least one channel",
                path=path,
            )
        channel_ids = [channel.id & AWC_STREAM_ID_MASK for channel in layout.channels]
        if len(channel_ids) != len(set(channel_ids)):
            report.issue(
                "awc.stream.channels.duplicate",
                "Multichannel stream contains duplicate channel IDs",
                path=path,
            )
        known_ids = {candidate.hash for candidate in awc.streams}
        for channel_id in channel_ids:
            if channel_id not in known_ids:
                report.issue(
                    "awc.stream.channel.missing",
                    f"Multichannel layout references missing stream 0x{channel_id:08X}",
                    path=path,
                )
        sample_rates = {int(channel.sample_rate) for channel in layout.channels}
        sample_counts = {int(channel.samples) for channel in layout.channels}
        if any(value <= 0 for value in sample_rates):
            report.issue(
                "awc.stream.sample_rate.invalid",
                "Every multichannel stream must have a positive sample rate",
                path=path,
            )
        if any(value <= 0 for value in sample_counts):
            report.issue(
                "awc.stream.sample_count.invalid",
                "Every multichannel stream must have a positive sample count",
                path=path,
            )
        if len(sample_rates) > 1 or len(sample_counts) > 1:
            report.issue(
                "awc.stream.channels.unsynchronized",
                "Multichannel streams must use equal sample rates and sample counts",
                path=path,
            )
        codecs = {channel.codec for channel in layout.channels}
        if codecs == {AwcCodecType.MP3} and stream.data_chunk is not None:
            from .streaming import (
                derive_mp3_streaming_seek_table,
                inspect_mp3_streaming_data,
            )

            try:
                expected_seek_table = derive_mp3_streaming_seek_table(
                    stream.data_chunk.data,
                    block_count=layout.block_count,
                    block_size=layout.block_size,
                    channel_count=len(layout.channels),
                )
            except ValueError:
                expected_seek_table = None
            blocks = None
            try:
                blocks = inspect_mp3_streaming_data(
                    stream.data_chunk.data,
                    block_count=layout.block_count,
                    block_size=layout.block_size,
                    channel_count=len(layout.channels),
                    sample_rate=next(iter(sample_rates), 0),
                )
            except ValueError as exc:
                report.issue(
                    "awc.stream.mp3.layout.invalid",
                    str(exc),
                    path=f"{path}.data",
                )
            else:
                for channel_index, channel in enumerate(layout.channels):
                    authored_samples = sum(
                        block.channels[channel_index].sample_count for block in blocks
                    )
                    if authored_samples != int(channel.samples):
                        report.issue(
                            "awc.stream.mp3.samples.invalid",
                            "MP3 block sample counts do not match the stream format",
                            path=f"{path}.channels[{channel_index}].samples",
                        )
            _validate_mp3_seek_table(
                report,
                stream,
                expected_seek_table,
                block_count=layout.block_count,
                path=f"{path}.seek_table",
            )
        return

    if stream.codec is None:
        report.issue(
            "awc.stream.format.missing",
            "Audio stream has no format metadata",
            path=path,
        )
    if stream.sample_rate <= 0:
        report.issue(
            "awc.stream.sample_rate.invalid",
            "Audio stream must have a positive sample rate",
            path=path,
        )
    if stream.sample_count <= 0:
        report.issue(
            "awc.stream.sample_count.invalid",
            "Audio stream must have a positive sample count",
            path=path,
        )


def validate_awc_stream(awc: Awc, stream: AwcStream) -> ValidationReport:
    report = ValidationReport()
    stream_ids = [candidate.hash for candidate in awc.streams]
    if len(stream_ids) != len(set(stream_ids)):
        report.issue(
            "awc.stream.id.duplicate",
            "AWC stream IDs must be unique",
            path="streams",
        )
    _validate_stream(report, awc, stream)
    return report


def validate_awc(awc: Awc) -> ValidationReport:
    report = validate_awc_binary_fields(awc)
    if awc.multi_channel_encrypt_flag and not awc.multi_channel_flag:
        report.issue(
            "awc.flags.multichannel_encryption.invalid",
            "Multichannel encryption requires a multichannel container",
            path="flags",
        )
    if awc.multi_channel_flag and awc.single_channel_encrypt_flag:
        report.issue(
            "awc.flags.encryption_mode.invalid",
            "Multichannel containers cannot use single-channel encryption",
            path="flags",
        )
    stream_ids = [stream.hash for stream in awc.streams]
    if len(stream_ids) != len(set(stream_ids)):
        report.issue(
            "awc.stream.id.duplicate",
            "AWC stream IDs must be unique",
            path="streams",
        )
    streams = awc_playback_streams(awc)
    if not streams:
        report.issue(
            "awc.stream.missing",
            "AWC contains no playable audio stream",
            severity=DiagnosticSeverity.WARNING,
            path="streams",
        )
    for stream in streams:
        _validate_stream(report, awc, stream)
    if awc.multi_channel_flag and len(streams) != 1:
        report.issue(
            "awc.stream.owner.invalid",
            "A multichannel AWC must have exactly one stream-format owner",
            path="streams",
        )
    return report


__all__ = [
    "awc_channel_codecs",
    "awc_playback_streams",
    "resolve_awc_playback_stream",
    "validate_awc",
    "validate_awc_stream",
]
