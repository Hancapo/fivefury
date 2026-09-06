import struct

from fivefury import YedExpression, YedInstruction, YedInstructionType, YedTrack
from fivefury.hashing import crc32
from fivefury.yed.instructions import (
    build_instruction_buffers,
    parse_instruction_buffers,
)


def test_direction_is_independent_from_format_and_bone_identity():
    track = YedTrack.quaternion(123, 26, is_input=True)
    assert track.flags == 0x81
    track.is_input = False
    assert track.flags == 1
    assert track.bone_id == 123
    expression = YedExpression.create("test")
    read = expression.ensure_track(123, 26, is_input=True)
    write = expression.ensure_track(123, 26)
    assert read is not write
    assert expression.ensure_track(123, 26, is_input=True) is read


def test_crc32_standard_vector_and_incremental_seed():
    assert crc32(b"123456789") == 0xCBF43926
    assert crc32(b"56789", crc32(b"1234")) == 0xCBF43926


def test_rebuild_branches_refreshes_all_three_stream_offsets():
    instructions = [
        YedInstruction(YedInstructionType.PUSH1),
        YedInstruction(YedInstructionType.JUMP_IF_FALSE, operands={"instruction_offset": 2}),
        YedInstruction(YedInstructionType.PUSH_VECTOR, operands={"value": (1, 2, 3, 4)}),
        YedInstruction(YedInstructionType.PUSH_FLOAT, operands={"value": 5}),
        YedInstruction(YedInstructionType.END),
    ]
    data1, data2, data3 = build_instruction_buffers(instructions)
    assert struct.unpack_from("<III", data2) == (16, 4, 2)
    decoded = parse_instruction_buffers(data1, data2, data3)
    assert decoded[1].operands == {"data1_offset": 16, "data2_offset": 4, "instruction_offset": 2}
