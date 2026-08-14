from __future__ import annotations

import importlib
import math
import random
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from fivefury import (
    GameFileType,
    MetaHash,
    YcdAnimationTrack,
    YedExpression,
    YedInstruction,
    YedInstructionType,
    YedStream,
    YedTrack,
    YedTrackFormat,
    audit_yed_cache,
    build_yed_bytes,
    create_yed,
    evaluate_yed,
    jenk_hash,
    read_yed,
)
from fivefury.vector import (
    quat_from_euler_xyz,
    quat_multiply,
    quat_normalize,
    quat_to_euler_xyz,
)


def _stream(*instructions: YedInstruction) -> YedStream:
    return YedStream(
        name_hash=MetaHash(jenk_hash("main")),
        depth=8,
        data1=b"",
        data2=b"",
        data3=b"",
        instructions=list(instructions),
    )


def _instruction(kind: YedInstructionType, **operands: object) -> YedInstruction:
    return YedInstruction(kind, operands=dict(operands))


def _read_track_expression(
    name: str,
    *,
    source_bone: int,
    source_track: int,
    target_bone: int,
    component: int | None = None,
    format: YedTrackFormat = YedTrackFormat.VECTOR3,
    use_defaults: bool = False,
) -> YedExpression:
    expression = YedExpression.create(name)
    read = (
        _instruction(
            YedInstructionType.TRACK_GET,
            bone_id=source_bone,
            track=source_track,
            use_defaults=use_defaults,
        )
        if component is None
        else _instruction(
            YedInstructionType.TRACK_GET_COMP,
            bone_id=source_bone,
            track=source_track,
            component_index=component,
            format=int(format),
            use_defaults=use_defaults,
        )
    )
    expression.streams = [
        _stream(
            read,
            _instruction(
                YedInstructionType.TRACK_SET,
                bone_id=target_bone,
                track=int(YcdAnimationTrack.BONE_TRANSLATION),
            ),
            _instruction(YedInstructionType.END),
        )
    ]
    return expression


def test_missing_facial_scale_whole_vector_preserves_unit_default() -> None:
    expression = _read_track_expression(
        "facial_scale_vector_default",
        source_bone=10866,
        source_track=int(YcdAnimationTrack.FACIAL_SCALE),
        target_bone=1,
    )

    result = evaluate_yed(create_yed(expression), (expression.short_name,), {})

    assert result.output_tracks[(1, 0)] == (1.0, 1.0, 1.0, 0.0)


@pytest.mark.parametrize("component", range(3), ids=("x", "y", "z"))
def test_missing_facial_scale_component_defaults_to_zero(component: int) -> None:
    expression = _read_track_expression(
        f"facial_scale_component_{component}",
        source_bone=10866,
        source_track=int(YcdAnimationTrack.FACIAL_SCALE),
        target_bone=component + 1,
        component=component,
    )

    result = evaluate_yed(create_yed(expression), (expression.short_name,), {})

    assert result.output_tracks[(component + 1, 0)] == (0.0, 0.0, 0.0, 0.0)


def test_missing_generic_scale_component_defaults_to_zero() -> None:
    expression = _read_track_expression(
        "generic_scale_component_default",
        source_bone=10866,
        source_track=int(YcdAnimationTrack.GENERIC_SCALE),
        target_bone=1,
        component=1,
    )

    result = evaluate_yed(create_yed(expression), (expression.short_name,), {})

    assert result.output_tracks[(1, 0)] == (0.0, 0.0, 0.0, 0.0)


def test_present_facial_scale_component_returns_authored_value() -> None:
    track = int(YcdAnimationTrack.FACIAL_SCALE)
    expression = _read_track_expression(
        "facial_scale_component_authored",
        source_bone=10866,
        source_track=track,
        target_bone=1,
        component=1,
    )

    result = evaluate_yed(
        create_yed(expression),
        (expression.short_name,),
        {(10866, track): (1.25, 1.5, 1.75, 0.0)},
    )

    assert result.output_tracks[(1, 0)] == (1.5, 1.5, 1.5, 1.5)


