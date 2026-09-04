import pytest

from fivefury import Awc, AwcStream, ValidationError, read_awc
from fivefury.awc.structures import AwcFormat, AwcStreamFormat


@pytest.mark.parametrize("rate", (32000, 44100, 48000, 65535))
def test_awc_preserves_representable_pcm_frequency(rate):
    awc = Awc(streams=[AwcStream.from_pcm("sample", bytes(64), sample_rate=rate)])
    assert read_awc(awc.to_bytes()).streams[0].sample_rate == rate


@pytest.mark.parametrize("multichannel", (False, True))
def test_awc_rejects_96khz_before_replacing_destination(tmp_path, multichannel):
    awc = (Awc.from_channel_pcm("sample", [bytes(64), bytes(64)], sample_rate=96000)
           if multichannel else Awc(streams=[AwcStream.from_pcm("sample", bytes(64), sample_rate=96000)]))
    assert any(issue.path.endswith("sample_rate") for issue in awc.validate().errors)
    target = tmp_path / "audio.awc"
    target.write_bytes(b"existing")
    with pytest.raises(ValidationError, match="uint16"):
        awc.save(target)
    assert target.read_bytes() == b"existing"


@pytest.mark.parametrize("kind,field,value", (
    (AwcFormat, "samples", 2**32), (AwcFormat, "play_begin", 256),
    (AwcFormat, "loop_end", -1), (AwcFormat, "peak", 2**32),
    (AwcStreamFormat, "unused1", 256), (AwcStreamFormat, "sample_rate", 96000),
))
def test_awc_format_rejects_packed_overflow(kind, field, value):
    fmt = kind()
    setattr(fmt, field, value)
    with pytest.raises(ValidationError, match=field):
        fmt.to_bytes()
