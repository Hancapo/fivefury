from __future__ import annotations

import pytest

from fivefury import (
    Awc,
    AwcCodecType,
    AwcSpeaker,
    AwcStream,
    BuildContext,
    CutAudioCodec,
    CutsceneAudioAssets,
    CutsceneProject,
    Dat54SimpleSound,
    Dat54StreamingSound,
    DecodedAudio,
    DlcPack,
    GameTarget,
    RelSoundIndex,
    awc_channel_codecs,
    build_cutscene_audio_assets,
    read_awc,
    read_rel,
)


def _awc(channel_count: int) -> Awc:
    channels = [bytes([index + 1, 0]) * 32 for index in range(channel_count)]
    if channel_count == 1:
        return Awc([AwcStream.from_pcm("voice", channels[0], sample_rate=48000)])
    return Awc.from_channel_pcm("voice", channels, sample_rate=48000)


def _assets(channel_count: int, game: GameTarget = GameTarget.GTA5_ENHANCED):
    return build_cutscene_audio_assets(
        "SCENE.WA",
        _awc(channel_count),
        wavepack_name="scene_audio",
        context=BuildContext(game=game),
    )


def _root(assets) -> Dat54StreamingSound:
    return next(
        item for item in assets.sounds.items if isinstance(item, Dat54StreamingSound)
    )


def _children(assets) -> list[Dat54SimpleSound]:
    return [item for item in assets.sounds.items if isinstance(item, Dat54SimpleSound)]


def test_cut_audio_streaming_root_uses_retail_header() -> None:
    root = _root(_assets(2))

    assert root.header.flags == 0x0080A001
    assert root.header.flags2 == 0xAA91AAAA
    assert root.header.release_time == 300
    assert root.header.category == 0x7F01B626


@pytest.mark.parametrize(
    ("channel_count", "expected"),
    [
        (1, [(0x00800000, 0, 4)]),
        (2, [(0x00800040, 307, 0), (0x00800040, 53, 0)]),
        (
            3,
            [
                (0x00800000, 0, 4),
                (0x00800040, 307, 0),
                (0x00800040, 53, 0),
            ],
        ),
        (
            5,
            [
                (0x00800000, 0, 4),
                (0x00800000, 0, 1),
                (0x00800000, 0, 16),
                (0x00800000, 0, 2),
                (0x00800000, 0, 32),
            ],
        ),
    ],
)
def test_cut_audio_channel_routing(channel_count: int, expected) -> None:
    children = _children(_assets(channel_count))

    assert [
        (child.header.flags, child.header.pan, child.header.speaker_mask)
        for child in children
    ] == expected


def test_enhanced_and_legacy_awc_profiles_remain_distinct() -> None:
    enhanced = _assets(2, GameTarget.GTA5_ENHANCED)
    legacy = _assets(2, GameTarget.GTA5)

    assert enhanced.awc.flags == 0xFF0C
    assert legacy.awc.flags == 0xFF05
    assert awc_channel_codecs(enhanced.awc) == (AwcCodecType.MP3,) * 2
    assert awc_channel_codecs(legacy.awc) == (AwcCodecType.PCM,) * 2


def test_cut_audio_binary_round_trip_preserves_graph_and_pcm() -> None:
    assets = _assets(3)
    original_pcm = assets.awc.pcm_bytes()
    files = assets.build_files()
    rebuilt_awc = read_awc(files[assets.awc_name])
    sounddata = assets.build_sounddata()
    rebuilt_rel = read_rel(files[sounddata.release_name])

    assert rebuilt_awc.flags == assets.awc.flags
    assert rebuilt_awc.pcm_bytes() == original_pcm
    assert rebuilt_rel.to_bytes() == files[sounddata.release_name]


def test_cut_audio_validation_rejects_generic_headers() -> None:
    assets = _assets(2)
    _root(assets).header.flags = 0xAAAAAAAA
    _children(assets)[0].header.flags = 0xAAAAAAAA

    codes = {issue.code for issue in assets.validate()}

    assert "cut.audio.header.streaming.invalid" in codes
    assert "cut.audio.routing.invalid" in codes


@pytest.mark.parametrize("channel_count", (1, 2, 3, 5))
def test_enhanced_retail_audio_is_authored_as_mp3(channel_count: int) -> None:
    assets = _assets(channel_count)

    assert awc_channel_codecs(assets.awc) == (AwcCodecType.MP3,) * channel_count
    assert not assets.validate().errors


