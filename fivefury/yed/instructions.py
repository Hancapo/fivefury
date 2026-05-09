from __future__ import annotations

import struct
from typing import Any

from .constants import SPRING_BLOCK_SIZE
from .enums import YedInstructionType
from .model import YedInstruction

_EMPTY_INSTRUCTIONS = {
    YedInstructionType.END,
    YedInstructionType.POP,
    YedInstructionType.DUP,
    YedInstructionType.PUSH0,
    YedInstructionType.PUSH1,
    YedInstructionType.VECTOR_ABS,
    YedInstructionType.VECTOR_NEG,
    YedInstructionType.VECTOR_RCP,
    YedInstructionType.VECTOR_SQRT,
    YedInstructionType.VECTOR_NEG3,
    YedInstructionType.VECTOR_SQUARE,
    YedInstructionType.VECTOR_DEG2RAD,
    YedInstructionType.VECTOR_RAD2DEG,
    YedInstructionType.VECTOR_SATURATE,
    YedInstructionType.FROM_EULER,
    YedInstructionType.TO_EULER,
    YedInstructionType.VECTOR_ADD,
    YedInstructionType.VECTOR_SUB,
    YedInstructionType.VECTOR_MUL,
    YedInstructionType.VECTOR_MIN,
    YedInstructionType.VECTOR_MAX,
    YedInstructionType.QUAT_MUL,
    YedInstructionType.VECTOR_GREATER_THAN,
    YedInstructionType.VECTOR_LESS_THAN,
    YedInstructionType.VECTOR_GREATER_EQUAL,
    YedInstructionType.VECTOR_LESS_EQUAL,
    YedInstructionType.VECTOR_CLAMP,
    YedInstructionType.VECTOR_LERP,
    YedInstructionType.VECTOR_MAD,
    YedInstructionType.QUAT_SLERP,
    YedInstructionType.TO_VECTOR,
    YedInstructionType.PUSH_TIME,
    YedInstructionType.VECTOR_TRANSFORM,
    YedInstructionType.PUSH_DELTA_TIME,
    YedInstructionType.VECTOR_EQUAL,
    YedInstructionType.VECTOR_NOT_EQUAL,
}

