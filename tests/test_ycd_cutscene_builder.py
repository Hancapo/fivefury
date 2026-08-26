from __future__ import annotations

import math
import struct

import pytest

from fivefury import (
    GEN9_YCD_RUNTIME_PROFILE,
    YCD_CUTSCENE_SEQUENCE_FRAME_LIMIT,
    CutCameraCutPayload,
    CutScene,
    GameTarget,
    MetaHash,
    Quaternion,
    Vector3,
    YcdAnimationTrack,
    YcdChannelEncoding,
    YcdChannelEncodingPolicy,
    YcdChannelType,
    YcdClipAnimationEntry,
    YcdClipAnimationList,
    YcdClipProperty,
    YcdClipPropertyAttribute,
    YcdClipPropertyAttributeType,
    YcdClipTag,
    YcdClipType,
    YcdCutsceneBoneAnimation,
    YcdCutsceneBuilder,
    YcdFacialTrackSamples,
    YcdFacialTrackSet,
    YcdQuaternionEncoding,
    YcdQuaternionLayout,
    YcdTrackFormat,
    audit_ycd_quaternion_layout,
    build_cutscene_sections,
    build_ycd_bytes,
    read_ycd,
    scene_to_cut,
)
from fivefury.resource import split_rsc7_sections, virtual_to_offset


def test_build_cutscene_sections_uses_camera_cuts() -> None:
    sections = build_cutscene_sections(10.0, [2.5, 7.0], fps=30.0)

    assert [
        (section.index, section.start_time, section.end_time) for section in sections
    ] == [
        (0, 0.0, 2.5),
        (1, 2.5, 7.0),
        (2, 7.0, 10.0),
    ]
    assert sections[0].frame_count == 76
    assert sections[1].frame_count == 136
    assert sections[2].frame_count == 91


def test_cutscene_builder_builds_sectioned_ycds_roundtrip() -> None:
    builder = YcdCutsceneBuilder.create(
        "demo_scene", duration=1.0, camera_cuts=[0.5], fps=30.0
    )
    builder.camera(
        position={0.0: Vector3(), 1.0: Vector3(10.0, 0.0, 0.0)},
        rotation=Quaternion(),
        field_of_view={0.0: 40.0, 1.0: 60.0},
    )
    builder.prop(
        "prop_box",
        position={0.0: Vector3(1.0, 0.0, 0.0), 1.0: Vector3(1.0, 10.0, 0.0)},
        rotation=Quaternion(),
        mover_position={0.0: Vector3(), 1.0: Vector3(0.0, 2.0, 0.0)},
        mover_rotation=Quaternion(),
    )

    ycds = builder.build_ycds()

    assert [ycd.path for ycd in ycds] == ["demo_scene-0.ycd", "demo_scene-1.ycd"]
    assert [clip.short_name for clip in ycds[0].clips] == [
        "exportcamera-0",
        "prop_box-0",
    ]
    assert [clip.short_name for clip in ycds[1].clips] == [
        "exportcamera-1",
        "prop_box-1",
    ]

    section0_raw = build_ycd_bytes(ycds[0])
    section0 = read_ycd(section0_raw)
    section1 = read_ycd(build_ycd_bytes(ycds[1]))
    assert all(animation.vft == 0x405A58F0 for animation in section0.animations)
    assert all(clip.vft == 0x405A4088 for clip in section0.clips)
    assert all(clip.unknown_04h == 1 for clip in section0.clips)
    assert all(clip.unknown_48h == 1 for clip in section0.clips)
    assert all(clip.property_map_reserved_0ch == 0x01000000 for clip in section0.clips)

    _, system_data, _ = split_rsc7_sections(section0_raw)
    buckets_pointer = struct.unpack_from("<Q", system_data, 0x28)[0]
    bucket_capacity = struct.unpack_from("<H", system_data, 0x30)[0]
    buckets_offset = virtual_to_offset(buckets_pointer)
    clip_offsets: list[int] = []
    for bucket_index in range(bucket_capacity):
        entry_pointer = struct.unpack_from(
            "<Q",
            system_data,
            buckets_offset + (bucket_index * 8),
        )[0]
        while entry_pointer:
            entry_offset = virtual_to_offset(entry_pointer)
            clip_pointer = struct.unpack_from(
                "<Q",
                system_data,
                entry_offset + 0x08,
            )[0]
            clip_offsets.append(virtual_to_offset(clip_pointer))
            entry_pointer = struct.unpack_from(
                "<Q",
                system_data,
                entry_offset + 0x10,
            )[0]

    assert len(clip_offsets) == len(section0.clips)
    for clip_offset in clip_offsets:
        assert struct.unpack_from("<I", system_data, clip_offset)[0] == 0x405A4088
        assert struct.unpack_from("<Q", system_data, clip_offset + 0x38)[0]
        assert struct.unpack_from("<Q", system_data, clip_offset + 0x40)[0]

    cam0 = section0.get_clip("exportcamera-0")
    cam1 = section1.get_clip("exportcamera-1")
    prop0 = section0.get_clip("prop_box-0")
    prop1 = section1.get_clip("prop_box-1")

    assert cam0 is not None and cam0.animation is not None
    assert cam1 is not None and cam1.animation is not None
    assert prop0 is not None and prop0.animation is not None
    assert prop1 is not None and prop1.animation is not None

    cam0_start = cam0.evaluate_camera_animation_at_time(0.0)
    cam1_start = cam1.evaluate_camera_animation_at_time(0.0)
    prop0_start = prop0.evaluate_object_animation_at_time(0.0)
    prop1_start = prop1.evaluate_object_animation_at_time(0.0)
    prop0_end = prop0.evaluate_object_animation_at_time(0.5)
    prop1_end = prop1.evaluate_object_animation_at_time(0.5)
    prop1_root = prop1.evaluate_root_motion_at_time(0.0)

    assert cam0_start.position.components == pytest.approx((0.0, 0.0, 0.0))
    assert cam0_start.field_of_view == pytest.approx(40.0)
    assert cam1_start.position.components == pytest.approx((5.0, 0.0, 0.0), abs=0.2)
    assert cam1_start.field_of_view == pytest.approx(50.0, abs=0.5)

    assert prop0_start.position.components == pytest.approx((1.0, 0.0, 0.0))
    assert prop1_start.position.components == pytest.approx((1.0, 5.0, 0.0), abs=0.2)
    assert prop0_end.position.components == pytest.approx((1.0, 5.0, 0.0), abs=0.2)
    assert prop1_end.position.components == pytest.approx((1.0, 10.0, 0.0), abs=0.2)
    assert prop1_root.position.components == pytest.approx((0.0, 1.0, 0.0), abs=0.2)

    assert any(
        int(bone.track) == int(YcdAnimationTrack.MOVER_TRANSLATION)
        for bone in prop1.animation.bone_ids
    )
    assert any(
        int(bone.track) == int(YcdAnimationTrack.CAMERA_FIELD_OF_VIEW)
        for bone in cam1.animation.bone_ids
    )


