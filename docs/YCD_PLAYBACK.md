# Compiled YCD playback

Mutable YCD models remain the authoring interface. Compile once when beginning
repeated playback, not once per frame:

```python
from fivefury import read_ycd

ycd = read_ycd("scene-0.ycd")
clip = ycd.get_clip("actor_dual-0")
sampler = clip.compile()
tracks = sampler.evaluate_tracks_at_time(1.234)
```

`YcdAnimation.compile()` returns `YcdAnimationSampler`, with the existing
`evaluate_tracks(frame, track=None, interpolate=True)` shape. A clip returns
`YcdClipSampler`, with `evaluate_tracks_at_time` and `evaluate_tracks_at_phase`.
Results remain dictionaries keyed by `(bone_id, track_id)`, containing nominal
`Vector4` or `Quaternion` objects. There are no application-facing native handles.

## Lifetime and edits

- Compilation copies decoded channel cycles into owned native float64 buffers.
  It does not retain the editable model, reader, RPF or external buffer.
- A sampler is immutable. Source edits deliberately do not change it; recompile
  after editing channels, bindings, sequence structure or clip timing.
- Dropping the last sampler reference releases its storage. There is no global
  plan cache, sampled-frame cache or retained per-seek state.
- `sample_bytes` reports copied channel data, excluding metadata and output
  objects. Static channels keep one value per component rather than a full frame
  array. Indirect channels retain their decoded frame cycle.
- Samplers can be shared by concurrent actors. Evaluation releases the GIL for
  native sampling and allocates independent output state per call.
- Multiple `YcdClipSampler` instances can explicitly share one compiled
  `animation`, with independent duration/loop metadata.

Do not modify a model concurrently with its compilation. An already compiled
sampler is independent of subsequent mutations and seeks.

## Sampling contract

The compiled path uses decoded channel values; it does not requantize or change
the animation. Opcode 7/8 reconstruction or normalization occurs after scalar
interpolation, using the current block's overlapping sample. Ordinary quaternion
tracks retain their existing shortest-path normalized interpolation.

Integer arguments and `interpolate=False` retain integer evaluation behavior,
including cyclic channel lookup. Fractional requests retain the existing endpoint
clamping and missing-track rules. Nonfinite or unrepresentably large native frame
indices are rejected.

Clip time and phase conversion are shared with `YcdClipAnimation`. The existing
methods clamp to clip duration/phase; they do not apply an implicit rate change
or wrap solely because the loop flag is set. A caller that currently computes
looped phase or time must keep doing so. This is a performance path, not a change
to the runtime interpretation of clip timing metadata.

The compilation boundary expects valid decoded or built channel layouts. A
cached quaternion opcode without a matching cached sequence, an invalid omitted
component or an incomplete cached component set is rejected rather than guessed.

## Verification

Unit tests compare mutable and compiled results at integer/fractional frames,
sequence overlaps, out-of-range seeks, channel cycles and missing keys. They also
cover edits, detached lifetime, concurrent evaluation and output construction.
Performance cases are in `tests/performance/bench_ycd_playback.py`.

Library sampling improvements are not viewer FPS predictions: rendering,
skinning, expression evaluation and scheduling remain separate workloads.
