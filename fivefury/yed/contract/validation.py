from __future__ import annotations

from ...authoring.diagnostics import DiagnosticSeverity, ValidationReport
from ..enums import YedInstructionType as Op
from .derive import derive_contract
from .state import expression_state


def executable(expression) -> bool:
    return any(
        any(opcode != Op.END for opcode in stream.data3)
        or any(instruction.type != Op.END for instruction in stream.instructions)
        for stream in expression.streams
    )


def validate_expression_contract(expression) -> ValidationReport:
    report = ValidationReport()
    if not 0 <= expression.signature <= 0xFFFFFFFF:
        report.issue(
            "yed.native.signature.range", "Signature must fit uint32", path="signature"
        )
    if not executable(expression):
        return report
    if not expression.signature:
        report.issue(
            "yed.native.signature.zero",
            "Executable expression has no native attachment signature",
            path="signature",
        )
    original = expression._original_contract_state
    preserved = original is not None and original == expression_state(expression)
    try:
        expected = derive_contract(expression)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        report.issue(
            "yed.native.contract.unsupported",
            str(exc),
            severity=DiagnosticSeverity.WARNING
            if preserved
            else DiagnosticSeverity.ERROR,
        )
        return report
    if expression.signature and expression.signature != expected.signature:
        report.issue(
            "yed.native.signature.unverifiable"
            if preserved
            else "yed.native.signature.stale",
            "Original pre-packing signature is not reproducible"
            if preserved
            else "Signature does not match the instruction access traversal",
            path="signature",
            severity=DiagnosticSeverity.WARNING
            if preserved
            else DiagnosticSeverity.ERROR,
        )
    actual_tracks = [
        (track.bone_id, track.track, track.flags) for track in expression.tracks
    ]
    expected_tracks = [
        (track.bone_id, track.track, track.flags) for track in expected.tracks
    ]
    if actual_tracks != expected_tracks:
        report.issue(
            "yed.native.tracks.mismatch",
            "Directional track table does not match the instruction access traversal",
            path="tracks",
        )
    if expression.variables != expected.variables:
        report.issue(
            "yed.native.variables.mismatch",
            "Variable table does not match accelerated operands",
            path="variables",
        )
    if [spring.raw for spring in expression.springs] != [
        spring.raw for spring in expected.springs
    ]:
        report.issue(
            "yed.native.motions.mismatch",
            "Motion descriptors do not match the executable streams",
            path="springs",
        )
    for stream_index, (actual, rebuilt) in enumerate(
        zip(expression.streams, expected.streams, strict=True)
    ):
        if not preserved and (
            actual.data1,
            actual.data2,
            actual.data3,
            actual.depth,
        ) != (rebuilt.data1, rebuilt.data2, rebuilt.data3, rebuilt.depth):
            report.issue(
                "yed.native.buffers.stale",
                "Recalculate the runtime contract after changing instructions",
                path=f"streams[{stream_index}]",
            )
        for instruction_index, (left, right) in enumerate(
            zip(actual.instructions, rebuilt.instructions, strict=True)
        ):
            for key in (
                "track_index",
                "source_infos",
                "bone_track_rot",
                "bone_track_pos",
                "variable_index",
                "data1_offset",
                "data2_offset",
            ):
                if right.operands.get(key) != left.operands.get(key):
                    report.issue(
                        "yed.native.operand.mismatch",
                        f"Accelerated index or branch offset {key} is inconsistent",
                        path=f"streams[{stream_index}].instructions[{instruction_index}].{key}",
                    )
    if not preserved and expression.max_stream_size != expected.max_stream_size:
        report.issue(
            "yed.native.stream_size.stale",
            "Maximum stream size does not match the serialized instruction buffers",
            path="max_stream_size",
        )
    return report
