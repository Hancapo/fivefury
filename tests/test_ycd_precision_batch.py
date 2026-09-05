from __future__ import annotations

import math

import numpy as np
import pytest

from fivefury import (
    AuthoringCancelled,
    AuthoringOperation,
    AuthoringStage,
    GameTarget,
    Quaternion,
    Vector3,
    YcdAnimation,
    YcdAnimationTrack,
    YcdChannelEncoding,
    YcdChannelEncodingPolicy,
    YcdCutsceneBuilder,
    build_ycd_bytes,
    read_ycd,
)
from fivefury._native import _ffi
from fivefury.ycd import write
from fivefury.ycd.sequence_channels import YcdAnimSequence
from tests.test_ycd_cached_subframes import PAIRS, packed_channels


@pytest.mark.parametrize("layout", [-2, -1, 0, 1, 2, 3])
def test_native_precision_matches_scalar_runtime_at_all_samples(layout):
    rng = np.random.default_rng(183)
    packed = rng.uniform(-0.45, 0.45, (27, 4))
    expected = rng.uniform(-1, 1, (27, 4))
    expected /= np.linalg.norm(expected, axis=1)[:, None]
    samples = packed.copy()
    if layout >= 0:
        samples = np.column_stack(
            [
                packed[:, component]
                if component < layout
                else np.zeros(27)
                if component == layout
                else packed[:, component - 1]
                for component in range(4)
            ]
        )
    sequence = YcdAnimSequence(
        channels=packed_channels(samples, layout if layout >= 0 else -1),
        is_cached_quaternion=layout != -1,
    )
    if layout == -1:
        sequence.channels.pop()
    component_error = angular_error = subframe_error = worst = 0.0
    for frame in range(27):
        reference = Quaternion(*expected[frame])
        actual = sequence.evaluate_quaternion(frame)
        component_error = max(
            component_error,
            min(
                max(abs(a - b) for a, b in zip(reference, actual, strict=True)),
                max(abs(a + b) for a, b in zip(reference, actual, strict=True)),
            ),
        )
        angular_error = max(angular_error, reference.angular_error_degrees(actual))
        if frame == 26:
            continue
        for alpha in (0.25, 0.5, 0.75):
            target = reference.nlerp(Quaternion(*expected[frame + 1]), alpha)
            evaluated = (
                actual.nlerp(sequence.evaluate_quaternion(frame + 1), alpha)
                if layout == -1
                else sequence.evaluate_quaternion(frame + alpha)
            )
            error = target.angular_error_degrees(evaluated)
            if error > subframe_error:
                subframe_error, worst = error, frame + alpha
    result = _ffi.ycd_compare_samples(expected, packed, 4, layout, 27, True)
    assert result == pytest.approx(
        (component_error, angular_error, subframe_error, worst), abs=1e-10
    )


@pytest.mark.parametrize("dimensions", [1, 3])
def test_native_precision_scalar_vector_contract(dimensions):
    reference = np.zeros((13, 4))
    packed = np.zeros_like(reference)
    packed[4, dimensions - 1] = 0.125
    assert _ffi.ycd_compare_samples(reference, packed, dimensions, -1, 13, False) == (
        0.125,
        0,
        0,
        0,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        (bytes(31), bytes(32), 4, -2, 1, True),
        (bytes(32), bytes(32), 4, -3, 1, True),
        (bytes(32), bytes(32), 3, 1, 1, True),
        (bytes(32), bytes(32), 4, -2, 2, True),
    ],
)
def test_native_precision_rejects_invalid_buffers(kwargs):
    with pytest.raises(ValueError):
        _ffi.ycd_compare_samples(*kwargs)


def builder(game=GameTarget.GTA5):
    result = YcdCutsceneBuilder.create(
        "batch",
        duration=20,
        camera_cuts=[10],
        game=game,
        channel_policy=YcdChannelEncodingPolicy(
            encoding=YcdChannelEncoding.RAW_FLOAT,
            maximum_error=1e-3,
            maximum_angular_error_degrees=0.05,
        ),
    )
    result.prop(
        "actor",
        mover_rotation=[
            Quaternion(0, 0, math.sin(frame / 50), math.cos(frame / 50))
            for frame in range(601)
        ],
    )
    return result


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_build_encodes_each_section_once_without_scalar_sampling(monkeypatch, game):
    asset = builder(game)
    count = 0
    original = asset._build_section

    def counted(index):
        nonlocal count
        count += 1
        return original(index)

    monkeypatch.setattr(asset, "_build_section", counted)
    monkeypatch.setattr(
        YcdAnimation,
        "evaluate_tracks",
        lambda *a, **kw: pytest.fail("Scalar sampler on validation path"),
    )
    assert len(asset.build_ycds()) == count == 2


