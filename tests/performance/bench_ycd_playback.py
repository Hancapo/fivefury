import pytest

from fivefury import GameTarget, YcdChannelEncoding, build_ycd_bytes, read_ycd
from tests.support.ycd import facial_rig_builder

pytestmark = pytest.mark.performance


@pytest.fixture
def playback_animation():
    builder, _ = facial_rig_builder(GameTarget.GTA5_ENHANCED, YcdChannelEncoding.RETAIL)
    return read_ycd(build_ycd_bytes(builder.build_ycds()[0])).animations[0]


def test_mutable_ycd_playback(benchmark, playback_animation):
    assert benchmark(playback_animation.evaluate_tracks, 123.37)


def test_compiled_ycd_playback(benchmark, playback_animation):
    sampler = playback_animation.compile()
    assert benchmark(sampler.evaluate_tracks, 123.37)