@pytest.mark.parametrize(
    ("track", "component", "format", "expected"),
    [
        (YcdAnimationTrack.BONE_TRANSLATION, 1, YedTrackFormat.VECTOR3, 5.0),
        (YcdAnimationTrack.BONE_ROTATION, 2, YedTrackFormat.QUATERNION, math.radians(30.0)),
        (YcdAnimationTrack.BONE_SCALE, 0, YedTrackFormat.VECTOR3, 1.5),
    ],
    ids=("translation", "rotation", "scale"),
)
def test_missing_bone_component_uses_skeleton_default(
    track: YcdAnimationTrack,
    component: int,
    format: YedTrackFormat,
    expected: float,
) -> None:
    expression = _read_track_expression(
        f"bone_component_default_{int(track)}",
        source_bone=7,
        source_track=int(track),
        target_bone=1,
        component=component,
        format=format,
    )
    bone = SimpleNamespace(
        tag=7,
        translation=(4.0, 5.0, 6.0),
        rotation=quat_from_euler_xyz((math.radians(10.0), math.radians(20.0), math.radians(30.0))),
        scale=(1.5, 2.0, 2.5),
    )

    result = evaluate_yed(
        create_yed(expression),
        (expression.short_name,),
        {},
        skeleton=SimpleNamespace(bones=[bone]),
    )

    assert result.output_tracks[(1, 0)] == pytest.approx((expected,) * 4)


def test_component_use_defaults_ignores_authored_values() -> None:
    facial_track = int(YcdAnimationTrack.FACIAL_SCALE)
    facial = _read_track_expression(
        "forced_facial_component_default",
        source_bone=10866,
        source_track=facial_track,
        target_bone=1,
        component=0,
        use_defaults=True,
    )
    translation = _read_track_expression(
        "forced_bone_component_default",
        source_bone=7,
        source_track=int(YcdAnimationTrack.BONE_TRANSLATION),
        target_bone=2,
        component=1,
        use_defaults=True,
    )
    skeleton = SimpleNamespace(
        bones=[
            SimpleNamespace(
                tag=7,
                translation=(4.0, 5.0, 6.0),
                rotation=(0.0, 0.0, 0.0, 1.0),
                scale=(1.0, 1.0, 1.0),
            )
        ]
    )

    result = evaluate_yed(
        create_yed(facial, translation),
        (facial.short_name, translation.short_name),
        {
            (10866, facial_track): (9.0, 9.0, 9.0, 0.0),
            (7, int(YcdAnimationTrack.BONE_TRANSLATION)): (8.0, 8.0, 8.0, 0.0),
        },
        skeleton=skeleton,
    )

    assert result.output_tracks[(1, 0)] == (0.0, 0.0, 0.0, 0.0)
    assert result.output_tracks[(2, 0)] == (5.0, 5.0, 5.0, 5.0)


def _assert_same_rotation(
    actual: tuple[float, float, float, float],
    expected: tuple[float, float, float, float],
    *,
    tolerance: float = 1e-9,
) -> None:
    actual = quat_normalize(actual)
    expected = quat_normalize(expected)
    alignment = abs(sum(left * right for left, right in zip(actual, expected)))
    assert alignment == pytest.approx(1.0, abs=tolerance)


def test_rage_euler_xyz_compound_reference_reaches_the_vm() -> None:
    angles = tuple(math.radians(value) for value in (30.0, -40.0, 55.0))
    expected = (
        0.368276296063,
        -0.180736259985,
        0.497636296346,
        0.764241513295,
    )
    expression = YedExpression.create("compound_euler")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH_VECTOR, value=(*angles, 0.0)),
            _instruction(YedInstructionType.FROM_EULER),
            _instruction(YedInstructionType.DUP),
            _instruction(YedInstructionType.TRACK_SET, bone_id=1, track=1),
            _instruction(YedInstructionType.TO_EULER),
            _instruction(YedInstructionType.TRACK_SET, bone_id=2, track=0),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(create_yed(expression), ("compound_euler",), {})

    assert quat_from_euler_xyz(angles) == pytest.approx(expected, abs=1e-12)
    assert quat_to_euler_xyz(expected) == pytest.approx(angles, abs=1e-12)
    assert result.output_tracks[(1, 1)] == pytest.approx(expected, abs=1e-12)
    assert result.output_tracks[(2, 0)][:3] == pytest.approx(angles, abs=1e-12)
    assert result.issues == []


