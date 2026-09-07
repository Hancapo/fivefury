from __future__ import annotations

from collections.abc import Sequence

from ...authoring.diagnostics import ValidationReport
from ..model import YedExpression
from .frame import YedFrameLayout, _format_size, resolve_frame_indices


def validate_frame_binding(
    expression: YedExpression,
    frame: YedFrameLayout,
    indices: Sequence[int | None],
) -> ValidationReport:
    report = expression.validate_runtime_contract()
    report.extend(frame.validate(), path="frame")
    if len(indices) != len(expression.tracks):
        report.issue(
            "yed.frame.binding.count",
            f"Expected {len(expression.tracks)} logical indices, received {len(indices)}; allocator padding is not part of the track table",
            path="indices",
        )
    if not report.valid:
        return report
    expected = resolve_frame_indices(expression.tracks, frame)
    for index, (track, offset, target) in enumerate(
        zip(expression.tracks, indices, expected, strict=True)
    ):
        path = f"indices[{index}]"
        context = f"Bone {track.bone_id}, channel {track.track}, {track.format.name}"
        if offset is None:
            report.issue(
                "yed.frame.binding.unavailable",
                f"{context}: captured offset is unavailable, not a missing channel",
                path=path,
            )
            continue
        if not isinstance(offset, int):
            report.issue(
                "yed.frame.binding.type",
                f"{context}: offset must be an integer",
                path=path,
            )
            continue
        width = _format_size(track.format)
        if offset < 0 or offset + width > frame.buffer_size:
            report.issue(
                "yed.frame.binding.range",
                f"{context}: offset {offset} is outside the {frame.buffer_size}-byte frame",
                path=path,
            )
        if offset % width:
            report.issue(
                "yed.frame.binding.alignment",
                f"{context}: offset {offset} requires {width}-byte alignment",
                path=path,
            )
        if offset != target:
            report.issue(
                "yed.frame.binding.mismatch",
                f"{context}: expected offset {target}, received {offset}; rebind after frame or expression changes",
                path=path,
            )
    return report
