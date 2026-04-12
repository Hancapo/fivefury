from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import (
    MetaHash,
    YcdAnimationTrack,
    YcdCameraAnimationSample,
    YcdChannelType,
    YcdClipAnimation,
    YcdFacialAnimationSample,
    YcdClipPropertyAttributeType,
    YcdSequence,
    YcdTransformSample,
    YcdUvAnimationSample,
    build_ycd_bytes,
    read_ycd,
)
from fivefury.resource import get_resource_total_page_count, split_rsc7_sections


TESTS_DIR = Path(__file__).resolve().parent
YCD_PATH = TESTS_DIR / "maude_mcs_1-0.ycd"
REFERENCE_YCD_DIR = TESTS_DIR.parent / "references" / "ycd"


pytestmark = pytest.mark.skipif(not YCD_PATH.is_file(), reason="ycd samples not available")


def test_read_ycd_smoke() -> None:
    ycd = read_ycd(YCD_PATH)

    assert ycd.header.version == 46
    assert len(ycd.clips) == 5
    assert len(ycd.animations) == 5
    assert ycd.clip_bucket_capacity == 11
    assert ycd.clip_entry_count == 5
    assert ycd.animation_bucket_capacity == 11
    assert ycd.animation_entry_count == 5
    assert all(isinstance(clip, YcdClipAnimation) for clip in ycd.clips)

    export_camera = next(clip for clip in ycd.clips if clip.short_name == "exportcamera-0")
    assert export_camera.animation is not None
    assert export_camera.animation.frames == 241
    assert export_camera.animation.duration == pytest.approx(8.0)
    assert export_camera.tag_count == 1
    assert export_camera.property_count == 2
    assert export_camera.tags
    assert export_camera.properties
    assert export_camera.tags[0].start_phase == pytest.approx(0.8082083463668823)
    assert export_camera.tags[0].end_phase == pytest.approx(0.8126250505447388)
    assert export_camera.tags[0].tags
    assert export_camera.properties[0].attributes
    assert export_camera.properties[0].attributes[0].attribute_type is YcdClipPropertyAttributeType.INT
    assert export_camera.properties[0].attributes[0].value == 0

    animation = export_camera.animation
    assert animation.sequence_count == 4
    assert animation.bone_id_count == 13
    assert len(animation.sequences) == 4
    assert len(animation.bone_ids) == 13
    assert isinstance(animation.sequences[0], YcdSequence)
    assert animation.sequences[0].num_frames == 64
    assert animation.sequences[0].frame_length == 4
    assert animation.bone_ids[0].bone_id == 0
    assert animation.bone_ids[0].track == 7

    maude = next(clip for clip in ycd.clips if clip.short_name == "csb_maude_dual-0")
    assert maude.animation is not None
    assert maude.animation.sequence_count == 1
    assert maude.animation.bone_id_count == 145
    assert maude.animation.sequences[0].frame_length == 76


def test_ycd_build_cutscene_map_strips_suffixes() -> None:
    ycd = read_ycd(YCD_PATH)
    cutscene_map = ycd.build_cutscene_map(0)

    camera = cutscene_map[MetaHash("exportcamera").uint]
    maude = cutscene_map[MetaHash("csb_maude").uint]

    assert camera.short_name == "exportcamera-0"
    assert maude.short_name == "csb_maude_dual-0"


