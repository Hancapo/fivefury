from __future__ import annotations

import math
from pathlib import Path

import pytest

from fivefury import (
    MetaHash,
    Ycd,
    YcdAnimation,
    YcdAnimationTrack,
    YcdAnimationBoneId,
    YcdAnimSequence,
    YcdCameraAnimationSample,
    YcdChannelType,
    YcdClipAnimation,
    YcdFacialAnimationSample,
    YcdClipPropertyAttributeType,
    YcdSequence,
    YcdTrackFormat,
    YcdTransformSample,
    YcdUvAnimationSample,
    YcdUvClipBinding,
    YcdUvTransformSample,
    build_ycd_bytes,
    build_ycd_uv_clip_hash,
    build_ycd_uv_clip_name,
    get_ycd_track_format,
    parse_ycd_uv_clip_binding,
    read_ycd,
)
from fivefury.ycd.sequence_channels import YcdQuantizeFloatChannel, YcdStaticFloatChannel
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
    assert clip.uv_binding == YcdUvClipBinding(object_name="sm_21_uvanim", slot_index=1)
    assert clip.uv_object_name == "sm_21_uvanim"
    assert clip.uv_slot_index == 1
    assert clip.hash.uint == build_ycd_uv_clip_hash("sm_21_uvanim", 1).uint
    assert clip.short_name == build_ycd_uv_clip_name("sm_21_uvanim", 1)

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
    assert all(sequence.bone_id is not None and sequence.bone_id.bone_id == 0 for sequence in animation.uv_sequences)
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
    assert isinstance(uv_sample, YcdUvTransformSample)
    assert isinstance(uv_sample, YcdUvAnimationSample)
    assert uv_sample.uv0 is not None
    assert uv_sample.uv1 is not None
    assert len(uv_sample.uv0) == 3
    assert len(uv_sample.uv1) == 3
    assert uv_sample.slide_u == uv_sample.uv0
    assert uv_sample.slide_v == uv_sample.uv1

    obj_ycd = read_ycd(REFERENCE_YCD_DIR / "cs2_08.ycd")
    obj_clip = obj_ycd.get_clip("cs2_08_animboxmain")
    assert obj_clip is not None
    object_sample = obj_clip.evaluate_object_animation_at_time(obj_clip.duration * 0.5)
    assert isinstance(object_sample, YcdTransformSample)
    assert object_sample.position is not None
    assert object_sample.rotation is not None


