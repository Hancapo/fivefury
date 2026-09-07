# AWC playback contracts

`read_awc` decodes the container; reading successfully does not certify audio
playback. `Awc.validate()` checks stream metadata, encoded payload capacity and
streaming timelines. `to_bytes()` and `save()` enforce those checks before writing.
`save()` replaces the destination atomically after validation and serialization.

```python
from fivefury import Awc

bank = Awc.from_channel_mp3("dialogue", [left_pcm16, right_pcm16], sample_rate=48000)
bank.validate().raise_for_errors()
bank.save("dialogue.awc")
```

## Streaming

- Every stream table is sorted by its 29-bit hash. Channel order is independent
  and remains in STREAM_FORMAT.
- MP3 channel payloads begin on 16-byte boundaries. Encoded size excludes that
  padding, and the shared packet-table region is aligned to 2048 bytes.
- PCM uses extended block headers and absolute packet sample positions. Only
  intermediate blocks are padded to the nominal streaming block size.
- Legacy PCM/ADPCM fixed-block headers remain readable, including final packet
  padding bounded by the codec's packet sample count. New authoring uses the
  extended marker; validation does not mistake original legacy markers for MP3.
- Skipped samples represent the repeated prefix of an overlapping packet. They
  are removed from decoded output and counted when checking block continuity.
- Sample capacity comes from payloads, not matching declared durations alone.
- Retail MP3 trimming can leave a larger pre-trim frame counter. Validation
  permits a bounded final-packet trim and uses the actual decoded frame capacity.

Playback validation covers fixed-width PCM/float data, ADPCM block dimensions and
step indices, mono MP3 frame seek tables, and MP3/PCM/ADPCM streaming timelines.
Other codec layouts are reported with `awc.codec.unsupported`; recognizing a
codec identifier does not establish its playback contract.

## Preservation

An imported, unchanged resource whose only validation errors are unsupported
codecs can retain its exact original bytes. This is preservation, not successful
playback validation. Editing its serialized fields invalidates that path.
Known malformed data is not exempt merely because it came from a file.

Metadata-only containers can remain readable/writable with a no-playable-stream
warning. An incomplete audio stream with FORMAT but no DATA (or the reverse) is
an error, as are duplicate chunk types in an audio stream.

These checks do not prove audio quality, correct REL references, native mounting
or successful in-game playback. They do not identify a crash without matching
runtime evidence.
