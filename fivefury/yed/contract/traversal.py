from __future__ import annotations

from dataclasses import dataclass

from ..enums import YedInstructionType as Op
from ..model import YedInstruction

READS = frozenset(
    {
        Op.TRACK_GET,
        Op.TRACK_GET_COMP,
        Op.TRACK_GET_OFFSET,
        Op.TRACK_GET_OFFSET_COMP,
        Op.TRACK_GET_BONE_TRANSFORM,
        Op.TRACK_VALID,
        Op.UNKNOWN_23,
    }
)
WRITES = frozenset(
    {
        Op.TRACK_SET,
        Op.TRACK_SET_COMP,
        Op.TRACK_SET_OFFSET,
        Op.TRACK_SET_OFFSET_COMP,
        Op.TRACK_SET_BONE_TRANSFORM,
    }
)
BLENDS = frozenset({Op.BLEND_VECTOR, Op.BLEND_QUATERNION})
_PUSHES = (
    (READS - {Op.UNKNOWN_23})
    | BLENDS
    | {
        Op.PUSH0,
        Op.PUSH1,
        Op.PUSH_FLOAT,
        Op.PUSH_VECTOR,
        Op.PUSH_TIME,
        Op.PUSH_DELTA_TIME,
        Op.GET_VARIABLE,
    }
)
_UNARY = {
    Op.VECTOR_ABS,
    Op.VECTOR_NEG,
    Op.VECTOR_RCP,
    Op.VECTOR_SQRT,
    Op.VECTOR_NEG3,
    Op.VECTOR_SQUARE,
    Op.VECTOR_DEG2RAD,
    Op.VECTOR_RAD2DEG,
    Op.VECTOR_SATURATE,
    Op.FROM_EULER,
    Op.TO_EULER,
    Op.UNKNOWN_23,
}
_BINARY = {
    Op.VECTOR_ADD,
    Op.VECTOR_SUB,
    Op.VECTOR_MUL,
    Op.VECTOR_MIN,
    Op.VECTOR_MAX,
    Op.QUAT_MUL,
    Op.VECTOR_GREATER_THAN,
    Op.VECTOR_LESS_THAN,
    Op.VECTOR_GREATER_EQUAL,
    Op.VECTOR_LESS_EQUAL,
    Op.VECTOR_TRANSFORM,
    Op.VECTOR_EQUAL,
    Op.VECTOR_NOT_EQUAL,
}
_TERNARY = {
    Op.VECTOR_CLAMP,
    Op.VECTOR_LERP,
    Op.VECTOR_MAD,
    Op.QUAT_SLERP,
    Op.TO_VECTOR,
    Op.LOOK_AT,
}


class UnsupportedContract(ValueError):
    """The pre-packing access order cannot be established safely."""


@dataclass(frozen=True, slots=True, eq=False)
class _Node:
    instruction: YedInstruction | None = None
    children: tuple[_Node, ...] = ()
    uninitialized: bool = False


