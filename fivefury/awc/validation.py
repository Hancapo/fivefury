from __future__ import annotations

from typing import TYPE_CHECKING

from ..authoring import DiagnosticSeverity, ValidationReport
from .constants import AWC_STREAM_ID_MASK

if TYPE_CHECKING:
    from .structures import Awc, AwcStream


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
        if len(layout.channels) < 2:
            report.issue(
                "awc.stream.channels.invalid",
                "A multichannel stream must describe at least two channels",
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
    report = ValidationReport()
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
    "awc_playback_streams",
    "resolve_awc_playback_stream",
    "validate_awc",
    "validate_awc_stream",
]
