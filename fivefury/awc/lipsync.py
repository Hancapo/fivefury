from __future__ import annotations

from ..authoring.diagnostics import ValidationReport
from ..ycd.model import Ycd, YcdClipAnimation


def validate_awc_lipsync(ycd: Ycd) -> ValidationReport:
    report = ValidationReport()
    if len(ycd.clips) != 1:
        report.issue(
            "awc.lipsync.clips.count",
            f"Lip-sync dictionaries require exactly one clip, got {len(ycd.clips)}",
            path="clips",
        )
        return report

    clip = ycd.clips[0]
    if not isinstance(clip, YcdClipAnimation):
        report.issue(
            "awc.lipsync.clip.type",
            "The lip-sync clip must be an animation clip",
            path="clips[0]",
        )
    elif clip.animation is None:
        report.issue(
            "awc.lipsync.clip.animation.required",
            "The lip-sync clip has no animation payload",
            path="clips[0].animation",
        )
    elif clip.animation not in ycd.animations:
        report.issue(
            "awc.lipsync.clip.animation.external",
            "The lip-sync clip references an animation outside the dictionary",
            path="clips[0].animation",
        )
    return report


def require_valid_awc_lipsync(ycd: Ycd) -> Ycd:
    validate_awc_lipsync(ycd).raise_for_errors()
    return ycd


__all__ = ["require_valid_awc_lipsync", "validate_awc_lipsync"]