def test_cutscene_builder_can_emit_one_late_streaming_section() -> None:
    builder = YcdCutsceneBuilder.create(
        "demo_scene",
        duration=1.0,
        section_index_start=12,
        fps=30.0,
    )
    builder.camera(
        position=Vector3(),
        rotation=Quaternion(),
        field_of_view=45.0,
    )

    ycd = builder.build_ycds()[0]

    assert ycd.path == "demo_scene-12.ycd"
    assert [clip.short_name for clip in ycd.clips] == ["exportcamera-12"]


def test_cutscene_builder_uses_explicit_streaming_cuts_from_scene() -> None:
    scene = CutScene.create(duration=6.0, camera_cut_list=[2.0, 4.0])
    camera = scene.camera("exportcamera")
    scene.camera_cut(1.0, camera, CutCameraCutPayload("shot_0"))
    scene.camera_cut(3.0, camera, CutCameraCutPayload("shot_1"))

    builder = YcdCutsceneBuilder.from_cut(scene)

    assert builder.camera_cuts == [2.0, 4.0]


def test_cutscene_builder_writes_enhanced_runtime_headers() -> None:
    profile = GEN9_YCD_RUNTIME_PROFILE
    builder = YcdCutsceneBuilder.create(
        "enhanced_scene",
        duration=1.0,
        game=GameTarget.GTA5_ENHANCED,
    )
    builder.prop(
        "prop_box",
        position=Vector3(),
        rotation=Quaternion(),
    )
    ycd = builder.build_ycds()[0]
    animation = ycd.animations[0]
    clip = ycd.clips[0]
    clip.properties = [
        YcdClipProperty(
            name_hash=MetaHash("phase"),
            attributes=[
                YcdClipPropertyAttribute(
                    name_hash=MetaHash("index"),
                    attribute_type=YcdClipPropertyAttributeType.INT,
                    value=1,
                )
            ],
        )
    ]
    clip.tags = [
        YcdClipTag(name_hash=MetaHash("block"), start_phase=0.0, end_phase=1.0)
    ]
    ycd.clips.append(
        YcdClipAnimationList(
            hash=MetaHash("prop_box_list-0"),
            name="prop_box_list-0",
            short_name="prop_box_list-0",
            clip_type=YcdClipType.ANIMATION_LIST,
            total_duration=1.0,
            animations=[
                YcdClipAnimationEntry(
                    start_time=0.0,
                    end_time=1.0,
                    rate=1.0,
                    animation_hash=animation.hash,
                    animation=animation,
                )
            ],
        )
    )

    rebuilt = read_ycd(build_ycd_bytes(ycd))

    assert rebuilt.game is GameTarget.GTA5_ENHANCED
    assert rebuilt.file_vft == profile.file_vft
    assert rebuilt.animation_map_vft == profile.animation_map_vft
    assert {item.vft for item in rebuilt.animations} == {profile.animation_vft}
    assert {item.vft for item in rebuilt.clips} == {
        profile.clip_animation_vft,
        profile.clip_animation_list_vft,
    }
    rebuilt_clip = next(
        item for item in rebuilt.clips if item.clip_type is YcdClipType.ANIMATION
    )
    assert rebuilt_clip.properties[0].vft == profile.clip_property_vft
    assert rebuilt_clip.properties[0].attributes[0].vft == profile.attribute_vft(
        YcdClipPropertyAttributeType.INT
    )
    assert rebuilt_clip.tags[0].vft == profile.clip_tag_vft


