# Compiled YED evaluation

For repeated playback, compile expression selection and skeleton defaults once:

```python
from fivefury import read_yed

yed = read_yed("expressions.yed")
evaluator = yed.compile(expression_names, skeleton=skeleton)
result = evaluator.evaluate(tracks, time=seconds, delta_time=delta_seconds)
```

`YedEvaluator` returns the same `YedEvaluationResult` as `evaluate_yed`: typed
tracks, output tracks, variables, expression names, issues and native-attachment
diagnostics. It is not a private native handle. The existing mutable convenience
function also uses the native typed boundary, but checks complete program/default
content before reusing its bounded program cache.

## Ownership

- A compiled evaluator owns a native snapshot of programs and skeleton defaults;
  no source YED/skeleton is retained. Recompile after edits or expression-set changes.
- Compilation captures unresolved-expression and zero-signature diagnostics.
  Those diagnostics describe the snapshot, not subsequent source edits.
- Evaluations have independent native frames and release the GIL during the VM
  batch. There is no implicit per-actor state or cached last frame.
- Pass a separate mutable `variables` mapping per actor only when persistent
  variable state is intended. Without it, evaluation starts with fresh variables.
- Input Vector3, Vector4, Quaternion and scalar/iterable values cross the boundary
  directly. The native result contains final nominal Vector4 values, avoiding
  repeated Python dictionary/tuple conversions.
- Output values may share immutable Vector4 objects with matching final tracks
  within the same result. Result mappings and evaluation state are independent.

## Editable models

`evaluate_yed` detects changes to operands, instruction contents, stream metadata
and skeleton defaults, even when object/list identities and lengths stay unchanged.
This requires inspecting source content and is not the high-throughput playback
path. Use `compile()` once for repeated immutable playback instead of depending on
an incomplete cache signature or invoking compilation for every frame.

CPU evaluation and native attachment remain separate checks. A numerical output
does not prove that the expression can attach to a runtime actor. Compilation does
not erase diagnostics, repair malformed assets or certify in-game behavior.