def test_euler_xyz_roundtrip_preserves_finite_rotations() -> None:
    expression = YedExpression.create("euler_roundtrip")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.TRACK_GET, bone_id=1, track=1),
            _instruction(YedInstructionType.TO_EULER),
            _instruction(YedInstructionType.FROM_EULER),
            _instruction(YedInstructionType.TRACK_SET, bone_id=2, track=1),
            _instruction(YedInstructionType.END),
        )
    ]
    yed = create_yed(expression)
    rotations = [
        quat_from_euler_xyz(tuple(math.radians(value) for value in angles))
        for angles in (
            (0.0, 0.0, 0.0),
            (90.0, 0.0, 0.0),
            (0.0, -90.0, 0.0),
            (0.0, 0.0, 90.0),
            (30.0, -40.0, 55.0),
            (-120.0, 25.0, 170.0),
            (15.0, 89.9, -35.0),
            (-22.0, -89.9, 64.0),
        )
    ]
    rotations.append(tuple(-value for value in rotations[4]))
    generator = random.Random(0x594544)
    for _ in range(64):
        rotations.append(
            quat_normalize(tuple(generator.uniform(-1.0, 1.0) for _ in range(4)))
        )

    for rotation in rotations:
        python_roundtrip = quat_from_euler_xyz(quat_to_euler_xyz(rotation))
        result = evaluate_yed(yed, ("euler_roundtrip",), {(1, 1): rotation})
        _assert_same_rotation(python_roundtrip, rotation, tolerance=1e-8)
        _assert_same_rotation(result.output_tracks[(2, 1)], rotation, tolerance=1e-8)
        assert result.issues == []


def test_evaluate_yed_maps_a_facial_control_to_a_bone_track() -> None:
    expression = YedExpression.create("head_000_r")
    expression.streams = [
        _stream(
            _instruction(
                YedInstructionType.TRACK_GET,
                bone_id=8133,
                track=int(YcdAnimationTrack.FACIAL_CONTROL),
            ),
            _instruction(YedInstructionType.PUSH_VECTOR, value=(4.0, 2.0, 1.0, 0.0)),
            _instruction(YedInstructionType.VECTOR_MUL),
            _instruction(
                YedInstructionType.TRACK_SET,
                bone_id=59307,
                track=int(YcdAnimationTrack.BONE_TRANSLATION),
            ),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(
        create_yed(expression),
        ("head_000_r",),
        {(8133, int(YcdAnimationTrack.FACIAL_CONTROL)): (0.25, 0.25, 0.25, 0.25)},
    )

    assert result.output_tracks[(59307, 0)] == pytest.approx((1.0, 0.5, 0.25, 0.0))
    assert result.evaluated_expressions == ["head_000_r"]
    assert result.issues == []


def test_vector_transform_preserves_vector_length() -> None:
    expression = YedExpression.create("rotate")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH_VECTOR, value=(2.0, 0.0, 0.0, 0.0)),
            _instruction(
                YedInstructionType.PUSH_VECTOR,
                value=(0.0, 0.0, 2**-0.5, 2**-0.5),
            ),
            _instruction(YedInstructionType.VECTOR_TRANSFORM),
            _instruction(YedInstructionType.TRACK_SET, bone_id=1, track=0),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(create_yed(expression), ("rotate",), {})

    assert result.output_tracks[(1, 0)] == pytest.approx((0.0, 2.0, 0.0, 0.0))


def test_unsupported_instruction_is_reported_without_guessing() -> None:
    expression = YedExpression.create("unsupported")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.TRACK_GET_BONE_TRANSFORM),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(create_yed(expression), ("unsupported",), {})

    assert result.output_tracks == {}
    assert [issue.code for issue in result.issues] == ["yed.vm.unsupported_instruction"]


