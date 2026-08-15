from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from fivefury import (
    YED_FACIAL_ROOT_BONE_ID,
    CutFacialAnimationMode,
    CutScene,
    GameFileCache,
    YcdAnimationTrack,
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

_ENHANCED_ROOT_VALUE = os.environ.get("FIVEFURY_GTA5_ENHANCED_PATH")
_ENHANCED_ROOT = Path(_ENHANCED_ROOT_VALUE) if _ENHANCED_ROOT_VALUE else None


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

    codes = {issue.code for issue in scene.validate()}

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
        issue.code for issue in hashed.validate()
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


@pytest.mark.skipif(
    _ENHANCED_ROOT is None or not _ENHANCED_ROOT.is_dir(),
    reason="set FIVEFURY_GTA5_ENHANCED_PATH to run the retail YED regression",
)
def test_retail_facial_component_defaults_preserve_analog_bone_scales() -> None:
    assert _ENHANCED_ROOT is not None
    scale_track = int(YcdAnimationTrack.BONE_SCALE)
    programs = ("head_000_r", "teef_000_u")
    local_time = 4.76666697099119

    with GameFileCache(
        _ENHANCED_ROOT,
        load_audio=False,
        load_peds=True,
        load_vehicles=False,
        use_index_cache=True,
    ) as cache:
        cache.scan_game(gen9=True)
        bundle = cache.resolve_cutscene("pro_mcs_5.cut")

        brad = bundle.bindings[2]
        brad_clip = bundle.scene.clip_for_binding(brad.binding, cut_index=3)
        assert brad_clip is not None and brad_clip.animation is not None
        brad_skeleton = brad.model.main_drawable.skeleton
        brad_result = evaluate_yed(
            brad.expression_dictionary,
            programs,
            brad_clip.animation.evaluate_tracks(143),
            skeleton=brad_skeleton,
            time=local_time,
            delta_time=1.0 / 30.0,
        )

        player = bundle.bindings[3]
        player_clip = bundle.scene.clip_for_binding(player.binding, cut_index=3)
        assert player_clip is not None and player_clip.animation is not None
        player_result = evaluate_yed(
            player.expression_dictionary,
            programs,
            player_clip.animation.evaluate_tracks(143),
            skeleton=player.model.main_drawable.skeleton,
            time=local_time,
            delta_time=1.0 / 30.0,
        )

    analog_tags = {
        int(bone.tag)
        for bone in brad_skeleton.bones
        if "analog" in str(bone.name).casefold()
    }
    analog_scales = {
        bone_id: value
        for (bone_id, track), value in brad_result.output_tracks.items()
        if bone_id in analog_tags and track == scale_track
    }

    assert len(analog_tags) == 16
    assert set(analog_scales) == analog_tags
    assert all(
        value == pytest.approx((1.0, 1.0, 1.0, 1.0))
        for value in analog_scales.values()
    )
    assert analog_scales[20943] == pytest.approx((1.0, 1.0, 1.0, 1.0))
    assert player_result.output_tracks[(20943, scale_track)] == pytest.approx(
        (0.9998352745, 1.0018154658, 1.0003070484, 1.0),
        abs=1e-9,
    )
    assert brad_result.issues == []
    assert player_result.issues == []
