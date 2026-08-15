from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from .model import Ycd
from .sequence_channels import (
    YcdAnimChannel,
    YcdCachedQuaternionChannel,
    YcdChannelType,
    YcdStaticQuaternionChannel,
)
from .sequence_tracks import is_ycd_rotation_track


class YcdQuaternionLayout(StrEnum):
    STATIC = "static"
    EXPLICIT = "explicit"
    CACHED_QUATERNION1 = "cached_quaternion1"
    CACHED_QUATERNION2 = "cached_quaternion2"


@dataclass(slots=True)
class YcdQuaternionLayoutAudit:
    counts: dict[tuple[int, YcdQuaternionLayout], int] = field(default_factory=dict)

    def count(
        self,
        layout: YcdQuaternionLayout,
        *,
        track: int | None = None,
    ) -> int:
        return sum(
            count
            for (track_id, current_layout), count in self.counts.items()
            if current_layout is layout and (track is None or track_id == int(track))
        )

    @property
    def dominant_dynamic_layout(self) -> YcdQuaternionLayout | None:
        dynamic = {
            layout: self.count(layout)
            for layout in YcdQuaternionLayout
            if layout is not YcdQuaternionLayout.STATIC
        }
        maximum = max(dynamic.values(), default=0)
        if maximum == 0:
            return None
        return min(layout for layout, count in dynamic.items() if count == maximum)


def _quaternion_layout(channels: list[YcdAnimChannel]) -> YcdQuaternionLayout:
    for channel in channels:
        if not isinstance(channel, YcdCachedQuaternionChannel):
            continue
        if channel.channel_type is YcdChannelType.CACHED_QUATERNION1:
            return YcdQuaternionLayout.CACHED_QUATERNION1
        return YcdQuaternionLayout.CACHED_QUATERNION2
    if len(channels) == 1 and isinstance(channels[0], YcdStaticQuaternionChannel):
        return YcdQuaternionLayout.STATIC
    return YcdQuaternionLayout.EXPLICIT


def audit_ycd_quaternion_layout(
    ycds: Iterable[Ycd],
) -> YcdQuaternionLayoutAudit:
    report = YcdQuaternionLayoutAudit()
    for ycd in ycds:
        for animation in ycd.animations:
            for sequence in animation.sequences:
                for anim_sequence in sequence.anim_sequences:
                    bone = anim_sequence.bone_id
                    if bone is None or not is_ycd_rotation_track(int(bone.track)):
                        continue
                    key = (int(bone.track), _quaternion_layout(anim_sequence.channels))
                    report.counts[key] = report.counts.get(key, 0) + 1
    return report


__all__ = [
    "YcdQuaternionLayout",
    "YcdQuaternionLayoutAudit",
    "audit_ycd_quaternion_layout",
]