class _Traversal:
    def __init__(self, instructions: list[YedInstruction]):
        self.instructions = instructions
        self.depth = 1

    def target(self, index: int) -> int:
        target = (
            index + 1 + int(self.instructions[index].operands["instruction_offset"])
        )
        if not index < target < len(self.instructions):
            raise ValueError(f"Invalid branch target at instruction {index}")
        return target

    def parse(
        self,
        start: int,
        end: int,
        stack: list[_Node],
        consumed_condition: _Node | None = None,
    ) -> tuple[list[_Node], list[_Node]]:
        roots: list[_Node] = []
        index = start
        while index < end:
            instruction = self.instructions[index]
            instruction.require_parsed()
            op = instruction.type
            if op == Op.END:
                if index != len(self.instructions) - 1:
                    raise UnsupportedContract(
                        "Instructions following END are not authorable"
                    )
                break
            if op in (Op.JUMP_IF_FALSE, Op.JUMP_IF_TRUE):
                if not stack or stack[-1].uninitialized:
                    raise ValueError("Conditional branch has no condition")
                target = self.target(index)
                if target > end:
                    raise UnsupportedContract("Overlapping branch regions")
                condition = stack[-1]
                prefix = stack[:-1]
                has_else = (
                    target > index + 1 and self.instructions[target - 1].type == Op.JUMP
                )
                join = self.target(target - 1) if has_else else target
                if join > end:
                    raise UnsupportedContract("Branch escapes its enclosing expression")
                left_roots, left_stack = self.parse(
                    index + 1, target - int(has_else), stack.copy(), condition
                )
                right_roots, right_stack = (
                    self.parse(target, join, stack.copy(), condition)
                    if has_else
                    else ([], stack.copy())
                )
                if (
                    left_stack[: len(prefix)] != prefix
                    or right_stack[: len(prefix)] != prefix
                ):
                    raise UnsupportedContract("Branch rewrites an outer stack value")
                if left_roots or right_roots:
                    if left_stack != right_stack or left_stack not in (prefix, stack):
                        raise UnsupportedContract(
                            "Mixed statement/value branch requires an explicit expression tree"
                        )
                    roots.append(_Node(children=(condition, *left_roots, *right_roots)))
                    stack = prefix + ([_Node()] if left_stack == stack else [])
                else:
                    if len(left_stack) != len(stack) or len(right_stack) != len(stack):
                        raise UnsupportedContract(
                            "Conditional value has inconsistent stack depth"
                        )
                    children = (condition,) + tuple(
                        value
                        for value in (left_stack[-1], right_stack[-1])
                        if value is not condition
                    )
                    stack = prefix + [_Node(children=children)]
                index = join
                continue
            if op == Op.JUMP:
                raise UnsupportedContract(
                    "Unstructured jumps cannot establish expression traversal"
                )
            if op == Op.DUP:
                if not stack or stack[-1].instruction is not None or stack[-1].children:
                    raise UnsupportedContract(
                        "Duplicated computed values need the original expression tree"
                    )
                stack.append(_Node(uninitialized=stack[-1].uninitialized))
            elif op == Op.POP:
                if not stack:
                    raise ValueError("Expression stack underflow")
                discarded = stack.pop()
                if discarded is not consumed_condition and (
                    discarded.instruction is not None or discarded.children
                ):
                    roots.append(discarded)
            elif op in _PUSHES:
                stack.append(_Node(instruction))
            elif op == Op.DEFINE_SPRING:
                roots.append(_Node(instruction))
            else:
                arity = (
                    1
                    if op in _UNARY or op in WRITES or op == Op.SET_VARIABLE
                    else 2
                    if op in _BINARY
                    else 3
                    if op in _TERNARY
                    else 0
                )
                if not arity:
                    raise UnsupportedContract(
                        f"Unsupported contract opcode: {instruction.name}"
                    )
                if len(stack) < arity:
                    raise ValueError("Expression stack underflow")
                children = tuple(stack[-arity:])
                if any(child.uninitialized for child in children):
                    raise ValueError("Expression consumes an uninitialized stack slot")
                del stack[-arity:]
                node = _Node(instruction, children)
                if op in WRITES or op == Op.SET_VARIABLE:
                    roots.append(node)
                else:
                    stack.append(node)
            self.depth = max(self.depth, len(stack))
            if self.depth > 256:
                raise ValueError("YED expression exceeds the 256-slot runtime stack")
            index += 1
        return roots, stack


def preorder(instructions: list[YedInstruction]) -> tuple[list[YedInstruction], int]:
    """Recover supported expression trees from stack code, then visit parents first."""
    if not instructions or instructions[-1].type != Op.END:
        raise ValueError("YED streams must end with END")
    traversal = _Traversal(instructions)
    roots, stack = traversal.parse(0, len(instructions), [_Node(uninitialized=True)])
    pending = list(reversed([*roots, *stack]))
    result = []
    visited: set[int] = set()
    while pending:
        node = pending.pop()
        if node.instruction is not None:
            identity = id(node.instruction)
            if identity in visited:
                raise UnsupportedContract(
                    "A packed operation has multiple traversal owners"
                )
            visited.add(identity)
            result.append(node.instruction)
        pending.extend(reversed(node.children))
    return result, traversal.depth