def test_enhanced_retail_validation_rejects_analysis_pcm() -> None:
    assets = build_cutscene_audio_assets(
        "SCENE.WA",
        _awc(2),
        wavepack_name="scene_audio",
        context=BuildContext(game=GameTarget.GTA5_ENHANCED),
        codec=CutAudioCodec.ANALYSIS_PCM,
    )
    assert awc_channel_codecs(assets.awc) == (AwcCodecType.PCM,) * 2
    assert not assets.validate().errors

    assets.codec = CutAudioCodec.RETAIL
    issue = next(
        issue
        for issue in assets.validate().errors
        if issue.code == "cut.audio.codec.uncompressed"
    )

    assert "preview decoding can work" in issue.message


def test_enhanced_retail_accepts_decoded_pcm_and_resamples_to_48000_hz() -> None:
    source = DecodedAudio(
        pcm=b"\x00\x00\x01\x00" * 1_000,
        sample_rate=1_000,
        channels=2,
    )

    assets = build_cutscene_audio_assets(
        "SCENE.WA",
        source,
        wavepack_name="scene_audio",
        context=BuildContext(game=GameTarget.GTA5_ENHANCED),
    )
    layout = assets.awc.streams[0].stream_format_chunk

    assert layout is not None
    assert [channel.sample_rate for channel in layout.channels] == [48_000, 48_000]
    assert [channel.codec for channel in layout.channels] == [
        AwcCodecType.MP3,
        AwcCodecType.MP3,
    ]


@pytest.mark.parametrize("channel_count", (1, 3))
def test_awc_channel_codecs_cover_single_and_multichannel_audio(
    channel_count: int,
) -> None:
    assert (
        awc_channel_codecs(_awc(channel_count)) == (AwcCodecType.PCM,) * channel_count
    )


def test_awc_validation_rejects_incompatible_encryption_flags() -> None:
    awc = _awc(1)
    awc.multi_channel_encrypt_flag = True

    assert "awc.flags.multichannel_encryption.invalid" in {
        issue.code for issue in awc.validate().errors
    }

    awc = _awc(2)
    awc.single_channel_encrypt_flag = True

    assert "awc.flags.encryption_mode.invalid" in {
        issue.code for issue in awc.validate().errors
    }


def test_enhanced_cut_audio_survives_final_dlc_round_trip() -> None:
    assets = build_cutscene_audio_assets(
        "SCENE.WA",
        Awc(
            [
                AwcStream.from_pcm(
                    "voice",
                    b"\x00\x00" * 48_000,
                    sample_rate=48_000,
                )
            ]
        ),
        wavepack_name="scene_audio",
        context=BuildContext(game=GameTarget.GTA5_ENHANCED),
    )
    project = CutsceneProject.create(
        "scene",
        duration=1.0,
        game=GameTarget.GTA5_ENHANCED,
    )
    project.camera()
    project.audio(assets, stop=1.0)
    pack = DlcPack("scene_pack", game=GameTarget.GTA5_ENHANCED)
    pack.cutscene(project.build(cut_name="scene.cut"))

    assert pack.to_bytes(game=GameTarget.GTA5_ENHANCED)


def test_explicit_cut_audio_layout_must_match_awc() -> None:
    with pytest.raises(ValueError, match="layout must match"):
        build_cutscene_audio_assets(
            "SCENE.WA",
            _awc(2),
            wavepack_name="scene_audio",
            context=BuildContext(game=GameTarget.GTA5_ENHANCED),
            channels=(AwcSpeaker.FRONT_CENTER,),
        )


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
            _awc(1),
            wavepack_name="scene_audio",
            context=BuildContext(),
        )


def test_multichannel_sound_graph_preserves_awc_channel_hashes() -> None:
    assets = _assets(2)
    graph = RelSoundIndex((assets.sounds,)).resolve(assets.root_name)

    assert graph.complete
    assert set(graph.stream_hashes) == {
        stream.hash for stream in assets.awc.channel_streams
    }


def test_validation_rejects_container_and_duration_mismatches() -> None:
    assets = _assets(1)
    root = _root(assets)
    simple = _children(assets)[0]
    root.duration = 0
    simple.container_name = "wrong_pack/wrong_bank"

    codes = {issue.code for issue in assets.validate()}

    assert "cut.audio.container.unresolved" in codes
    assert "cut.audio.duration.insufficient" in codes


def test_direct_audio_assets_report_missing_awc_streams() -> None:
    valid = _assets(1)
    broken = CutsceneAudioAssets(
        reference=valid.reference,
        awc=Awc(),
        sounds=valid.sounds,
        awc_name=valid.awc_name,
        sounds_name=valid.sounds_name,
        wavepack_name=valid.wavepack_name,
        game=valid.game,
    )

    assert "cut.audio.stream.unresolved" in {issue.code for issue in broken.validate()}
