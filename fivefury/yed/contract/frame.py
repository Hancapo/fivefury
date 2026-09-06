from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..enums import YedTrackFormat
from ..model import YedTrack


@dataclass(frozen=True, slots=True)
class YedFrameDof:
    bone_id: int
    track: int
    format: YedTrackFormat
    offset: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "format", YedTrackFormat(self.format))
        if (
            not 0 <= self.bone_id <= 0xFFFF
            or not 0 <= self.track <= 0xFF
            or not 0 <= self.offset <= 0xFFFF
        ):
            raise ValueError("Frame DOF fields exceed their packed widths")


def resolve_frame_indices(
    tracks: Sequence[YedTrack],
    dofs: Sequence[YedFrameDof],
    *,
    read_only_offset: int,
    write_only_offset: int,
) -> tuple[int, ...]:
    if any(
        not 0 <= offset <= 0xFFFF
        for offset in (
            read_only_offset,
            write_only_offset,
            *(dof.offset for dof in dofs),
        )
    ):
        raise ValueError("Frame offsets must fit a uint16 expression accelerator")
    lookup = {}
    for dof in dofs:
        key = (dof.track, dof.bone_id)
        if key in lookup:
            raise ValueError("Duplicate frame DOF")
        lookup[key] = dof
    result = []
    for track in tracks:
        dof = lookup.get((track.track, track.bone_id))
        result.append(
            dof.offset
            if dof is not None and dof.format == track.format
            else read_only_offset
            if track.is_input
            else write_only_offset
        )
    return tuple(result)