def test_sequence_encoding_is_reused_only_within_one_write(monkeypatch):
    asset = builder().build_ycds()[0]
    count = 0
    original = write.build_sequence_data

    def counted(sequence):
        nonlocal count
        count += 1
        return original(sequence)

    monkeypatch.setattr(write, "build_sequence_data", counted)
    expected = sum(len(animation.sequences) for animation in asset.animations)
    data = build_ycd_bytes(asset)
    assert count == expected
    build_ycd_bytes(asset)
    assert count == expected * 2
    assert build_ycd_bytes(read_ycd(data)) == data


def test_independent_builds_observe_mutation():
    asset = builder()
    before = build_ycd_bytes(asset.build_ycds()[0])
    asset.prop("actor", mover_position=Vector3(12, 3, 4))
    after = build_ycd_bytes(asset.build_ycds()[0])
    assert before != after
    rebuilt = read_ycd(after).animations[0]
    assert rebuilt.evaluate_tracks(0)[
        (0, int(YcdAnimationTrack.MOVER_TRANSLATION))
    ].xyz == Vector3(12, 3, 4)


def test_save_reuses_validated_bytes_without_another_write(monkeypatch, tmp_path):
    asset = builder()
    original = write.build_ycd_bytes
    calls = 0

    def counted(ycd, **kwargs):
        nonlocal calls
        calls += 1
        return original(ycd, **kwargs)

    from fivefury.ycd import channel_validation

    monkeypatch.setattr(channel_validation, "build_ycd_bytes", counted)
    monkeypatch.setattr(write, "build_ycd_bytes", counted)
    paths = asset.save(tmp_path)
    assert len(paths) == calls == 2
    assert all(read_ycd(path.read_bytes()).animations for path in paths)


def test_progress_and_cancellation_during_validation_preserve_outputs(tmp_path):
    progress = []

    def record(value):
        progress.append(value)
        if value.stage is AuthoringStage.VALIDATE and value.completed == 1:
            operation.cancel()

    operation = AuthoringOperation(record)
    with pytest.raises(AuthoringCancelled):
        builder().save(tmp_path, operation=operation)
    assert not list(tmp_path.glob("*.ycd"))
    assert any(value.stage is AuthoringStage.VALIDATE for value in progress)


def test_cancelled_operation_does_not_start_encoding(monkeypatch):
    asset = builder()
    operation = AuthoringOperation()
    operation.cancel()
    monkeypatch.setattr(
        asset,
        "_build_section",
        lambda *args: pytest.fail("Encoding after cancellation"),
    )
    with pytest.raises(AuthoringCancelled):
        asset.build_ycds(operation=operation)


def test_successful_progress_reaches_completion():
    progress = []
    builder().build_ycds(operation=AuthoringOperation(progress.append))
    assert progress[-1].stage is AuthoringStage.BUILD
    assert progress[-1].completed == progress[-1].total == 2
    validation = [value for value in progress if value.stage is AuthoringStage.VALIDATE]
    assert validation[-1].completed == validation[-1].total


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_validation_checks_corruption_in_physical_sequence_overlap(monkeypatch, game):
    omitted, left, right = PAIRS[0]
    samples = [Quaternion(*(left if frame < 287 else right)) for frame in range(301)]
    asset = YcdCutsceneBuilder.create(
        "overlap",
        duration=10,
        game=game,
        channel_policy=YcdChannelEncodingPolicy(
            encoding=YcdChannelEncoding.RAW_FLOAT,
            maximum_error=1e-3,
            maximum_angular_error_degrees=0.05,
        ),
    )
    asset.prop("actor", mover_rotation=samples)
    original = asset._build_section

    def corrupted(index):
        ycd = original(index)
        sequence = ycd.animations[0].sequences[0].anim_sequences[0]
        sequence.channels = packed_channels([left] * 287 + [right], omitted)
        return ycd

    monkeypatch.setattr(asset, "_build_section", corrupted)
    report = asset.validate()
    issue = next(
        issue
        for issue in report.issues
        if issue.code == "ycd.channel_precision.subframe_angular_error_exceeded"
    )
    assert issue.path.endswith(".frames[286.5]")
    assert not any(
        issue.code == "ycd.channel_precision.angular_error_exceeded"
        for issue in report.issues
    )
