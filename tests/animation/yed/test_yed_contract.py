from __future__ import annotations

import copy
import struct
import zlib

import pytest

from fivefury import (
    GameTarget,
    MetaHash,
    YedExpression,
    YedFrameDof,
    YedInstruction,
    YedStream,
    YedTrackFormat,
    create_yed,
    evaluate_yed,
    read_yed,
)
from fivefury import (
    YedInstructionType as Op,
)
from fivefury.resource import build_rsc7, split_rsc7_sections


def access(op, bone=7, track=25):
    return YedInstruction(op, operands={"bone_id": bone, "track": track, "format": 0})


def expression(*instructions):
    result = YedExpression.create("probe")
    result.streams = [
        YedStream(
            MetaHash("main"),
            0,
            b"",
            b"",
            b"",
            instructions=[*instructions, YedInstruction(Op.END)],
        )
    ]
    return result


def guarded():
    return expression(
        access(Op.TRACK_VALID),
        YedInstruction(Op.JUMP_IF_FALSE, operands={"instruction_offset": 2}),
        access(Op.TRACK_GET),
        access(Op.TRACK_SET, track=0),
    )


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_guarded_signature_and_accelerators_match_independent_binary_contract(game):
    source = guarded().recalculate_runtime_contract()
    expected = zlib.crc32(struct.pack("<III", (25 << 16) | 7, 7, (25 << 16) | 7))
    assert source.signature == expected
    assert [(t.bone_id, t.track, t.flags) for t in source.tracks] == [
        (7, 25, 0x80),
        (7, 0, 0),
    ]
    valid, branch, read, write, _ = source.streams[0].instructions
    assert [i.operands["track_index"] for i in (valid, read, write)] == [0, 0, 1]
    assert branch.operands == {
        "instruction_offset": 2,
        "data1_offset": 0,
        "data2_offset": 16,
    }
    raw = create_yed(source, game=game).to_bytes()
    loaded = read_yed(raw)
    _, system, _ = split_rsc7_sections(raw)
    assert (
        struct.unpack_from("<I", system, loaded.expressions[0].offset + 0x74)[0]
        == expected
    )
    assert loaded.to_bytes() == raw
    assert loaded.validate_runtime_contract().valid


def test_repeated_reads_are_hashed_and_direction_is_part_of_deduplication():
    item = expression(
        access(Op.TRACK_GET),
        access(Op.TRACK_GET),
        YedInstruction(Op.VECTOR_ADD),
        access(Op.TRACK_SET),
    ).recalculate_runtime_contract()
    word = (25 << 16) | 7
    assert item.signature == zlib.crc32(struct.pack("<III", word, word, word))
    assert len(item.tracks) == 2
    assert [t.is_input for t in item.tracks] == [False, True]
    assert [
        i.operands["track_index"]
        for i in item.streams[0].instructions
        if "track_index" in i.operands
    ] == [1, 1, 0]


def test_stale_contract_validation_does_not_mutate_and_recalculation_is_deterministic():
    item = guarded().recalculate_runtime_contract()
    before = item.signature
    item.streams[0].instructions[2].operands["bone_id"] = 8
    state = copy.deepcopy(item)
    assert not item.validate_runtime_contract().valid
    assert item == state
    item.recalculate_runtime_contract()
    assert item.signature != before
    serialized = create_yed(item).to_bytes()
    item.recalculate_runtime_contract()
    assert create_yed(item).to_bytes() == serialized
    item.tracks[0].is_input = False
    assert "yed.native.tracks.mismatch" in {
        issue.code for issue in item.validate_runtime_contract()
    }


def test_zero_signature_export_fails_but_cpu_diagnostics_are_separate(tmp_path):
    item = guarded()
    yed = create_yed(item)
    result = evaluate_yed(yed, ["probe"], {(7, 25): (1, 2, 3, 0)})
    assert tuple(result.output_tracks[(7, 0)]) == (1, 2, 3, 0)
    assert not result.issues
    assert result.native_diagnostics[0].code == "yed.native.signature.zero"
    target = tmp_path / "invalid.yed"
    with pytest.raises(ValueError, match="signature.zero"):
        yed.save(target)
    assert not target.exists()


def test_direction_selects_missing_or_mistyped_frame_sentinel_without_aliasing():
    item = expression(
        access(Op.TRACK_GET), access(Op.TRACK_SET)
    ).recalculate_runtime_contract()
    assert item.resolve_frame_indices([], read_only_offset=8, write_only_offset=24) == (
        24,
        8,
    )
    wrong = [YedFrameDof(7, 25, YedTrackFormat.QUATERNION, 40)]
    assert item.resolve_frame_indices(
        wrong, read_only_offset=8, write_only_offset=24
    ) == (24, 8)
    matching = [YedFrameDof(7, 25, YedTrackFormat.VECTOR3, 40)]
    assert item.resolve_frame_indices(
        matching, read_only_offset=8, write_only_offset=24
    ) == (40, 40)


