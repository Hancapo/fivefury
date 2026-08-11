from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any

from ..vector import (
    Vector4,
    quat_from_euler_xyz,
    quat_from_euler_xyz_raw,
    quat_inverse,
    quat_multiply,
    quat_multiply_raw,
    quat_nlerp,
    quat_normalize,
    quat_rotate_vector,
    quat_to_euler_xyz,
    vec4_map,
    vec4_map2,
)
from .enums import YedInstructionType, YedTrackFormat

DofKey = tuple[int, int]
VariableKey = tuple[int, int]

_LINEAR_BLEND_CACHE_LIMIT = 2048
_LINEAR_BLEND_CACHE: OrderedDict[tuple[int, int], tuple[Any, Any, tuple[Any, ...]]] = (
    OrderedDict()
)


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


def _v(value: object, *, scalar: bool = False) -> Vector4:
    if isinstance(value, (int, float)):
        number = float(value)
        return (number, number, number, number) if scalar else (number, 0.0, 0.0, 0.0)
    values = tuple(float(item) for item in value)  # type: ignore[arg-type]
    if len(values) >= 4:
        return values[:4]  # type: ignore[return-value]
    if len(values) == 3:
        return values[0], values[1], values[2], 0.0
    if len(values) == 1:
        return _v(values[0], scalar=scalar)
    return (0.0, 0.0, 0.0, 0.0)


def _quat_rotate(vector: Vector4, rotation: Vector4) -> Vector4:
    rotated = quat_rotate_vector(rotation, vector[:3])
    return (*rotated, vector[3])


class _Frame:
    def __init__(self, tracks: Mapping[DofKey, object], skeleton: object | None):
        self.tracks = {key: _v(value) for key, value in tracks.items()}
        self.outputs: dict[DofKey, Vector4] = {}
        self.defaults: dict[DofKey, Vector4] = {}
        self.bones = {
            int(getattr(bone, "tag", -1)): bone
            for bone in getattr(skeleton, "bones", ())
        }

    def default(self, key: DofKey) -> Vector4:
        cached = self.defaults.get(key)
        if cached is not None:
            return cached
        bone_id, track = key
        bone = self.bones.get(bone_id)
        if bone is not None and track == 0:
            value = _v(getattr(bone, "translation", (0.0, 0.0, 0.0)))
        elif bone is not None and track == 1:
            value = _v(getattr(bone, "rotation", (0.0, 0.0, 0.0, 1.0)))
        elif bone is not None and track == 2:
            value = _v(getattr(bone, "scale", (1.0, 1.0, 1.0)))
        elif track in (37, 38):
            value = (1.0, 1.0, 1.0, 0.0)
        else:
            value = (0.0, 0.0, 0.0, 1.0)
        self.defaults[key] = value
        return value

    def get(self, key: DofKey, force_default: bool = False) -> Vector4:
        if not force_default and key in self.tracks:
            return self.tracks[key]
        return self.default(key)

    def get_component(
        self, key: DofKey, component: int, format_value: int, force_default: bool
    ) -> Vector4:
        value = self.get(key, force_default)
        if int(format_value) == int(YedTrackFormat.QUATERNION):
            value = (*quat_to_euler_xyz(value), 0.0)
        component = min(max(int(component), 0), 3)
        return _v(value[component], scalar=True)

    def get_relative(self, key: DofKey, force_default: bool = False) -> Vector4:
        if force_default or key not in self.tracks:
            return (0.0, 0.0, 0.0, 1.0)
        current = self.tracks[key]
        default = self.default(key)
        if key[1] == 1 and key[0] in self.bones:
            return quat_multiply(quat_inverse(default), current)
        if key[1] in (0, 2) and key[0] in self.bones:
            return vec4_map2(current, default, lambda left, right: left - right)
        return (0.0, 0.0, 0.0, 1.0)

    def get_relative_component(
        self, key: DofKey, component: int, format_value: int, force_default: bool
    ) -> Vector4:
        value = self.get_relative(key, force_default)
        if int(format_value) == int(YedTrackFormat.QUATERNION):
            value = (*quat_to_euler_xyz(value), 0.0)
        component = min(max(int(component), 0), 3)
        return _v(value[component], scalar=True)

    def set(self, key: DofKey, value: Vector4) -> None:
        self.tracks[key] = value
        self.outputs[key] = value

    def set_relative(self, key: DofKey, value: Vector4) -> None:
        default = self.default(key)
        if key[1] == 1 and key[0] in self.bones:
            value = quat_multiply(default, value)
        elif key[1] in (0, 2) and key[0] in self.bones:
            value = vec4_map2(default, value, lambda left, right: left + right)
        self.set(key, value)

    def set_component(
        self, key: DofKey, component: int, format_value: int, scalar: float
    ) -> None:
        current = list(self.get(key))
        component = min(max(int(component), 0), 3)
        if int(format_value) == int(YedTrackFormat.QUATERNION):
            euler = list(quat_to_euler_xyz(tuple(current)))
            euler[component] = scalar
            self.set(key, quat_from_euler_xyz(tuple(euler)))
            return
        current[component] = scalar
        self.set(key, tuple(current))  # type: ignore[arg-type]

    def set_relative_component(
        self, key: DofKey, component: int, format_value: int, scalar: float
    ) -> None:
        default = self.default(key)
        if key[0] not in self.bones or key[1] not in (0, 1, 2):
            return
        component = min(max(int(component), 0), 3)
        if key[1] == 1 or int(format_value) == int(YedTrackFormat.QUATERNION):
            current_relative = list(
                quat_to_euler_xyz(
                    quat_multiply(quat_inverse(default), self.get(key))
                )
            )
            default_euler = quat_to_euler_xyz(default)
            current_relative[component] = scalar + default_euler[component]
            self.set(
                key,
                quat_multiply(default, quat_from_euler_xyz(tuple(current_relative))),
            )
            return
        current = list(self.get(key))
        current[component] = scalar + default[component]
        self.set(key, tuple(current))  # type: ignore[arg-type]