def test_cutscene_builder_returns_empty_when_no_animated_clips() -> None:
    builder = YcdCutsceneBuilder.create("empty_scene", duration=5.0)

    assert builder.build_ycds() == []


def test_cutscene_builder_authors_merged_facial_tracks() -> None:
    builder = YcdCutsceneBuilder.create("facial_scene", duration=1.0, fps=30.0)
    builder.ped(
        "cs_actor",
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
        facial=YcdFacialTrackSet(
            controls={0x1234: {0.0: 0.0, 1.0: 1.0}},
            translations={0x2345: Vector3(1.0, 2.0, 3.0)},
            rotations={0x3456: Quaternion()},
            scales={0x4567: Vector3(1.0, 1.1, 1.2)},
            visemes={0x5678: 0.75},
            blend_shapes={0x6789: 0.5},
            animated_normal_maps={
                0x789A: YcdFacialTrackSamples(
                    Vector3(0.1, 0.2, 0.3), format=YcdTrackFormat.VECTOR3
                )
            },
            tinting=0.25,
        ),
    )

    rebuilt = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    clip = rebuilt.get_clip("cs_actor_dual-0")

    assert clip is not None and clip.animation is not None
    bindings = {
        (int(binding.bone_id), int(binding.track)): YcdTrackFormat(int(binding.format))
        for binding in clip.animation.bone_ids
    }
    assert (
        bindings[(0x789A, int(YcdAnimationTrack.ANIMATED_NORMAL_MAPS))]
        is YcdTrackFormat.VECTOR3
    )
    assert (
        bindings[(0x4567, int(YcdAnimationTrack.FACIAL_SCALE))]
        is YcdTrackFormat.VECTOR3
    )
    assert bindings[(0, int(YcdAnimationTrack.FACIAL_TINTING))] is YcdTrackFormat.FLOAT

    samples = clip.evaluate_facial_animation_at_time(0.5)
    assert samples[0x1234].control == pytest.approx(0.5, abs=0.02)
    assert samples[0x2345].translation.components == pytest.approx((1.0, 2.0, 3.0))
    assert samples[0x3456].rotation.components == pytest.approx((0.0, 0.0, 0.0, 1.0))
    assert samples[0x4567].scale.components == pytest.approx((1.0, 1.1, 1.2))
    assert samples[0x5678].viseme == pytest.approx(0.75)
    assert samples[0x6789].blend_shape == pytest.approx(0.5)
    assert samples[0x789A].animated_normal_maps.components == pytest.approx(
        (0.1, 0.2, 0.3)
    )
    assert samples[0].tinting == pytest.approx(0.25)


def test_add_facial_animation_promotes_existing_body_clip_to_dual() -> None:
    builder = YcdCutsceneBuilder.create("facial_scene", duration=0.1, fps=30.0)
    builder.ped(
        "cs_actor",
        mover_position=Vector3(),
        mover_rotation=Quaternion(),
    )
    builder.facial_animation("cs_actor", YcdFacialTrackSet(controls={1: 1.0}))

    ycd = builder.build_ycds()[0]

    assert [clip.short_name for clip in ycd.clips] == ["cs_actor_dual-0"]


