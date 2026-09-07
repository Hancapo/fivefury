import struct
from dataclasses import replace

import pytest

from fivefury import YedFrameDof, YedFrameLayout, YedTrack, YedTrackFormat
from fivefury.hashing import fletcher32


def codes(frame):
    return {issue.code for issue in frame.validate()}


def test_layout_packs_each_format_in_four_value_groups_with_separate_sentinels():
    frame = YedFrameLayout.derive(
        [
            YedTrack.scalar(3, 30),
            YedTrack.quaternion(2, 1),
            YedTrack.vector3(9),
            YedTrack.vector3(4),
            YedTrack.vector3(4, is_input=True),
            YedTrack.scalar(1, 30),
        ]
    )
    assert [(d.track, d.bone_id, d.offset) for d in frame.dofs] == [
        (0, 4, 0),
        (0, 9, 16),
        (1, 2, 64),
        (30, 1, 128),
        (30, 3, 132),
    ]
    assert (frame.buffer_size, frame.read_only_offset, frame.write_only_offset) == (
        176,
        144,
        160,
    )
    assert frame.validate().valid
    assert YedFrameLayout.derive([]).signature == 0xFFFFFFFF
    assert frame.signature == fletcher32(
        struct.pack("<10H", 128, 4, 128, 9, 385, 2, 7810, 1, 7810, 3)
    )


@pytest.mark.parametrize("offset", [1, 8, 24, 0xFFFF])
def test_invalid_vector_offsets_are_reported_without_silently_repairing(offset):
    frame = YedFrameLayout((YedFrameDof(7, 25, YedTrackFormat.VECTOR3, offset),), 96)
    assert "yed.frame.offset.alignment" in codes(frame)
    assert frame.dofs[0].offset == offset
    with pytest.raises(ValueError, match="yed.frame.offset"):
        _ = frame.signature


@pytest.mark.parametrize("size", [0, 16, 33, 65536])
def test_frame_size_reserves_two_distinct_aligned_sentinel_slots(size):
    assert "yed.frame.size" in codes(YedFrameLayout((), size))


def test_overlapping_and_noncanonical_dofs_cannot_share_a_frame_signature():
    frame = YedFrameLayout.derive([YedTrack.vector3(1), YedTrack.vector3(2)])
    overlap = replace(frame, dofs=(frame.dofs[0], replace(frame.dofs[1], offset=0)))
    assert "yed.frame.offset.layout" in codes(overlap)
    assert "yed.frame.dofs.order" in codes(
        replace(frame, dofs=tuple(reversed(frame.dofs)))
    )
    assert "yed.frame.dofs.order" in codes(replace(frame, dofs=(frame.dofs[0],) * 2))
    sentinel = replace(
        frame,
        dofs=(replace(frame.dofs[0], offset=frame.read_only_offset), frame.dofs[1]),
    )
    assert "yed.frame.offset.range" in codes(sentinel)


def test_conflicting_input_and_output_types_do_not_create_two_physical_dofs():
    with pytest.raises(ValueError, match="conflicting formats"):
        YedFrameLayout.derive(
            [YedTrack.vector3(1), YedTrack.quaternion(1, is_input=True)]
        )


def test_largest_aligned_vector_frame_and_uint16_overflow():
    frame = YedFrameLayout.derive(YedTrack.vector3(bone) for bone in range(4092))
    assert frame.buffer_size == 65504
    assert frame.write_only_offset == 65488
    with pytest.raises(ValueError, match="uint16"):
        YedFrameLayout.derive(YedTrack.vector3(bone) for bone in range(4093))


def test_signature_uses_formats_and_bone_ids_but_not_track_direction():
    frame = YedFrameLayout.derive([YedTrack.vector3(1, 25)])
    assert (
        frame.signature
        == YedFrameLayout.derive([YedTrack.vector3(1, 25, is_input=True)]).signature
    )
    assert (
        frame.signature != YedFrameLayout.derive([YedTrack.quaternion(1, 25)]).signature
    )
    assert frame.signature != YedFrameLayout.derive([YedTrack.vector3(2, 25)]).signature


@pytest.mark.parametrize("count", [0, 1, 179, 180, 181, 858, 4092])
def test_fletcher_matches_independent_modular_sum_across_reduction_boundaries(count):
    words = [(index * 31337) & 0xFFFF for index in range(count * 2)]
    sum1 = sum(words) % 65535 or 65535
    sum2 = (
        sum((len(words) - index) * word for index, word in enumerate(words)) % 65535
        or 65535
    )
    assert fletcher32(struct.pack(f"<{len(words)}H", *words)) == (sum2 << 16) | sum1
    with pytest.raises(ValueError, match="uint16"):
        fletcher32(b"\x00")
