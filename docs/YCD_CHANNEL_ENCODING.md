# YCD channel encoding

`YcdChannelEncodingPolicy` selects codecs and optional read-back accuracy limits.
The builder policy is the default; an individual `track(..., channel_policy=...)`
replaces it for that track only.

| Track | RETAIL, varying components | RAW_FLOAT, varying components |
| --- | --- | --- |
| Bone/mover translation and rotation | 16-bit quantized floats | 32-bit floats |
| Facial translation, rotation and scale | 16-bit quantized floats | 32-bit floats |
| Other tracks, including camera channels | 32-bit floats | 32-bit floats |

Static tracks and constant components keep their static codecs. Quaternion
packing is a separate choice: the channel policy does not disable cached
reconstruction or change its runtime interpolation order. Compression does not
rename tracks or clips, remove controls, alter timing, or change section and
sequence boundaries.

## Mixed precision

```python
from fivefury import (
    Vector3,
    YcdAnimationTrack,
    YcdChannelEncoding,
    YcdChannelEncodingPolicy,
    YcdCutsceneBuilder,
)

high = YcdChannelEncodingPolicy(
    encoding=YcdChannelEncoding.RAW_FLOAT,
    maximum_error=2e-5,
    maximum_angular_error_degrees=0.05,
)
face = YcdChannelEncodingPolicy(
    encoding=YcdChannelEncoding.RETAIL,
    maximum_error=1e-5,
    maximum_angular_error_degrees=0.05,
)
builder = YcdCutsceneBuilder.create("scene", duration=1.0, channel_policy=high)
builder.track(
    "actor_dual",
    track=YcdAnimationTrack.MOVER_TRANSLATION,
    samples={0.0: Vector3(), 1.0: Vector3(100, 0, 0)},
)
builder.track(
    "actor_dual",
    track=YcdAnimationTrack.FACIAL_TRANSLATION,
    bone_id=7,
    samples={0.0: Vector3(), 1.0: Vector3(0, 0.02, 0)},
    channel_policy=face,
)
ycds = builder.build_ycds()
```

Use the same per-track policy for `FACIAL_ROTATION` and `FACIAL_SCALE`.
Facial rotations take `Quaternion` samples; translation and scale take `Vector3`.
Keep the original facial control IDs and merged body/face clip names.

## Accuracy contract

- `maximum_error` limits the largest absolute component difference, not vector
  length or world-space displacement. Quaternion comparisons account for the
  equivalence of opposite signs.
- `maximum_angular_error_degrees` independently limits rotation error.
- Both limits cover integer frames and subframes at 0.25, 0.5 and 0.75 of every
  interval, including the stored overlap at a physical sequence boundary.
- Validation uses encoded and decoded values, including float32 quantization
  parameters. It does not certify just the original in-memory samples.
- Cached quaternion validation interpolates stored components before
  reconstruction/normalization, matching that codec's behavior.

These are checks at specified sample locations, not a proof of an error bound at
every real-valued time. A component-only quaternion policy still checks subframes;
an angular bound is not required to enable those checks.

`validate()` reports precision errors without weakening the requested limits.
Integer component failures use `ycd.channel_precision.error_exceeded`; subframe
component failures use `ycd.channel_precision.subframe_error_exceeded`. Each
diagnostic identifies its worst frame within the generated section. Quaternion
component failures also report the maximum angular error for the same sampling
phase, even when that angular error meets its independent limit. The two maxima
need not occur at the same frame.

`build_ycds()` and `save()` reject violations before returning or publishing the
outputs. There is no automatic fallback to RAW_FLOAT or lower precision: choose
another policy explicitly if the requested codec cannot meet the limit.
RAW_FLOAT also has float32 rounding and is not an unlimited-precision mode.

Existing YCD bytes are not retroactively compressed. Rebuild the CUT/YCD assets
from the original authored samples after adopting a different channel policy.
