from __future__ import annotations

from ...authoring.diagnostics import ValidationReport
from ..enums import YedInstructionType as Op
from ..enums import YedTrackFormat
from .traversal import READS, WRITES

_FRAME_ACCESSES = READS | WRITES
_SCALAR_ACCESSES = {Op.TRACK_GET_COMP, Op.TRACK_SET_COMP, Op.TRACK_VALID}
_COMPONENT_ACCESSES = _SCALAR_ACCESSES | {
    Op.TRACK_GET_OFFSET_COMP,
    Op.TRACK_SET_OFFSET_COMP,
}


def validate_frame_accesses(expression) -> ValidationReport:
    report = ValidationReport()
    for stream_index, stream in enumerate(expression.streams):
        for index, instruction in enumerate(stream.instructions):
            op = instruction.type
            if op not in _FRAME_ACCESSES or not instruction.parsed:
                continue
            path = f"streams[{stream_index}].instructions[{index}]"
            operands = instruction.operands
            try:
                format = YedTrackFormat(operands["format"])
            except (KeyError, ValueError, TypeError):
                report.issue(
                    "yed.native.frame.format",
                    "Frame access requires a known storage format",
                    path=f"{path}.format",
                )
                continue
            if format == YedTrackFormat.FLOAT and op not in _SCALAR_ACCESSES:
                report.issue(
                    "yed.native.frame.access_width",
                    "This opcode requires vector storage; FLOAT reads and writes must use TRACK_GET_COMP or TRACK_SET_COMP",
                    path=f"{path}.format",
                )
            if op not in _COMPONENT_ACCESSES:
                continue
            component = operands.get("component_index", 0)
            maximum = (
                0
                if format == YedTrackFormat.FLOAT
                else 2
                if format == YedTrackFormat.QUATERNION and op != Op.TRACK_VALID
                else 3
            )
            if not isinstance(component, int) or not 0 <= component <= maximum:
                report.issue(
                    "yed.native.frame.component",
                    f"{format.name} access requires a component from 0 to {maximum}; quaternion component operations address Euler XYZ, not XYZW",
                    path=f"{path}.component_index",
                )
    return report