def test_cutscene_builder_preserves_static_negative_w_quaternion() -> None:
    authored = Quaternion(0.752974, 0.058145, -0.440166, -0.485699)
    builder = YcdCutsceneBuilder.create("negative_w", duration=0.1, fps=30.0)
    builder.prop("actor_q", rotation=authored)

    rebuilt = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    clip = rebuilt.get_clip("actor_q-0")
    assert clip is not None and clip.animation is not None
    actual = clip.animation.evaluate_tracks(0)[
        (0, int(YcdAnimationTrack.BONE_ROTATION))
    ]
    dot = abs(sum(left * right for left, right in zip(authored, actual, strict=True)))
    authored_length = sum(value * value for value in authored) ** 0.5
    actual_length = sum(value * value for value in actual) ** 0.5

    assert dot / (authored_length * actual_length) == pytest.approx(1.0, abs=1e-6)


def test_cutscene_builder_preserves_hashes_that_look_like_pointers() -> None:
    builder = YcdCutsceneBuilder.create("pointer_hash", duration=0.1, fps=30.0)
    builder.prop(
        "cc_cscakebox_i14__q012",
        position=Vector3(),
        rotation=Quaternion(),
    )

    source = builder.build_ycds()[0]
    expected_animation_hashes = [animation.hash.uint for animation in source.animations]
    expected_clip_hashes = [clip.hash.uint for clip in source.clips]

    rebuilt = read_ycd(build_ycd_bytes(source))

    assert [
        animation.hash.uint for animation in rebuilt.animations
    ] == expected_animation_hashes
    assert [clip.hash.uint for clip in rebuilt.clips] == expected_clip_hashes


def test_cutscene_builder_supports_multi_bone_object_animation() -> None:
    builder = YcdCutsceneBuilder.create("multi_bone_scene", duration=1.0, fps=30.0)
    builder.prop(
        "p_lamarneck_01_s",
        mover_position={0.0: Vector3(), 1.0: Vector3(0.0, 1.0, 0.0)},
        mover_rotation=Quaternion(),
        bones={
            7869: YcdCutsceneBoneAnimation(
                position={0.0: Vector3(), 1.0: Vector3(1.0, 0.0, 0.0)},
                rotation=Quaternion(),
            ),
            10994: {
                "position": {0.0: Vector3(), 1.0: Vector3(0.0, 1.0, 0.0)},
                "rotation": {
                    0.0: Quaternion(),
                    1.0: Quaternion(0.0, 0.0, 0.70710678, 0.70710678),
                },
            },
        },
    )

    ycd = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    clip = ycd.get_clip("p_lamarneck_01_s-0")

    assert clip is not None and clip.animation is not None
    bone_pairs = {
        (int(bone.bone_id), int(bone.track)) for bone in clip.animation.bone_ids
    }
    assert (7869, int(YcdAnimationTrack.BONE_TRANSLATION)) in bone_pairs
    assert (7869, int(YcdAnimationTrack.BONE_ROTATION)) in bone_pairs
    assert (10994, int(YcdAnimationTrack.BONE_TRANSLATION)) in bone_pairs
    assert (10994, int(YcdAnimationTrack.BONE_ROTATION)) in bone_pairs
    assert (0, int(YcdAnimationTrack.MOVER_TRANSLATION)) in bone_pairs
    assert (0, int(YcdAnimationTrack.MOVER_ROTATION)) in bone_pairs

    evaluated_tracks = clip.animation.evaluate_object_animation(15.0)
    assert (7869, int(YcdAnimationTrack.BONE_TRANSLATION)) in evaluated_tracks
    assert (10994, int(YcdAnimationTrack.BONE_ROTATION)) in evaluated_tracks
    assert evaluated_tracks[
        (7869, int(YcdAnimationTrack.BONE_TRANSLATION))
    ].xyz.components == pytest.approx((0.5, 0.0, 0.0), abs=0.2)
    assert evaluated_tracks[
        (10994, int(YcdAnimationTrack.BONE_TRANSLATION))
    ].xyz.components == pytest.approx((0.0, 0.5, 0.0), abs=0.2)

    root_motion = clip.evaluate_root_motion_at_time(0.5)
    assert root_motion.position.components == pytest.approx(
        (0.0, 0.5, 0.0), abs=0.2
    )


def test_cutscene_builder_adds_static_mover_tracks_for_bone_only_props() -> None:
    builder = YcdCutsceneBuilder.create("bone_only_scene", duration=1.0, fps=30.0)
    builder.prop(
        "skinned_prop",
        bones={
            1: YcdCutsceneBoneAnimation(
                position={0.0: Vector3(), 1.0: Vector3(1.0, 0.0, 0.0)},
                rotation=Quaternion(),
            )
        },
    )

    ycd = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    clip = ycd.get_clip("skinned_prop-0")

    assert clip is not None and clip.animation is not None
    bone_pairs = {
        (int(bone.bone_id), int(bone.track)) for bone in clip.animation.bone_ids
    }
    assert (0, int(YcdAnimationTrack.MOVER_TRANSLATION)) in bone_pairs
    assert (0, int(YcdAnimationTrack.MOVER_ROTATION)) in bone_pairs
    assert clip.evaluate_root_motion_at_time(0.5).position.components == pytest.approx(
        (0.0, 0.0, 0.0), abs=0.01
    )