def test_absolute_and_relative_tracks_use_skeleton_defaults_by_tag() -> None:
    source_bone = SimpleNamespace(
        tag=10,
        translation=(10.0, 20.0, 30.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
        scale=(1.0, 1.0, 1.0),
    )
    target_bone = SimpleNamespace(
        tag=20,
        translation=(100.0, 200.0, 300.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
        scale=(1.0, 1.0, 1.0),
    )
    expression = YedExpression.create("relative")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.TRACK_GET, bone_id=10, track=0),
            _instruction(YedInstructionType.TRACK_SET, bone_id=30, track=0),
            _instruction(YedInstructionType.TRACK_GET_OFFSET, bone_id=10, track=0),
            _instruction(YedInstructionType.TRACK_SET_OFFSET, bone_id=20, track=0),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(
        create_yed(expression),
        ("relative",),
        {(10, 0): (11.0, 22.0, 33.0, 0.0)},
        skeleton=SimpleNamespace(bones=[target_bone, source_bone]),
    )

    assert result.output_tracks[(30, 0)] == pytest.approx((11.0, 22.0, 33.0, 0.0))
    assert result.output_tracks[(20, 0)] == pytest.approx(
        (101.0, 202.0, 303.0, 0.0)
    )


def test_relative_rotation_and_scale_compose_with_skeleton_defaults() -> None:
    half = 2**-0.5
    bone = SimpleNamespace(
        tag=10,
        translation=(0.0, 0.0, 0.0),
        rotation=(half, 0.0, 0.0, half),
        scale=(2.0, 3.0, 4.0),
    )
    expression = YedExpression.create("relative_transforms")
    expression.streams = [
        _stream(
            _instruction(
                YedInstructionType.PUSH_VECTOR,
                value=(0.0, half, 0.0, half),
            ),
            _instruction(YedInstructionType.TRACK_SET_OFFSET, bone_id=10, track=1),
            _instruction(
                YedInstructionType.PUSH_VECTOR,
                value=(0.5, 1.0, 1.5, 0.0),
            ),
            _instruction(YedInstructionType.TRACK_SET_OFFSET, bone_id=10, track=2),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(
        create_yed(expression),
        ("relative_transforms",),
        {},
        skeleton=SimpleNamespace(bones=[bone]),
    )

    assert result.output_tracks[(10, 1)] == pytest.approx((0.5, 0.5, 0.5, 0.5))
    assert result.output_tracks[(10, 2)] == pytest.approx((2.5, 4.0, 5.5, 0.0))


def test_component_writes_support_vectors_and_quaternions() -> None:
    expression = YedExpression.create("components")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH_FLOAT, value=9.0),
            _instruction(
                YedInstructionType.TRACK_SET_COMP,
                bone_id=1,
                track=0,
                component_index=1,
                format=int(YedTrackFormat.VECTOR3),
            ),
            _instruction(YedInstructionType.PUSH_FLOAT, value=math.pi / 2.0),
            _instruction(
                YedInstructionType.TRACK_SET_COMP,
                bone_id=2,
                track=1,
                component_index=2,
                format=int(YedTrackFormat.QUATERNION),
            ),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(
        create_yed(expression),
        ("components",),
        {
            (1, 0): (1.0, 2.0, 3.0, 0.0),
            (2, 1): (0.0, 0.0, 0.0, 1.0),
        },
    )

    assert result.output_tracks[(1, 0)] == pytest.approx((1.0, 9.0, 3.0, 0.0))
    assert result.output_tracks[(2, 1)] == pytest.approx(
        (0.0, 0.0, 2**-0.5, 2**-0.5)
    )


def test_quaternion_component_write_preserves_compound_rage_axes() -> None:
    angles = tuple(math.radians(value) for value in (30.0, -40.0, 55.0))
    replacement = math.radians(-36.2039)
    initial = quat_from_euler_xyz(angles)
    expected = quat_from_euler_xyz((replacement, angles[1], angles[2]))
    expression = YedExpression.create("compound_component")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH_FLOAT, value=replacement),
            _instruction(
                YedInstructionType.TRACK_SET_COMP,
                bone_id=4407,
                track=1,
                component_index=0,
                format=int(YedTrackFormat.QUATERNION),
            ),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(
        create_yed(expression),
        ("compound_component",),
        {(4407, 1): initial},
    )

    _assert_same_rotation(result.output_tracks[(4407, 1)], expected)
    assert result.issues == []


def test_michael_ear_component_regression_stays_near_neutral() -> None:
    neutral = {
        4407: (
            -0.04937572777271271,
            -0.6273804903030396,
            0.06097438931465149,
            0.7747502326965332,
        ),
        6621: (
            -0.04937604069709778,
            0.6273804306983948,
            -0.06097400188446045,
            0.774750292301178,
        ),
    }
    replacement = math.radians(-36.2039)
    expression = YedExpression.create("head_000_r_ear_regression")
    instructions = []
    for bone_tag in neutral:
        instructions.extend(
            (
                _instruction(YedInstructionType.PUSH_FLOAT, value=replacement),
                _instruction(
                    YedInstructionType.TRACK_SET_COMP,
                    bone_id=bone_tag,
                    track=1,
                    component_index=0,
                    format=int(YedTrackFormat.QUATERNION),
                ),
            )
        )
    expression.streams = [
        _stream(*instructions, _instruction(YedInstructionType.END))
    ]

    result = evaluate_yed(
        create_yed(expression),
        ("head_000_r_ear_regression",),
        {(bone_tag, 1): rotation for bone_tag, rotation in neutral.items()},
    )

    for bone_tag, neutral_rotation in neutral.items():
        final_rotation = quat_normalize(result.output_tracks[(bone_tag, 1)])
        alignment = abs(
            sum(
                left * right
                for left, right in zip(final_rotation, neutral_rotation)
            )
        )
        angular_distance = math.degrees(
            2.0 * math.acos(max(-1.0, min(1.0, alignment)))
        )
        assert angular_distance < 0.3
        assert sum(value * value for value in final_rotation) == pytest.approx(1.0)
    assert result.issues == []


def test_relative_quaternion_component_write_uses_compound_default_pose() -> None:
    base_angles = tuple(math.radians(value) for value in (12.0, -25.0, 33.0))
    relative_angles = tuple(math.radians(value) for value in (4.0, -7.0, 11.0))
    replacement = math.radians(-8.0)
    base = quat_from_euler_xyz(base_angles)
    current = quat_multiply(base, quat_from_euler_xyz(relative_angles))
    expected_relative = (
        replacement + base_angles[0],
        relative_angles[1],
        relative_angles[2],
    )
    expected = quat_multiply(base, quat_from_euler_xyz(expected_relative))
    bone = SimpleNamespace(
        tag=4407,
        translation=(0.0, 0.0, 0.0),
        rotation=base,
        scale=(1.0, 1.0, 1.0),
    )
    expression = YedExpression.create("relative_component")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH_FLOAT, value=replacement),
            _instruction(
                YedInstructionType.TRACK_SET_OFFSET_COMP,
                bone_id=4407,
                track=1,
                component_index=0,
                format=int(YedTrackFormat.QUATERNION),
            ),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(
        create_yed(expression),
        ("relative_component",),
        {(4407, 1): current},
        skeleton=SimpleNamespace(bones=[bone]),
    )

    _assert_same_rotation(result.output_tracks[(4407, 1)], expected)
    assert result.issues == []


