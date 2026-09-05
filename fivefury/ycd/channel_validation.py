from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .._native import _ffi
from ..authoring import (
    AuthoringOperation,
    AuthoringProgress,
    AuthoringStage,
    ValidationReport,
)
from .reader import read_ycd
from .sequence_channels import (
    YcdAnimSequence,
    YcdCachedQuaternionChannel,
    YcdChannelType,
    YcdIndirectQuantizeFloatChannel,
    YcdLinearFloatChannel,
    YcdQuantizeFloatChannel,
    YcdRawFloatChannel,
)
from .sequence_tracks import YcdTrackFormat
from .write import build_ycd_bytes

if TYPE_CHECKING:
    from .cutscene import YcdCutsceneBuilder, YcdCutsceneSection
    from .model import Ycd


def _packed_samples(sequence: YcdAnimSequence, count: int) -> tuple[np.ndarray, int]:
    samples = np.zeros((count, 4), dtype=np.float64)
    component = 0
    layout = -1
    for channel in sequence.channels:
        if isinstance(channel, YcdCachedQuaternionChannel):
            layout = (
                int(channel.quat_index)
                if channel.channel_type is YcdChannelType.CACHED_QUATERNION1
                else -2
            )
            continue
        width = channel.component_count
        if component + width > 4:
            raise ValueError("YCD sequence exceeds four stored components")
        if isinstance(channel, YcdIndirectQuantizeFloatChannel):
            if channel.frames and len(channel.values):
                indices = np.resize(np.asarray(channel.frames, dtype=np.int64), count)
                values = np.asarray(channel.values, dtype=np.float64)
                samples[:, component] = values[indices]
            else:
                samples[:, component] = channel.offset
        elif isinstance(
            channel,
            (YcdRawFloatChannel, YcdQuantizeFloatChannel, YcdLinearFloatChannel),
        ):
            values = np.asarray(channel.values, dtype=np.float64)
            if len(values):
                samples[:, component] = (
                    values if len(values) == count else np.resize(values, count)
                )
            else:
                samples[:, component] = channel.evaluate_float(0)
        else:
            samples[:, component : component + width] = channel.evaluate_components(0)
        component += width
    return samples, layout


def validate_cutscene_section_precision(
    builder: YcdCutsceneBuilder,
    section: YcdCutsceneSection,
    report: ValidationReport,
    *,
    asset: Ycd | None = None,
    operation: AuthoringOperation | None = None,
) -> bytes | None:
    if not any(
        (track.channel_policy or builder.channel_policy).requires_validation
        for clip in builder._clips.values()
        for track in clip.tracks
    ):
        return None
    total = sum(
        (track.channel_policy or builder.channel_policy).requires_validation
        for clip in builder._clips.values()
        for track in clip.tracks
    )
    completed = 0
    progress_asset = f"{builder.name}-{builder.section_index_start + section.index}.ycd"
    if operation is not None:
        operation.checkpoint(
            AuthoringProgress(AuthoringStage.VALIDATE, progress_asset, 0, total)
        )
    encoded = build_ycd_bytes(
        asset if asset is not None else builder._build_section(section.index)
    )
    decoded = read_ycd(encoded)
    output_index = builder.section_index_start + section.index
    for clip_spec in builder._clips.values():
        constrained = [
            (track, track.channel_policy or builder.channel_policy)
            for track in clip_spec.tracks
            if (track.channel_policy or builder.channel_policy).requires_validation
        ]
        if not constrained:
            continue
        clip = decoded.get_clip(f"{clip_spec.name}-{output_index}")
        if clip is None or clip.animation is None:
            report.issue(
                "ycd.channel_precision.animation_missing",
                "Binary read-back is missing the animation required for precision validation",
                asset=builder.name,
                path=f"clips[{clip_spec.name}]",
            )
            continue
        animation = clip.animation
        blocks = [
            (
                block,
                {
                    (
                        int(sequence.bone_id.bone_id),
                        int(sequence.bone_id.track),
                    ): sequence
                    for sequence in block.anim_sequences
                    if sequence.bone_id is not None
                },
            )
            for block in animation.sequences
        ]
        for track, policy in constrained:
            key = (int(track.bone_id), int(track.track))
            path = f"clips[{clip_spec.name}].tracks[{key[0]},{key[1]}]"
            components = track.samples.window(
                section.start_frame, section.frame_count
            ).components
            dimensions = len(components)
            reference = np.zeros((section.frame_count, 4), dtype=np.float64)
            for index, values in enumerate(components):
                reference[:, index] = values
            maximum = [0.0, 0.0, 0.0]
            worst_frame = 0.0
            covered = 0
            for block_index, (block, sequences) in enumerate(blocks):
                if operation is not None:
                    operation.checkpoint()
                sequence = sequences.get(key)
                start = block_index * animation.sequence_frame_limit
                last_block = block_index == len(blocks) - 1
                count = min(
                    block.num_frames
                    if last_block
                    else animation.sequence_frame_limit + 1,
                    section.frame_count - start,
                )
                if sequence is None or count <= 0:
                    continue
                packed, layout = _packed_samples(sequence, count)
                if dimensions == 4 and layout == -1 and not last_block:
                    next_sequence = blocks[block_index + 1][1].get(key)
                    if next_sequence is not None:
                        packed[-1] = next_sequence.evaluate_quaternion(0).components
                integer_count = min(count, animation.sequence_frame_limit)
                if last_block:
                    integer_count = count
                errors = _ffi.ycd_compare_samples(
                    reference[start : start + count],
                    packed,
                    dimensions,
                    layout,
                    integer_count,
                    track.format is YcdTrackFormat.QUATERNION
                    and policy.maximum_angular_error_degrees is not None,
                )
                covered += integer_count
                if errors[2] > maximum[2]:
                    worst_frame = start + errors[3]
                maximum = [
                    max(previous, current)
                    for previous, current in zip(maximum, errors[:3], strict=True)
                ]
            if covered != section.frame_count:
                report.issue(
                    "ycd.channel_precision.track_missing",
                    "Binary read-back is missing track samples required for precision validation",
                    asset=builder.name,
                    path=path,
                )
                continue
            limits = (
                policy.maximum_error,
                policy.maximum_angular_error_degrees,
                policy.maximum_angular_error_degrees,
            )
            codes = (
                "error_exceeded",
                "angular_error_exceeded",
                "subframe_angular_error_exceeded",
            )
            labels = ("read-back", "angular", "subframe angular")
            for index, (error, limit) in enumerate(zip(maximum, limits, strict=True)):
                if limit is not None and error > limit:
                    report.issue(
                        f"ycd.channel_precision.{codes[index]}",
                        f"Binary {labels[index]} error {error:.9g} exceeds the requested {limit:.9g}",
                        asset=builder.name,
                        path=f"{path}.frames[{worst_frame:g}]" if index == 2 else path,
                    )
            completed += 1
            if operation is not None:
                operation.checkpoint(
                    AuthoringProgress(
                        AuthoringStage.VALIDATE, progress_asset, completed, total
                    )
                )
    return encoded


__all__ = ["validate_cutscene_section_precision"]
