from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any

from .._native import NativeYedProgram
from ..vector import Vector4
from .enums import YedInstructionType

DofKey = tuple[int, int]
VariableKey = tuple[int, int]

_PROGRAM_CACHE_LIMIT = 64


@dataclass(slots=True, frozen=True)
class YedEvaluationIssue:
    code: str
    message: str
    expression: str | None = None
    stream: str | None = None
    instruction: int | None = None


@dataclass(slots=True)
class YedEvaluationResult:
    tracks: dict[DofKey, Vector4]
    output_tracks: dict[DofKey, Vector4] = field(default_factory=dict)
    variables: dict[VariableKey, Vector4] = field(default_factory=dict)
    evaluated_expressions: list[str] = field(default_factory=list)
    issues: list[YedEvaluationIssue] = field(default_factory=list)


@dataclass(slots=True)
class _CachedProgram:
    yed: Any
    skeleton: Any
    names: tuple[str | int, ...]
    signature: tuple[Any, ...]
    program: NativeYedProgram


_PROGRAM_CACHE: OrderedDict[tuple[int, int, tuple[str | int, ...]], _CachedProgram] = (
    OrderedDict()
)

_TRACK_OPERATIONS = {
    YedInstructionType.TRACK_GET,
    YedInstructionType.TRACK_GET_COMP,
    YedInstructionType.TRACK_GET_OFFSET,
    YedInstructionType.TRACK_GET_OFFSET_COMP,
    YedInstructionType.TRACK_GET_BONE_TRANSFORM,
    YedInstructionType.TRACK_VALID,
    YedInstructionType.UNKNOWN_23,
    YedInstructionType.TRACK_SET,
    YedInstructionType.TRACK_SET_COMP,
    YedInstructionType.TRACK_SET_OFFSET,
    YedInstructionType.TRACK_SET_OFFSET_COMP,
    YedInstructionType.TRACK_SET_BONE_TRANSFORM,
}
_VARIABLE_OPERATIONS = {
    YedInstructionType.GET_VARIABLE,
    YedInstructionType.SET_VARIABLE,
}
_JUMP_OPERATIONS = {
    YedInstructionType.JUMP,
    YedInstructionType.JUMP_IF_FALSE,
    YedInstructionType.JUMP_IF_TRUE,
}
_BLEND_OPERATIONS = {
    YedInstructionType.BLEND_VECTOR,
    YedInstructionType.BLEND_QUATERNION,
}


def _native_vector(value: object) -> tuple[float, float, float, float]:
    if isinstance(value, (int, float)):
        return float(value), 0.0, 0.0, 0.0
    values = tuple(float(item) for item in value)  # type: ignore[arg-type]
    if len(values) >= 4:
        return values[:4]  # type: ignore[return-value]
    if len(values) == 3:
        return values[0], values[1], values[2], 0.0
    if len(values) == 1:
        return values[0], 0.0, 0.0, 0.0
    return 0.0, 0.0, 0.0, 0.0


