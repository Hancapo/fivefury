from __future__ import annotations

import math

import pytest

from fivefury import (
    GameTarget,
    Quaternion,
    YcdAnimationTrack,
    YcdChannelType,
    YcdCutsceneBuilder,
    build_ycd_bytes,
    read_ycd,
)
from fivefury.ycd.sequence_channels import (
    YcdCachedQuaternionChannel,
    YcdRawFloatChannel,
)


PAIRS = (
    (
        3,
        (
            0.7500555515289307,
            -0.18713344633579254,
            -0.6336289048194885,
            0.030201885046735766,
        ),
        (
            -0.7221301198005676,
            0.2660178244113922,
            0.6377001404762268,
            0.03318339959751179,
        ),
    ),
    (
        1,
        (
            0.6469215154647827,
            0.013298065472475832,
            0.689765989780426,
            0.32486703991889954,
        ),
        (
            -0.6486276984214783,
            0.04947353642910962,
            -0.6504743695259094,
            -0.3920683264732361,
        ),
    ),
)
GAMES = (GameTarget.GTA5, GameTarget.GTA5_ENHANCED)
TRACK = (0, int(YcdAnimationTrack.MOVER_ROTATION))


def packed_channels(samples, omitted):
    components = [index for index in range(4) if index != omitted]
    return [
        *(
            YcdRawFloatChannel(
                channel_type=YcdChannelType.RAW_FLOAT,
                channel_index=slot,
                values=[value[index] for value in samples],
            )
            for slot, index in enumerate(components)
        ),
        YcdCachedQuaternionChannel(
            channel_type=(
                YcdChannelType.CACHED_QUATERNION1
                if omitted >= 0
                else YcdChannelType.CACHED_QUATERNION2
            ),
            channel_index=len(components),
            quat_index=max(omitted, 0),
        ),
    ]


def runtime_rotation(samples, omitted, alpha):
    # Independent stream-order oracle, not the public sampler's math helper.
    values = [a + (b - a) * alpha for a, b in zip(*samples, strict=True)]
    if omitted >= 0:
        values[omitted] = math.sqrt(
            max(1.0 - sum(v * v for i, v in enumerate(values) if i != omitted), 0.0)
        )
    else:
        length = math.sqrt(sum(v * v for v in values))
        values = [v / length for v in values]
    return Quaternion.from_iterable(values)


@pytest.mark.parametrize("game", GAMES)
@pytest.mark.parametrize("omitted,left,right", PAIRS)
@pytest.mark.parametrize("alpha", (0.25, 0.5, 0.75))
def test_serialized_cached_flip_is_not_hidden_by_sampler(
    game, omitted, left, right, alpha
):
    builder = YcdCutsceneBuilder.create("subframe", duration=1 / 30, game=game)
    builder.prop("actor", mover_rotation=[Quaternion(*left), Quaternion(*right)])
    ycd = builder.build_ycds()[0]
    sequence = ycd.animations[0].find_sequences(track=YcdAnimationTrack.MOVER_ROTATION)[
        0
    ]
    sequence.channels = packed_channels((left, right), omitted)
    animation = read_ycd(build_ycd_bytes(ycd)).animations[0]
    actual = animation.evaluate_tracks(alpha)[TRACK]
    assert actual.components == pytest.approx(
        runtime_rotation((left, right), omitted, alpha).components, abs=2e-6
    )
    if alpha == 0.5:
        assert (
            actual.angular_error_degrees(
                Quaternion(*left).nlerp(Quaternion(*right), alpha)
            )
            > 177
        )