def test_cutscene_builder_splits_long_skeletal_clips_into_vanilla_sized_sequences() -> (
    None
):
    builder = YcdCutsceneBuilder.create("long_scene", duration=24.4, fps=30.0)
    builder.prop(
        "skinned_prop",
        mover_position={0.0: Vector3(), 24.4: Vector3(1.0, 0.0, 0.0)},
        mover_rotation=Quaternion(),
        bones={
            0xB692: YcdCutsceneBoneAnimation(
                rotation={
                    0.0: Quaternion(),
                    24.4: Quaternion(0.0, 0.0, 0.70710678, 0.70710678),
                }
            )
        },
    )

    ycd = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    clip = ycd.get_clip("skinned_prop-0")

    assert clip is not None and clip.animation is not None
    assert clip.animation.sequence_frame_limit == YCD_CUTSCENE_SEQUENCE_FRAME_LIMIT
    assert [sequence.num_frames for sequence in clip.animation.sequences] == [
        288,
        288,
        159,
    ]
    assert all(
        len(sequence.anim_sequences) == len(clip.animation.bone_ids)
        for sequence in clip.animation.sequences
    )
    assert any(
        int(channel.channel_type) == int(YcdChannelType.QUANTIZE_FLOAT)
        for sequence in clip.animation.sequences
        for anim_sequence in sequence.anim_sequences
        if int(anim_sequence.bone_id.track) == int(YcdAnimationTrack.BONE_ROTATION)
        for channel in anim_sequence.channels
    )


def test_cutscene_builder_channel_policy_can_be_overridden_per_track() -> None:
    raw_policy = YcdChannelEncodingPolicy(YcdChannelEncoding.RAW_FLOAT)
    builder = YcdCutsceneBuilder.create(
        "track_precision",
        duration=1.0,
        channel_policy=raw_policy,
    )
    samples = {0.0: Vector3(), 1.0: Vector3(10.0, 2.0, -1.0)}
    builder.track(
        "actor",
        track=YcdAnimationTrack.BONE_TRANSLATION,
        samples=samples,
        bone_id=1,
    )
    builder.track(
        "actor",
        track=YcdAnimationTrack.BONE_TRANSLATION,
        samples=samples,
        bone_id=2,
        channel_policy=YcdChannelEncodingPolicy(),
    )

    animation = builder.build_ycds()[0].animations[0]
    raw = animation.find_sequences(
        bone_id=1, track=YcdAnimationTrack.BONE_TRANSLATION
    )[0]
    retail = animation.find_sequences(
        bone_id=2, track=YcdAnimationTrack.BONE_TRANSLATION
    )[0]

    assert YcdChannelType.RAW_FLOAT in {
        channel.channel_type for channel in raw.channels
    }
    assert YcdChannelType.QUANTIZE_FLOAT in {
        channel.channel_type for channel in retail.channels
    }


def test_explicit_retail_channel_policy_preserves_default_binary_output() -> None:
    def build(policy: YcdChannelEncodingPolicy | None = None) -> bytes:
        kwargs = {} if policy is None else {"channel_policy": policy}
        builder = YcdCutsceneBuilder.create(
            "retail_default",
            duration=1.0,
            **kwargs,
        )
        builder.track(
            "actor",
            track=YcdAnimationTrack.MOVER_TRANSLATION,
            samples={0.0: Vector3(), 1.0: Vector3(10.0, 2.0, -1.0)},
        )
        return build_ycd_bytes(builder.build_ycds()[0])

    assert build() == build(YcdChannelEncodingPolicy())


def test_cutscene_builder_reports_unreachable_retail_precision() -> None:
    builder = YcdCutsceneBuilder.create(
        "retail_precision",
        duration=1.0,
        channel_policy=YcdChannelEncodingPolicy(maximum_error=2e-5),
    )
    builder.track(
        "actor",
        track=YcdAnimationTrack.MOVER_TRANSLATION,
        samples={0.0: Vector3(), 1.0: Vector3(100.0, 0.0, 0.0)},
    )

    report = builder.validate()

    assert "ycd.channel_precision.error_exceeded" in {
        issue.code for issue in report.errors
    }
    with pytest.raises(ValueError, match="ycd.channel_precision.error_exceeded"):
        builder.build_ycds()


