import copy
from dataclasses import replace

import pytest

from fivefury import (
    GameTarget,
    MetaHash,
    YedExpression,
    YedFrameLayout,
    YedInstruction,
    YedStream,
    YedTrack,
    create_yed,
    read_yed,
)
from fivefury import (
    YedInstructionType as Op,
)
from tests.support.yed import large_expression


def complete_frame():
    channels = [
        t
        for bone in range(56462, 56717)
        for t in (
            YedTrack.vector3(bone),
            YedTrack.quaternion(bone, 1),
        )
    ]
    channels.extend(
        t
        for bone in range(56462, 56636)
        for t in (
            YedTrack.vector3(bone, 25),
            YedTrack.quaternion(bone, 26),
        )
    )
    return YedFrameLayout.derive(channels)


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_large_multistream_aliases_roundtrip_with_global_indices_and_complete_frame(
    game,
):
    expression = large_expression()
    frame = complete_frame()
    assert len(expression.tracks) == 588
    assert len(frame.dofs) == 858
    yed = create_yed(expression, game=game)
    yed.clone_expression("calibrated", "head")
    yed.clone_expression("calibrated", "upper")
    raw = yed.to_bytes()
    reread = read_yed(raw)
    assert reread.game == game
    assert reread.to_bytes() == raw
    expected = expression.resolve_frame_indices(frame)
    for alias in reread.expressions:
        assert alias.resolve_frame_indices(frame) == expected
        assert alias.validate_frame_binding(frame, expected).valid
        for stream in alias.streams:
            for instruction in stream.instructions:
                if instruction.type not in (Op.TRACK_GET, Op.TRACK_SET):
                    continue
                operand = instruction.operands
                track = alias.tracks[operand["track_index"]]
                assert (track.bone_id, track.track, int(track.format)) == (
                    operand["bone_id"],
                    operand["track"],
                    operand["format"],
                )
                assert track.is_input == (instruction.type == Op.TRACK_GET)
        assert alias.streams[1].instructions[0].operands["track_index"] >= 128
    lookup = {(d.track, d.bone_id): d.offset for d in frame.dofs}
    assert expected == tuple(lookup[t.track, t.bone_id] for t in expression.tracks)
    assert all(
        offset % 16 == 0 and offset + 16 <= frame.read_only_offset
        for offset in expected
    )


def test_corrupt_table_reports_exact_slot_alignment_range_and_identity_without_mutation():
    expression, frame = large_expression(), complete_frame()
    indices = list(expression.resolve_frame_indices(frame))
    indices[332] = 0xFFFF
    before = copy.deepcopy((expression, frame, indices))
    report = expression.validate_frame_binding(frame, indices)
    assert {i.code for i in report} == {
        "yed.frame.binding.range",
        "yed.frame.binding.alignment",
        "yed.frame.binding.mismatch",
    }
    assert all(i.path == "indices[332]" and "56545" in i.message for i in report)
    assert (expression, frame, indices) == before


def test_changed_frame_rejects_stale_aligned_offsets_and_rebinding_is_deterministic():
    expression, original = large_expression(), complete_frame()
    cached = expression.resolve_frame_indices(original)
    changed = YedFrameLayout.derive([*expression.tracks, YedTrack.vector3(1)])
    assert not expression.validate_frame_binding(changed, cached).valid
    refreshed = expression.resolve_frame_indices(changed)
    assert refreshed != cached
    assert expression.validate_frame_binding(changed, refreshed).valid


def test_missing_channels_use_directional_sentinels_but_missing_capture_data_is_an_error():
    expression = large_expression()
    frame = YedFrameLayout.derive([])
    indices = expression.resolve_frame_indices(frame)
    assert indices == tuple(0 if t.is_input else 16 for t in expression.tracks)
    assert expression.validate_frame_binding(frame, indices).valid
    unavailable = list(indices)
    unavailable[332] = None
    assert [i.code for i in expression.validate_frame_binding(frame, unavailable)] == [
        "yed.frame.binding.unavailable"
    ]
    assert [
        i.code for i in expression.validate_frame_binding(frame, indices + (0,) * 4)
    ] == ["yed.frame.binding.count"]


def test_expression_changes_require_recalculation_not_only_new_frame_indices():
    expression, frame = large_expression(), complete_frame()
    indices = expression.resolve_frame_indices(frame)
    expression.streams[0].instructions[0].operands["bone_id"] = 4
    assert "yed.native.signature.stale" in {
        i.code for i in expression.validate_frame_binding(frame, indices)
    }
    with pytest.raises(ValueError, match="yed.native"):
        expression.resolve_frame_indices(frame)
    expression.recalculate_runtime_contract()
    assert not expression.validate_frame_binding(frame, indices).valid


def test_layout_corruption_is_reported_before_binding_comparison():
    expression, frame = large_expression(), complete_frame()
    indices = expression.resolve_frame_indices(frame)
    broken = replace(
        frame, dofs=(replace(frame.dofs[0], offset=0xFFFF), *frame.dofs[1:])
    )
    report = expression.validate_frame_binding(broken, indices)
    assert any(i.path == "frame.dofs[0].offset" for i in report)


def test_scalar_bindings_accept_four_byte_alignment_and_reject_wrong_sentinel():
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
                    Op.TRACK_GET_COMP, operands={"bone_id": 2, "track": 30, "format": 2}
                ),
                YedInstruction(
                    Op.TRACK_SET_COMP, operands={"bone_id": 2, "track": 30, "format": 2}
                ),
                YedInstruction(Op.END),
            ],
        )
    )
    expression.recalculate_runtime_contract()
    frame = YedFrameLayout.derive([YedTrack.scalar(1, 30), YedTrack.scalar(2, 30)])
    assert expression.resolve_frame_indices(frame) == (4, 4)
    assert expression.validate_frame_binding(frame, (4, 4)).valid
    assert not expression.validate_frame_binding(
        frame, (frame.write_only_offset, frame.read_only_offset)
    ).valid


def test_matching_signatures_and_table_counts_do_not_certify_a_cached_binding():
    vector = large_expression()
    quaternion = copy.deepcopy(vector)
    for stream in quaternion.streams:
        for instruction in stream.instructions:
            if instruction.type in (Op.TRACK_GET, Op.TRACK_SET):
                instruction.operands["format"] = 1
    quaternion.recalculate_runtime_contract()
    assert quaternion.signature == vector.signature
    assert len(quaternion.tracks) == len(vector.tracks)
    frame = complete_frame()
    cached = vector.resolve_frame_indices(frame)
    assert not quaternion.validate_frame_binding(frame, cached).valid
    assert quaternion.validate_frame_binding(
        frame, quaternion.resolve_frame_indices(frame)
    ).valid
