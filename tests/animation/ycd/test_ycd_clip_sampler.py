import pytest

from fivefury import GameTarget, YcdChannelEncoding
from tests.support.ycd import facial_rig_builder


@pytest.mark.parametrize("looped", [False, True])
@pytest.mark.parametrize("rate", [0.5, 1.0, 2.0])
def test_clip_snapshot_matches_existing_timing_and_phase_contract(looped, rate):
    builder, _ = facial_rig_builder(
        GameTarget.GTA5, YcdChannelEncoding.RETAIL, controls=1
    )
    clip = builder.build_ycds()[0].clips[0]
    clip.flags = int(looped)
    clip.rate = rate
    clip.start_time = 2
    clip.end_time = 12
    compiled = clip.compile()
    assert compiled.is_looped == clip.is_looped
    for seconds in (-5, 0, 0.125, 9.55, 9.575, 10, 20, 100):
        assert compiled.get_animation_frame_at_time(
            seconds
        ) == clip.get_animation_frame_at_time(seconds)
        for interpolate in (True, False):
            expected = clip.evaluate_tracks_at_time(seconds, interpolate=interpolate)
            actual = compiled.evaluate_tracks_at_time(seconds, interpolate=interpolate)
            assert actual.keys() == expected.keys()
            for key in actual:
                assert tuple(actual[key]) == pytest.approx(
                    tuple(expected[key]), abs=2e-12
                )
    for phase in (-1, 0, 0.001, 0.5, 1, 2):
        assert compiled.get_animation_frame(phase) == clip.get_animation_frame(phase)
        expected = clip.evaluate_tracks_at_phase(phase)
        actual = compiled.evaluate_tracks_at_phase(phase)
        assert actual.keys() == expected.keys()
        for key in actual:
            assert tuple(actual[key]) == pytest.approx(tuple(expected[key]), abs=2e-12)
    before = compiled.evaluate_tracks_at_time(2.25)
    clip.end_time = 0
    clip.animation = None
    assert compiled.evaluate_tracks_at_time(2.25) == before
    assert clip.compile().evaluate_tracks_at_time(10) == {}


def test_clip_sampler_track_filter_and_stateless_seeks():
    builder, _ = facial_rig_builder(
        GameTarget.GTA5_ENHANCED, YcdChannelEncoding.RETAIL, controls=1
    )
    sampler = builder.build_ycds()[0].clips[0].compile()
    original = sampler.evaluate_tracks_at_time(1.234)
    sampler.evaluate_tracks_at_time(9.78)
    assert sampler.evaluate_tracks_at_time(1.234) == original
    assert sampler.evaluate_tracks_at_time(1, track=999) == {}
    rotations = sampler.evaluate_tracks_at_time(1, track=26)
    assert rotations and all(key[1] == 26 for key in rotations)
