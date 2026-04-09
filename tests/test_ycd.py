from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import (
    MetaHash,
    YcdClipAnimation,
    YcdClipPropertyAttributeType,
    YcdSequence,
    read_ycd,
)


TESTS_DIR = Path(__file__).resolve().parent
YCD_PATH = TESTS_DIR / "maude_mcs_1-0.ycd"


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
