from __future__ import annotations

from typing import TYPE_CHECKING

from ..authoring import ValidationReport
from ..vector import Quaternion, Vector3
from .reader import read_ycd
from .sequence_tracks import YcdTrackFormat
from .write import build_ycd_bytes

if TYPE_CHECKING:
    from .cutscene import YcdCutsceneBuilder, YcdCutsceneSection


def validate_cutscene_section_precision(
    builder: YcdCutsceneBuilder,
    section: YcdCutsceneSection,
    report: ValidationReport,
) -> None:
    if not any(
        (track.channel_policy or builder.channel_policy).requires_validation
        for clip in builder._clips.values()
        for track in clip.tracks
    ):
        return

    output_index = builder.section_index_start + section.index
    decoded = read_ycd(build_ycd_bytes(builder._build_section(section.index)))
    for clip_spec in builder._clips.values():
        constrained = [
            (
                track,
                track.channel_policy or builder.channel_policy,
                track.samples[section.start_frame : section.end_frame + 1],
            )
            for track in clip_spec.tracks
            if (track.channel_policy or builder.channel_policy).requires_validation
        ]
        if not constrained:
            continue
        clip = decoded.get_clip(f"{clip_spec.name}-{output_index}")
        if clip is None or clip.animation is None:
            continue
        maximum_errors = [0.0] * len(constrained)
        maximum_angular_errors = [0.0] * len(constrained)
        for frame in range(section.frame_count):
            values = clip.animation.evaluate_tracks(frame, interpolate=False)
            for track_index, (track_spec, _policy, source) in enumerate(constrained):
                if frame >= len(source):
                    continue
                expected = source[frame]
                key = (int(track_spec.bone_id), int(track_spec.track))
                actual = values.get(key)
                if actual is None:
                    continue
                expected_components = (
                    expected.components
                    if isinstance(expected, (Vector3, Quaternion))
                    else (float(expected),)
                )
                components = actual.components[: len(expected_components)]
                if track_spec.format is YcdTrackFormat.QUATERNION:
                    if not isinstance(expected, Quaternion) or not isinstance(
                        actual, Quaternion
                    ):
                        raise TypeError("Quaternion precision validation requires Quaternion samples")
                    direct = max(
                        abs(left - right)
                        for left, right in zip(
                            expected_components, components, strict=True
                        )
                    )
                    negated = max(
                        abs(left + right)
                        for left, right in zip(
                            expected_components, components, strict=True
                        )
                    )
                    maximum_errors[track_index] = max(
                        maximum_errors[track_index], min(direct, negated)
                    )
                    maximum_angular_errors[track_index] = max(
                        maximum_angular_errors[track_index],
                        expected.angular_error_degrees(actual),
                    )
                else:
                    maximum_errors[track_index] = max(
                        maximum_errors[track_index],
                        max(
                            abs(left - right)
                            for left, right in zip(
                                expected_components, components, strict=True
                            )
                        ),
                    )

        for track_index, (track_spec, policy, _source) in enumerate(constrained):
            key = (int(track_spec.bone_id), int(track_spec.track))
            path = f"clips[{clip_spec.name}].tracks[{key[0]},{key[1]}]"
            maximum_error = maximum_errors[track_index]
            maximum_angular_error = maximum_angular_errors[track_index]
            if (
                policy.maximum_error is not None
                and maximum_error > policy.maximum_error
            ):
                report.issue(
                    "ycd.channel_precision.error_exceeded",
                    f"Binary read-back error {maximum_error:.9g} exceeds "
                    f"the requested {policy.maximum_error:.9g}",
                    asset=builder.name,
                    path=path,
                )
            if (
                track_spec.format is YcdTrackFormat.QUATERNION
                and policy.maximum_angular_error_degrees is not None
                and maximum_angular_error > policy.maximum_angular_error_degrees
            ):
                report.issue(
                    "ycd.channel_precision.angular_error_exceeded",
                    f"Binary angular error {maximum_angular_error:.9g} degrees exceeds "
                    f"the requested {policy.maximum_angular_error_degrees:.9g}",
                    asset=builder.name,
                    path=path,
                )


__all__ = ["validate_cutscene_section_precision"]
