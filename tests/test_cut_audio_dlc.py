from __future__ import annotations

import pytest

from fivefury import (
    Awc,
    AwcCodecType,
    AwcStream,
    BuildContext,
    CutsceneProject,
    DlcDataFileType,
    DlcPack,
    GameFileCache,
    GameTarget,
    Quaternion,
    RelExternalNameTable,
    RpfArchive,
    Vector3,
    awc_channel_codecs,
    build_cutscene_audio_assets,
    read_awc,
    read_dlc_content,
    read_rel,
    validate_dlc_sounddata_archive,
)
from fivefury.cut.audio_references import cut_audio_asset_container_hashes
from fivefury.hashing import jenk_hash


def _assets(game: GameTarget = GameTarget.GTA5):
    awc = Awc(
        [
            AwcStream.from_pcm(
                "example_seq",
                b"\x00\x00" * 2000,
                sample_rate=1000,
            )
        ]
    )
    audio = build_cutscene_audio_assets(
        "EXAMPLE_SEQ.WA",
        awc,
        wavepack_name="dlc_exam_audio",
        context=BuildContext(game=game),
    )
    project = CutsceneProject.create("example", duration=1.0, game=game)
    project.camera(position=Vector3(), rotation=Quaternion())
    project.audio(audio)
    return project.build(cut_name="example.cut")


@pytest.mark.parametrize("game", [GameTarget.GTA5, GameTarget.GTA5_ENHANCED])
def test_dlc_cutscene_preserves_target_and_registers_audio(game: GameTarget) -> None:
    pack = DlcPack("example_audio", game=game)
    registration = pack.cutscene(_assets(game))

    rebuilt = RpfArchive.from_bytes(pack.to_bytes(), load_nested=True)
    content_entry = rebuilt.find_entry("content.xml")
    assert content_entry is not None
    content = read_dlc_content(rebuilt.read_entry_bytes(content_entry))
    types = {item.filename: item.file_type for item in content.data_files}

    assert pack.game is game
    assert registration.archive_path == "x64/cutscenes/example.rpf"
    assert types["dlc_example_audio:/%PLATFORM%/audio/example_seq_sounds.dat"] == (
        DlcDataFileType.AUDIO_SOUNDDATA.value
    )
    assert types["dlc_example_audio:/x64/audio/sfx/dlc_exam_audio"] == (
        DlcDataFileType.AUDIO_WAVEPACK.value
    )
    assert not any(
        item.filename.endswith(".awc") and item.file_type == DlcDataFileType.RPF.value
        for item in content.data_files
    )
    for path in (
        "x64/cutscenes/example.rpf/example.cut",
        "x64/audio/example_seq_sounds.dat54",
        "x64/audio/example_seq_sounds.dat54.rel",
        "x64/audio/example_seq_sounds.dat54.nametable",
        "x64/audio/sfx/dlc_exam_audio/example_seq_mastered_only.awc",
    ):
        assert rebuilt.find_entry(path) is not None
    awc_entry = rebuilt.find_entry(
        "x64/audio/sfx/dlc_exam_audio/example_seq_mastered_only.awc"
    )
    assert awc_entry is not None
    rebuilt_awc = read_awc(rebuilt.read_entry_bytes(awc_entry))
    expected_codec = (
        AwcCodecType.MP3
        if game is GameTarget.GTA5_ENHANCED
        else AwcCodecType.PCM
    )
    assert awc_channel_codecs(rebuilt_awc) == (expected_codec,)
    assert not any(
        entry.full_path.casefold().startswith("x64/audio/config/")
        for entry in rebuilt.iter_entries()
    )

    sounddata = registration.sounddata[0]
    release = rebuilt.read_entry_bytes(rebuilt.find_entry(sounddata.release_path))
    names_data = rebuilt.read_entry_bytes(rebuilt.find_entry(sounddata.name_table_path))
    assert read_rel(release).to_bytes() == release
    names = RelExternalNameTable.from_bytes(names_data)
    assert names.to_bytes() == names_data
    assert names.names == sounddata.metadata.name_table.names

    pack.files.clear()
    assert validate_dlc_sounddata_archive(pack, rebuilt).valid
    rebuilt.close()


@pytest.mark.parametrize("payload_index", range(3))
def test_dlc_sounddata_requires_every_physical_payload(payload_index: int) -> None:
    pack = DlcPack("example_audio")
    registration = pack.cutscene(_assets()).sounddata[0]
    archive = pack.to_rpf()
    missing_path = registration.payload_paths[payload_index]
    missing = archive.find_entry(missing_path)
    assert missing is not None and missing.parent is not None
    missing.parent.remove_file(missing)
    rebuilt = RpfArchive.from_bytes(archive.to_bytes(), load_nested=True)

    assert "dlc.sounddata.payload.missing" in {
        issue.code for issue in validate_dlc_sounddata_archive(pack, rebuilt)
    }
    rebuilt.close()


def test_dlc_rejects_legacy_raw_sounddata_layout() -> None:
    pack = DlcPack("bobei")
    old_path = "x64/audio/config/bobei_sounds.dat"
    pack.file(old_path, b"legacy raw payload")
    pack.content.file(pack.path(old_path), DlcDataFileType.AUDIO_SOUNDDATA)

    assert {
        "dlc.sounddata.unresolved",
        "dlc.sounddata.layout.legacy_raw",
    }.issubset(issue.code for issue in pack.validate())


def test_dlc_cutscene_validation_detects_missing_audio_mounts() -> None:
    pack = DlcPack("example_audio")
    registration = pack.cutscene(_assets())
    pack.content.data_files = [
        item
        for item in pack.content.data_files
        if item.filename not in registration.wavepack_registrations
    ]

    assert "cut.audio.wavepack.unregistered" in {
        issue.code for issue in pack.validate()
    }


def test_audio_container_hash_uses_the_wavepack_relative_bank_path() -> None:
    class Asset:
        stem = "example_seq_mastered_only"
        path = "dlc.rpf/x64/audio/sfx/dlc_exam_audio/example_seq_mastered_only.awc"

    class RetailAsset:
        stem = "pro_mcs_5_seq_mastered_only"
        path = "x64/audio/sfx/prologue.rpf/pro_mcs_5_seq_mastered_only.awc"

    assert cut_audio_asset_container_hashes(Asset()) == (
        jenk_hash("dlc_exam_audio/example_seq_mastered_only"),
    )
    assert cut_audio_asset_container_hashes(RetailAsset()) == (0x91ECFC6A,)


def test_generated_dlc_resolves_cut_audio_through_rel_bank_path(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = DlcPack("example_audio", game=GameTarget.GTA5)
    pack.cutscene(_assets())
    pack.save_dlc_rpf(tmp_path / "example_audio" / "dlc.rpf")
    monkeypatch.setattr(
        "fivefury.cut.resolution.audio.cut_audio_hint_names",
        lambda _hints: (),
    )

    with GameFileCache(
        tmp_path,
        game=GameTarget.GTA5,
        load_vehicles=False,
        load_peds=False,
        use_index_cache=False,
    ) as cache:
        cache.scan(load_keys=False)
        bundle = cache.resolve_cutscene("example.cut")

    assert not bundle.issues
    resolved = bundle.audio["EXAMPLE_SEQ.WA"]
    assert resolved.sound_hashes
    assert resolved.stream_hashes
    assert resolved.asset.path.endswith("example_seq_mastered_only.awc")