_BONE_INSTRUCTIONS = {
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

_VARIABLE_INSTRUCTIONS = {YedInstructionType.GET_VARIABLE, YedInstructionType.SET_VARIABLE}
_JUMP_INSTRUCTIONS = {YedInstructionType.JUMP, YedInstructionType.JUMP_IF_TRUE, YedInstructionType.JUMP_IF_FALSE}
_BLEND_INSTRUCTIONS = {YedInstructionType.BLEND_VECTOR, YedInstructionType.BLEND_QUATERNION}


def _take(data: bytes, offset: int, size: int, label: str) -> bytes:
    end = offset + size
    if offset < 0 or end > len(data):
        raise ValueError(f"{label} operands are truncated")
    return data[offset:end]


def _parse_blend(data1: bytes, offset: int) -> tuple[dict[str, Any], int]:
    start = offset
    byte_length, source_count, num_source_weights, unknown_1 = struct.unpack("<IIII", _take(data1, offset, 16, "blend"))
    offset += 16
    source_infos = []
    for _ in range(source_count):
        track_index, component_offset = struct.unpack("<HH", _take(data1, offset, 4, "blend source"))
        source_infos.append({"track_index": track_index, "component_offset": component_offset})
        offset += 4
    value_count = (source_count // 4) * (6 + ((max(num_source_weights, 1) - 1) * 9))
    values = []
    for _ in range(value_count):
        values.append(struct.unpack("<4f", _take(data1, offset, 16, "blend value")))
        offset += 16
    if byte_length and offset - start != byte_length:
        raise ValueError(f"blend byte length mismatch: declared {byte_length}, parsed {offset - start}")
    return (
        {
            "byte_length": byte_length,
            "source_count": source_count,
            "num_source_weights": num_source_weights,
            "unknown_1": unknown_1,
            "source_infos": source_infos,
            "values": values,
        },
        offset,
    )


def parse_instruction_buffers(data1: bytes, data2: bytes, data3: bytes) -> list[YedInstruction]:
    instructions: list[YedInstruction] = []
    offset1 = 0
    offset2 = 0
    for index, opcode in enumerate(data3):
        try:
            instruction_type = YedInstructionType(opcode)
            operands: dict[str, Any] = {}
            data1_offset = offset1
            data2_offset = offset2
            if instruction_type in _EMPTY_INSTRUCTIONS:
                pass
            elif instruction_type is YedInstructionType.PUSH_FLOAT:
                (value,) = struct.unpack("<f", _take(data2, offset2, 4, instruction_type.name))
                operands["value"] = value
                offset2 += 4
            elif instruction_type is YedInstructionType.PUSH_VECTOR:
                operands["value"] = struct.unpack("<4f", _take(data1, offset1, 16, instruction_type.name))
                offset1 += 16
            elif instruction_type in _BONE_INSTRUCTIONS:
                track_index, bone_id, track, format_value, component_index, use_defaults = struct.unpack(
                    "<HHBBBB",
                    _take(data2, offset2, 8, instruction_type.name),
                )
                operands.update(
                    {
                        "track_index": track_index,
                        "bone_id": bone_id,
                        "track": track,
                        "format": format_value,
                        "component_index": component_index,
                        "use_defaults": bool(use_defaults),
                    }
                )
                offset2 += 8
            elif instruction_type in _VARIABLE_INSTRUCTIONS:
                variable, variable_index = struct.unpack("<II", _take(data2, offset2, 8, instruction_type.name))
                operands.update({"variable": variable, "variable_index": variable_index})
                offset2 += 8
            elif instruction_type in _JUMP_INSTRUCTIONS:
                data1_offset_delta, data2_offset_delta, data3_offset = struct.unpack("<III", _take(data2, offset2, 12, instruction_type.name))
                operands.update(
                    {
                        "data1_offset": data1_offset_delta,
                        "data2_offset": data2_offset_delta,
                        "instruction_offset": data3_offset,
                    }
                )
                offset2 += 12
            elif instruction_type is YedInstructionType.DEFINE_SPRING:
                raw = _take(data1, offset1, SPRING_BLOCK_SIZE + 16, instruction_type.name)
                bone_track_rot, bone_track_pos, unknown_13, unknown_14 = struct.unpack_from("<IIII", raw, SPRING_BLOCK_SIZE)
                operands.update(
                    {
                        "spring_raw": raw[:SPRING_BLOCK_SIZE],
                        "bone_track_rot": bone_track_rot,
                        "bone_track_pos": bone_track_pos,
                        "unknown_13": unknown_13,
                        "unknown_14": unknown_14,
                    }
                )
                offset1 += SPRING_BLOCK_SIZE + 16
            elif instruction_type is YedInstructionType.LOOK_AT:
                raw = _take(data1, offset1, 32, instruction_type.name)
                operands.update(
                    {
                        "offset": struct.unpack_from("<4f", raw, 0),
                        "look_at_axis": struct.unpack_from("<I", raw, 16)[0],
                        "up_axis": struct.unpack_from("<I", raw, 20)[0],
                        "origin": struct.unpack_from("<I", raw, 24)[0],
                        "unknown_05": struct.unpack_from("<I", raw, 28)[0],
                    }
                )
                offset1 += 32
            elif instruction_type in _BLEND_INSTRUCTIONS:
                operands, offset1 = _parse_blend(data1, offset1)
            else:
                raise ValueError(f"unsupported YED instruction opcode {opcode:#04x}")
            instructions.append(
                YedInstruction(
                    instruction_type,
                    index=index,
                    data1_offset=data1_offset,
                    data2_offset=data2_offset,
                    operands=operands,
                )
            )
        except Exception as exc:
            instructions.append(YedInstruction(opcode, index=index, data1_offset=offset1, data2_offset=offset2, parsed=False, parse_error=str(exc)))
            break
    if instructions and all(instruction.parsed for instruction in instructions):
        if offset1 != len(data1):
            instructions.append(
                YedInstruction(
                    YedInstructionType.END,
                    index=len(instructions),
                    data1_offset=offset1,
                    data2_offset=offset2,
                    parsed=False,
                    parse_error=f"{len(data1) - offset1} trailing bytes in data1",
                )
            )
        elif offset2 != len(data2):
            instructions.append(
                YedInstruction(
                    YedInstructionType.END,
                    index=len(instructions),
                    data1_offset=offset1,
                    data2_offset=offset2,
                    parsed=False,
                    parse_error=f"{len(data2) - offset2} trailing bytes in data2",
                )
            )
    return instructions


def _append_blend(data: bytearray, operands: dict[str, Any]) -> None:
    source_infos = list(operands.get("source_infos", []))
    values = list(operands.get("values", []))
    num_source_weights = max(int(operands.get("num_source_weights", 1)), 1)
    source_count = int(operands.get("source_count", len(source_infos)))
    byte_length = 16 + (source_count * 4) + (len(values) * 16)
    data.extend(struct.pack("<IIII", byte_length, source_count, num_source_weights, int(operands.get("unknown_1", 0))))
    for source in source_infos:
        data.extend(struct.pack("<HH", int(source["track_index"]) & 0xFFFF, int(source["component_offset"]) & 0xFFFF))
    for value in values:
        data.extend(struct.pack("<4f", *value))


def build_instruction_buffers(instructions: list[YedInstruction]) -> tuple[bytes, bytes, bytes]:
    data1 = bytearray()
    data2 = bytearray()
    data3 = bytearray()
    for index, instruction in enumerate(instructions):
        instruction.require_parsed()
        instruction.index = index
        instruction.data1_offset = len(data1)
        instruction.data2_offset = len(data2)
        instruction_type = YedInstructionType(instruction.opcode)
        operands = instruction.operands
        data3.append(instruction_type.value)
        if instruction_type in _EMPTY_INSTRUCTIONS:
            continue
        if instruction_type is YedInstructionType.PUSH_FLOAT:
            data2.extend(struct.pack("<f", float(operands["value"])))
        elif instruction_type is YedInstructionType.PUSH_VECTOR:
            data1.extend(struct.pack("<4f", *operands["value"]))
        elif instruction_type in _BONE_INSTRUCTIONS:
            data2.extend(
                struct.pack(
                    "<HHBBBB",
                    int(operands["track_index"]) & 0xFFFF,
                    int(operands["bone_id"]) & 0xFFFF,
                    int(operands["track"]) & 0xFF,
                    int(operands["format"]) & 0xFF,
                    int(operands["component_index"]) & 0xFF,
                    1 if operands.get("use_defaults") else 0,
                )
            )
        elif instruction_type in _VARIABLE_INSTRUCTIONS:
            data2.extend(struct.pack("<II", int(operands["variable"]), int(operands.get("variable_index", 0))))
        elif instruction_type in _JUMP_INSTRUCTIONS:
            data2.extend(
                struct.pack(
                    "<III",
                    int(operands.get("data1_offset", 0)),
                    int(operands.get("data2_offset", 0)),
                    int(operands["instruction_offset"]),
                )
            )
        elif instruction_type is YedInstructionType.DEFINE_SPRING:
            spring_raw = bytes(operands["spring_raw"])
            if len(spring_raw) != SPRING_BLOCK_SIZE:
                raise ValueError("YED spring instruction raw block has invalid size")
            data1.extend(spring_raw)
            data1.extend(
                struct.pack(
                    "<IIII",
                    int(operands.get("bone_track_rot", 0)),
                    int(operands.get("bone_track_pos", 0)),
                    int(operands.get("unknown_13", 0)),
                    int(operands.get("unknown_14", 0)),
                )
            )
        elif instruction_type is YedInstructionType.LOOK_AT:
            data1.extend(struct.pack("<4f", *operands["offset"]))
            data1.extend(
                struct.pack(
                    "<IIII",
                    int(operands["look_at_axis"]),
                    int(operands["up_axis"]),
                    int(operands["origin"]),
                    int(operands.get("unknown_05", 0)),
                )
            )
        elif instruction_type in _BLEND_INSTRUCTIONS:
            _append_blend(data1, operands)
        else:
            raise ValueError(f"unsupported YED instruction opcode {instruction.opcode:#04x}")
    return bytes(data1), bytes(data2), bytes(data3)


__all__ = [
    "build_instruction_buffers",
    "parse_instruction_buffers",
]