def test_imported_instruction_edits_are_not_silently_discarded_by_writer():
    source = read_yed(create_yed(guarded().recalculate_runtime_contract()).to_bytes())
    source.expressions[0].streams[0].instructions[2].operands["bone_id"] = 8
    assert source.dirty
    with pytest.raises(ValueError, match="stale|mismatch"):
        source.to_bytes()
    source.recalculate_runtime_contract()
    reread = read_yed(source.to_bytes())
    assert reread.expressions[0].streams[0].instructions[2].operands["bone_id"] == 8


def test_unrecognized_import_is_preserved_only_unchanged():
    valid = create_yed(guarded().recalculate_runtime_contract()).to_bytes()
    loaded = read_yed(valid)
    header, data, graphics = split_rsc7_sections(valid)
    system = bytearray(data)
    stream = loaded.expressions[0].streams[0]
    system[stream.offset + 16 + len(stream.data1) + len(stream.data2)] = 0xFE
    raw = build_rsc7(bytes(system), version=header.version, graphics_data=graphics)
    original = read_yed(raw)
    assert original.to_bytes() == raw
    original.expressions[0].name = "pack:/changed.expr"
    with pytest.raises(ValueError):
        original.to_bytes()


def test_failed_finalization_leaves_entire_dictionary_unchanged():
    yed = create_yed(guarded(), expression(YedInstruction(0xFE)))
    before = copy.deepcopy(yed)
    with pytest.raises(ValueError):
        yed.recalculate_runtime_contract()
    assert yed == before


def test_empty_expression_remains_valid_without_a_fake_signature():
    yed = create_yed("empty")
    assert yed.validate_runtime_contract().valid
    assert read_yed(yed.to_bytes()).expressions[0].signature == 0


def test_uninitialized_stack_output_cannot_be_finalized():
    with pytest.raises(ValueError, match="uninitialized"):
        expression(access(Op.TRACK_SET)).recalculate_runtime_contract()


def test_nested_conditional_visits_outer_output_before_condition_and_both_arms():
    item = expression(
        access(Op.TRACK_VALID, bone=1),
        YedInstruction(Op.JUMP_IF_FALSE, operands={"instruction_offset": 3}),
        YedInstruction(Op.POP),
        access(Op.TRACK_GET, bone=2),
        YedInstruction(Op.JUMP, operands={"instruction_offset": 2}),
        YedInstruction(Op.POP),
        access(Op.TRACK_GET, bone=3),
        access(Op.TRACK_SET, bone=4, track=0),
    ).recalculate_runtime_contract()
    words = [4, (25 << 16) | 1, (25 << 16) | 2, (25 << 16) | 3]
    assert item.signature == zlib.crc32(struct.pack("<4I", *words))
    assert [(t.bone_id, t.is_input) for t in item.tracks] == [
        (4, False),
        (1, True),
        (2, True),
        (3, True),
    ]


def test_access_order_changes_crc_even_with_the_same_dof_set():
    item = expression(
        access(Op.TRACK_GET, bone=1),
        access(Op.TRACK_GET, bone=2),
        YedInstruction(Op.VECTOR_ADD),
        access(Op.TRACK_SET, bone=3),
    ).recalculate_runtime_contract()
    signature = item.signature
    instructions = item.streams[0].instructions
    instructions[0], instructions[1] = instructions[1], instructions[0]
    assert not item.validate_runtime_contract().valid
    item.recalculate_runtime_contract()
    assert item.signature != signature


def test_discarded_read_still_contributes_to_the_runtime_contract():
    item = expression(
        access(Op.TRACK_GET, bone=1),
        YedInstruction(Op.POP),
        access(Op.TRACK_GET, bone=2),
        access(Op.TRACK_SET, bone=3, track=0),
    ).recalculate_runtime_contract()
    words = [(25 << 16) | 1, 3, (25 << 16) | 2]
    assert item.signature == zlib.crc32(struct.pack("<3I", *words))
    assert [(t.bone_id, t.is_input) for t in item.tracks] == [
        (1, True),
        (3, False),
        (2, True),
    ]
    assert read_yed(create_yed(item).to_bytes()).validate_runtime_contract().valid


def test_value_only_edits_still_require_coherent_buffers():
    item = expression(
        YedInstruction(Op.PUSH_FLOAT, operands={"value": 1.0}), access(Op.TRACK_SET)
    ).recalculate_runtime_contract()
    item.streams[0].instructions[0].operands["value"] = 2.0
    assert "yed.native.buffers.stale" in {
        issue.code for issue in item.validate_runtime_contract()
    }
    item.recalculate_runtime_contract()
    assert item.validate_runtime_contract().valid
