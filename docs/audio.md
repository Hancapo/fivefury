# Audio

AWC conversion and REL-oriented audio workflow notes.
## Audio AWC Conversion

`fivefury.awc` can decode common desktop audio formats through `miniaudio` and write PCM `.awc` files. Mono input is written as a normal single-channel AWC; stereo or multichannel input is written as a real multichannel AWC with a `STREAM_FORMAT` source stream and logical channel streams.

```python
from fivefury import Awc, convert_audio_to_awc

# Direct file-to-file conversion. The stream name defaults to the source stem.
convert_audio_to_awc("music/stinger.mp3", "stream/stinger.awc")

# Force stereo output if the source is mono or has more channels than you need.
convert_audio_to_awc("music/song.flac", "stream/song.awc", channels=2)

# In-memory authoring when you also need to inspect or post-process the AWC.
awc = Awc.from_audio("radio_intro", "audio/radio_intro.ogg")
awc.save("stream/radio_intro.awc")
```

The converter currently normalizes input to signed 16-bit PCM and preserves the source channel count unless `channels=` is provided. Use `.rel` metadata to expose the resulting `.awc` stream as a playable sound, radio entry, cutscene audio, or other game audio object.
