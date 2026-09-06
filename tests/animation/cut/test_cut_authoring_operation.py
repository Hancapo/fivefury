from pathlib import Path
from unittest.mock import patch

import pytest

from fivefury import (
    AuthoringCancelled,
    AuthoringOperation,
    AuthoringStage,
    CutsceneProject,
    GameTarget,
    Quaternion,
    Vector3,
    YcdCutsceneBuilder,
    YcdFacialTrackSet,
)
from fivefury.common import atomic_write_files


def project(game=GameTarget.GTA5):
    result = CutsceneProject.create("operation", duration=2, camera_cuts=[1], game=game)
    ped = result.scene.ped("actor")
    result.animate(
        ped,
        mover_position=Vector3(),
        facial=YcdFacialTrackSet(controls={1: 0.5, 2: 0.25}),
    )
    result.camera(position=Vector3(), rotation=Quaternion())
    return result


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_one_operation_builds_each_section_once_and_preserves_output(game):
    subject = project(game)
    progress = []
    operation = AuthoringOperation(progress.append)
    original = subject.animations._build_section
    with patch.object(subject.animations, "_build_section", wraps=original) as build:
        assets = subject.build(operation=operation)
        files = assets.build_files(operation=operation)
        assert build.call_count == 2
        assert all(
            call.kwargs["operation"] is operation for call in build.call_args_list
        )
    assert {event.stage for event in progress} == set(AuthoringStage)
    assert all(0 <= event.completed <= event.total for event in progress)
    assert files == project(game).build().build_files()


def test_cancel_inside_facial_track_build():
    subject = project()

    def cancel(event):
        if (
            event.stage is AuthoringStage.BUILD
            and event.asset == "actor_dual-0"
            and event.completed == 1
        ):
            operation.cancel()

    operation = AuthoringOperation(cancel)
    with pytest.raises(AuthoringCancelled):
        subject.build(operation=operation)
    assert subject.scene.animation_dictionary.sections == []


@pytest.mark.parametrize("stage", [AuthoringStage.VALIDATE, AuthoringStage.WRITE])
def test_cancel_in_validation_or_serialization_preserves_existing_outputs(
    stage, tmp_path
):
    assets = project().build()
    existing = tmp_path / "operation.cut"
    existing.write_bytes(b"original")

    def cancel(event):
        if event.stage is stage:
            operation.cancel()

    operation = AuthoringOperation(cancel)
    with pytest.raises(AuthoringCancelled):
        assets.save(tmp_path, operation=operation)
    assert existing.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [existing]


def test_cancel_after_staging_first_file_does_not_publish_batch(tmp_path):
    assets = project().build()

    def cancel(event):
        if event.stage is AuthoringStage.WRITE and event.asset == str(
            tmp_path / "operation-1.ycd"
        ):
            operation.cancel()

    operation = AuthoringOperation(cancel)
    with pytest.raises(AuthoringCancelled):
        assets.save(tmp_path, operation=operation)
    assert list(tmp_path.iterdir()) == []


def test_pre_cancelled_operation_does_no_section_work():
    operation = AuthoringOperation()
    operation.cancel()
    with (
        patch.object(
            YcdCutsceneBuilder,
            "_build_section",
            side_effect=AssertionError("unexpected build"),
        ),
        pytest.raises(AuthoringCancelled),
    ):
        project().build(operation=operation)


def test_batch_replace_failure_restores_originals(tmp_path, monkeypatch):
    from fivefury import common

    first, second = tmp_path / "first.cut", tmp_path / "second.ycd"
    first.write_bytes(b"old cut")
    second.write_bytes(b"old ycd")
    replace = common.os.replace

    def fail(source, target):
        if Path(source).name == "new" and Path(target) == second:
            raise OSError("injected replacement failure")
        return replace(source, target)

    monkeypatch.setattr(common.os, "replace", fail)
    with pytest.raises(OSError, match="injected"):
        atomic_write_files({first: b"new cut", second: b"new ycd"})
    assert first.read_bytes() == b"old cut"
    assert second.read_bytes() == b"old ycd"
    assert set(tmp_path.iterdir()) == {first, second}


def test_failed_rollback_retains_recovery_files(tmp_path, monkeypatch):
    from fivefury import common

    target = tmp_path / "asset.cut"
    target.write_bytes(b"original")
    replace = common.os.replace

    def fail(source, destination):
        if Path(destination) == target:
            raise OSError("destination unavailable")
        return replace(source, destination)

    monkeypatch.setattr(common.os, "replace", fail)
    with pytest.raises(OSError, match="unavailable"):
        atomic_write_files({target: b"replacement"})
    backups = list(tmp_path.glob(".asset.cut.*/old"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"original"


def test_cancelled_asset_validation_is_not_a_diagnostic():
    assets = project().build()
    operation = AuthoringOperation()
    operation.cancel()
    with pytest.raises(AuthoringCancelled):
        assets.validate(operation=operation)