@pytest.mark.parametrize(
    ("instructions", "code"),
    [
        ((_instruction(YedInstructionType.POP),), "yed.vm.execution_error"),
        ((_instruction(YedInstructionType.PUSH_FLOAT),), "yed.vm.execution_error"),
        ((YedInstruction(0xFE),), "yed.vm.unknown_opcode"),
        (
            (
                YedInstruction(
                    YedInstructionType.PUSH_FLOAT,
                    parsed=False,
                    parse_error="truncated operand",
                ),
            ),
            "yed.vm.unparsed_instruction",
        ),
    ],
)
def test_malformed_streams_return_structured_issues(
    instructions: tuple[YedInstruction, ...],
    code: str,
) -> None:
    expression = YedExpression.create("malformed")
    expression.streams = [_stream(*instructions)]

    result = evaluate_yed(create_yed(expression), ("malformed",), {})

    assert result.output_tracks == {}
    assert [issue.code for issue in result.issues] == [code]


def test_jump_loops_stop_at_the_deterministic_step_limit() -> None:
    expression = YedExpression.create("loop")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.JUMP, instruction_offset=-1),
        )
    ]

    result = evaluate_yed(create_yed(expression), ("loop",), {})

    assert [issue.code for issue in result.issues] == ["yed.vm.step_limit"]


