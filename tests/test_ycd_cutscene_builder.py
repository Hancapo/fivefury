from __future__ import annotations

import struct
from pathlib import Path

import pytest

from fivefury import (
    GEN9_YCD_RUNTIME_PROFILE,
    YCD_CUTSCENE_SEQUENCE_FRAME_LIMIT,
    GameTarget,
    MetaHash,
    YcdAnimationTrack,
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
    build_cutscene_sections,
    build_ycd_bytes,
    read_cut,
    read_ycd,
)
from fivefury.resource import split_rsc7_sections, virtual_to_offset

TESTS_DIR = Path(__file__).resolve().parent
CUT_SAMPLE_PATH = TESTS_DIR.parent / "references" / "lamar_1_int.cut"


def test_build_cutscene_sections_uses_camera_cuts() -> None:
    sections = build_cutscene_sections(10.0, [2.5, 7.0], fps=30.0)

    assert [(section.index, section.start_time, section.end_time) for section in sections] == [
        (0, 0.0, 2.5),
        (1, 2.5, 7.0),
        (2, 7.0, 10.0),
    ]
    assert sections[0].frame_count == 76
    assert sections[1].frame_count == 136
    assert sections[2].frame_count == 91


def test_cutscene_builder_builds_sectioned_ycds_roundtrip() -> None:
    builder = YcdCutsceneBuilder.create("demo_scene", duration=1.0, camera_cuts=[0.5], fps=30.0)
    builder.add_camera(
        position={0.0: (0.0, 0.0, 0.0), 1.0: (10.0, 0.0, 0.0)},
        rotation=(0.0, 0.0, 0.0, 1.0),
        field_of_view={0.0: 40.0, 1.0: 60.0},
    )
    builder.add_prop(
        "prop_box",
        position={0.0: (1.0, 0.0, 0.0), 1.0: (1.0, 10.0, 0.0)},
        rotation=(0.0, 0.0, 0.0, 1.0),
        mover_position={0.0: (0.0, 0.0, 0.0), 1.0: (0.0, 2.0, 0.0)},
        mover_rotation=(0.0, 0.0, 0.0, 1.0),
    )

    ycds = builder.build_ycds()

    assert [ycd.path for ycd in ycds] == ["demo_scene-0.ycd", "demo_scene-1.ycd"]
    assert [clip.short_name for clip in ycds[0].clips] == ["exportcamera-0", "prop_box-0"]
    assert [clip.short_name for clip in ycds[1].clips] == ["exportcamera-1", "prop_box-1"]

    section0_raw = build_ycd_bytes(ycds[0])
    section0 = read_ycd(section0_raw)
    section1 = read_ycd(build_ycd_bytes(ycds[1]))
    assert all(animation.vft == 0x405A58F0 for animation in section0.animations)
    assert all(clip.vft == 0x405A4088 for clip in section0.clips)
    assert all(clip.unknown_04h == 1 for clip in section0.clips)
    assert all(clip.unknown_48h == 1 for clip in section0.clips)
    assert all(
        clip.property_map_reserved_0ch == 0x01000000
        for clip in section0.clips
    )

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
    prop1_root = prop1.evaluate_root_motion_at_time(0.0)

    assert cam0_start.position == pytest.approx((0.0, 0.0, 0.0))
    assert cam0_start.field_of_view == pytest.approx(40.0)
    assert cam1_start.position == pytest.approx((5.0, 0.0, 0.0), abs=0.2)
    assert cam1_start.field_of_view == pytest.approx(50.0, abs=0.5)

    assert prop0_start.position == pytest.approx((1.0, 0.0, 0.0))
    assert prop1_start.position == pytest.approx((1.0, 5.0, 0.0), abs=0.2)
    assert prop1_root.position == pytest.approx((0.0, 1.0, 0.0), abs=0.2)

    assert any(int(bone.track) == int(YcdAnimationTrack.MOVER_TRANSLATION) for bone in prop1.animation.bone_ids)
    assert any(int(bone.track) == int(YcdAnimationTrack.CAMERA_FIELD_OF_VIEW) for bone in cam1.animation.bone_ids)