def test_ycd_clip_and_animation_lookup() -> None:
    ycd = read_ycd(YCD_PATH)

    camera = ycd.get_clip("exportcamera-0")
    assert camera is not None
    assert camera.get_property(camera.properties[0].name_hash) is camera.properties[0]
    assert camera.get_tag(camera.tags[0].name_hash) is camera.tags[0]

    animation = ycd.get_animation(camera.animation.hash)
    assert animation is camera.animation
    assert animation.find_bone(0, track=7) is not None


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_uv_animation_support() -> None:
    ycd = read_ycd(REFERENCE_YCD_DIR / "sm_21.ycd")
    clip = ycd.get_clip("sm_21_uvanim_uv_1")

    assert clip is not None
    assert clip.animation is not None
    assert clip.has_uv_animation
    assert not clip.has_object_animation

    animation = clip.animation
    assert animation.has_uv_animation
    assert animation.uv_sequences
    assert {sequence.track for sequence in animation.uv_sequences} == {
        int(YcdAnimationTrack.SHADER_SLIDE_U),
        int(YcdAnimationTrack.SHADER_SLIDE_V),
    }

    uv_values = animation.evaluate_uv_animation(0)
    assert uv_values
    assert len(uv_values) == 2
    assert set(track for _, track in uv_values) == {
        int(YcdAnimationTrack.SHADER_SLIDE_U),
        int(YcdAnimationTrack.SHADER_SLIDE_V),
    }
    assert animation.sequences[0].anim_sequences
    assert animation.sequences[0].anim_sequences[0].channels
    assert animation.sequences[0].anim_sequences[0].channels[0].channel_type in {
        YcdChannelType.STATIC_VECTOR3,
        YcdChannelType.STATIC_FLOAT,
        YcdChannelType.QUANTIZE_FLOAT,
    }


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_object_animation_support() -> None:
    ycd = read_ycd(REFERENCE_YCD_DIR / "cs2_08.ycd")
    clip = ycd.get_clip("cs2_08_animboxmain")

    assert clip is not None
    assert clip.animation is not None
    assert clip.has_object_animation

    animation = clip.animation
    assert animation.has_object_animation
    assert {sequence.track for sequence in animation.object_sequences} == {
        int(YcdAnimationTrack.BONE_TRANSLATION),
        int(YcdAnimationTrack.BONE_ROTATION),
    }

    object_values = animation.evaluate_object_animation(0)
    assert object_values
    assert set(track for _, track in object_values) == {
        int(YcdAnimationTrack.BONE_TRANSLATION),
        int(YcdAnimationTrack.BONE_ROTATION),
    }
    rotation_sequence = animation.find_sequences(track=YcdAnimationTrack.BONE_ROTATION)[0]
    assert rotation_sequence.is_rotation_track
    assert len(rotation_sequence.evaluate_quaternion(0)) == 4


def test_ycd_root_motion_camera_and_bone_support() -> None:
    ycd = read_ycd(YCD_PATH)

    actor = ycd.get_clip("csb_maude_dual-0")
    assert actor is not None
    assert actor.animation is not None
    assert actor.has_root_motion
    assert actor.has_facial_animation

    root_motion = actor.evaluate_root_motion_at_time(actor.duration * 0.5)
    assert isinstance(root_motion, YcdTransformSample)
    assert root_motion.position is not None
    assert root_motion.rotation is not None
    assert len(root_motion.position) == 3
    assert len(root_motion.rotation) == 4

    facial_samples = actor.evaluate_facial_animation_at_time(actor.duration * 0.5)
    assert facial_samples
    assert all(isinstance(sample, YcdFacialAnimationSample) for sample in facial_samples.values())
    assert any(sample.control is not None for sample in facial_samples.values())
    assert any(sample.translation is not None for sample in facial_samples.values())
    assert any(sample.rotation is not None for sample in facial_samples.values())

    camera = ycd.get_clip("exportcamera-0")
    assert camera is not None
    assert camera.animation is not None
    assert camera.has_camera_animation

    camera_sample = camera.evaluate_camera_animation_at_time(camera.duration * 0.5)
    assert isinstance(camera_sample, YcdCameraAnimationSample)
    assert camera_sample.position is not None
    assert camera_sample.rotation is not None
    assert len(camera_sample.tracks) >= 5
    assert int(YcdAnimationTrack.CAMERA_FIELD_OF_VIEW) in camera_sample.tracks
    assert camera_sample.field_of_view is not None


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_time_based_uv_and_object_evaluation() -> None:
    uv_ycd = read_ycd(REFERENCE_YCD_DIR / "sm_21.ycd")
    uv_clip = uv_ycd.get_clip("sm_21_uvanim_uv_1")
    assert uv_clip is not None
    uv_sample = uv_clip.evaluate_uv_animation_at_time(uv_clip.duration * 0.5)
    assert isinstance(uv_sample, YcdUvAnimationSample)
    assert uv_sample.slide_u is not None
    assert uv_sample.slide_v is not None

    obj_ycd = read_ycd(REFERENCE_YCD_DIR / "cs2_08.ycd")
    obj_clip = obj_ycd.get_clip("cs2_08_animboxmain")
    assert obj_clip is not None
    object_sample = obj_clip.evaluate_object_animation_at_time(obj_clip.duration * 0.5)
    assert isinstance(object_sample, YcdTransformSample)
    assert object_sample.position is not None
    assert object_sample.rotation is not None


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_read_all_reference_ycd_samples() -> None:
    sample_paths = sorted(REFERENCE_YCD_DIR.glob("*.ycd"))

    assert sample_paths

    for path in sample_paths:
        ycd = read_ycd(path)
        assert ycd.clips
        assert ycd.animations
        assert ycd.clip_bucket_capacity >= ycd.clip_entry_count
        assert ycd.animation_bucket_capacity >= ycd.animation_entry_count
        for animation in ycd.animations:
            for sequence in animation.sequences:
                assert len(sequence.anim_sequences) <= animation.bone_id_count