@pytest.mark.parametrize(
    ("case_name", "frame_count", "translation_span"),
    [
        ("rp_14_section_0_RP_14_0_cs_roman_d_0", 31, 12.1),
        ("intro_section_3_rom1_a_0_cs_roman_d_0", 1437, 93.3),
    ],
)
def test_cutscene_builder_raw_float_meets_roman_roundtrip_precision(
    case_name: str,
    frame_count: int,
    translation_span: float,
) -> None:
    duration = (frame_count - 1) / 30.0
    translations = [
        Vector3(
            translation_span * frame / (frame_count - 1),
            math.sin(frame * 0.13) * 0.75,
            math.cos(frame * 0.07) * 0.25,
        )
        for frame in range(frame_count)
    ]
    rotations = [
        Quaternion(
            math.sin(angle / 2.0) / math.sqrt(3.0),
            math.sin(angle / 2.0) / math.sqrt(3.0),
            math.sin(angle / 2.0) / math.sqrt(3.0),
            math.cos(angle / 2.0),
        )
        for angle in (
            math.radians(20.0 + 140.0 * frame / (frame_count - 1))
            for frame in range(frame_count)
        )
    ]
    builder = YcdCutsceneBuilder.create(
        case_name,
        duration=duration,
        fps=30.0,
        game=GameTarget.GTA5_ENHANCED,
        channel_policy=YcdChannelEncodingPolicy(
            encoding=YcdChannelEncoding.RAW_FLOAT,
            maximum_error=2e-5,
            maximum_angular_error_degrees=0.002,
        ),
    )
    builder.track(
        "cs_roman_d_0",
        track=YcdAnimationTrack.MOVER_TRANSLATION,
        samples=translations,
    )
    builder.track(
        "cs_roman_d_0",
        track=YcdAnimationTrack.MOVER_ROTATION,
        samples=rotations,
    )

    report = builder.validate()
    rebuilt = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    animation = rebuilt.animations[0]
    translation_error = 0.0
    angular_error = 0.0
    for frame, (expected_position, expected_rotation) in enumerate(
        zip(translations, rotations, strict=True)
    ):
        tracks = animation.evaluate_tracks(frame, interpolate=False)
        actual_position = tracks[(0, int(YcdAnimationTrack.MOVER_TRANSLATION))]
        actual_rotation = tracks[(0, int(YcdAnimationTrack.MOVER_ROTATION))]
        translation_error = max(
            translation_error,
            max(
                abs(left - right)
                for left, right in zip(
                    expected_position, actual_position.xyz, strict=True
                )
            ),
        )
        angular_error = max(
            angular_error,
            expected_rotation.angular_error_degrees(actual_rotation),
        )

    assert report.valid
    assert translation_error < 2e-5
    assert angular_error < 0.002


def test_cutscene_builder_preserves_rotations_across_overlapping_sequences() -> None:
    frame_count = 361
    rotations = [
        Quaternion(
            0.0,
            0.0,
            math.sin(math.pi * frame / 360.0),
            math.cos(math.pi * frame / 360.0),
        )
        for frame in range(frame_count)
    ]
    builder = YcdCutsceneBuilder.create(
        "continuous_rotation",
        duration=12.0,
        fps=30.0,
    )
    builder.prop("actor", mover_rotation=rotations)

    animation = builder.build_ycds()[0].animations[0]
    assert len(animation.sequences) == 2
    emitted: list[Quaternion] = []
    sequence_samples: list[list[Quaternion]] = []
    for sequence in animation.sequences:
        rotation = next(
            item
            for item in sequence.anim_sequences
            if int(item.bone_id.track) == int(YcdAnimationTrack.MOVER_ROTATION)
        )
        values = [
            rotation.evaluate_quaternion(frame) for frame in range(sequence.num_frames)
        ]
        sequence_samples.append(values)
        emitted.extend(values if not emitted else values[1:])

    assert len(emitted) == frame_count
    assert abs(sequence_samples[0][-1].dot(sequence_samples[1][0])) > 1.0 - 1e-9
    assert all(
        abs(expected.dot(actual)) > 1.0 - 1e-6
        for expected, actual in zip(rotations, emitted, strict=True)
    )


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_cutscene_builder_uses_retail_cached_quaternions_for_dynamic_tracks(
    game: GameTarget,
) -> None:
    rotations = {
        0.0: Quaternion(),
        1.0: Quaternion(0.5, 0.5, 0.5, 0.5),
    }
    builder = YcdCutsceneBuilder.create("cached_tracks", duration=1.0, game=game)
    builder.camera(rotation=rotations)
    builder.prop(
        "actor",
        mover_rotation=rotations,
        bones={7: YcdCutsceneBoneAnimation(rotation=rotations)},
    )

    ycd = builder.build_ycds()[0]
    tracks = {
        int(YcdAnimationTrack.CAMERA_ROTATION),
        int(YcdAnimationTrack.MOVER_ROTATION),
        int(YcdAnimationTrack.BONE_ROTATION),
    }
    sequences = [
        anim_sequence
        for animation in ycd.animations
        for sequence in animation.sequences
        for anim_sequence in sequence.anim_sequences
        if int(anim_sequence.bone_id.track) in tracks
    ]

    assert len(sequences) == 3
    assert all(sequence.is_cached_quaternion for sequence in sequences)
    assert all(len(sequence.channels) == 4 for sequence in sequences)
    assert all(
        [channel.channel_type for channel in sequence.channels].count(
            YcdChannelType.CACHED_QUATERNION1
        )
        == 1
        for sequence in sequences
    )
    assert all(
        YcdChannelType.CACHED_QUATERNION2
        not in {channel.channel_type for channel in sequence.channels}
        for sequence in sequences
    )