def _compile_linear_blend(
    expression: Any, operands: Mapping[str, Any]
) -> tuple[Any, ...]:
    cache_key = (id(expression), id(operands))
    cached = _LINEAR_BLEND_CACHE.get(cache_key)
    if cached is not None and cached[0] is expression and cached[1] is operands:
        _LINEAR_BLEND_CACHE.move_to_end(cache_key)
        return cached[2]
    sources = list(operands.get("source_infos", ()))
    values = list(operands.get("values", ()))
    interval_count = max(int(operands.get("num_source_weights", 1)), 1)
    compiled: list[Any] = []
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
            component = max(0, int(source.get("component_offset", 0)) // 4)
            axes: list[Any] = []
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
                    (int(track.bone_id), int(track.track)),
                    min(component, 3),
                    tuple(axes),
                )
            )
    result = tuple(compiled)
    _LINEAR_BLEND_CACHE[cache_key] = (expression, operands, result)
    _LINEAR_BLEND_CACHE.move_to_end(cache_key)
    while len(_LINEAR_BLEND_CACHE) > _LINEAR_BLEND_CACHE_LIMIT:
        _LINEAR_BLEND_CACHE.popitem(last=False)
    return result


def _linear_blend(
    expression: Any,
    operands: Mapping[str, Any],
    frame: _Frame,
    *,
    quaternion: bool,
) -> Vector4:
    result = (0.0, 0.0, 0.0, 1.0) if quaternion else (0.0, 0.0, 0.0, 0.0)
    for key, component, axes in _compile_linear_blend(expression, operands):
        input_value = frame.get(key)[component]
        partial = []
        for multiplier, additive, intervals in axes:
            value = additive + multiplier * input_value
            for begin, multiplier, additive in intervals:
                if input_value > begin:
                    value = additive + multiplier * input_value
            partial.append(value)
        if quaternion:
            result = quat_multiply_raw(
                result, quat_from_euler_xyz_raw(tuple(partial))
            )
        else:
            result = (
                result[0] + partial[0],
                result[1] + partial[1],
                result[2] + partial[2],
                0.0,
            )
    return quat_normalize(result) if quaternion else result


def _frame_operand(instruction: Any) -> tuple[DofKey, int, int, bool]:
    operands = instruction.operands
    return (
        (int(operands.get("bone_id", 0)), int(operands.get("track", 0))),
        int(operands.get("component_index", 0)),
        int(operands.get("format", 0)),
        bool(operands.get("use_defaults", False)),
    )