def test_ycd_uv_binding_helpers() -> None:
    binding = parse_ycd_uv_clip_binding("sm_21_uvanim_uv_1")
    assert binding == YcdUvClipBinding(object_name="sm_21_uvanim", slot_index=1)
    assert binding is not None
    assert binding.clip_name == "sm_21_uvanim_uv_1"
    assert binding.clip_hash.uint == build_ycd_uv_clip_hash("sm_21_uvanim", 1).uint
    assert build_ycd_uv_clip_name("sm_21_uvanim", 1) == "sm_21_uvanim_uv_1"
    assert parse_ycd_uv_clip_binding("plain_clip_name") is None


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
    def _assert_attribute_equivalent(original_attribute, rebuilt_attribute) -> None:
        assert rebuilt_attribute.name_hash.uint == original_attribute.name_hash.uint
        assert rebuilt_attribute.attribute_type == original_attribute.attribute_type
        if isinstance(original_attribute.value, tuple):
            assert rebuilt_attribute.value == pytest.approx(original_attribute.value)
        elif isinstance(original_attribute.value, float):
            assert rebuilt_attribute.value == pytest.approx(original_attribute.value)
        else:
            assert rebuilt_attribute.value == original_attribute.value
        assert rebuilt_attribute.unknown_04h == original_attribute.unknown_04h
        assert rebuilt_attribute.unknown_09h == original_attribute.unknown_09h
        assert rebuilt_attribute.unknown_0ah == original_attribute.unknown_0ah
        assert rebuilt_attribute.unknown_0ch == original_attribute.unknown_0ch
        assert rebuilt_attribute.unknown_10h == original_attribute.unknown_10h
        assert rebuilt_attribute.unknown_14h == original_attribute.unknown_14h
        assert rebuilt_attribute.unknown_1ch == original_attribute.unknown_1ch
        if isinstance(original_attribute.extra, float):
            assert rebuilt_attribute.extra == pytest.approx(original_attribute.extra)
        else:
            assert rebuilt_attribute.extra == original_attribute.extra

    def _assert_property_equivalent(original_property, rebuilt_property) -> None:
        assert rebuilt_property.name_hash.uint == original_property.name_hash.uint
        assert rebuilt_property.unknown_04h == original_property.unknown_04h
        assert rebuilt_property.unknown_08h == original_property.unknown_08h
        assert rebuilt_property.unknown_0ch == original_property.unknown_0ch
        assert rebuilt_property.unknown_10h == original_property.unknown_10h
        assert rebuilt_property.unknown_14h == original_property.unknown_14h
        assert rebuilt_property.unknown_1ch == original_property.unknown_1ch
        assert rebuilt_property.unknown_2ch == original_property.unknown_2ch
        assert rebuilt_property.unknown_30h == original_property.unknown_30h
        assert rebuilt_property.unknown_34h == original_property.unknown_34h
        assert rebuilt_property.unknown_hash.uint == original_property.unknown_hash.uint
        assert rebuilt_property.unknown_3ch == original_property.unknown_3ch
        assert len(rebuilt_property.attributes) == len(original_property.attributes)
        for original_attribute, rebuilt_attribute in zip(original_property.attributes, rebuilt_property.attributes, strict=True):
            _assert_attribute_equivalent(original_attribute, rebuilt_attribute)

    def _assert_tag_equivalent(original_tag, rebuilt_tag) -> None:
        _assert_property_equivalent(original_tag, rebuilt_tag)
        assert rebuilt_tag.start_phase == pytest.approx(original_tag.start_phase)
        assert rebuilt_tag.end_phase == pytest.approx(original_tag.end_phase)
        assert rebuilt_tag.has_block_tag == original_tag.has_block_tag
        assert rebuilt_tag.tag_list_reserved_0ch == original_tag.tag_list_reserved_0ch
        assert rebuilt_tag.tag_list_reserved_14h == original_tag.tag_list_reserved_14h
        assert rebuilt_tag.tag_list_reserved_18h == original_tag.tag_list_reserved_18h
        assert rebuilt_tag.tag_list_reserved_1ch == original_tag.tag_list_reserved_1ch
        assert len(rebuilt_tag.tags) == len(original_tag.tags)
        for original_nested_tag, rebuilt_nested_tag in zip(original_tag.tags, rebuilt_tag.tags, strict=True):
            _assert_tag_equivalent(original_nested_tag, rebuilt_nested_tag)

    def _assert_channel_equivalent(original_channel, rebuilt_channel) -> None:
        assert type(rebuilt_channel) is type(original_channel)
        assert rebuilt_channel.channel_type == original_channel.channel_type
        assert rebuilt_channel.sequence_index == original_channel.sequence_index
        assert rebuilt_channel.channel_index == original_channel.channel_index
        if hasattr(original_channel, "value"):
            original_value = original_channel.value
            rebuilt_value = rebuilt_channel.value
            if isinstance(original_value, tuple):
                assert rebuilt_value == pytest.approx(original_value)
            else:
                assert rebuilt_value == pytest.approx(original_value)
        if hasattr(original_channel, "values"):
            assert rebuilt_channel.values == pytest.approx(original_channel.values)
        if hasattr(original_channel, "frames"):
            assert rebuilt_channel.frames == original_channel.frames
        if hasattr(original_channel, "value_list"):
            assert rebuilt_channel.value_list == original_channel.value_list
        if hasattr(original_channel, "quat_index"):
            assert rebuilt_channel.quat_index == original_channel.quat_index
        for attribute_name in ("quantum", "offset"):
            if hasattr(original_channel, attribute_name):
                assert getattr(rebuilt_channel, attribute_name) == pytest.approx(getattr(original_channel, attribute_name))

    def _assert_anim_sequence_equivalent(original_anim_sequence, rebuilt_anim_sequence) -> None:
        assert rebuilt_anim_sequence.is_cached_quaternion == original_anim_sequence.is_cached_quaternion
        original_bone = original_anim_sequence.bone_id
        rebuilt_bone = rebuilt_anim_sequence.bone_id
        if original_bone is None:
            assert rebuilt_bone is None
        else:
            assert rebuilt_bone is not None
            assert rebuilt_bone.bone_id == original_bone.bone_id
            assert rebuilt_bone.track == original_bone.track
            assert int(rebuilt_bone.format) == int(original_bone.format)
        assert len(rebuilt_anim_sequence.channels) == len(original_anim_sequence.channels)
        for original_channel, rebuilt_channel in zip(
            original_anim_sequence.channels,
            rebuilt_anim_sequence.channels,
            strict=True,
        ):
            _assert_channel_equivalent(original_channel, rebuilt_channel)

    def _assert_sequence_equivalent(original_sequence, rebuilt_sequence) -> None:
        assert rebuilt_sequence.hash.uint == original_sequence.hash.uint
        assert rebuilt_sequence.num_frames == original_sequence.num_frames
        assert rebuilt_sequence.frame_length == original_sequence.frame_length
        assert rebuilt_sequence.chunk_size == original_sequence.chunk_size
        assert rebuilt_sequence.root_motion_ref_counts == original_sequence.root_motion_ref_counts
        assert rebuilt_sequence.unused_08h == original_sequence.unused_08h
        assert rebuilt_sequence.unused_14h == original_sequence.unused_14h
        assert [(item.channel_type, item.channel_index) for item in rebuilt_sequence.root_position_refs] == [
            (item.channel_type, item.channel_index) for item in original_sequence.root_position_refs
        ]
        assert [(item.channel_type, item.channel_index) for item in rebuilt_sequence.root_rotation_refs] == [
            (item.channel_type, item.channel_index) for item in original_sequence.root_rotation_refs
        ]
        assert len(rebuilt_sequence.anim_sequences) == len(original_sequence.anim_sequences)
        for original_anim_sequence, rebuilt_anim_sequence in zip(
            original_sequence.anim_sequences,
            rebuilt_sequence.anim_sequences,
            strict=True,
        ):
            _assert_anim_sequence_equivalent(original_anim_sequence, rebuilt_anim_sequence)

    def _assert_animation_equivalent(original_animation, rebuilt_animation) -> None:
        assert rebuilt_animation.hash.uint == original_animation.hash.uint
        assert rebuilt_animation.frames == original_animation.frames
        assert rebuilt_animation.sequence_frame_limit == original_animation.sequence_frame_limit
        assert rebuilt_animation.duration == pytest.approx(original_animation.duration)
        assert rebuilt_animation.usage_count == original_animation.usage_count
        assert rebuilt_animation.sequence_count == original_animation.sequence_count
        assert rebuilt_animation.bone_id_count == original_animation.bone_id_count
        assert rebuilt_animation.vft == original_animation.vft
        assert rebuilt_animation.flags == original_animation.flags
        assert rebuilt_animation.max_seq_block_length == original_animation.max_seq_block_length
        assert rebuilt_animation.raw_unknown_hash.uint == original_animation.raw_unknown_hash.uint
        assert len(rebuilt_animation.bone_ids) == len(original_animation.bone_ids)
        for original_bone_id, rebuilt_bone_id in zip(original_animation.bone_ids, rebuilt_animation.bone_ids, strict=True):
            assert rebuilt_bone_id.bone_id == original_bone_id.bone_id
            assert rebuilt_bone_id.track == original_bone_id.track
        assert int(rebuilt_bone_id.format) == int(original_bone_id.format)
        assert len(rebuilt_animation.sequences) == len(original_animation.sequences)
        for original_sequence, rebuilt_sequence in zip(original_animation.sequences, rebuilt_animation.sequences, strict=True):
            _assert_sequence_equivalent(original_sequence, rebuilt_sequence)

    assert rebuilt.header.version == original.header.version
    assert len(rebuilt.clips) == len(original.clips)
    assert len(rebuilt.animations) == len(original.animations)
    assert rebuilt.clip_entry_count == original.clip_entry_count
    assert rebuilt.animation_entry_count == original.animation_entry_count
    assert rebuilt.clip_bucket_capacity >= rebuilt.clip_entry_count
    assert rebuilt.animation_bucket_capacity >= rebuilt.animation_entry_count

    for original_animation, rebuilt_animation in zip(original.animations, rebuilt.animations, strict=True):
        _assert_animation_equivalent(original_animation, rebuilt_animation)

    for original_clip, rebuilt_clip in zip(original.clips, rebuilt.clips, strict=True):
        assert rebuilt_clip.hash.uint == original_clip.hash.uint
        assert rebuilt_clip.short_name == original_clip.short_name
        assert rebuilt_clip.clip_type == original_clip.clip_type
        assert rebuilt_clip.flags == original_clip.flags
        assert rebuilt_clip.reserved_34h == original_clip.reserved_34h
        assert rebuilt_clip.has_block_tag == original_clip.has_block_tag
        assert rebuilt_clip.tag_list_reserved_0ch == original_clip.tag_list_reserved_0ch
        assert rebuilt_clip.tag_list_reserved_14h == original_clip.tag_list_reserved_14h
        assert rebuilt_clip.tag_list_reserved_18h == original_clip.tag_list_reserved_18h
        assert rebuilt_clip.tag_list_reserved_1ch == original_clip.tag_list_reserved_1ch
        assert rebuilt_clip.property_map_reserved_0ch == original_clip.property_map_reserved_0ch
        assert len(rebuilt_clip.tags) == len(original_clip.tags)
        assert len(rebuilt_clip.properties) == len(original_clip.properties)
        for original_tag, rebuilt_tag in zip(original_clip.tags, rebuilt_clip.tags, strict=True):
            _assert_tag_equivalent(original_tag, rebuilt_tag)
        for original_property, rebuilt_property in zip(original_clip.properties, rebuilt_clip.properties, strict=True):
            _assert_property_equivalent(original_property, rebuilt_property)
        if isinstance(original_clip, YcdClipAnimation):
            assert isinstance(rebuilt_clip, YcdClipAnimation)
            assert original_clip.animation is not None
            assert rebuilt_clip.animation is not None
            assert rebuilt_clip.animation.hash.uint == original_clip.animation.hash.uint
            assert rebuilt_clip.reserved_64h == original_clip.reserved_64h
            assert rebuilt_clip.reserved_68h == original_clip.reserved_68h
            assert rebuilt_clip.reserved_6ch == original_clip.reserved_6ch
        else:
            assert isinstance(rebuilt_clip, type(original_clip))
            if hasattr(original_clip, "total_duration"):
                assert rebuilt_clip.total_duration == pytest.approx(original_clip.total_duration)
                assert rebuilt_clip.parallel == original_clip.parallel
                assert rebuilt_clip.parallel_padding == original_clip.parallel_padding
                assert rebuilt_clip.reserved_68h == original_clip.reserved_68h
                assert rebuilt_clip.reserved_6ch == original_clip.reserved_6ch
                assert len(rebuilt_clip.animations) == len(original_clip.animations)
                for original_entry, rebuilt_entry in zip(original_clip.animations, rebuilt_clip.animations, strict=True):
                    assert rebuilt_entry.start_time == pytest.approx(original_entry.start_time)
                    assert rebuilt_entry.end_time == pytest.approx(original_entry.end_time)
                    assert rebuilt_entry.rate == pytest.approx(original_entry.rate)
                    assert rebuilt_entry.alignment_padding_0ch == original_entry.alignment_padding_0ch


