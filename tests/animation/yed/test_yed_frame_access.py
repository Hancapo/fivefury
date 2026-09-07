import copy

import pytest

from fivefury import (
    GameTarget,
    MetaHash,
    YedExpression,
    YedInstruction,
    YedStream,
    create_yed,
    read_yed,
)
from fivefury import (
    YedInstructionType as Op,
)
from fivefury.resource import build_rsc7, split_rsc7_sections


def program(read=Op.TRACK_GET_COMP, write=Op.TRACK_SET_COMP, format=2, component=0):
    expression = YedExpression.create("scalar")
    expression.streams.append(
        YedStream(
            MetaHash("main"),
            0,
            b"",
            b"",
            b"",
            instructions=[
                YedInstruction(
                    read,
                    operands={
                        "bone_id": 7,
                        "track": 30,
                        "format": format,
                        "component_index": component,
                    },
                ),
                YedInstruction(
                    write,
                    operands={
                        "bone_id": 7,
                        "track": 30,
                        "format": format,
                        "component_index": component,
                    },
                ),
                YedInstruction(Op.END),
            ],
        )
    )
    return expression


@pytest.mark.parametrize(
    "read,write",
    [
        (Op.TRACK_GET, Op.TRACK_SET_COMP),
        (Op.TRACK_GET_COMP, Op.TRACK_SET),
        (Op.TRACK_GET_OFFSET_COMP, Op.TRACK_SET_COMP),
        (Op.TRACK_GET_COMP, Op.TRACK_SET_OFFSET_COMP),
    ],
)
def test_scalar_frame_access_cannot_use_vector_width_opcodes(read, write):
    expression = program(read, write)
    before = copy.deepcopy(expression)
    assert "yed.native.frame.access_width" in {
        i.code for i in expression.validate_runtime_contract()
    }
    with pytest.raises(ValueError, match="yed.native.frame.access_width"):
        expression.recalculate_runtime_contract()
    assert expression == before


@pytest.mark.parametrize("format,component", [(2, 1), (2, -1), (0, 4), (1, 3)])
def test_component_access_cannot_escape_storage_or_address_quaternion_w_as_euler(
    format, component
):
    expression = program(format=format, component=component)
    assert "yed.native.frame.component" in {
        i.code for i in expression.validate_runtime_contract()
    }
    with pytest.raises(ValueError, match="yed.native.frame.component"):
        expression.recalculate_runtime_contract()


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_valid_scalar_components_roundtrip_and_unsafe_import_cannot_bypass_validation(
    game, tmp_path
):
    yed = create_yed(program().recalculate_runtime_contract(), game=game)
    raw = yed.to_bytes()
    loaded = read_yed(raw)
    assert loaded.validate_runtime_contract().valid
    assert loaded.to_bytes() == raw
    header, system, graphics = split_rsc7_sections(raw)
    stream = loaded.expressions[0].streams[0]
    system = bytearray(system)
    opcodes = stream.offset + 16 + len(stream.data1) + len(stream.data2)
    system[opcodes] = int(Op.TRACK_GET)
    unsafe = read_yed(
        build_rsc7(bytes(system), version=header.version, graphics_data=graphics)
    )
    assert not unsafe.dirty
    assert "yed.native.frame.access_width" in {
        i.code for i in unsafe.validate_runtime_contract()
    }
    target = tmp_path / "existing.yed"
    target.write_bytes(raw)
    with pytest.raises(ValueError, match="yed.native.frame.access_width"):
        unsafe.save(target)
    assert target.read_bytes() == raw
