import pytest

from fivefury import Awc, AwcChunk, AwcChunkType, AwcCodecType, AwcStream, read_awc


def test_rejected_export_is_atomic(tmp_path):
    awc = Awc.from_channel_mp3("probe", [bytes(9600)] * 2)
    owner = awc.streams[0]
    owner.chunks.remove(owner.seek_table_chunk)
    path = tmp_path / "audio.awc"
    path.write_bytes(b"original")
    with pytest.raises(ValueError, match="seek_table.missing"):
        awc.save(path)
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("missing", [AwcChunkType.DATA, AwcChunkType.FORMAT])
def test_partial_stream_cannot_escape_playback_selection(missing):
    stream = AwcStream.from_pcm("mono", bytes(200), sample_rate=48000)
    stream.chunks = [chunk for chunk in stream.chunks if chunk.type != missing]
    with pytest.raises(ValueError, match="missing"):
        Awc([stream]).to_bytes()


def test_unknown_codec_original_is_preserved_only_unchanged():
    awc = Awc([AwcStream.from_pcm("mono", bytes(200), sample_rate=48000)])
    raw = bytearray(awc.to_bytes())
    fmt = next(c for c in awc.streams[0].chunks if c.type == AwcChunkType.FORMAT)
    raw[fmt.info.offset + 19] = AwcCodecType.VORBIS
    original = read_awc(raw)
    assert not original.validate().valid
    assert original.to_bytes() == bytes(raw)
    original.streams[0].format_chunk.samples += 1
    with pytest.raises(ValueError, match="codec.unsupported"):
        original.to_bytes()


def test_unknown_codec_authoring_is_not_certified():
    awc = Awc([AwcStream.from_pcm("mono", bytes(200), sample_rate=48000)])
    awc.streams[0].format_chunk.codec = AwcCodecType.VORBIS
    with pytest.raises(ValueError, match="codec.unsupported"):
        awc.to_bytes()


def test_duplicate_data_chunks_are_rejected():
    stream = AwcStream.from_pcm("mono", bytes(200), sample_rate=48000)
    stream.chunks.append(AwcChunk(AwcChunkType.DATA, data=bytes(200)))
    with pytest.raises(ValueError, match="chunk.duplicate"):
        Awc([stream]).to_bytes()
