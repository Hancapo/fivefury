from __future__ import annotations

import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ...authoring.diagnostics import ValidationReport
from ...binary import align
from ...hashing import fletcher32
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


def _format_size(format: YedTrackFormat) -> int:
    return 4 if format == YedTrackFormat.FLOAT else 16


def _layout(formats: Sequence[YedTrackFormat]) -> tuple[list[int], int]:
    offsets = [0] * len(formats)
    cursor = 0
    for format in YedTrackFormat:
        size = _format_size(format)
        count = 0
        for index, item in enumerate(formats):
            if item == format:
                offsets[index] = cursor
                cursor += size
                count += 1
        cursor += (align(count, 4) - count) * size
    return offsets, cursor + 32


@dataclass(frozen=True, slots=True)
class YedFrameLayout:
    """Complete runtime DOF layout; offsets are frame bytes, not bone indices."""

    dofs: tuple[YedFrameDof, ...]
    buffer_size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "dofs", tuple(self.dofs))

    @classmethod
    def derive(cls, tracks: Iterable[YedTrack]) -> YedFrameLayout:
        channels = {}
        for track in tracks:
            key = (track.track, track.bone_id)
            if key in channels and channels[key] != track.format:
                raise ValueError("A frame DOF cannot have conflicting formats")
            channels[key] = track.format
        ordered = sorted(channels)
        offsets, size = _layout([channels[key] for key in ordered])
        if size > 0xFFFF:
            raise ValueError("Frame buffer exceeds its uint16 size")
        result = cls(
            tuple(
                YedFrameDof(bone, track, channels[track, bone], offset)
                for (track, bone), offset in zip(ordered, offsets, strict=True)
            ),
            size,
        )
        result.validate().raise_for_errors()
        return result

    @property
    def read_only_offset(self) -> int:
        return self.buffer_size - 32

    @property
    def write_only_offset(self) -> int:
        return self.buffer_size - 16

    @property
    def signature(self) -> int:
        self.validate().raise_for_errors()
        return fletcher32(
            b"".join(
                struct.pack(
                    "<HH", (dof.track << 8) | int(dof.format) | 0x80, dof.bone_id
                )
                for dof in self.dofs
            )
        )

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        if not 32 <= self.buffer_size <= 0xFFFF or self.buffer_size % 16:
            report.issue(
                "yed.frame.size",
                "Frame size must be 16-byte aligned and fit uint16, including two sentinel slots",
                path="buffer_size",
            )
        keys = [(dof.track, dof.bone_id) for dof in self.dofs]
        if keys != sorted(set(keys)):
            report.issue(
                "yed.frame.dofs.order",
                "Frame DOFs must be unique and sorted by track and bone ID",
                path="dofs",
            )
        offsets, size = _layout([dof.format for dof in self.dofs])
        if size != self.buffer_size:
            report.issue(
                "yed.frame.layout.size",
                f"Packed DOFs and sentinels require {size} bytes, not {self.buffer_size}",
                path="buffer_size",
            )
        for index, (dof, expected) in enumerate(zip(self.dofs, offsets, strict=True)):
            path = f"dofs[{index}].offset"
            width = _format_size(dof.format)
            if dof.offset % width:
                report.issue(
                    "yed.frame.offset.alignment",
                    f"Offset {dof.offset} requires {width}-byte alignment",
                    path=path,
                )
            if dof.offset + width > self.read_only_offset:
                report.issue(
                    "yed.frame.offset.range",
                    f"DOF storage at {dof.offset} exceeds the data region ending at {self.read_only_offset}",
                    path=path,
                )
            if dof.offset != expected:
                report.issue(
                    "yed.frame.offset.layout",
                    f"DOF offset is {dof.offset}; canonical frame layout requires {expected}",
                    path=path,
                )
        return report


def resolve_frame_indices(
    tracks: Sequence[YedTrack], frame: YedFrameLayout
) -> tuple[int, ...]:
    frame.validate().raise_for_errors()
    lookup = {(dof.track, dof.bone_id): dof for dof in frame.dofs}
    return tuple(
        dof.offset
        if (dof := lookup.get((track.track, track.bone_id))) is not None
        and dof.format == track.format
        else frame.read_only_offset
        if track.is_input
        else frame.write_only_offset
        for track in tracks
    )