@pytest.mark.parametrize("game", GAMES)
@pytest.mark.parametrize("alpha", (0.0, 0.25, 0.5, 0.75, 1.0))
def test_normalization_opcode_runs_after_scalar_interpolation(game, alpha):
    samples = ((0.2, 0.3, 0.4, 0.5), (0.7, 0.1, 0.3, 0.2))
    builder = YcdCutsceneBuilder.create("normalize", duration=1 / 30, game=game)
    builder.prop("actor", mover_rotation=[Quaternion(*sample) for sample in samples])
    ycd = builder.build_ycds()[0]
    sequence = ycd.animations[0].find_sequences(track=YcdAnimationTrack.MOVER_ROTATION)[
        0
    ]
    sequence.channels = packed_channels(samples, -1)
    data = build_ycd_bytes(ycd)
    decoded = read_ycd(data)
    actual = decoded.animations[0].evaluate_tracks(alpha)[TRACK]
    assert actual.components == pytest.approx(
        runtime_rotation(samples, -1, alpha).components, abs=2e-7
    )
    assert build_ycd_bytes(decoded) == data


@pytest.mark.parametrize("game", GAMES)
@pytest.mark.parametrize("_omitted,left,right", PAIRS)
def test_export_repairs_fixture_orientations_at_subframes(game, _omitted, left, right):
    builder = YcdCutsceneBuilder.create("repaired", duration=1 / 30, game=game)
    builder.prop("actor", mover_rotation=[Quaternion(*left), Quaternion(*right)])
    animation = read_ycd(build_ycd_bytes(builder.build_ycds()[0])).animations[0]
    for alpha in (0, 0.25, 0.5, 0.75, 1):
        expected = Quaternion(*left).nlerp(Quaternion(*right), alpha)
        assert (
            expected.angular_error_degrees(animation.evaluate_tracks(alpha)[TRACK])
            < 0.01
        )


@pytest.mark.parametrize("game", GAMES)
def test_full_turns_use_native_normalization_with_continuous_overlap(game):
    samples = [
        Quaternion(
            math.sin(angle) / math.sqrt(3),
            math.sin(angle) / math.sqrt(3),
            math.sin(angle) / math.sqrt(3),
            math.cos(angle),
        )
        for angle in ((frame + 0.37) * math.pi / 60 for frame in range(600))
    ]
    # Arbitrary source signs must not leak into any serialized scalar interval.
    signed = [
        sample if frame % 2 else Quaternion(*(-v for v in sample))
        for frame, sample in enumerate(samples)
    ]
    builder = YcdCutsceneBuilder.create("loops", duration=599 / 30, game=game)
    builder.prop("actor", mover_rotation=signed)
    data = build_ycd_bytes(builder.build_ycds()[0])
    decoded = read_ycd(data)
    animation = decoded.animations[0]
    assert len(animation.sequences) == 3
    for block in animation.sequences[:2]:
        assert block.root_rotation_ref_count == 5
        assert any(ref.raw_bytes[0] == 8 for ref in block.root_rotation_refs)
    for frame in range(599):
        for alpha in (0.0, 0.25, 0.5, 0.75):
            actual = animation.evaluate_tracks(frame + alpha)[TRACK]
            expected = samples[frame].nlerp(samples[frame + 1], alpha)
            assert actual.angular_error_degrees(expected) < 0.01, (frame, alpha)
    assert build_ycd_bytes(decoded) == data


@pytest.mark.parametrize("game", GAMES)
def test_small_finger_rotations_keep_compact_reconstruction(game):
    samples = [
        Quaternion(math.sin(frame / 10000), 0, 0, math.cos(frame / 10000))
        for frame in range(31)
    ]
    builder = YcdCutsceneBuilder.create("finger", duration=1, game=game)
    builder.prop("actor", mover_rotation=samples)
    animation = read_ycd(build_ycd_bytes(builder.build_ycds()[0])).animations[0]
    assert animation.sequences[0].root_rotation_ref_count == 4
    for frame in range(30):
        for alpha in (0.25, 0.5, 0.75):
            expected = samples[frame].nlerp(samples[frame + 1], alpha)
            assert (
                expected.angular_error_degrees(
                    animation.evaluate_tracks(frame + alpha)[TRACK]
                )
                < 0.001
            )
