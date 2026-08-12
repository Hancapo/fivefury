from __future__ import annotations

import io
import os
import struct
import wave
from pathlib import Path

import pytest

from fivefury import (
    Awc,
    AwcChunk,
    AwcChunkType,
    AwcCodecType,
    AwcFormat,
    AwcStream,
    AwcStreamFormat,
    AwcStreamFormatChunk,
    DecodedAudio,
    GameFileCache,
    GameFileType,
    build_awc_bytes,
    read_awc,
)

_ENHANCED_ROOT_VALUE = os.environ.get("FIVEFURY_GTA5_ENHANCED_PATH")
_ENHANCED_ROOT = Path(_ENHANCED_ROOT_VALUE) if _ENHANCED_ROOT_VALUE else None


def test_enhanced_mp3_codec_is_decoded_to_pcm(monkeypatch) -> None:
    stream = AwcStream(
        1,
        [
            AwcChunk(
                AwcChunkType.FORMAT,
                format=AwcFormat(samples=3, sample_rate=48000, codec=AwcCodecType.MP3),
            ),
            AwcChunk(AwcChunkType.DATA, data=b"encoded-mp3"),
        ],
    )
    calls = []

    def decode(source, **kwargs):
        calls.append((source, kwargs))
        return DecodedAudio(b"\x01\x00\x02\x00\x03\x00", 48000, 1)

    monkeypatch.setattr("fivefury.awc.conversion.decode_audio", decode)

    assert stream.pcm_bytes() == b"\x01\x00\x02\x00\x03\x00"
    assert calls == [
        (
            b"encoded-mp3",
            {"sample_rate": 48000, "channels": 1, "source_format": ".mp3"},
        )
    ]


def test_enhanced_multichannel_block_uses_encoded_size_and_sample_count(
    monkeypatch,
) -> None:
    encoded = b"mp3data"
    header = struct.pack("<6i", -1, 1, 0, 3, 0, len(encoded))
    offsets = struct.pack("<i", 0)
    data = header + offsets
    data += b"\x00" * ((-len(data)) % 0x800)
    data += encoded + b"padding"
    channel = AwcStreamFormat(
        id=2,
        samples=3,
        sample_rate=48000,
        codec=AwcCodecType.MP3,
    )
    source = AwcStream(
        0,
        [
            AwcChunk(
                AwcChunkType.STREAM_FORMAT,
                stream_format=AwcStreamFormatChunk(
                    block_count=1,
                    block_size=len(data),
                    channels=[channel],
                ),
            ),
            AwcChunk(AwcChunkType.DATA, data=data),
        ],
    )
    awc = Awc([source, AwcStream(2, stream_format=channel)], flags=4)

    def decode(payload, **_kwargs):
        assert payload == encoded
        return DecodedAudio(b"\x01\x00\x02\x00\x03\x00\x04\x00", 48000, 1)

    monkeypatch.setattr("fivefury.awc.conversion.decode_audio", decode)

    assert awc.pcm_bytes() == b"\x01\x00\x02\x00\x03\x00"


@pytest.mark.skipif(
    _ENHANCED_ROOT is None or not _ENHANCED_ROOT.is_dir(),
    reason="set FIVEFURY_GTA5_ENHANCED_PATH to run the retail AWC regression",
)
def test_retail_compact_multichannel_awc_decodes_to_aligned_pcm() -> None:
    assert _ENHANCED_ROOT is not None
    with GameFileCache(
        _ENHANCED_ROOT,
        load_audio=True,
        load_peds=False,
        load_vehicles=False,
        use_index_cache=True,
    ) as cache:
        cache.scan_game(gen9=True)
        bundle = cache.resolve_cutscene("pro_mcs_3_pt1.cut")

        resolved = next(
            audio
            for audio in bundle.audio.values()
            if "pro_mcs_3_pt1_mastered_only" in audio.asset.path.casefold()
        )
        wav = resolved.wav_bytes()

    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    with wave.open(io.BytesIO(wav), "rb") as decoded:
        assert decoded.getcomptype() == "NONE"
        assert decoded.getnchannels() == 3
        assert decoded.getsampwidth() == 2
        assert decoded.getframerate() == 48000
        assert decoded.getnframes() == 1277248
        assert decoded.getnframes() / decoded.getframerate() == pytest.approx(
            26.609333333333332,
            abs=1 / decoded.getframerate(),
        )
    assert (len(wav) - 44) % (3 * 2) == 0