def _run_stream(
    expression: Any,
    stream: Any,
    frame: _Frame,
    variables: MutableMapping[VariableKey, Vector4],
    *,
    time: float,
    delta_time: float,
) -> list[YedEvaluationIssue]:
    issues: list[YedEvaluationIssue] = []
    stack: list[Vector4] = []
    instructions = stream.instructions
    pc = 0
    steps = 0
    max_steps = max(1024, len(instructions) * 8)

    def fail(code: str, message: str, instruction: Any) -> None:
        issues.append(
            YedEvaluationIssue(
                code,
                message,
                expression=expression.short_name,
                stream=str(
                    getattr(stream.name_hash, "text", None)
                    or getattr(stream.name_hash, "uint", "")
                ),
                instruction=int(getattr(instruction, "index", pc)),
            )
        )

    while 0 <= pc < len(instructions) and steps < max_steps:
        instruction = instructions[pc]
        steps += 1
        if not instruction.parsed:
            fail("yed.vm.unparsed_instruction", instruction.parse_error, instruction)
            break
        try:
            op = YedInstructionType(instruction.opcode)
        except ValueError:
            fail(
                "yed.vm.unknown_opcode",
                f"unsupported opcode 0x{instruction.opcode:02X}",
                instruction,
            )
            break
        operands = instruction.operands
        next_pc = pc + 1
        try:
            if op is YedInstructionType.END:
                break
            if op is YedInstructionType.POP:
                stack.pop()
            elif op is YedInstructionType.DUP:
                stack.append(stack[-1])
            elif op is YedInstructionType.PUSH0:
                stack.append((0.0, 0.0, 0.0, 0.0))
            elif op is YedInstructionType.PUSH1:
                stack.append((1.0, 1.0, 1.0, 1.0))
            elif op is YedInstructionType.PUSH_FLOAT:
                stack.append(_v(operands["value"], scalar=True))
            elif op is YedInstructionType.PUSH_VECTOR:
                stack.append(_v(operands["value"]))
            elif op in {
                YedInstructionType.TRACK_GET,
                YedInstructionType.TRACK_GET_COMP,
                YedInstructionType.TRACK_GET_OFFSET,
                YedInstructionType.TRACK_GET_OFFSET_COMP,
                YedInstructionType.TRACK_VALID,
            }:
                key, component, format_value, force_default = _frame_operand(
                    instruction
                )
                if op is YedInstructionType.TRACK_GET:
                    stack.append(frame.get(key, force_default))
                elif op is YedInstructionType.TRACK_GET_COMP:
                    stack.append(
                        frame.get_component(key, component, format_value, force_default)
                    )
                elif op is YedInstructionType.TRACK_GET_OFFSET:
                    stack.append(frame.get_relative(key, force_default))
                elif op is YedInstructionType.TRACK_GET_OFFSET_COMP:
                    stack.append(
                        frame.get_relative_component(
                            key, component, format_value, force_default
                        )
                    )
                else:
                    valid = key in frame.tracks
                    stack.append(_v(1.0 if valid else 0.0, scalar=True))
            elif op in {
                YedInstructionType.TRACK_SET,
                YedInstructionType.TRACK_SET_COMP,
                YedInstructionType.TRACK_SET_OFFSET,
                YedInstructionType.TRACK_SET_OFFSET_COMP,
            }:
                key, component, format_value, _ = _frame_operand(instruction)
                value = stack.pop()
                if op is YedInstructionType.TRACK_SET:
                    frame.set(key, value)
                elif op is YedInstructionType.TRACK_SET_COMP:
                    frame.set_component(key, component, format_value, value[0])
                elif op is YedInstructionType.TRACK_SET_OFFSET:
                    frame.set_relative(key, value)
                else:
                    frame.set_relative_component(key, component, format_value, value[0])
            elif op is YedInstructionType.DEFINE_SPRING:
                pass
            elif op is YedInstructionType.VECTOR_ABS:
                stack[-1] = vec4_map(stack[-1], abs)
            elif op is YedInstructionType.VECTOR_NEG:
                stack[-1] = vec4_map(stack[-1], lambda value: -value)
            elif op is YedInstructionType.VECTOR_RCP:
                stack[-1] = vec4_map(
                    stack[-1], lambda value: 1.0 / value if value else 0.0
                )
            elif op is YedInstructionType.VECTOR_SQRT:
                stack[-1] = vec4_map(
                    stack[-1], lambda value: math.sqrt(max(value, 0.0))
                )
            elif op is YedInstructionType.VECTOR_NEG3:
                value = stack[-1]
                stack[-1] = (-value[0], -value[1], -value[2], value[3])
            elif op is YedInstructionType.VECTOR_SQUARE:
                stack[-1] = vec4_map(stack[-1], lambda value: value * value)
            elif op is YedInstructionType.VECTOR_DEG2RAD:
                stack[-1] = vec4_map(stack[-1], math.radians)
            elif op is YedInstructionType.VECTOR_RAD2DEG:
                stack[-1] = vec4_map(stack[-1], math.degrees)
            elif op is YedInstructionType.VECTOR_SATURATE:
                stack[-1] = vec4_map(
                    stack[-1], lambda value: max(0.0, min(1.0, value))
                )
            elif op is YedInstructionType.FROM_EULER:
                stack[-1] = quat_from_euler_xyz(stack[-1][:3])
            elif op is YedInstructionType.TO_EULER:
                stack[-1] = (*quat_to_euler_xyz(stack[-1]), 0.0)
            elif op in {
                YedInstructionType.VECTOR_ADD,
                YedInstructionType.VECTOR_SUB,
                YedInstructionType.VECTOR_MUL,
                YedInstructionType.VECTOR_MIN,
                YedInstructionType.VECTOR_MAX,
                YedInstructionType.VECTOR_GREATER_THAN,
                YedInstructionType.VECTOR_LESS_THAN,
                YedInstructionType.VECTOR_GREATER_EQUAL,
                YedInstructionType.VECTOR_LESS_EQUAL,
                YedInstructionType.VECTOR_EQUAL,
                YedInstructionType.VECTOR_NOT_EQUAL,
            }:
                right, left = stack.pop(), stack.pop()
                operations = {
                    YedInstructionType.VECTOR_ADD: lambda a, b: a + b,
                    YedInstructionType.VECTOR_SUB: lambda a, b: a - b,
                    YedInstructionType.VECTOR_MUL: lambda a, b: a * b,
                    YedInstructionType.VECTOR_MIN: min,
                    YedInstructionType.VECTOR_MAX: max,
                    YedInstructionType.VECTOR_GREATER_THAN: lambda a, b: (
                        1.0 if a > b else 0.0
                    ),
                    YedInstructionType.VECTOR_LESS_THAN: lambda a, b: (
                        1.0 if a < b else 0.0
                    ),
                    YedInstructionType.VECTOR_GREATER_EQUAL: lambda a, b: (
                        1.0 if a >= b else 0.0
                    ),
                    YedInstructionType.VECTOR_LESS_EQUAL: lambda a, b: (
                        1.0 if a <= b else 0.0
                    ),
                    YedInstructionType.VECTOR_EQUAL: lambda a, b: (
                        1.0 if a == b else 0.0
                    ),
                    YedInstructionType.VECTOR_NOT_EQUAL: lambda a, b: (
                        1.0 if a != b else 0.0
                    ),
                }
                stack.append(vec4_map2(left, right, operations[op]))
            elif op is YedInstructionType.QUAT_MUL:
                right, left = stack.pop(), stack.pop()
                stack.append(quat_multiply(left, right))
            elif op is YedInstructionType.VECTOR_CLAMP:
                maximum, minimum, value = stack.pop(), stack.pop(), stack.pop()
                stack.append(
                    tuple(max(minimum[i], min(maximum[i], value[i])) for i in range(4))
                )  # type: ignore[arg-type]
            elif op is YedInstructionType.VECTOR_LERP:
                amount, end, start = stack.pop(), stack.pop(), stack.pop()
                stack.append(
                    tuple(start[i] + (end[i] - start[i]) * amount[i] for i in range(4))
                )  # type: ignore[arg-type]
            elif op is YedInstructionType.VECTOR_MAD:
                add, multiplier, value = stack.pop(), stack.pop(), stack.pop()
                stack.append(tuple(add[i] + value[i] * multiplier[i] for i in range(4)))  # type: ignore[arg-type]
            elif op is YedInstructionType.QUAT_SLERP:
                amount, end, start = stack.pop(), stack.pop(), stack.pop()
                stack.append(quat_nlerp(start, end, amount[0]))
            elif op is YedInstructionType.TO_VECTOR:
                z, y, x = stack.pop(), stack.pop(), stack.pop()
                stack.append((x[0], y[0], z[0], 0.0))
            elif op is YedInstructionType.PUSH_TIME:
                stack.append(_v(time, scalar=True))
            elif op is YedInstructionType.PUSH_DELTA_TIME:
                stack.append(_v(delta_time, scalar=True))
            elif op is YedInstructionType.VECTOR_TRANSFORM:
                rotation, vector = stack.pop(), stack.pop()
                stack.append(_quat_rotate(vector, rotation))
            elif op is YedInstructionType.GET_VARIABLE:
                variable_hash = int(operands.get("variable", 0))
                index = int(operands.get("variable_index", 0))
                stack.append(
                    variables.get(
                        (variable_hash, index), (0.0, 0.0, 0.0, 0.0)
                    )
                )
            elif op is YedInstructionType.SET_VARIABLE:
                variable_hash = int(operands.get("variable", 0))
                index = int(operands.get("variable_index", 0))
                variables[(variable_hash, index)] = stack.pop()
            elif op in {
                YedInstructionType.BLEND_VECTOR,
                YedInstructionType.BLEND_QUATERNION,
            }:
                stack.append(
                    _linear_blend(
                        expression,
                        operands,
                        frame,
                        quaternion=op is YedInstructionType.BLEND_QUATERNION,
                    )
                )
            elif op in {
                YedInstructionType.JUMP,
                YedInstructionType.JUMP_IF_TRUE,
                YedInstructionType.JUMP_IF_FALSE,
            }:
                take = op is YedInstructionType.JUMP
                if op is YedInstructionType.JUMP_IF_TRUE:
                    take = not all(component == 0.0 for component in stack[-1])
                elif op is YedInstructionType.JUMP_IF_FALSE:
                    take = all(component == 0.0 for component in stack[-1])
                if take:
                    next_pc = pc + 1 + int(operands.get("instruction_offset", 0))
                    if not 0 <= next_pc < len(instructions):
                        raise ValueError(f"jump target {next_pc} is outside the stream")
            else:
                fail(
                    "yed.vm.unsupported_instruction",
                    f"{op.name} is not implemented",
                    instruction,
                )
                break
        except (IndexError, KeyError, TypeError, ValueError, OverflowError) as exc:
            fail("yed.vm.execution_error", f"{op.name}: {exc}", instruction)
            break
        pc = next_pc
    if 0 <= pc < len(instructions) and steps >= max_steps:
        issues.append(
            YedEvaluationIssue(
                "yed.vm.step_limit",
                "expression stream exceeded its deterministic instruction limit",
                expression=expression.short_name,
            )
        )
    return issues


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
    """Evaluate selected serialized RAGE expression streams against typed DOFs.

    Expressions are processed in the supplied order. Unknown or unparsed VM
    instructions stop only their containing stream and are reported; no pose is
    guessed for unsupported operations.
    """

    frame = _Frame(tracks, skeleton)
    variable_values: MutableMapping[VariableKey, Vector4] = (
        variables if variables is not None else {}
    )
    result = YedEvaluationResult(frame.tracks, variables=dict(variable_values))
    seen: set[int] = set()
    for name in expression_names:
        expression = yed.get_expression(name)
        if expression is None:
            result.issues.append(
                YedEvaluationIssue(
                    "yed.expression_unresolved",
                    f"expression {name!r} was not found",
                    expression=str(name),
                )
            )
            continue
        identity = int(expression.name_hash.uint)
        if identity in seen:
            continue
        seen.add(identity)
        result.evaluated_expressions.append(expression.short_name)
        for stream in expression.streams:
            result.issues.extend(
                _run_stream(
                    expression,
                    stream,
                    frame,
                    variable_values,
                    time=float(time),
                    delta_time=float(delta_time),
                )
            )
    result.tracks = frame.tracks
    result.output_tracks = frame.outputs
    result.variables = dict(variable_values)
    return result


__all__ = [
    "DofKey",
    "VariableKey",
    "Vector4",
    "YedEvaluationIssue",
    "YedEvaluationResult",
    "evaluate_yed",
]
