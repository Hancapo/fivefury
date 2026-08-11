from __future__ import annotations

import pytest

from fivefury import (
    Awc,
    AwcChunk,
    AwcChunkType,
    AwcStream,
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
    builder.add_ped(
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

    assert validate_awc_lipsync(empty) == [
        "lip-sync dictionaries require exactly one clip, got 0"
    ]
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
