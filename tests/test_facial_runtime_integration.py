from __future__ import annotations

from types import SimpleNamespace

import pytest

from fivefury import (
    YED_FACIAL_ROOT_BONE_ID,
    CutFacialAnimationMode,
    CutScene,
    YcdCutsceneBuilder,
    YcdFacialTrackSet,
    YedInstruction,
    YedInstructionType,
    YedPedExpressionBinding,
    YedStream,
    YedTrack,
    YmtPedInitData,
    build_yed_bytes,
    create_yed,
    evaluate_yed,
    get_ped_expression_binding,
    set_ped_expression_binding,
    validate_yed,
)
from fivefury.metahash import MetaHash


def test_cut_ped_merged_facial_mode_resolves_dual_clip() -> None:
    animations = YcdCutsceneBuilder.create("facial_scene", duration=1.0)
    animations.ped(
        "actor",
        mover_position=(0.0, 0.0, 0.0),
        facial=YcdFacialTrackSet(controls={7: 0.5}),
    )
    scene = CutScene(scene_name="facial_scene", duration=1.0)
    scene.clip_dicts.extend(animations.build_ycds())
    ped = scene.ped(
        "actor",
        animation_clip_base="actor",
        facial_animation=CutFacialAnimationMode.MERGED,
    )

    assert ped.runtime_animation_clip_base == "actor_dual"
    assert scene.clip_for_binding(ped) is not None
    assert scene.clip_for_binding(ped).short_name == "actor_dual-0"


def test_cut_validation_rejects_non_runtime_facial_states() -> None:
    scene = CutScene(scene_name="facial_scene", duration=1.0)
    separate = scene.ped("separate", animation_clip_base="separate")
    separate.found_face_animation = True
    missing_base = scene.ped("0x12345678")
    missing_base.configure_facial_animation(CutFacialAnimationMode.MERGED)
    missing_override = scene.ped("missing_override", animation_clip_base="override")
    missing_override.override_face_animation = True
    missing_override.face_and_body_are_merged = True

    codes = {issue.code for issue in scene.validation_report()}

    assert "ped.face.separate.unsupported" in codes
    assert "ped.face.clip_base.missing" in codes
    assert "ped.face.override_filename.missing" in codes

    hashed = CutScene(scene_name="hashed_scene", duration=1.0)
    hashed_ped = hashed.ped(
        "0x87654321",
        anim_streaming_base=0x12345678,
    )
    hashed_ped.configure_facial_animation(CutFacialAnimationMode.MERGED)
    assert "ped.face.clip_base.missing" not in {
        issue.code for issue in hashed.validation_report()
    }


def test_ped_expression_binding_requires_one_complete_source() -> None:
    fields: dict[str, object] = {}
    set_ped_expression_binding(
        fields,
        expression_dictionary_name="facials@gen_male",
        expression_name="male_std",
    )

    assert get_ped_expression_binding(fields) == YedPedExpressionBinding(
        expression_dictionary_name="facials@gen_male",
        expression_name="male_std",
    )
    with pytest.raises(ValueError, match="cannot be combined"):
        set_ped_expression_binding(fields, expression_set_name="default")
    with pytest.raises(ValueError, match="must be specified together"):
        set_ped_expression_binding(
            {}, expression_dictionary_name="facials@gen_male"
        )


def test_ymt_ped_metadata_exposes_expression_name() -> None:
    ped = YmtPedInitData.from_value(
        {
            "ExpressionSetName": 0,
            "ExpressionDictionaryName": 0x1234,
            "ExpressionName": 0x5678,
        }
    )

    assert int(ped.expression_dictionary_name) == 0x1234
    assert int(ped.expression_name) == 0x5678


def test_yed_validation_requires_facial_root_and_valid_vm_references() -> None:
    yed = create_yed("male_std")
    expression = yed.expressions[0]
    expression.tracks.append(YedTrack.scalar(YED_FACIAL_ROOT_BONE_ID))
    expression.streams.append(
        YedStream(
            name_hash=MetaHash("face"),
            depth=1,
            data1=b"",
            data2=b"",
            data3=b"",
            instructions=[
                YedInstruction(
                    YedInstructionType.TRACK_GET,
                    operands={"track_index": 3},
                )
            ],
        )
    )
    skeleton = SimpleNamespace(bones=[SimpleNamespace(tag=1)])

    codes = {issue.code for issue in validate_yed(yed, skeleton=skeleton)}

    assert "facial-root-bone-missing" in codes
    assert "stream-track-index-invalid" in codes
    with pytest.raises(ValueError, match="references track"):
        build_yed_bytes(yed)


@pytest.mark.parametrize(
    ("condition", "branch_type", "expected"),
    [
        (0.0, YedInstructionType.JUMP_IF_FALSE, 2.0),
        (1.0, YedInstructionType.JUMP_IF_FALSE, 1.0),
        (1.0, YedInstructionType.JUMP_IF_TRUE, 2.0),
        (0.0, YedInstructionType.JUMP_IF_TRUE, 1.0),
    ],
)
def test_yed_conditional_branches_match_rage_zero_semantics(
    condition: float,
    branch_type: YedInstructionType,
    expected: float,
) -> None:
    yed = create_yed("branch")
    yed.expressions[0].streams = [
        YedStream(
            name_hash=MetaHash("main"),
            depth=4,
            data1=b"",
            data2=b"",
            data3=b"",
            instructions=[
                YedInstruction(
                    YedInstructionType.PUSH_FLOAT,
                    operands={"value": condition},
                ),
                YedInstruction(
                    branch_type,
                    operands={"instruction_offset": 2},
                ),
                YedInstruction(
                    YedInstructionType.PUSH_FLOAT,
                    operands={"value": 1.0},
                ),
                YedInstruction(
                    YedInstructionType.JUMP,
                    operands={"instruction_offset": 1},
                ),
                YedInstruction(
                    YedInstructionType.PUSH_FLOAT,
                    operands={"value": 2.0},
                ),
                YedInstruction(
                    YedInstructionType.TRACK_SET,
                    operands={"bone_id": 1, "track": 0},
                ),
                YedInstruction(YedInstructionType.END),
            ],
        )
    ]

    result = evaluate_yed(yed, ("branch",), {})

    assert result.output_tracks[(1, 0)][0] == pytest.approx(expected)
    assert result.issues == []
