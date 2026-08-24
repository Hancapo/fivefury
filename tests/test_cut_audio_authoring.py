from __future__ import annotations

import pytest

from fivefury import (
    Awc,
    AwcStream,
    CutsceneAudioAssets,
    Dat54SimpleSound,
    Dat54StreamingSound,
    RelSoundIndex,
    build_cutscene_audio_assets,
    read_awc,
    read_rel,
)


def _mono_awc(name: str = "example_seq") -> Awc:
    return Awc([AwcStream.from_pcm(name, b"\x00\x00" * 4800, sample_rate=48000)])


def test_build_cutscene_audio_assets_from_mono_awc() -> None:
    assets = build_cutscene_audio_assets(
        "EXAMPLE_SEQ.WA",
        _mono_awc(),
        wavepack_name="dlc_exam_audio",
    )

    assert assets.reference == "EXAMPLE_SEQ.WA"
    assert assets.awc_name == "example_seq_mastered_only.awc"
    assert assets.sounds_name == "example_seq_sounds.dat"
    assert assets.bank_name == "dlc_exam_audio/example_seq_mastered_only"
    assert assets.sounds.name_table == [assets.bank_name]
    root = assets.sounds.find_item(assets.root_name)
    assert isinstance(root, Dat54StreamingSound)
    assert root.duration == 100
    graph = RelSoundIndex((assets.sounds,)).resolve(assets.root_name)
    assert graph.complete
    assert graph.stream_hashes == (_mono_awc().streams[0].hash,)


def test_multichannel_audio_authors_one_simple_sound_per_channel() -> None:
    awc = Awc.from_channel_pcm(
        "stereo_seq",
        [b"\x00\x00" * 2400, b"\x00\x00" * 2400],
        sample_rate=48000,
    )
    assets = build_cutscene_audio_assets(
        "STEREO_SEQ.WA",
        awc,
        wavepack_name="dlc_ster_audio",
    )
    simple_sounds = [
        item for item in assets.sounds.items if isinstance(item, Dat54SimpleSound)
    ]

    assert len(simple_sounds) == 2
    assert {sound.file_name for sound in simple_sounds} == {
        stream.hash for stream in awc.channel_streams
    }
    root = assets.sounds.find_item(assets.root_name)
    assert isinstance(root, Dat54StreamingSound)
    assert root.duration == 50


@pytest.mark.parametrize(
    "reference",
    (
        "EXAMPLE_SEQ_MASTERED.WA",
        "EXAMPLE_SEQ_MASTERED_ONLY.WA",
        "EXAMPLE_SEQ_EDITED.WA",
        "folder/EXAMPLE_SEQ.WA",
        "EXAMPLE_SEQ.AWC",
    ),
)
def test_invalid_logical_references_are_rejected(reference: str) -> None:
    with pytest.raises(ValueError):
        build_cutscene_audio_assets(
            reference,
            _mono_awc(),
            wavepack_name="dlc_exam_audio",
        )


def test_audio_files_survive_awc_and_rel_round_trip() -> None:
    assets = build_cutscene_audio_assets(
        "EXAMPLE_SEQ.WA",
        _mono_awc(),
        wavepack_name="dlc_exam_audio",
    )
    files = assets.build_files()

    rebuilt_awc = read_awc(files[assets.awc_name])
    rebuilt_rel = read_rel(files[assets.sounds_name])
    assert rebuilt_awc.streams[0].hash == assets.awc.streams[0].hash
    assert rebuilt_rel.name_table == [assets.bank_name]
    assert RelSoundIndex((rebuilt_rel,)).resolve(assets.root_name).complete


def test_validation_rejects_container_and_duration_mismatches() -> None:
    assets = build_cutscene_audio_assets(
        "EXAMPLE_SEQ.WA",
        _mono_awc(),
        wavepack_name="dlc_exam_audio",
    )
    root = assets.sounds.find_item(assets.root_name)
    simple = next(
        item for item in assets.sounds.items if isinstance(item, Dat54SimpleSound)
    )
    assert isinstance(root, Dat54StreamingSound)
    root.duration = 1
    simple.container_name = "wrong_pack/wrong_bank"

    codes = {issue.code for issue in assets.validate()}
    assert "cut.audio.container.unresolved" in codes
    assert "cut.audio.duration.insufficient" in codes


def test_direct_audio_assets_report_missing_awc_streams() -> None:
    valid = build_cutscene_audio_assets(
        "EXAMPLE_SEQ.WA",
        _mono_awc(),
        wavepack_name="dlc_exam_audio",
    )
    broken = CutsceneAudioAssets(
        reference=valid.reference,
        awc=Awc(),
        sounds=valid.sounds,
        awc_name=valid.awc_name,
        sounds_name=valid.sounds_name,
        wavepack_name=valid.wavepack_name,
    )

    assert "cut.audio.stream.unresolved" in {
        issue.code for issue in broken.validate()
    }