def test_cutscene_builder_keeps_static_quaternions_static() -> None:
    builder = YcdCutsceneBuilder.create("static_rotation", duration=1.0)
    builder.prop("actor", rotation=Quaternion())

    sequence = builder.build_ycds()[0].animations[0].sequences[0].anim_sequences[0]

    assert [channel.channel_type for channel in sequence.channels] == [
        YcdChannelType.STATIC_QUATERNION
    ]
    assert not sequence.is_cached_quaternion


def test_cutscene_builder_can_emit_explicit_quaternion_components() -> None:
    builder = YcdCutsceneBuilder.create(
        "explicit_rotation",
        duration=1.0,
        quaternion_encoding=YcdQuaternionEncoding.EXPLICIT,
    )
    builder.prop(
        "actor",
        mover_rotation={
            0.0: Quaternion(),
            1.0: Quaternion(0.0, 0.0, 1.0, 0.0),
        },
    )

    rotation = (
        builder.build_ycds()[0]
        .animations[0]
        .find_sequences(track=YcdAnimationTrack.MOVER_ROTATION)[0]
    )

    assert len(rotation.channels) == 4
    assert not rotation.is_cached_quaternion
    assert YcdChannelType.CACHED_QUATERNION1 not in {
        channel.channel_type for channel in rotation.channels
    }


def test_cached_quaternion_orients_each_sample_for_the_omitted_component() -> None:
    axis_length = math.sqrt(14.0)
    rotations = [
        Quaternion(
            math.sin(angle / 2.0) / axis_length,
            2.0 * math.sin(angle / 2.0) / axis_length,
            3.0 * math.sin(angle / 2.0) / axis_length,
            math.cos(angle / 2.0),
        )
        for angle in (4.0 * math.pi * frame / 30.0 for frame in range(31))
    ]
    cached = YcdCutsceneBuilder.create("cached_unrepresentable", duration=1.0)
    cached.prop("actor", mover_rotation=rotations)

    ycd = cached.build_ycds()[0]
    rotation = ycd.animations[0].find_sequences(
        track=YcdAnimationTrack.MOVER_ROTATION
    )[0]

    assert all(
        any(rotation.components[index] < 0.0 for rotation in rotations)
        for index in range(4)
    )
    assert rotation.is_cached_quaternion
    assert all(
        abs(expected.dot(rotation.evaluate_quaternion(frame))) > 1.0 - 1e-6
        for frame, expected in enumerate(rotations)
    )


def test_cached_quaternion_roundtrip_preserves_rotation_accuracy() -> None:
    frame_count = 31
    rotations = [
        Quaternion(
            math.sin(angle / 2.0) / math.sqrt(3.0),
            math.sin(angle / 2.0) / math.sqrt(3.0),
            math.sin(angle / 2.0) / math.sqrt(3.0),
            math.cos(angle / 2.0),
        )
        for angle in (
            math.radians(20.0 + (140.0 * frame / (frame_count - 1)))
            for frame in range(frame_count)
        )
    ]
    builder = YcdCutsceneBuilder.create("cached_accuracy", duration=1.0, fps=30.0)
    builder.prop("actor", mover_rotation=rotations)

    first_bytes = build_ycd_bytes(builder.build_ycds()[0])
    rebuilt = read_ycd(first_bytes)
    second_bytes = build_ycd_bytes(rebuilt)
    animation = rebuilt.animations[0]
    sequence = animation.sequences[0]

    assert first_bytes == second_bytes
    assert sequence.root_rotation_ref_count == 4
    assert any(
        ref.channel_type == int(YcdChannelType.CACHED_QUATERNION1)
        for ref in sequence.root_rotation_refs
    )
    for frame, expected in enumerate(rotations):
        actual = animation.evaluate_tracks(frame)[
            (0, int(YcdAnimationTrack.MOVER_ROTATION))
        ]
        assert expected.angular_error_degrees(actual) < 0.01
    for frame in (0.25, 7.5, 15.75, 29.5):
        frame0 = math.floor(frame)
        expected = rotations[frame0].nlerp(rotations[frame0 + 1], frame - frame0)
        actual = animation.evaluate_tracks(frame)[
            (0, int(YcdAnimationTrack.MOVER_ROTATION))
        ]
        assert expected.angular_error_degrees(actual) < 0.01