def test_ycd_roundtrip_smoke() -> None:
    expected = read_ycd(YCD_PATH)
    source = read_ycd(YCD_PATH)
    raw = build_ycd_bytes(source)
    rebuilt = read_ycd(raw)
    header, system_data, _ = split_rsc7_sections(raw)
    pages_info_offset = int.from_bytes(system_data[0x08:0x10], "little") - 0x50000000

    assert system_data[pages_info_offset + 0x08] == get_resource_total_page_count(header.system_flags)
    assert system_data[pages_info_offset + 0x09] == get_resource_total_page_count(header.graphics_flags)
    _assert_ycd_roundtrip_equivalent(expected, rebuilt)


def _mutate_first_serializable_channel(animation) -> tuple[int, int, int, str, object]:
    for sequence_index, sequence in enumerate(animation.sequences):
        for anim_sequence_index, anim_sequence in enumerate(sequence.anim_sequences):
            for channel_index, channel in enumerate(anim_sequence.channels):
                if hasattr(channel, "frames") and hasattr(channel, "values"):
                    target = float(getattr(channel, "offset", 0.0)) + (float(getattr(channel, "quantum", 0.0)) or 1.0)
                    channel.values = [target]
                    channel.frames = [0] * max(sequence.num_frames, 1)
                    return sequence_index, anim_sequence_index, channel_index, "values", target
                if hasattr(channel, "values"):
                    values = getattr(channel, "values")
                    if values:
                        target = float(getattr(channel, "offset", 0.0)) + (float(getattr(channel, "quantum", 0.0)) or 1.0)
                        channel.values = [target] * len(values)
                        return sequence_index, anim_sequence_index, channel_index, "values", target
                if hasattr(channel, "value"):
                    current = getattr(channel, "value")
                    if isinstance(current, tuple) and len(current) == 4:
                        xyz = (0.1, 0.2, 0.3)
                        w = math.sqrt(max(1.0 - sum(component * component for component in xyz), 0.0))
                        target = (*xyz, w)
                    elif isinstance(current, tuple) and len(current) == 3:
                        target = (1.0, 2.0, 3.0)
                    else:
                        target = 1.25
                    channel.value = target
                    return sequence_index, anim_sequence_index, channel_index, "value", target
    raise AssertionError("No serializable YCD channel was found")


