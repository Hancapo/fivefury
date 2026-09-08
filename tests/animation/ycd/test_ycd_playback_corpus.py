import os
from pathlib import Path

import pytest

from fivefury import YcdClipAnimation, read_ycd


@pytest.mark.integration("FIVEFURY_TEST_YCD_PLAYBACK_CORPUS")
def test_compiled_playback_matches_external_clip_corpus():
    paths = sorted(Path(os.environ["FIVEFURY_TEST_YCD_PLAYBACK_CORPUS"]).rglob("*.ycd"))
    assert paths
    for path in paths:
        ycd = read_ycd(path)
        for clip in ycd.clips:
            if not isinstance(clip, YcdClipAnimation):
                continue
            sampler = clip.compile()
            frames = {0, 1, clip.get_animation_frame(1)}
            if clip.animation:
                frames.update(
                    boundary + delta
                    for boundary in range(
                        max(clip.animation.sequence_frame_limit, 1),
                        clip.animation.frames,
                        max(clip.animation.sequence_frame_limit, 1),
                    )
                    for delta in (-0.75, -0.5, -0.25, 0, 0.25)
                )
                for frame in frames:
                    expected = clip.animation.evaluate_tracks(frame)
                    actual = sampler.animation.evaluate_tracks(frame)
                    assert actual.keys() == expected.keys()
                    for key in expected:
                        assert type(actual[key]) is type(expected[key])
                        assert tuple(actual[key]) == pytest.approx(
                            tuple(expected[key]), abs=2e-12
                        )
            for seconds in (
                -1,
                0,
                0.017,
                clip.duration / 2,
                clip.duration,
                clip.duration + 1,
            ):
                expected = clip.evaluate_tracks_at_time(seconds)
                actual = sampler.evaluate_tracks_at_time(seconds)
                assert actual.keys() == expected.keys()
                for key in expected:
                    assert tuple(actual[key]) == pytest.approx(
                        tuple(expected[key]), abs=2e-12
                    )