def test_expression_order_and_duplicate_suppression_are_deterministic() -> None:
    first = YedExpression.create("first")
    first.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH_FLOAT, value=1.0),
            _instruction(YedInstructionType.TRACK_SET, bone_id=1, track=0),
            _instruction(YedInstructionType.END),
        )
    ]
    second = YedExpression.create("second")
    second.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH_FLOAT, value=2.0),
            _instruction(YedInstructionType.TRACK_SET, bone_id=1, track=0),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(
        create_yed(first, second),
        ("first", "first", "second"),
        {},
    )

    assert result.evaluated_expressions == ["first", "second"]
    assert result.output_tracks[(1, 0)][0] == pytest.approx(2.0)


def test_variables_persist_only_through_explicit_caller_state() -> None:
    variable_hash = jenk_hash("blink_state")
    expression = YedExpression.create("variables")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH_FLOAT, value=0.75),
            _instruction(
                YedInstructionType.SET_VARIABLE,
                variable=variable_hash,
                variable_index=0,
            ),
            _instruction(
                YedInstructionType.GET_VARIABLE,
                variable=variable_hash,
                variable_index=0,
            ),
            _instruction(YedInstructionType.TRACK_SET, bone_id=1, track=0),
            _instruction(YedInstructionType.END),
        )
    ]
    state = {}

    persisted = evaluate_yed(
        create_yed(expression),
        ("variables",),
        {},
        variables=state,
    )
    isolated = evaluate_yed(create_yed(expression), (), {}, variables=None)

    assert state[(variable_hash, 0)] == pytest.approx((0.75, 0.75, 0.75, 0.75))
    assert persisted.variables == state
    assert isolated.variables == {}


def test_track_input_coercion_matches_the_public_vector_rules() -> None:
    expression = YedExpression.create("coercion")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.TRACK_GET, bone_id=1, track=0),
            _instruction(YedInstructionType.TRACK_SET, bone_id=10, track=0),
            _instruction(YedInstructionType.TRACK_GET, bone_id=2, track=0),
            _instruction(YedInstructionType.TRACK_SET, bone_id=20, track=0),
            _instruction(YedInstructionType.TRACK_GET, bone_id=3, track=0),
            _instruction(YedInstructionType.TRACK_SET, bone_id=30, track=0),
            _instruction(YedInstructionType.END),
        )
    ]

    result = evaluate_yed(
        create_yed(expression),
        ("coercion",),
        {(1, 0): 2.0, (2, 0): (3.0,), (3, 0): (4.0, 5.0, 6.0)},
    )

    assert result.output_tracks[(10, 0)] == (2.0, 0.0, 0.0, 0.0)
    assert result.output_tracks[(20, 0)] == (3.0, 0.0, 0.0, 0.0)
    assert result.output_tracks[(30, 0)] == (4.0, 5.0, 6.0, 0.0)