@pytest.mark.skipif(
    _ENHANCED_ROOT is None or not _ENHANCED_ROOT.is_dir(),
    reason="set FIVEFURY_GTA5_ENHANCED_PATH to run the retail AWC regression",
)
def test_retail_encrypted_cut_audio_loads_through_the_cache() -> None:
    assert _ENHANCED_ROOT is not None
    paths = (
        "x64/audio/sfx/prologue.rpf/pro_mcs_1_mastered_only.awc",
        "x64/audio/sfx/prologue.rpf/pro_mcs_5_seq_mastered_only.awc",
        "update/x64/dlcpacks/mpsecurity/dlc.rpf/x64/audio/sfx/dlc_security/fix_pro_mcs1_mastered.awc",
    )
    expected_cues = (
        ("pro_mcs_5.cut", 0xA3BCA9C3, "pro_mcs_5_seq_mastered_only.awc"),
        ("fix_pro_mcs1.cut", 0x3C66E70A, "fix_pro_mcs1_mastered.awc"),
    )

    with GameFileCache(
        _ENHANCED_ROOT,
        load_audio=True,
        load_peds=False,
        load_vehicles=False,
        use_index_cache=True,
    ) as cache:
        cache.scan_game(gen9=True)
        for path in paths:
            asset = cache.find_path(path, kind=GameFileType.AWC)
            assert asset is not None
            assert isinstance(cache.load_asset(asset).parsed, Awc)

        for cut_name, cue_hash, awc_name in expected_cues:
            bundle = cache.resolve_cutscene(cut_name)
            resolved = bundle.audio[cue_hash]
            assert resolved.asset.name == awc_name
            wav = resolved.wav_bytes()
            assert wav[:4] == b"RIFF"
            assert wav[8:12] == b"WAVE"
            assert not any(
                issue.code in {"audio.container_invalid", "audio.container_unresolved"}
                for issue in bundle.issues
            )


def test_enhanced_mp3_seek_table_preserves_uint16_entries() -> None:
    stream = AwcStream(
        1,
        [
            AwcChunk(
                AwcChunkType.FORMAT,
                format=AwcFormat(
                    samples=3,
                    sample_rate=48000,
                    codec=AwcCodecType.MP3,
                ),
            ),
            AwcChunk(
                AwcChunkType.SEEK_TABLE,
                seek_table=[0, 2, 4],
                seek_table_entry_size=2,
            ),
            AwcChunk(AwcChunkType.DATA, data=b"mp3"),
        ],
    )

    rebuilt = read_awc(build_awc_bytes(Awc([stream])))
    seek = rebuilt.streams[0].chunks[1]

    assert seek.seek_table_entry_size == 2
    assert seek.seek_table == [0, 2, 4]
    assert seek.to_payload() == struct.pack("<3H", 0, 2, 4)


def test_multichannel_encryption_is_applied_per_large_block() -> None:
    left = struct.pack("<6h", -1000, -500, 0, 500, 1000, 1500)
    right = struct.pack("<6h", 1500, 1000, 500, 0, -500, -1000)
    awc = Awc.from_channel_pcm("encrypted_stereo", [left, right], sample_rate=32000)
    awc.multi_channel_encrypt_flag = True

    encoded = build_awc_bytes(awc)
    rebuilt = read_awc(encoded)

    assert rebuilt.multi_channel_encrypt_flag
    assert rebuilt.pcm_bytes() == Awc.from_channel_pcm(
        "encrypted_stereo", [left, right], sample_rate=32000
    ).pcm_bytes()
