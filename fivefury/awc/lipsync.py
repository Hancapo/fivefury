from __future__ import annotations

from ..ycd import Ycd, YcdClipAnimation


def validate_awc_lipsync(ycd: Ycd) -> list[str]:
    issues: list[str] = []
    if len(ycd.clips) != 1:
        issues.append(
            f"lip-sync dictionaries require exactly one clip, got {len(ycd.clips)}"
        )
        return issues

    clip = ycd.clips[0]
    if not isinstance(clip, YcdClipAnimation):
        issues.append("the lip-sync clip must be an animation clip")
    elif clip.animation is None:
        issues.append("the lip-sync clip has no animation payload")
    elif clip.animation not in ycd.animations:
        issues.append("the lip-sync clip references an animation outside the dictionary")
    return issues


def require_valid_awc_lipsync(ycd: Ycd) -> Ycd:
    issues = validate_awc_lipsync(ycd)
    if issues:
        raise ValueError("invalid AWC lip-sync dictionary: " + "; ".join(issues))
    return ycd


__all__ = ["require_valid_awc_lipsync", "validate_awc_lipsync"]