def test_compiled_program_is_reused_and_invalidated_by_stream_replacement() -> None:
    evaluator = importlib.import_module("fivefury.yed.evaluate")
    evaluator._PROGRAM_CACHE.clear()
    expression = YedExpression.create("cached")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH1),
            _instruction(YedInstructionType.TRACK_SET, bone_id=1, track=0),
            _instruction(YedInstructionType.END),
        )
    ]
    yed = create_yed(expression)

    evaluate_yed(yed, ("cached",), {})
    first = next(iter(evaluator._PROGRAM_CACHE.values())).program
    evaluate_yed(yed, ("cached",), {})
    assert next(iter(evaluator._PROGRAM_CACHE.values())).program is first

    expression.streams[0].instructions = list(expression.streams[0].instructions)
    evaluate_yed(yed, ("cached",), {})
    assert next(iter(evaluator._PROGRAM_CACHE.values())).program is not first


def test_compiled_program_can_evaluate_concurrent_frames() -> None:
    expression = YedExpression.create("parallel")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.TRACK_GET, bone_id=1, track=0),
            _instruction(YedInstructionType.PUSH_FLOAT, value=2.0),
            _instruction(YedInstructionType.VECTOR_MUL),
            _instruction(YedInstructionType.TRACK_SET, bone_id=2, track=0),
            _instruction(YedInstructionType.END),
        )
    ]
    yed = create_yed(expression)

    def run(value: float) -> tuple[float, float, float, float]:
        result = evaluate_yed(yed, ("parallel",), {(1, 0): value})
        return result.output_tracks[(2, 0)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        values = list(executor.map(run, (float(index) for index in range(64))))

    assert values == [(float(index * 2), 0.0, 0.0, 0.0) for index in range(64)]


def _blend_operands(multiplier: float) -> dict[str, object]:
    return {
        "source_count": 4,
        "num_source_weights": 1,
        "source_infos": [
            {"track_index": index, "component_offset": 0}
            for index in range(4)
        ],
        "values": [
            (multiplier, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
        ],
    }


def _compound_quaternion_blend_operands() -> dict[str, object]:
    first = tuple(math.radians(value) for value in (30.0, -40.0, 55.0))
    second = tuple(math.radians(value) for value in (-12.0, 18.0, 27.0))
    return {
        "source_count": 4,
        "num_source_weights": 1,
        "source_infos": [
            {"track_index": index, "component_offset": 0}
            for index in range(4)
        ],
        "values": [
            (first[0], second[0], 0.0, 0.0),
            (first[1], second[1], 0.0, 0.0),
            (first[2], second[2], 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
        ],
    }


def test_linear_vector_and_quaternion_blends_use_serialized_sources() -> None:
    vector = YedExpression.create(
        "vector_blend",
        tracks=[YedTrack.scalar(index + 1, 24) for index in range(4)],
    )
    vector.streams = [
        _stream(
            _instruction(YedInstructionType.BLEND_VECTOR, **_blend_operands(3.0)),
            _instruction(YedInstructionType.TRACK_SET, bone_id=20, track=0),
            _instruction(YedInstructionType.END),
        )
    ]
    quaternion = YedExpression.create(
        "quaternion_blend",
        tracks=[YedTrack.scalar(index + 1, 24) for index in range(4)],
    )
    quaternion.streams = [
        _stream(
            _instruction(
                YedInstructionType.BLEND_QUATERNION,
                **_blend_operands(math.pi / 2.0),
            ),
            _instruction(YedInstructionType.TRACK_SET, bone_id=21, track=1),
            _instruction(YedInstructionType.END),
        )
    ]
    tracks = {(1, 24): (1.0, 0.0, 0.0, 0.0)}

    result = evaluate_yed(
        create_yed(vector, quaternion),
        ("vector_blend", "quaternion_blend"),
        tracks,
    )

    assert result.output_tracks[(20, 0)] == pytest.approx((3.0, 0.0, 0.0, 0.0))
    assert result.output_tracks[(21, 1)] == pytest.approx(
        (2**-0.5, 0.0, 0.0, 2**-0.5)
    )


def test_quaternion_blend_preserves_compound_serialized_source_order() -> None:
    first = tuple(math.radians(value) for value in (30.0, -40.0, 55.0))
    second = tuple(math.radians(value) for value in (-12.0, 18.0, 27.0))
    expression = YedExpression.create(
        "compound_quaternion_blend",
        tracks=[YedTrack.scalar(index + 1, 24) for index in range(4)],
    )
    expression.streams = [
        _stream(
            _instruction(
                YedInstructionType.BLEND_QUATERNION,
                **_compound_quaternion_blend_operands(),
            ),
            _instruction(YedInstructionType.TRACK_SET, bone_id=4407, track=1),
            _instruction(YedInstructionType.END),
        )
    ]
    expected = quat_multiply(
        quat_from_euler_xyz(first),
        quat_from_euler_xyz(second),
    )

    result = evaluate_yed(
        create_yed(expression),
        ("compound_quaternion_blend",),
        {
            (1, 24): (1.0, 0.0, 0.0, 0.0),
            (2, 24): (1.0, 0.0, 0.0, 0.0),
        },
    )

    _assert_same_rotation(result.output_tracks[(4407, 1)], expected)
    assert result.issues == []


def test_missing_skeleton_uses_typed_fallback_and_tagged_skeleton_uses_default() -> None:
    expression = YedExpression.create("defaults")
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.TRACK_GET, bone_id=7, track=0),
            _instruction(YedInstructionType.TRACK_SET, bone_id=8, track=0),
            _instruction(YedInstructionType.END),
        )
    ]
    yed = create_yed(expression)

    missing = evaluate_yed(yed, ("defaults",), {})
    tagged = evaluate_yed(
        yed,
        ("defaults",),
        {},
        skeleton=SimpleNamespace(
            bones=[
                SimpleNamespace(
                    tag=7,
                    translation=(4.0, 5.0, 6.0),
                    rotation=(0.0, 0.0, 0.0, 1.0),
                    scale=(1.0, 1.0, 1.0),
                )
            ]
        ),
    )

    assert missing.output_tracks[(8, 0)] == (0.0, 0.0, 0.0, 1.0)
    assert tagged.output_tracks[(8, 0)] == (4.0, 5.0, 6.0, 0.0)


