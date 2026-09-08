from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from fivefury import (
    MetaHash,
    Quaternion,
    Vector3,
    Vector4,
    YedExpression,
    YedInstruction,
    YedStream,
    create_yed,
    evaluate_yed,
)
from fivefury import (
    YedInstructionType as Op,
)
from tests.support.yed import large_expression


def test_compiled_evaluator_matches_public_typed_results_and_diagnostics():
    yed = create_yed(large_expression())
    names = ("calibrated", "missing", "calibrated")
    tracks = {
        (t.bone_id, t.track): Vector4(0.1, 0.2, 0.3, 1)
        for t in yed.expressions[0].tracks
        if t.is_input
    }
    compiled = yed.compile(names)
    for value in (
        Vector4(1, 2, 3, 4),
        Quaternion(),
        Vector3(1, 2, 3),
        1.5,
        [1, 2],
        (1,),
    ):
        tracks[123, 25] = value
        expected = evaluate_yed(yed, names, tracks)
        actual = compiled.evaluate(tracks)
        assert actual == expected
        assert all(isinstance(v, Vector4) for v in actual.tracks.values())
    before = compiled.evaluate(tracks)
    yed.expressions.clear()
    assert compiled.evaluate(tracks) == before
    assert yed.compile(names).evaluate(tracks).output_tracks == {}


def test_compiled_evaluator_is_stateless_for_seeks_and_concurrent_actors():
    yed = create_yed(large_expression())
    compiled = yed.compile(("calibrated",))
    frames = [{(56462, 25): Vector4(i, 2, 3, 0)} for i in range(16)]
    expected = [compiled.evaluate(frame) for frame in frames]
    with ThreadPoolExecutor(4) as pool:
        assert list(pool.map(compiled.evaluate, frames)) == expected
    assert compiled.evaluate(frames[0], time=50) == compiled.evaluate(frames[0], time=0)


def test_snapshot_keeps_operand_values_and_zero_signature_diagnostics():
    expression = YedExpression.create("constant")
    expression.streams = [
        YedStream(
            MetaHash("main"),
            1,
            b"",
            b"",
            b"",
            instructions=[
                YedInstruction(Op.PUSH_FLOAT, operands={"value": 2.0}),
                YedInstruction(Op.TRACK_SET, operands={"bone_id": 7, "track": 0}),
                YedInstruction(Op.END),
            ],
        )
    ]
    yed = create_yed(expression)
    snapshot = yed.compile(("constant",))
    before = snapshot.evaluate({})
    assert before.native_diagnostics
    expression.streams[0].instructions[0].operands["value"] = 5.0
    assert snapshot.evaluate({}) == before
    assert yed.compile(("constant",)).evaluate({}) != before
    assert evaluate_yed(yed, ("constant",), {}).output_tracks[7, 0].x == 5.0


def test_mutable_cache_and_compiled_defaults_observe_their_ownership_contracts():
    expression = YedExpression.create("defaults")
    expression.streams = [
        YedStream(
            MetaHash("main"),
            1,
            b"",
            b"",
            b"",
            instructions=[
                YedInstruction(
                    Op.TRACK_GET,
                    operands={"bone_id": 7, "track": 0, "use_defaults": True},
                ),
                YedInstruction(Op.TRACK_SET, operands={"bone_id": 8, "track": 0}),
                YedInstruction(Op.END),
            ],
        )
    ]
    yed = create_yed(expression)
    skeleton = SimpleNamespace(
        bones=[
            SimpleNamespace(
                tag=7,
                translation=Vector3(1, 2, 3),
                rotation=Quaternion(),
                scale=Vector3(1, 1, 1),
            )
        ]
    )
    compiled = yed.compile(("defaults",), skeleton=skeleton)
    before = evaluate_yed(yed, ("defaults",), {}, skeleton=skeleton)
    assert compiled.evaluate({}) == before
    skeleton.bones[0].translation = Vector3(4, 5, 6)
    assert compiled.evaluate({}) == before
    changed = evaluate_yed(yed, ("defaults",), {}, skeleton=skeleton)
    assert changed.output_tracks[8, 0].xyz == Vector3(4, 5, 6)


def test_variables_are_explicit_caller_state_and_outputs_remain_immutable():
    expression = YedExpression.create("state")
    expression.streams = [
        YedStream(
            MetaHash("main"),
            1,
            b"",
            b"",
            b"",
            instructions=[
                YedInstruction(Op.PUSH_FLOAT, operands={"value": 3.0}),
                YedInstruction(
                    Op.SET_VARIABLE, operands={"variable": 12, "variable_index": 0}
                ),
                YedInstruction(
                    Op.GET_VARIABLE, operands={"variable": 12, "variable_index": 0}
                ),
                YedInstruction(Op.TRACK_SET, operands={"bone_id": 7, "track": 0}),
                YedInstruction(Op.END),
            ],
        )
    ]
    yed = create_yed(expression)
    state = {}
    compiled = yed.compile(("state",))
    result = compiled.evaluate({}, variables=state)
    expected = evaluate_yed(yed, ("state",), {})
    assert result == expected
    assert state == result.variables
    assert result.tracks[7, 0] is result.output_tracks[7, 0]
    state.clear()
    assert compiled.evaluate({}) == expected
