from __future__ import annotations

import pytest

from fivefury import Awc, AwcStream, CutScene, CutsceneAssets, CutsceneProject
from fivefury.cut import build_cutscene_audio_assets


def _audio(duration: float = 2.0):
    sample_rate = 1000
    awc = Awc(
        [
            AwcStream.from_pcm(
                "example_seq",
                b"\x00\x00" * round(duration * sample_rate),
                sample_rate=sample_rate,
            )
        ]
    )
    return build_cutscene_audio_assets(
        "EXAMPLE_SEQ.WA",
        awc,
        wavepack_name="dlc_exam_audio",
    )


def _project() -> CutsceneProject:
    project = CutsceneProject.create("example", duration=1.0)
    project.camera()
    return project


def test_project_audio_authors_binding_and_runtime_events() -> None:
    project = _project()
    audio = _audio()

    binding = project.audio(audio, offset=0.25)
    assets = project.build(cut_name="example.cut")

    assert binding.name == "EXAMPLE_SEQ.WA"
    assert binding.offset == 0.25
    assert assets.audio == (audio,)
    events = [
        (event.event_name, event.start, event.target_id)
        for event in project.scene.timeline
        if event.target_id == binding.object_id
    ]
    assert events == [
        ("load_audio", 0.0, binding.object_id),
        ("play_audio", 0.0, binding.object_id),
        ("stop_audio", 1.0, binding.object_id),
    ]
    assert assets.validate().valid


def test_cutscene_assets_build_cut_rel_and_awc_together() -> None:
    project = _project()
    project.audio(_audio())

    files = project.build(cut_name="example.cut").build_files()

    assert set(files) == {
        "example.cut",
        "example_seq_sounds.dat",
        "example_seq_mastered_only.awc",
    }


def test_project_audio_rejects_range_past_master() -> None:
    project = _project()

    with pytest.raises(ValueError, match="exceed"):
        project.audio(_audio(1.0), offset=0.1)


def test_assets_report_unowned_and_unused_audio_references() -> None:
    scene = CutScene.create(scene_name="example", duration=1.0)
    binding = scene.audio("MISSING_SEQ.WA", fields={"fOffset": 0.0})
    scene.load_audio(0.0, "MISSING_SEQ.WA", target=binding)
    scene.play_audio(0.0, binding, "MISSING_SEQ.WA")
    scene.stop_audio(1.0, binding, "MISSING_SEQ.WA")

    missing_codes = {
        issue.code for issue in CutsceneAssets(scene, audio=(_audio(),)).validate()
    }
    unused_codes = {
        issue.code
        for issue in CutsceneAssets(
            CutScene.create(scene_name="empty", duration=1.0),
            audio=(_audio(),),
        ).validate()
    }
    assert "cut.audio.sound.unresolved" in missing_codes
    assert "cut.audio.reference.unused" in unused_codes


def test_assets_report_duplicate_audio_output_names() -> None:
    project = _project()
    first = _audio()
    project.audio(first)
    second = build_cutscene_audio_assets(
        "OTHER_SEQ.WA",
        _audio().awc,
        wavepack_name="dlc_exam_audio",
        awc_name=first.awc_name,
    )
    second_binding = project.scene.audio(second.reference, fields={"fOffset": 0.0})
    project.scene.load_audio(0.0, second.reference, target=second_binding)
    project.scene.play_audio(0.0, second_binding, second.reference)
    project.scene.stop_audio(1.0, second_binding, second.reference)

    assets = project.build()
    assets.audio = (*assets.audio, second)
    assert "cut.audio.name.duplicate" in {
        issue.code for issue in assets.validate()
    }


def test_cutscene_without_audio_keeps_the_existing_file_set() -> None:
    files = _project().build(cut_name="silent.cut").build_files()

    assert set(files) == {"silent.cut"}