def test_ycd_roundtrip_rebuilds_sequences_without_raw_data() -> None:
    expected = read_ycd(YCD_PATH)
    source = read_ycd(YCD_PATH)
    for animation in source.animations:
        for sequence in animation.sequences:
            sequence.raw_data = b""
    rebuilt = read_ycd(build_ycd_bytes(source))
    _assert_ycd_roundtrip_equivalent(expected, rebuilt)


def test_ycd_roundtrip_persists_channel_edits() -> None:
    ycd = read_ycd(YCD_PATH)
    clip = ycd.get_clip("exportcamera-0")
    assert clip is not None
    assert clip.animation is not None

    sequence_index, anim_sequence_index, channel_index, attribute_name, target = _mutate_first_serializable_channel(clip.animation)
    for sequence in clip.animation.sequences:
        sequence.raw_data = b""

    rebuilt = read_ycd(build_ycd_bytes(ycd))
    rebuilt_clip = rebuilt.get_clip("exportcamera-0")
    assert rebuilt_clip is not None
    assert rebuilt_clip.animation is not None
    rebuilt_channel = rebuilt_clip.animation.sequences[sequence_index].anim_sequences[anim_sequence_index].channels[channel_index]

    if attribute_name == "values":
        rebuilt_values = getattr(rebuilt_channel, "values")
        assert rebuilt_values
        assert rebuilt_values[0] == pytest.approx(target)
    else:
        rebuilt_value = getattr(rebuilt_channel, "value")
        if isinstance(target, tuple):
            assert rebuilt_value == pytest.approx(target)
        else:
            assert rebuilt_value == pytest.approx(target)


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_writer_rejects_uv_clip_hash_mismatch() -> None:
    ycd = read_ycd(REFERENCE_YCD_DIR / "sm_21.ycd")
    clip = ycd.get_clip("sm_21_uvanim_uv_1")
    assert clip is not None
    clip.hash = MetaHash("sm_21_uvanim_uv_1")
    with pytest.raises(ValueError, match="expected"):
        build_ycd_bytes(ycd)


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_writer_rejects_uv_clip_nonzero_bone_id() -> None:
    ycd = read_ycd(REFERENCE_YCD_DIR / "sm_21.ycd")
    clip = ycd.get_clip("sm_21_uvanim_uv_1")
    assert clip is not None
    assert clip.animation is not None
    sequence = clip.animation.uv_sequences[0]
    assert sequence.bone_id is not None
    sequence.bone_id.bone_id = 1
    with pytest.raises(ValueError, match="bone_id 0"):
        build_ycd_bytes(ycd)


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_roundtrip_all_reference_samples() -> None:
    sample_paths = sorted(REFERENCE_YCD_DIR.glob("*.ycd"))
    assert sample_paths
    for path in sample_paths:
        expected = read_ycd(path)
        source = read_ycd(path)
        rebuilt = read_ycd(build_ycd_bytes(source))
        _assert_ycd_roundtrip_equivalent(expected, rebuilt)


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_roundtrip_preserves_linear_float_channels() -> None:
    path = REFERENCE_YCD_DIR / "cs2_08.ycd"
    expected = read_ycd(path)
    rebuilt = read_ycd(build_ycd_bytes(read_ycd(path)))

    matched = False
    for original_animation, rebuilt_animation in zip(expected.animations, rebuilt.animations, strict=True):
        for original_sequence, rebuilt_sequence in zip(original_animation.sequences, rebuilt_animation.sequences, strict=True):
            for original_anim_sequence, rebuilt_anim_sequence in zip(
                original_sequence.anim_sequences,
                rebuilt_sequence.anim_sequences,
                strict=True,
            ):
                for original_channel, rebuilt_channel in zip(
                    original_anim_sequence.channels,
                    rebuilt_anim_sequence.channels,
                    strict=True,
                ):
                    if original_channel.channel_type is not YcdChannelType.LINEAR_FLOAT:
                        continue
                    matched = True
                    assert rebuilt_channel.values == pytest.approx(original_channel.values)
                    assert rebuilt_channel.value_list == original_channel.value_list
    assert matched


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_writer_derives_skeletal_bone_ids_and_channel_indices() -> None:
    path = REFERENCE_YCD_DIR / "cs2_08.ycd"
    expected = read_ycd(path)
    source = read_ycd(path)

    animation = source.animations[0]
    animation.bone_ids = []
    animation.bone_id_count = 0
    for sequence in animation.sequences:
        for anim_sequence in sequence.anim_sequences:
            for channel in anim_sequence.channels:
                channel.channel_index = 0
                channel.sequence_index = 0

    source.build()
    prepared_animation = source.animations[0]
    assert len(prepared_animation.bone_ids) == len(expected.animations[0].bone_ids)
    cached_sequence = next(
        anim_sequence
        for sequence in prepared_animation.sequences
        for anim_sequence in sequence.anim_sequences
        if any(channel.channel_type is YcdChannelType.CACHED_QUATERNION2 for channel in anim_sequence.channels)
    )
    assert [channel.channel_index for channel in cached_sequence.channels] == [0, 1, 2, 3, 4]

    rebuilt = read_ycd(build_ycd_bytes(source))
    _assert_ycd_roundtrip_equivalent(expected, rebuilt)