def test_cutscene_builder_writes_enhanced_runtime_headers() -> None:
    profile = GEN9_YCD_RUNTIME_PROFILE
    builder = YcdCutsceneBuilder.create(
        "enhanced_scene",
        duration=1.0,
        game=GameTarget.GTA5_ENHANCED,
    )
    builder.add_prop(
        "prop_box",
        position=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
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
    clip.tags = [YcdClipTag(name_hash=MetaHash("block"), start_phase=0.0, end_phase=1.0)]
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
    rebuilt_clip = next(item for item in rebuilt.clips if item.clip_type is YcdClipType.ANIMATION)
    assert rebuilt_clip.properties[0].vft == profile.clip_property_vft
    assert rebuilt_clip.properties[0].attributes[0].vft == profile.attribute_vft(
        YcdClipPropertyAttributeType.INT
    )
    assert rebuilt_clip.tags[0].vft == profile.clip_tag_vft


def test_cutscene_builder_returns_empty_when_no_animated_clips() -> None:
    builder = YcdCutsceneBuilder.create("empty_scene", duration=5.0)

    assert builder.build_ycds() == []


def test_cutscene_builder_supports_multi_bone_object_animation() -> None:
    builder = YcdCutsceneBuilder.create("multi_bone_scene", duration=1.0, fps=30.0)
    builder.add_prop(
        "p_lamarneck_01_s",
        mover_position={0.0: (0.0, 0.0, 0.0), 1.0: (0.0, 1.0, 0.0)},
        mover_rotation=(0.0, 0.0, 0.0, 1.0),
        bones={
            7869: YcdCutsceneBoneAnimation(
                position={0.0: (0.0, 0.0, 0.0), 1.0: (1.0, 0.0, 0.0)},
                rotation=(0.0, 0.0, 0.0, 1.0),
            ),
            10994: {
                "position": {0.0: (0.0, 0.0, 0.0), 1.0: (0.0, 1.0, 0.0)},
                "rotation": {0.0: (0.0, 0.0, 0.0, 1.0), 1.0: (0.0, 0.0, 0.70710678, 0.70710678)},
            },
        },
    )

    ycd = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    clip = ycd.get_clip("p_lamarneck_01_s-0")

    assert clip is not None and clip.animation is not None
    bone_pairs = {(int(bone.bone_id), int(bone.track)) for bone in clip.animation.bone_ids}
    assert (7869, int(YcdAnimationTrack.BONE_TRANSLATION)) in bone_pairs
    assert (7869, int(YcdAnimationTrack.BONE_ROTATION)) in bone_pairs
    assert (10994, int(YcdAnimationTrack.BONE_TRANSLATION)) in bone_pairs
    assert (10994, int(YcdAnimationTrack.BONE_ROTATION)) in bone_pairs
    assert (0, int(YcdAnimationTrack.MOVER_TRANSLATION)) in bone_pairs
    assert (0, int(YcdAnimationTrack.MOVER_ROTATION)) in bone_pairs

    evaluated_tracks = clip.animation.evaluate_object_animation(15.0)
    assert (7869, int(YcdAnimationTrack.BONE_TRANSLATION)) in evaluated_tracks
    assert (10994, int(YcdAnimationTrack.BONE_ROTATION)) in evaluated_tracks
    assert evaluated_tracks[(7869, int(YcdAnimationTrack.BONE_TRANSLATION))][:3] == pytest.approx((0.5, 0.0, 0.0), abs=0.2)
    assert evaluated_tracks[(10994, int(YcdAnimationTrack.BONE_TRANSLATION))][:3] == pytest.approx((0.0, 0.5, 0.0), abs=0.2)

    root_motion = clip.evaluate_root_motion_at_time(0.5)
    assert root_motion.position == pytest.approx((0.0, 0.5, 0.0), abs=0.2)


def test_cutscene_builder_adds_static_mover_tracks_for_bone_only_props() -> None:
    builder = YcdCutsceneBuilder.create("bone_only_scene", duration=1.0, fps=30.0)
    builder.add_prop(
        "skinned_prop",
        bones={
            1: YcdCutsceneBoneAnimation(
                position={0.0: (0.0, 0.0, 0.0), 1.0: (1.0, 0.0, 0.0)},
                rotation=(0.0, 0.0, 0.0, 1.0),
            )
        },
    )

    ycd = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    clip = ycd.get_clip("skinned_prop-0")

    assert clip is not None and clip.animation is not None
    bone_pairs = {(int(bone.bone_id), int(bone.track)) for bone in clip.animation.bone_ids}
    assert (0, int(YcdAnimationTrack.MOVER_TRANSLATION)) in bone_pairs
    assert (0, int(YcdAnimationTrack.MOVER_ROTATION)) in bone_pairs
    assert clip.evaluate_root_motion_at_time(0.5).position == pytest.approx((0.0, 0.0, 0.0), abs=0.01)


def test_cutscene_builder_splits_long_skeletal_clips_into_vanilla_sized_sequences() -> None:
    builder = YcdCutsceneBuilder.create("long_scene", duration=24.4, fps=30.0)
    builder.add_prop(
        "skinned_prop",
        mover_position={0.0: (0.0, 0.0, 0.0), 24.4: (1.0, 0.0, 0.0)},
        mover_rotation=(0.0, 0.0, 0.0, 1.0),
        bones={
            0xB692: YcdCutsceneBoneAnimation(
                rotation={0.0: (0.0, 0.0, 0.0, 1.0), 24.4: (0.0, 0.0, 0.70710678, 0.70710678)}
            )
        },
    )

    ycd = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    clip = ycd.get_clip("skinned_prop-0")

    assert clip is not None and clip.animation is not None
    assert clip.animation.sequence_frame_limit == YCD_CUTSCENE_SEQUENCE_FRAME_LIMIT
    assert [sequence.num_frames for sequence in clip.animation.sequences] == [288, 288, 159]
    assert all(len(sequence.anim_sequences) == len(clip.animation.bone_ids) for sequence in clip.animation.sequences)
    assert any(
        int(channel.channel_type) == int(YcdChannelType.QUANTIZE_FLOAT)
        for sequence in clip.animation.sequences
        for anim_sequence in sequence.anim_sequences
        if int(anim_sequence.bone_id.track) == int(YcdAnimationTrack.BONE_ROTATION)
        for channel in anim_sequence.channels
    )


@pytest.mark.skipif(not CUT_SAMPLE_PATH.is_file(), reason="cut sample not available")
def test_cutscene_builder_from_cut_reads_camera_cuts() -> None:
    cut = read_cut(CUT_SAMPLE_PATH)
    builder = YcdCutsceneBuilder.from_cut(cut, name="lamar_1_int")

    assert builder.duration == pytest.approx(142.86666870117188)
    assert builder.camera_cuts[:4] == pytest.approx([8.0, 16.0, 24.0, 32.5])
    assert len(builder.sections) == len(builder.camera_cuts) + 1
