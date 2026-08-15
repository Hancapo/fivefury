from __future__ import annotations

from types import SimpleNamespace

import pytest

from fivefury import (
    Awc,
    AwcChunk,
    AwcChunkType,
    AwcStream,
    ResolvedCutAudio,
    Ycd,
    YcdCutsceneBuilder,
    YcdFacialTrackSet,
    build_awc_bytes,
    build_ycd_embedded_resource,
    read_awc,
    read_ycd_embedded_resource,
    validate_awc_lipsync,
)
from fivefury.resource import ResourceHeader


def _facial_ycd() -> Ycd:
    builder = YcdCutsceneBuilder.create("speech", duration=0.1, fps=30.0)
    builder.ped(
        "speaker",
        mover_position=(0.0, 0.0, 0.0),
        mover_rotation=(0.0, 0.0, 0.0, 1.0),
        facial=YcdFacialTrackSet(visemes={1: {0.0: 0.0, 0.1: 1.0}}),
    )
    return builder.build_ycds()[0]


def test_embedded_ycd_resource_roundtrip() -> None:
    payload = build_ycd_embedded_resource(_facial_ycd())

    rebuilt = read_ycd_embedded_resource(payload)

    assert payload.startswith(b"RSC7")
    assert len(rebuilt.clips) == 1
    assert rebuilt.clips[0].has_facial_animation


def test_awc_stream_authors_typed_lipsync_chunk() -> None:
    stream = AwcStream("speech_line")

    chunk = stream.set_lipsync(_facial_ycd())
    rebuilt = read_awc(build_awc_bytes(Awc([stream])))

    assert chunk.type is AwcChunkType.LIPSYNC64
    assert rebuilt.streams[0].lipsync is not None
    assert rebuilt.streams[0].lipsync_chunk is not None
    assert rebuilt.streams[0].lipsync_chunk.name == "lipsync64"
    assert rebuilt.streams[0].lipsync.clips[0].has_facial_animation


def test_read_lipsync_payload_is_preserved_until_replaced() -> None:
    stream = AwcStream("speech_line")
    stream.set_lipsync(_facial_ycd())
    original = build_awc_bytes(Awc([stream]))
    parsed = read_awc(original)
    chunk = parsed.streams[0].lipsync_chunk

    assert chunk is not None and chunk.lipsync is not None
    original_payload = chunk.data
    chunk.lipsync.clips[0].name = "local_edit"

    assert chunk.to_payload() == original_payload
    assert build_awc_bytes(parsed) == original


def test_awc_lipsync_validation_rejects_non_runtime_dictionary() -> None:
    empty = Ycd(ResourceHeader(46, 0, 0), [], [])

    report = validate_awc_lipsync(empty)
    assert {issue.code for issue in report.errors} == {"awc.lipsync.clips.count"}
    with pytest.raises(ValueError, match="exactly one clip"):
        AwcStream("speech_line").set_lipsync(empty)


def test_opaque_lipsync_chunk_remains_lossless() -> None:
    original = build_awc_bytes(
        Awc(
            [
                AwcStream(
                    "speech_line",
                    [AwcChunk(AwcChunkType.CUSTOM_LIPSYNC, data=b"opaque")],
                )
            ]
        )
    )
    rebuilt = read_awc(original)
    chunk = rebuilt.streams[0].lipsync_chunk

    assert chunk is not None
    assert chunk.lipsync is None
    assert chunk.lipsync_error is not None
    assert chunk.to_payload() == b"opaque"
    assert build_awc_bytes(rebuilt) == original


def test_resolved_cut_audio_keeps_the_exact_decoded_stream_and_lipsync() -> None:
    unrelated = AwcStream.from_pcm("other_line", b"\x01\x00", sample_rate=1000)
    selected = AwcStream.from_pcm("speech_line", b"\x02\x00", sample_rate=1000)
    selected.set_lipsync(_facial_ycd())
    resolved = ResolvedCutAudio(
        "speech_line",
        SimpleNamespace(id=1, path="speech.awc"),
        SimpleNamespace(parsed=Awc([unrelated, selected])),
    )

    assert resolved.stream is selected
    assert resolved.stream_id == selected.hash
    assert resolved.lipsync is selected.lipsync
    assert resolved.lipsync_chunk is selected.lipsync_chunk
    assert resolved.wav_bytes() == selected.wav_bytes()


def test_resolved_cut_audio_reports_multiple_unmatched_streams_as_ambiguous() -> None:
    first = AwcStream.from_pcm("first", b"\x01\x00", sample_rate=1000)
    second = AwcStream.from_pcm("second", b"\x02\x00", sample_rate=1000)
    resolved = ResolvedCutAudio(
        "missing",
        SimpleNamespace(id=1, path="ambiguous.awc"),
        SimpleNamespace(parsed=Awc([first, second])),
    )

    assert resolved.stream is None
    assert resolved.stream_ambiguity == (first.hash, second.hash)
    with pytest.raises(ValueError, match="ambiguous"):
        resolved.wav_bytes()