@pytest.mark.skipif(not REFERENCE_YCD_DIR.is_dir(), reason="reference ycd samples not available")
def test_ycd_rotation_bone_ids_preserve_quaternion_format() -> None:
    source = read_ycd(REFERENCE_YCD_DIR / "cs2_08.ycd")

    rotation_bones = [
        bone
        for animation in source.animations
        for bone in animation.bone_ids
        if int(bone.track) == int(YcdAnimationTrack.BONE_ROTATION)
    ]
    assert rotation_bones
    assert all(int(bone.format) == int(YcdTrackFormat.QUATERNION) for bone in rotation_bones)

    rebuilt = read_ycd(build_ycd_bytes(source))
    rebuilt_rotation_bones = [
        bone
        for animation in rebuilt.animations
        for bone in animation.bone_ids
        if int(bone.track) == int(YcdAnimationTrack.BONE_ROTATION)
    ]
    assert rebuilt_rotation_bones
    assert all(int(bone.format) == int(YcdTrackFormat.QUATERNION) for bone in rebuilt_rotation_bones)


def test_ycd_bone_id_format_defaults_from_track() -> None:
    rotation_bone = YcdAnimationBoneId(bone_id=0, track=YcdAnimationTrack.BONE_ROTATION)
    translation_bone = YcdAnimationBoneId(bone_id=0, track=YcdAnimationTrack.BONE_TRANSLATION)
    uv_bone = YcdAnimationBoneId(bone_id=0, track=YcdAnimationTrack.SHADER_SLIDE_U)

    assert int(rotation_bone.format) == int(YcdTrackFormat.QUATERNION)
    assert int(translation_bone.format) == int(YcdTrackFormat.VECTOR3)
    assert int(uv_bone.format) == int(get_ycd_track_format(YcdAnimationTrack.SHADER_SLIDE_U))