def _compile_blend(expression: Any, operands: Mapping[str, Any]) -> tuple[Any, ...]:
    sources = list(operands.get("source_infos", ()))
    values = list(operands.get("values", ()))
    interval_count = max(int(operands.get("num_source_weights", 1)), 1)
    compiled = []
    value_index = 0
    for group_start in range(0, len(sources), 4):
        group = sources[group_start : group_start + 4]
        if len(group) < 4:
            break
        block_count = 6 + (interval_count - 1) * 9
        block = values[value_index : value_index + block_count]
        value_index += block_count
        if len(block) < block_count:
            break
        for lane, source in enumerate(group):
            track_index = int(source.get("track_index", -1))
            if not 0 <= track_index < len(expression.tracks):
                continue
            track = expression.tracks[track_index]
            component = min(max(int(source.get("component_offset", 0)) // 4, 0), 3)
            axes = []
            for axis in range(3):
                intervals = tuple(
                    (
                        float(block[6 + interval * 9 + axis][lane]),
                        float(block[6 + interval * 9 + 3 + axis][lane]),
                        float(block[6 + interval * 9 + 6 + axis][lane]),
                    )
                    for interval in range(interval_count - 1)
                )
                axes.append(
                    (
                        float(block[axis][lane]),
                        float(block[3 + axis][lane]),
                        intervals,
                    )
                )
            compiled.append(
                (
                    int(track.bone_id),
                    int(track.track),
                    component,
                    tuple(axes),
                )
            )
    return tuple(compiled)


def _instruction_payload(expression: Any, instruction: Any) -> tuple[str, object]:
    try:
        operation = YedInstructionType(instruction.opcode)
    except ValueError:
        return "", None
    operands = instruction.operands
    try:
        if operation is YedInstructionType.PUSH_FLOAT:
            return "", float(operands["value"])
        if operation is YedInstructionType.PUSH_VECTOR:
            return "", _native_vector(operands["value"])
        if operation in _TRACK_OPERATIONS:
            return "", (
                int(operands.get("bone_id", 0)),
                int(operands.get("track", 0)),
                int(operands.get("component_index", 0)),
                int(operands.get("format", 0)),
                bool(operands.get("use_defaults", False)),
            )
        if operation in _VARIABLE_OPERATIONS:
            return "", (
                int(operands.get("variable", 0)),
                int(operands.get("variable_index", 0)),
            )
        if operation in _JUMP_OPERATIONS:
            return "", int(operands.get("instruction_offset", 0))
        if operation in _BLEND_OPERATIONS:
            return "", _compile_blend(expression, operands)
    except (IndexError, KeyError, TypeError, ValueError, OverflowError) as exc:
        return str(exc), None
    return "", None


def _compile_instruction(expression: Any, instruction: Any) -> tuple[Any, ...]:
    operand_error, payload = _instruction_payload(expression, instruction)
    return (
        int(instruction.opcode),
        int(getattr(instruction, "index", 0)),
        bool(instruction.parsed),
        str(getattr(instruction, "parse_error", "")),
        operand_error,
        payload,
    )


def _stream_name(stream: Any) -> str:
    return str(
        getattr(stream.name_hash, "text", None)
        or getattr(stream.name_hash, "uint", "")
    )


def _program_spec(expressions: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(
        (
            expression.short_name,
            tuple(
                (
                    _stream_name(stream),
                    tuple(
                        _compile_instruction(expression, instruction)
                        for instruction in stream.instructions
                    ),
                )
                for stream in expression.streams
            ),
        )
        for expression in expressions
    )


def _skeleton_defaults(skeleton: object | None) -> tuple[Any, ...]:
    return tuple(
        (
            int(getattr(bone, "tag", -1)),
            _native_vector(getattr(bone, "translation", (0.0, 0.0, 0.0))),
            _native_vector(getattr(bone, "rotation", (0.0, 0.0, 0.0, 1.0))),
            _native_vector(getattr(bone, "scale", (1.0, 1.0, 1.0))),
        )
        for bone in getattr(skeleton, "bones", ())
    )


def _resolve_expressions(
    yed: Any, names: tuple[str | int, ...]
) -> tuple[tuple[Any, ...], list[YedEvaluationIssue]]:
    expressions = []
    issues = []
    seen: set[int] = set()
    for name in names:
        expression = yed.get_expression(name)
        if expression is None:
            issues.append(
                YedEvaluationIssue(
                    "yed.expression_unresolved",
                    f"expression {name!r} was not found",
                    expression=str(name),
                )
            )
            continue
        identity = int(expression.name_hash.uint)
        if identity not in seen:
            seen.add(identity)
            expressions.append(expression)
    return tuple(expressions), issues


def _program_signature(expressions: tuple[Any, ...], skeleton: object | None) -> tuple[Any, ...]:
    bones = getattr(skeleton, "bones", ())
    return (
        tuple(
            (
                id(expression),
                tuple(
                    (id(stream), id(stream.instructions), len(stream.instructions))
                    for stream in expression.streams
                ),
            )
            for expression in expressions
        ),
        id(bones),
        len(bones),
    )


def _get_program(
    yed: Any,
    skeleton: object | None,
    names: tuple[str | int, ...],
    expressions: tuple[Any, ...],
) -> NativeYedProgram:
    cache_key = (id(yed), id(skeleton), names)
    signature = _program_signature(expressions, skeleton)
    cached = _PROGRAM_CACHE.get(cache_key)
    if (
        cached is not None
        and cached.yed is yed
        and cached.skeleton is skeleton
        and cached.names == names
        and cached.signature == signature
    ):
        _PROGRAM_CACHE.move_to_end(cache_key)
        return cached.program
    program = NativeYedProgram(_program_spec(expressions), _skeleton_defaults(skeleton))
    _PROGRAM_CACHE[cache_key] = _CachedProgram(
        yed=yed,
        skeleton=skeleton,
        names=names,
        signature=signature,
        program=program,
    )
    _PROGRAM_CACHE.move_to_end(cache_key)
    while len(_PROGRAM_CACHE) > _PROGRAM_CACHE_LIMIT:
        _PROGRAM_CACHE.popitem(last=False)
    return program


def _native_issues(values: Iterable[tuple[Any, ...]]) -> list[YedEvaluationIssue]:
    return [
        YedEvaluationIssue(
            str(code),
            str(message),
            expression=str(expression) or None,
            stream=str(stream) or None,
            instruction=None if instruction is None else int(instruction),
        )
        for code, message, expression, stream, instruction in values
    ]


def evaluate_yed(
    yed: Any,
    expression_names: Iterable[str | int],
    tracks: Mapping[DofKey, object],
    *,
    skeleton: object | None = None,
    time: float = 0.0,
    delta_time: float = 0.0,
    variables: MutableMapping[VariableKey, Vector4] | None = None,
) -> YedEvaluationResult:
    """Evaluate selected serialized RAGE expression streams against typed DOFs."""

    names = tuple(expression_names)
    expressions, resolution_issues = _resolve_expressions(yed, names)
    program = _get_program(yed, skeleton, names, expressions)
    variable_values: MutableMapping[VariableKey, Vector4] = (
        variables if variables is not None else {}
    )
    native_tracks = {key: _native_vector(value) for key, value in tracks.items()}
    native_variables = {
        key: _native_vector(value) for key, value in variable_values.items()
    }
    result_tracks, outputs, result_variables, native_issues = program.evaluate(
        native_tracks,
        native_variables,
        time,
        delta_time,
    )
    typed_tracks = {key: Vector4.from_iterable(value) for key, value in result_tracks.items()}
    typed_outputs = {key: Vector4.from_iterable(value) for key, value in outputs.items()}
    typed_variables = {
        key: Vector4.from_iterable(value) for key, value in result_variables.items()
    }
    if variables is not None:
        variables.clear()
        variables.update(typed_variables)
    return YedEvaluationResult(
        tracks=typed_tracks,
        output_tracks=typed_outputs,
        variables=typed_variables,
        evaluated_expressions=[expression.short_name for expression in expressions],
        issues=[*resolution_issues, *_native_issues(native_issues)],
    )


__all__ = [
    "DofKey",
    "VariableKey",
    "Vector4",
    "YedEvaluationIssue",
    "YedEvaluationResult",
    "evaluate_yed",
]
