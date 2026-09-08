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
    YcdQuaternionEncoding,
    build_ycd_bytes,
    read_ycd,
)
from fivefury import (
    YcdAnimationTrack as Track,
)


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
@pytest.mark.parametrize("encoding", list(YcdChannelEncoding))
@pytest.mark.parametrize("override", [False, True])
def test_explicit_static_quaternions_keep_w_without_affecting_camera(
    game, encoding, override
):
    explicit = YcdQuaternionEncoding.EXPLICIT
    cached = YcdQuaternionEncoding.RETAIL_CACHED
    builder = YcdCutsceneBuilder.create(
        "static_w",
        duration=1,
        game=game,
        quaternion_encoding=cached if override else explicit,
    )
    value = Quaternion(math.sqrt(1 - 0.0002**2), 0, 0, 0.0002)
    builder.track(
        "actor_dual",
        track=Track.FACIAL_ROTATION,
        bone_id=7,
        samples=value,
        channel_policy=YcdChannelEncodingPolicy(encoding, 1e-5, 0.05),
        quaternion_encoding=explicit if override else None,
    )
    builder.track(
        "camera",
        track=Track.CAMERA_ROTATION,
        samples=Quaternion(),
        quaternion_encoding=cached,
    )
    raw = build_ycd_bytes(builder.build_ycds()[0])
    decoded = read_ycd(raw)
    animation = decoded.get_clip("actor_dual-0").animation
    sequence = animation.sequences[0].anim_sequences[0]
    assert [c.channel_type for c in sequence.channels] == [
        YcdChannelType.STATIC_FLOAT
    ] * 4
    camera = decoded.get_clip("camera-0").animation.sequences[0].anim_sequences[0]
    assert [c.channel_type for c in camera.channels] == [
        YcdChannelType.STATIC_QUATERNION
    ]
    for frame in (0, 0.25, 12.5, 29.75, 30):
        actual = animation.evaluate_tracks(frame)[7, int(Track.FACIAL_ROTATION)]
        assert actual.w == pytest.approx(value.w, abs=1e-8)
        assert actual.angular_error_degrees(value) < 0.001
    reread = read_ycd(build_ycd_bytes(decoded)).get_clip("actor_dual-0").animation
    assert [c.channel_type for c in reread.sequences[0].anim_sequences[0].channels] == [
        YcdChannelType.STATIC_FLOAT
    ] * 4
    assert reread.evaluate_tracks(0)[7, int(Track.FACIAL_ROTATION)].w == pytest.approx(
        value.w, abs=1e-8
    )


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_track_quaternion_override_keeps_frames_and_other_rotation_layouts(game):
    builder = YcdCutsceneBuilder.create("mixed_quaternions", duration=10, game=game)
    rotations = [
        Quaternion(math.sin(i / 10000), 0, 0, math.cos(i / 10000)) for i in range(301)
    ]
    for bone, override in [(1, None), (2, YcdQuaternionEncoding.EXPLICIT)]:
        builder.track(
            "actor_dual",
            track=Track.FACIAL_ROTATION,
            bone_id=bone,
            samples=rotations,
            quaternion_encoding=override,
            channel_policy=YcdChannelEncodingPolicy(
                YcdChannelEncoding.RAW_FLOAT, 1e-5, 0.05
            ),
        )
    decoded = read_ycd(build_ycd_bytes(builder.build_ycds()[0]))
    animation = decoded.animations[0]
    assert animation.frames == 301
    assert [b.num_frames for b in animation.sequences] == [288, 14]
    for block in animation.sequences:
        channels = {
            s.bone_id.bone_id: {c.channel_type for c in s.channels}
            for s in block.anim_sequences
        }
        assert channels[1] & {
            YcdChannelType.CACHED_QUATERNION1,
            YcdChannelType.CACHED_QUATERNION2,
        }
        assert not channels[2] & {
            YcdChannelType.CACHED_QUATERNION1,
            YcdChannelType.CACHED_QUATERNION2,
        }
    for frame in (0, 28.5, 286.25, 286.75, 287, 287.5, 300):
        start = math.floor(frame)
        expected = rotations[start].nlerp(rotations[min(start + 1, 300)], frame - start)
        actual = animation.evaluate_tracks(frame)[2, int(Track.FACIAL_ROTATION)]
        assert expected.angular_error_degrees(actual) < 0.001


def test_quaternion_override_rejects_nonquaternion_tracks_and_untyped_values():
    builder = YcdCutsceneBuilder.create("invalid_encoding", duration=1)
    with pytest.raises(ValueError, match="requires a quaternion track"):
        builder.track(
            "actor",
            track=Track.FACIAL_TRANSLATION,
            samples=Vector3(),
            quaternion_encoding=YcdQuaternionEncoding.EXPLICIT,
        )
    with pytest.raises(TypeError, match="must be a YcdQuaternionEncoding"):
        builder.track(
            "actor",
            track=Track.FACIAL_ROTATION,
            samples=Quaternion(),
            quaternion_encoding="explicit",
        )
