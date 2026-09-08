import copy
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from fivefury import (
    GameTarget,
    Quaternion,
    Vector4,
    YcdAnimationTrack,
    YcdChannelEncoding,
    build_ycd_bytes,
    read_ycd,
)
from fivefury.ycd.sequence_channels import (
    YcdAnimSequence,
    YcdChannelType,
    YcdIndirectQuantizeFloatChannel,
    YcdLinearFloatChannel,
    YcdQuantizeFloatChannel,
    YcdRawFloatChannel,
)
from tests.animation.ycd.samples import PAIRS, packed_channels
from tests.support.ycd import facial_rig_builder


def assert_tracks(actual, expected):
    assert actual.keys() == expected.keys()
    for key in expected:
        assert type(actual[key]) is type(expected[key])
        assert tuple(actual[key]) == pytest.approx(tuple(expected[key]), abs=2e-12)


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_native_plan_matches_mutable_sampling_and_owns_its_snapshot(game, monkeypatch):
    builder, _ = facial_rig_builder(game, YcdChannelEncoding.RETAIL, controls=4)
    animation = read_ycd(build_ycd_bytes(builder.build_ycds()[0])).animations[0]
    original = copy.deepcopy(animation)
    sampler = animation.compile()
    assert sampler.sample_bytes > 0
    times = [
        -3,
        -0.25,
        0,
        0.0,
        0.125,
        16.99,
        286.25,
        286.75,
        287,
        287.5,
        300,
        300.5,
        9999,
    ]
    for track in (None, YcdAnimationTrack.FACIAL_ROTATION, 999):
        for interpolate in (True, False):
            for frame in times:
                assert_tracks(
                    sampler.evaluate_tracks(
                        frame, track=track, interpolate=interpolate
                    ),
                    original.evaluate_tracks(
                        frame, track=track, interpolate=interpolate
                    ),
                )
    animation.sequences.clear()
    assert sampler.evaluate_tracks(0)
    assert animation.compile().evaluate_tracks(0) == {}
    del animation
    monkeypatch.setattr(
        YcdAnimSequence,
        "evaluate_quaternion",
        lambda *a: pytest.fail("Python sequence sampling"),
    )
    monkeypatch.setattr(
        YcdAnimSequence,
        "evaluate_vector4",
        lambda *a: pytest.fail("Python sequence sampling"),
    )
    with ThreadPoolExecutor(4) as pool:
        actual = list(pool.map(sampler.evaluate_tracks, times * 3))
    assert all(actual)


@pytest.mark.parametrize("layout,left,right", PAIRS)
def test_cached_reconstruction_runs_after_interpolation_in_native_plan(
    layout, left, right
):
    builder, _ = facial_rig_builder(
        GameTarget.GTA5, YcdChannelEncoding.RAW_FLOAT, controls=1
    )
    animation = builder.build_ycds()[0].animations[0]
    sequence = next(
        s for s in animation.sequences[0].anim_sequences if s.is_rotation_track
    )
    sequence.channels = packed_channels((left, right), layout)
    sequence.is_cached_quaternion = True
    sampler = animation.compile()
    for time in (0, 0.25, 0.5, 0.75, 1, 2.25):
        assert_tracks(sampler.evaluate_tracks(time), animation.evaluate_tracks(time))


@pytest.mark.parametrize(
    "channel",
    [
        YcdRawFloatChannel(YcdChannelType.RAW_FLOAT, values=[2, 3, 4]),
        YcdQuantizeFloatChannel(YcdChannelType.QUANTIZE_FLOAT, offset=7),
        YcdLinearFloatChannel(YcdChannelType.LINEAR_FLOAT, values=[0.1, 0.2]),
        YcdIndirectQuantizeFloatChannel(
            YcdChannelType.INDIRECT_QUANTIZE_FLOAT,
            offset=9,
            values=[1, 2],
            frames=[1, 99, 0, -1],
        ),
    ],
)
def test_decoded_channel_cycles_missing_components_and_keys(channel):
    builder, _ = facial_rig_builder(
        GameTarget.GTA5, YcdChannelEncoding.RAW_FLOAT, controls=1
    )
    animation = builder.build_ycds()[0].animations[0]
    seq = animation.sequences[0].anim_sequences[0]
    seq.channels = [copy.deepcopy(channel)]
    seq.is_cached_quaternion = False
    animation.sequences[0].anim_sequences = [seq]
    last = copy.deepcopy(seq)
    last.bone_id.bone_id += 100
    animation.sequences[1].anim_sequences = [last]
    sampler = animation.compile()
    for frame in (0, 1, 2, 3, 20.7, 286.5, 287, 300, 2000):
        assert_tracks(sampler.evaluate_tracks(frame), animation.evaluate_tracks(frame))


def test_native_sampling_constructs_only_final_public_values(monkeypatch):
    builder, _ = facial_rig_builder(
        GameTarget.GTA5, YcdChannelEncoding.RETAIL, controls=2
    )
    animation = builder.build_ycds()[0].animations[0]
    sampler = animation.compile()
    calls = []
    for cls in (Vector4, Quaternion):
        original = cls.__post_init__

        def counted(self, original=original):
            calls.append(type(self))
            original(self)

        monkeypatch.setattr(cls, "__post_init__", counted)
    result = sampler.evaluate_tracks(18.25)
    assert len(calls) == len(result)
    for frame in (float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite"):
            sampler.evaluate_tracks(frame)


def test_edits_to_channel_arrays_and_ids_require_explicit_recompile():
    builder, _ = facial_rig_builder(
        GameTarget.GTA5, YcdChannelEncoding.RAW_FLOAT, controls=1
    )
    animation = builder.build_ycds()[0].animations[0]
    seq = animation.sequences[0].anim_sequences[0]
    seq.channels = [
        YcdRawFloatChannel(YcdChannelType.RAW_FLOAT, values=np.arange(3, dtype=float))
    ]
    sampler = animation.compile()
    before = sampler.evaluate_tracks(0)
    seq.channels[0].values[0] = 999
    seq.bone_id.bone_id = 456
    assert sampler.evaluate_tracks(0) == before
    assert animation.compile().evaluate_tracks(0) != before
