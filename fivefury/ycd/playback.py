from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from .._native import _ffi
from ..vector import Quaternion, Vector4
from .channel_samples import decoded_channel_components
from .sequence_channels import YcdCachedQuaternionChannel, YcdChannelType
from .sequence_tracks import YcdAnimationTrack, is_ycd_rotation_track

if TYPE_CHECKING:
    from .model import YcdAnimation


def _sequence_snapshot(sequence):
    lanes = []
    layout = -1
    for channel in sequence.channels:
        if isinstance(channel, YcdCachedQuaternionChannel):
            if not sequence.is_cached_quaternion:
                raise ValueError(
                    "Compile requires cached quaternion opcodes to have a cached sequence layout"
                )
            layout = (
                -2
                if channel.channel_type is YcdChannelType.CACHED_QUATERNION2
                else int(channel.quat_index)
            )
        elif len(lanes) < 4:
            components = decoded_channel_components(channel)
            lanes.extend(
                np.ascontiguousarray(values)
                for values in components.T[: 4 - len(lanes)]
            )
    if sequence.is_cached_quaternion and layout == -1:
        raise ValueError(
            "Cached quaternion sequence is missing its reconstruction channel"
        )
    if layout >= 0 and (layout > 3 or len(lanes) != 3):
        raise ValueError(
            "Cached quaternion reconstruction requires three components and a valid omitted index"
        )
    if layout == -2 and len(lanes) != 4:
        raise ValueError("Cached quaternion normalization requires four components")
    return layout, tuple(lanes)


@dataclass(frozen=True, slots=True, init=False)
class YcdAnimationSampler:
    """An owned, immutable snapshot. Recompile explicitly after source edits."""

    frames: int
    sequence_frame_limit: int
    sample_bytes: int
    _plan: object

    def __init__(self, animation: YcdAnimation):
        keys = dict.fromkeys(
            (int(s.bone_id.bone_id), int(s.bone_id.track))
            for block in animation.sequences
            for s in block.anim_sequences
            if s.bone_id is not None
        )
        index = {key: i for i, key in enumerate(keys)}
        blocks = []
        sample_bytes = 0
        for block in animation.sequences:
            entries = []
            for sequence in block.anim_sequences:
                if sequence.bone_id is None:
                    continue
                key = (int(sequence.bone_id.bone_id), int(sequence.bone_id.track))
                layout, lanes = _sequence_snapshot(sequence)
                if layout != -1 and not is_ycd_rotation_track(key[1]):
                    raise ValueError(
                        "Cached quaternion layout requires a rotation track"
                    )
                entries.append((index[key], layout, lanes))
                sample_bytes += sum(lane.nbytes for lane in lanes)
            blocks.append(tuple(entries))
        plan = _ffi.ycd_playback_compile(
            tuple(blocks),
            tuple(keys),
            tuple(is_ycd_rotation_track(k[1]) for k in keys),
            Vector4,
            Quaternion,
        )
        object.__setattr__(self, "frames", int(animation.frames))
        object.__setattr__(
            self, "sequence_frame_limit", max(int(animation.sequence_frame_limit), 1)
        )
        object.__setattr__(self, "sample_bytes", sample_bytes)
        object.__setattr__(self, "_plan", plan)

    def evaluate_tracks(
        self,
        frame: float,
        *,
        track: int | YcdAnimationTrack | None = None,
        interpolate: bool = True,
    ) -> dict[tuple[int, int], Vector4 | Quaternion]:
        value = float(frame)
        if not math.isfinite(value):
            raise ValueError("YCD sample frame must be finite")
        return _ffi.ycd_playback_evaluate(
            self._plan,
            value,
            not interpolate or isinstance(frame, int),
            self.frames,
            self.sequence_frame_limit,
            None if track is None else int(track),
        )
