import math

import pytest

from fivefury import (
    GameTarget,
    Quaternion,
    Vector3,
    YcdAnimationTrack,
    YcdChannelEncoding,
    YcdChannelEncodingPolicy,
    YcdChannelType,
    YcdCutsceneBuilder,
    YcdQuaternionEncoding,
    build_ycd_bytes,
    read_ycd,
)


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize(
    "track",
    [
        YcdAnimationTrack.FACIAL_TRANSLATION,
        YcdAnimationTrack.FACIAL_ROTATION,
        YcdAnimationTrack.FACIAL_SCALE,
    ],
)
@pytest.mark.parametrize("quaternion_encoding", list(YcdQuaternionEncoding))
def test_serialized_facial_codecs_honor_track_policy(game, track, quaternion_encoding):
    raw = YcdChannelEncodingPolicy(YcdChannelEncoding.RAW_FLOAT)
    retail = YcdChannelEncodingPolicy(
        maximum_error=1e-5,
        maximum_angular_error_degrees=0.05,
    )
    rotation = track is YcdAnimationTrack.FACIAL_ROTATION
    samples = [
        Quaternion(0, math.sin(frame / 3000), 0, math.cos(frame / 3000))
        if rotation
        else Vector3(0, 0.02 * frame / 30, 0)
        for frame in range(31)
    ]
    builder = YcdCutsceneBuilder.create(
        "face_codec",
        duration=1,
        game=game,
        channel_policy=raw,
        quaternion_encoding=quaternion_encoding,
    )
    for bone, policy in [(7, retail), (8, raw)]:
        builder.track(
            "actor_dual",
            track=track,
            bone_id=bone,
            samples=samples,
            channel_policy=policy,
        )
    builder.track(
        "actor_dual", track=track, bone_id=9, samples=samples[0], channel_policy=retail
    )
    data = build_ycd_bytes(builder.build_ycds()[0])
    ycd = read_ycd(data)
    clip = ycd.get_clip("actor_dual-0")
    assert clip is not None and clip.animation is not None
    animation = clip.animation
    assert animation.frames == 31
    assert animation.duration == 1
    for bone, codec in [
        (7, YcdChannelType.QUANTIZE_FLOAT),
        (8, YcdChannelType.RAW_FLOAT),
    ]:
        sequence = animation.find_sequences(bone_id=bone, track=track)[0]
        types = {channel.channel_type for channel in sequence.channels}
        assert codec in types
        assert YcdChannelType.STATIC_FLOAT in types
        if rotation and quaternion_encoding is YcdQuaternionEncoding.RETAIL_CACHED:
            assert types & {
                YcdChannelType.CACHED_QUATERNION1,
                YcdChannelType.CACHED_QUATERNION2,
            }
    static = animation.find_sequences(bone_id=9, track=track)[0]
    assert [channel.channel_type for channel in static.channels] == [
        YcdChannelType.STATIC_QUATERNION if rotation else YcdChannelType.STATIC_VECTOR3
    ]
    for frame in range(31):
        value = animation.evaluate_tracks(frame)[(7, int(track))]
        if rotation:
            assert samples[frame].angular_error_degrees(value) <= 0.05
        else:
            assert tuple(value.xyz) == pytest.approx(tuple(samples[frame]), abs=1e-5)
    assert build_ycd_bytes(ycd) == data


def test_facial_retail_error_is_rejected_without_relaxing_requested_bound(tmp_path):
    builder = YcdCutsceneBuilder.create("face_precision", duration=1)
    builder.track(
        "actor_dual",
        track=YcdAnimationTrack.FACIAL_TRANSLATION,
        bone_id=7,
        samples={0.0: Vector3(), 1.0: Vector3(100, 0, 0)},
        channel_policy=YcdChannelEncodingPolicy(maximum_error=1e-8),
    )
    assert "ycd.channel_precision.error_exceeded" in {
        i.code for i in builder.validate().errors
    }
    with pytest.raises(ValueError, match="ycd.channel_precision.error_exceeded"):
        builder.save(tmp_path)
    assert not list(tmp_path.glob("*.ycd"))
