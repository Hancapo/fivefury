from __future__ import annotations

from types import SimpleNamespace

import pytest

from fivefury import (
    Awc,
    AwcChunk,
    AwcChunkType,
    AwcFormat,
    AwcStream,
    CutScene,
    Dat54MultitrackSound,
    Dat54SimpleSound,
    MetaHash,
    RelDatFileType,
    RelFile,
    RelSoundIndex,
)
from fivefury.cut.audio_references import (
    cut_audio_container_hints,
    cut_audio_references,
    cut_audio_sound_hashes,
)
from fivefury.cut.resolution.audio import _resolve_audio
from fivefury.gamefile import GameFileType


def _asset(asset_id: int, path: str) -> SimpleNamespace:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return SimpleNamespace(
        id=asset_id,
        path=path,
        stem=name.rsplit(".", 1)[0],
        kind=GameFileType.AWC,
    )


def _awc(stream: str | int) -> Awc:
    return Awc(
        [
            AwcStream(
                stream,
                [
                    AwcChunk(
                        AwcChunkType.FORMAT,
                        format=AwcFormat(samples=2, sample_rate=48000),
                    ),
                    AwcChunk(AwcChunkType.DATA, data=b"\0\0\0\0"),
                ],
            )
        ]
    )


def test_audio_container_hint_comes_from_the_target_audio_object() -> None:
    scene = CutScene.create(duration=2.0)
    audio = scene.audio("SUM23_CM1_INT.WA", object_id=3)
    reference = MetaHash("opaque_audio_event").uint
    scene.load_audio(0.0, str(reference), target=audio)

    assert cut_audio_references(scene) == ("SUM23_CM1_INT.WA",)
    assert cut_audio_container_hints(scene, ("SUM23_CM1_INT.WA",)) == {
        "SUM23_CM1_INT.WA": ("sum23_cm1_int",)
    }


def test_audio_resolution_uses_container_hint_and_source_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = MetaHash("opaque_audio_event").uint
    base = _asset(
        1,
        "x64/audio/sfx/base.rpf/sum23_cm1_int_mastered.awc",
    )
    update = _asset(
        2,
        "update/x64/dlcpacks/test/dlc.rpf/x64/audio/sfx/sum23_cm1_int_mastered.awc",
    )
    parsed = _awc("sum23_cm1_int")
    loaded = {
        base.id: SimpleNamespace(parsed=parsed),
        update.id: SimpleNamespace(parsed=parsed),
    }

    class Cache:
        @staticmethod
        def iter_assets(kind):
            assert kind is GameFileType.AWC
            return iter((base, update))

    monkeypatch.setattr(
        "fivefury.cut.resolution.audio._load_file",
        lambda _cache, asset, _issues: loaded[asset.id],
    )
    issues = []

    resolved = _resolve_audio(
        Cache(),
        (reference,),
        issues,
        container_hints={reference: ("sum23_cm1_int",)},
    )

    assert not issues
    assert resolved[reference].asset is update
    assert resolved[reference].container_reference == "sum23_cm1_int"


def test_audio_resolution_prefers_rel_sound_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = "scene_track"
    sound_hash = cut_audio_sound_hashes(reference)[0]
    container_hash = MetaHash("scene_bank").uint
    stream_hash = MetaHash("scene_voice").uint
    asset = _asset(1, "x64/audio/sfx/scene_bank.awc")
    parsed = _awc(stream_hash)
    sound_index = RelSoundIndex(
        [
            RelFile(
                RelDatFileType.DAT54_DATA_ENTRIES,
                items=[
                    Dat54SimpleSound(
                        name_hash=sound_hash,
                        container_name=container_hash,
                        file_name=stream_hash,
                    )
                ],
            )
        ]
    )

    class Cache:
        rel_sound_index_errors = ()

        @staticmethod
        def ensure_rel_sound_index():
            return sound_index

        @staticmethod
        def iter_assets(kind):
            assert kind is GameFileType.AWC
            return iter((asset,))

    monkeypatch.setattr(
        "fivefury.cut.resolution.audio._load_file",
        lambda _cache, _asset, _issues: SimpleNamespace(parsed=parsed),
    )
    issues = []

    resolved = _resolve_audio(Cache(), (reference,), issues)

    assert not issues
    assert resolved[reference].sound_hashes == (sound_hash,)
    assert resolved[reference].stream_hashes == (stream_hash,)
    assert resolved[reference].stream_id == (stream_hash & 0x1FFFFFFF)
    assert resolved[reference].sample_rate == 48000
    assert resolved[reference].channel_count == 1


def test_rel_bank_reference_does_not_have_to_match_awc_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fivefury import AwcStreamFormat, AwcStreamFormatChunk

    reference = "scene_track"
    root_hash = cut_audio_sound_hashes(reference)[0]
    left_hash = MetaHash("scene_track_left").uint
    right_hash = MetaHash("scene_track_right").uint
    bank_reference = 0x91ECFC6A
    asset = _asset(1, "x64/audio/sfx/scene_track_mastered_only.awc")
    source = AwcStream(
        "scene_track",
        [
            AwcChunk(
                AwcChunkType.STREAM_FORMAT,
                stream_format=AwcStreamFormatChunk(
                    1,
                    2048,
                    [
                        AwcStreamFormat(
                            id=left_hash,
                            samples=16,
                            sample_rate=48000,
                        ),
                        AwcStreamFormat(
                            id=right_hash,
                            samples=16,
                            sample_rate=48000,
                        ),
                    ],
                ),
            ),
            AwcChunk(AwcChunkType.DATA, data=b"audio"),
        ],
    )
    parsed = Awc(
        [source, AwcStream(left_hash), AwcStream(right_hash)],
        flags=4,
    )
    sound_index = RelSoundIndex(
        [
            RelFile(
                RelDatFileType.DAT54_DATA_ENTRIES,
                items=[
                    Dat54MultitrackSound(
                        name_hash=root_hash,
                        child_sounds=[left_hash, right_hash],
                    ),
                    Dat54SimpleSound(
                        name_hash=left_hash,
                        container_name=bank_reference,
                        file_name=left_hash,
                    ),
                    Dat54SimpleSound(
                        name_hash=right_hash,
                        container_name=bank_reference,
                        file_name=right_hash,
                    ),
                ],
            )
        ]
    )

    class Cache:
        @staticmethod
        def ensure_rel_sound_index():
            return sound_index

        @staticmethod
        def iter_assets(kind):
            assert kind is GameFileType.AWC
            return iter((asset,))

    monkeypatch.setattr(
        "fivefury.cut.resolution.audio._load_file",
        lambda _cache, _asset, _issues: SimpleNamespace(parsed=parsed),
    )
    issues = []

    resolved = _resolve_audio(
        Cache(),
        (reference,),
        issues,
        container_hints={reference: (reference,)},
    )

    assert not issues
    assert resolved[reference].asset is asset
    assert resolved[reference].stream is source
    assert resolved[reference].stream_hashes == (left_hash, right_hash)
    assert resolved[reference].channel_count == 2


def test_strict_cut_validation_rejects_play_before_load() -> None:
    scene = CutScene.create(duration=2.0)
    audio = scene.audio("scene_track.wa")
    scene.play_audio(0.0, audio, "scene_track")

    codes = {issue.code for issue in scene.validation_report(strict=True)}

    assert "play_audio.not_loaded" in codes