def test_yed_roundtrip_preserves_conditional_branch_opcodes() -> None:
    expression = YedExpression.create(
        "branches",
        tracks=[YedTrack.vector3(1, 0)],
    )
    expression.streams = [
        _stream(
            _instruction(YedInstructionType.PUSH0),
            _instruction(YedInstructionType.JUMP_IF_FALSE, instruction_offset=1),
            _instruction(YedInstructionType.PUSH1),
            _instruction(YedInstructionType.JUMP_IF_TRUE, instruction_offset=1),
            _instruction(YedInstructionType.PUSH0),
            _instruction(
                YedInstructionType.TRACK_SET,
                track_index=0,
                bone_id=1,
                track=0,
                format=int(YedTrackFormat.VECTOR3),
                component_index=0,
                use_defaults=False,
            ),
            _instruction(YedInstructionType.END),
        )
    ]

    original = build_yed_bytes(create_yed(expression))
    rebuilt = read_yed(original)
    opcodes = rebuilt.expressions[0].streams[0].data3

    assert opcodes[1] == 0x2C
    assert opcodes[3] == 0x2D
    assert build_yed_bytes(rebuilt) == original


def test_audit_yed_cache_uses_public_cache_api_and_limit() -> None:
    first = SimpleNamespace(path="expressions/first.yed")
    second = SimpleNamespace(path="expressions/second.yed")
    yed = create_yed(YedExpression.create("face"))
    yed.path = first.path

    class Cache:
        def __init__(self) -> None:
            self.loaded = []

        @staticmethod
        def iter_assets(kind):
            assert kind.name == "YED"
            return iter((first, second))

        def load_asset(self, asset):
            self.loaded.append(asset)
            return SimpleNamespace(kind=GameFileType.YED, parsed=yed)

    cache = Cache()
    reports = audit_yed_cache(cache, limit=1)

    assert cache.loaded == [first]
    assert len(reports) == 1
    assert reports[0].path == first.path