def _assert_ycd_roundtrip_equivalent(original, rebuilt) -> None:
    assert rebuilt.header.version == original.header.version
    assert len(rebuilt.clips) == len(original.clips)
    assert len(rebuilt.animations) == len(original.animations)
    assert rebuilt.clip_entry_count == original.clip_entry_count
    assert rebuilt.animation_entry_count == original.animation_entry_count
    assert rebuilt.clip_bucket_capacity >= rebuilt.clip_entry_count
    assert rebuilt.animation_bucket_capacity >= rebuilt.animation_entry_count

    for original_clip, rebuilt_clip in zip(original.clips, rebuilt.clips, strict=True):
        assert rebuilt_clip.hash.uint == original_clip.hash.uint
        assert rebuilt_clip.short_name == original_clip.short_name
        assert rebuilt_clip.clip_type == original_clip.clip_type
        assert len(rebuilt_clip.tags) == len(original_clip.tags)
        assert len(rebuilt_clip.properties) == len(original_clip.properties)
        if isinstance(original_clip, YcdClipAnimation):
            assert isinstance(rebuilt_clip, YcdClipAnimation)
            assert original_clip.animation is not None
            assert rebuilt_clip.animation is not None
            assert rebuilt_clip.animation.hash.uint == original_clip.animation.hash.uint
            assert rebuilt_clip.animation.frames == original_clip.animation.frames
            assert rebuilt_clip.animation.sequence_count == original_clip.animation.sequence_count
            assert rebuilt_clip.animation.bone_id_count == original_clip.animation.bone_id_count


def test_ycd_roundtrip_smoke() -> None:
    original = read_ycd(YCD_PATH)
    raw = build_ycd_bytes(original)
    rebuilt = read_ycd(raw)
    header, system_data, _ = split_rsc7_sections(raw)
    pages_info_offset = int.from_bytes(system_data[0x08:0x10], "little") - 0x50000000

    assert system_data[pages_info_offset + 0x08] == get_resource_total_page_count(header.system_flags)
    assert system_data[pages_info_offset + 0x09] == get_resource_total_page_count(header.graphics_flags)
    _assert_ycd_roundtrip_equivalent(original, rebuilt)


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_roundtrip_all_reference_samples() -> None:
    sample_paths = sorted(REFERENCE_YCD_DIR.glob("*.ycd"))
    assert sample_paths
    for path in sample_paths:
        original = read_ycd(path)
        rebuilt = read_ycd(build_ycd_bytes(original))
        _assert_ycd_roundtrip_equivalent(original, rebuilt)