def test_cached_quaternion_orients_omitted_component_positive() -> None:
    axis_length = math.sqrt(14.0)
    rotations = [
        Quaternion(
            -math.sin(angle / 2.0) / axis_length,
            -2.0 * math.sin(angle / 2.0) / axis_length,
            -3.0 * math.sin(angle / 2.0) / axis_length,
            math.cos(angle / 2.0),
        )
        for angle in (
            math.radians(100.0 + (160.0 * frame / 30.0)) for frame in range(31)
        )
    ]
    builder = YcdCutsceneBuilder.create("cached_sign", duration=1.0, fps=30.0)
    builder.prop("actor", mover_rotation=rotations)

    rotation = (
        builder.build_ycds()[0]
        .animations[0]
        .find_sequences(track=YcdAnimationTrack.MOVER_ROTATION)[0]
    )
    cached = next(
        channel
        for channel in rotation.channels
        if channel.channel_type is YcdChannelType.CACHED_QUATERNION1
    )

    assert cached.quat_index in {0, 1, 2}
    assert all(
        rotation.evaluate_quaternion(frame).components[cached.quat_index] >= 0.0
        for frame in range(31)
    )


def test_quaternion_layout_audit_reports_dynamic_encoding_by_track() -> None:
    rotations = {
        0.0: Quaternion(),
        1.0: Quaternion(0.0, 0.0, 1.0, 0.0),
    }
    cached = YcdCutsceneBuilder.create("cached", duration=1.0)
    cached.camera(rotation=rotations)
    explicit = YcdCutsceneBuilder.create(
        "explicit",
        duration=1.0,
        quaternion_encoding=YcdQuaternionEncoding.EXPLICIT,
    )
    explicit.prop("actor", mover_rotation=rotations)

    report = audit_ycd_quaternion_layout([*cached.build_ycds(), *explicit.build_ycds()])

    assert (
        report.count(
            YcdQuaternionLayout.CACHED_QUATERNION1,
            track=YcdAnimationTrack.CAMERA_ROTATION,
        )
        == 1
    )
    assert (
        report.count(
            YcdQuaternionLayout.EXPLICIT,
            track=YcdAnimationTrack.MOVER_ROTATION,
        )
        == 1
    )
    assert report.dominant_dynamic_layout is YcdQuaternionLayout.CACHED_QUATERNION1


def test_ycd_validation_rejects_invalid_cached_quaternion_index() -> None:
    builder = YcdCutsceneBuilder.create("invalid_cached_index", duration=1.0)
    builder.prop(
        "actor",
        mover_rotation={
            0.0: Quaternion(),
            1.0: Quaternion(0.0, 0.0, 1.0, 0.0),
        },
    )
    ycd = builder.build_ycds()[0]
    rotation = ycd.animations[0].find_sequences(track=YcdAnimationTrack.MOVER_ROTATION)[
        0
    ]
    cached = next(
        channel
        for channel in rotation.channels
        if channel.channel_type is YcdChannelType.CACHED_QUATERNION1
    )
    cached.quat_index = 4

    report = ycd.validate()

    assert "ycd.quaternion_cache.index_invalid" in {
        issue.code for issue in report.errors
    }


@pytest.mark.parametrize(
    "rotation",
    [
        Quaternion(0.0, 0.0, 0.0, 0.0),
        Quaternion(float("nan"), 0.0, 0.0, 1.0),
        Quaternion(float("inf"), 0.0, 0.0, 1.0),
    ],
)
def test_cutscene_builder_rejects_invalid_quaternions(rotation) -> None:
    builder = YcdCutsceneBuilder.create("invalid_rotation", duration=1.0)

    with pytest.raises(ValueError, match="Quaternion"):
        builder.prop("actor", rotation=rotation)


def test_cutscene_builder_from_cut_reads_camera_cuts() -> None:
    cut = scene_to_cut(
        CutScene.create(
            scene_name="generated_cut",
            duration=12.0,
            camera_cut_list=[2.0, 4.0, 8.5],
        )
    )
    builder = YcdCutsceneBuilder.from_cut(cut, name="lamar_1_int")

    assert builder.duration == pytest.approx(12.0)
    assert builder.camera_cuts == pytest.approx([2.0, 4.0, 8.5])
    assert len(builder.sections) == len(builder.camera_cuts) + 1
