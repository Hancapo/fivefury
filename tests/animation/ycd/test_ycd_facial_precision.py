import math

import pytest

from fivefury import (
    GameTarget,
    Quaternion,
    Vector3,
    YcdChannelEncoding,
    YcdChannelEncodingPolicy,
    YcdChannelType,
    YcdCutsceneBuilder,
    build_ycd_bytes,
    read_ycd,
)
from fivefury import (
    YcdAnimationTrack as Track,
)
from fivefury.ycd.sequence_channels import YcdRawFloatChannel
from tests.animation.ycd.samples import PAIRS, packed_channels
from tests.support.ycd import facial_rig_builder


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize("encoding", list(YcdChannelEncoding))
def test_static_quaternion_precision_identifies_integer_loss(game, encoding):
    builder = YcdCutsceneBuilder.create("static_precision", duration=1, game=game)
    builder.track(
        "actor_dual",
        track=Track.FACIAL_ROTATION,
        bone_id=7,
        samples=Quaternion(math.sqrt(1 - 0.0002**2), 0, 0, 0.0002),
        channel_policy=YcdChannelEncodingPolicy(encoding, 1e-5, 0.05),
    )
    report = builder.validate()
    integer = next(
        i for i in report.errors if i.code == "ycd.channel_precision.error_exceeded"
    )
    assert "integer component" in integer.message
    assert "; angular error" in integer.message
    assert integer.path.endswith(".frames[0]")
    assert any(
        i.code == "ycd.channel_precision.subframe_error_exceeded" for i in report.errors
    )
    assert not any("angular_error_exceeded" in i.code for i in report.errors)


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_dense_facial_rig_preserves_motion_and_reduces_serialized_size(game):
    compressed, sources = facial_rig_builder(game, YcdChannelEncoding.RETAIL)
    raw, _ = facial_rig_builder(game, YcdChannelEncoding.RAW_FLOAT)
    compressed_data = [build_ycd_bytes(ycd) for ycd in compressed.build_ycds()]
    raw_data = [build_ycd_bytes(ycd) for ycd in raw.build_ycds()]
    assert len(compressed_data) == len(raw_data) == 2
    assert sum(map(len, compressed_data)) < sum(map(len, raw_data))
    facial = {
        int(Track.FACIAL_TRANSLATION),
        int(Track.FACIAL_ROTATION),
        int(Track.FACIAL_SCALE),
    }
    for index, (encoded, reference) in enumerate(
        zip(compressed_data, raw_data, strict=True)
    ):
        decoded = read_ycd(encoded)
        animation = decoded.get_clip(f"actor_dual-{index}").animation
        raw_animation = read_ycd(reference).get_clip(f"actor_dual-{index}").animation
        assert decoded.game == game
        assert animation.bone_ids == raw_animation.bone_ids
        assert animation.duration == raw_animation.duration == 10
        assert animation.frames == raw_animation.frames == 301
        assert [s.num_frames for s in animation.sequences] == [288, 14]
        assert sum(s.data_length for s in animation.sequences) < sum(
            s.data_length for s in raw_animation.sequences
        )
        for block, raw_block in zip(
            animation.sequences, raw_animation.sequences, strict=True
        ):
            assert block.num_frames == raw_block.num_frames
            assert block.root_motion_ref_counts == raw_block.root_motion_ref_counts
            for seq in block.anim_sequences:
                types = {c.channel_type for c in seq.channels}
                track = int(seq.bone_id.track)
                assert (
                    YcdChannelType.QUANTIZE_FLOAT
                    if track in facial
                    else YcdChannelType.RAW_FLOAT
                ) in types
                if track in facial:
                    assert YcdChannelType.RAW_FLOAT not in types
                if track == int(Track.FACIAL_ROTATION):
                    assert types & {
                        YcdChannelType.CACHED_QUATERNION1,
                        YcdChannelType.CACHED_QUATERNION2,
                    }
        for frame in [*range(0, 300, 19), 285, 286, 287, 288, 298, 299, 300]:
            for alpha in (0,) if frame == 300 else (0, 0.25, 0.5, 0.75):
                actual = animation.evaluate_tracks(frame + alpha)
                for key, samples in sources.items():
                    position = index * 300 + frame
                    left, right = samples[position], samples[min(position + 1, 600)]
                    value = actual[key]
                    if isinstance(left, Quaternion):
                        expected = left.nlerp(right, alpha)
                        assert expected.angular_error_degrees(value) <= 0.05
                        assert (
                            min(
                                max(
                                    abs(a - b)
                                    for a, b in zip(expected, value, strict=True)
                                ),
                                max(
                                    abs(a + b)
                                    for a, b in zip(expected, value, strict=True)
                                ),
                            )
                            <= 1e-5
                        )
                    elif isinstance(left, Vector3):
                        tolerance = 1e-5 if key[1] in facial else 2e-5
                        assert tuple(value.xyz) == pytest.approx(
                            tuple(left.lerp(right, alpha)), abs=tolerance
                        )
                    else:
                        assert value.x == pytest.approx(
                            left + (right - left) * alpha, abs=2e-5
                        )


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize(
    "track", [Track.FACIAL_TRANSLATION, Track.FACIAL_SCALE, Track.CAMERA_FIELD_OF_VIEW]
)
def test_component_precision_checks_physical_overlap_before_save(
    monkeypatch, tmp_path, game, track
):
    builder = YcdCutsceneBuilder.create("component_overlap", duration=10, game=game)
    samples = [float(frame) / 300 for frame in range(301)]
    if track != Track.CAMERA_FIELD_OF_VIEW:
        samples = [Vector3(value, 0, 0) for value in samples]
    builder.track(
        "actor_dual",
        track=track,
        bone_id=7,
        samples=samples,
        channel_policy=YcdChannelEncodingPolicy(YcdChannelEncoding.RAW_FLOAT, 1e-5),
    )
    original = builder._build_section

    def corrupted(index, *, operation=None):
        ycd = original(index, operation=operation)
        sequence = ycd.animations[0].sequences[0].anim_sequences[0]
        channel = sequence.channels[0]
        assert isinstance(channel, YcdRawFloatChannel)
        values = list(channel.values)
        values[-1] += 1
        channel.values = values
        return ycd

    monkeypatch.setattr(builder, "_build_section", corrupted)
    with pytest.raises(
        ValueError, match="ycd.channel_precision.subframe_error_exceeded"
    ):
        builder.save(tmp_path)
    assert not list(tmp_path.glob("*.ycd"))


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_quaternion_component_bound_does_not_require_an_angular_bound(
    monkeypatch, game
):
    omitted, left, right = PAIRS[0]
    builder = YcdCutsceneBuilder.create("component_only", duration=1 / 30, game=game)
    builder.track(
        "actor_dual",
        track=Track.FACIAL_ROTATION,
        bone_id=7,
        samples=[Quaternion(*left), Quaternion(*right)],
        channel_policy=YcdChannelEncodingPolicy(
            YcdChannelEncoding.RETAIL, maximum_error=1e-3
        ),
    )
    assert builder.validate().valid
    original = builder._build_section

    def corrupted(index, *, operation=None):
        ycd = original(index, operation=operation)
        sequence = ycd.animations[0].sequences[0].anim_sequences[0]
        sequence.channels = packed_channels((left, right), omitted)
        return ycd

    monkeypatch.setattr(builder, "_build_section", corrupted)
    with pytest.raises(
        ValueError, match="ycd.channel_precision.subframe_error_exceeded"
    ):
        builder.build_ycds()