def test_ycd_writer_sanitizes_non_uv_quantize_overflow() -> None:
    values_z = [0.0, 0.5, 1.0]
    values_w = [-1.0, 0.0, 1.0]
    bone = YcdAnimationBoneId(bone_id=1234, track=YcdAnimationTrack.BONE_ROTATION)
    animation = YcdAnimation(
        hash=MetaHash("quantize_overflow_test"),
        frames=3,
        sequence_frame_limit=3,
        duration=0.1,
        usage_count=1,
        sequence_count=1,
        bone_id_count=1,
        sequences=[
            YcdSequence(
                hash=MetaHash("quantize_overflow_test_seq"),
                data_length=0,
                frame_offset=0,
                root_motion_refs_offset=0,
                num_frames=3,
                frame_length=0,
                indirect_quantize_float_num_ints=0,
                quantize_float_value_bits=0,
                chunk_size=0,
                root_motion_ref_counts=0,
                raw_data=b"",
                anim_sequences=[
                    YcdAnimSequence(
                        bone_id=bone,
                        channels=[
                            YcdStaticFloatChannel(channel_type=YcdChannelType.STATIC_FLOAT, channel_index=0, value=0.0),
                            YcdStaticFloatChannel(channel_type=YcdChannelType.STATIC_FLOAT, channel_index=1, value=0.0),
                            YcdQuantizeFloatChannel(
                                channel_type=YcdChannelType.QUANTIZE_FLOAT,
                                channel_index=2,
                                quantum=1.0 / 65536.0,
                                offset=0.0,
                                values=values_z,
                            ),
                            YcdQuantizeFloatChannel(
                                channel_type=YcdChannelType.QUANTIZE_FLOAT,
                                channel_index=3,
                                quantum=2.0 / 65536.0,
                                offset=-1.0,
                                values=values_w,
                            ),
                        ],
                    )
                ],
            )
        ],
        bone_ids=[bone],
    )

    ycd = Ycd(
        header=read_ycd(YCD_PATH).header,
        clips=[],
        animations=[animation],
        path="quantize_overflow_test.ycd",
    )

    rebuilt = read_ycd(build_ycd_bytes(ycd))
    rebuilt_animation = rebuilt.animations[0]
    rebuilt_sequence = rebuilt_animation.sequences[0]
    rebuilt_quantized = [
        channel
        for channel in rebuilt_sequence.anim_sequences[0].channels
        if isinstance(channel, YcdQuantizeFloatChannel)
    ]

    assert rebuilt_sequence.frame_length <= 8
    assert rebuilt_sequence.quantize_float_value_bits <= 32
    assert all(channel.value_bits <= 16 for channel in rebuilt_quantized)
    assert rebuilt_quantized[0].values == pytest.approx(values_z, abs=1e-5)
    assert rebuilt_quantized[1].values == pytest.approx(values_w, abs=2e-5)
