# FiveFury Style Guide

This document is normative. New code and refactors must follow these rules even when an older module does not.

## Design priorities

1. Model the game data faithfully.
2. Make valid authoring straightforward and invalid state visible.
3. Prefer one obvious operation over aliases and compatibility wrappers.
4. Keep binary policy in writers and domain policy in typed models.
5. Minimize code, indirection, allocations, and repeated work.

## Public API grammar

FiveFury models are ordinary typed Python objects. Their public collections are ordinary typed collections.

```python
entity = EntityDef(archetype_name="harbor_lamp", position=(10.0, 20.0, 5.0))
ymap.entities.append(entity)
```

An aggregate may expose a singular noun as a convenience factory. The factory constructs, registers, and returns the object.

```python
entity = ymap.entity("harbor_lamp", position=(10.0, 20.0, 5.0))
bone = skeleton.bone("root")
material = ydr.material("body", shader=YdrShader.DEFAULT)
```

Do not expose `add_*`, generic `add()`, or duplicate `create_*` aliases. Existing objects use `append`, `extend`, mapping assignment, or a domain relationship verb. A noun factory must not silently perform unrelated derivations.

One-to-one relationships use properties when assignment is sufficient:

```python
ydr.bound = collision
model.skeleton = skeleton
```

Use a verb only when the operation has domain behavior that property assignment cannot express.

| Verb | Required meaning |
| --- | --- |
| `ensure_*` | Return an existing component or create the minimum empty component. |
| `derive_*` | Produce data from authoritative source data. |
| `recalculate_*` | Replace existing derived values. |
| `normalize_*` | Canonicalize representation without inventing content. |
| `bind_*` | Establish and validate a semantic relationship. |
| `resolve_*` | Find a reference without modifying source data. |
| `validate` | Inspect only; never repair or mutate. |
| `build` | Finalize normalized in-memory state for serialization. |
| `save` | Build, validate, serialize, and atomically replace the destination. |

Do not use `get_*` for properties, `set_*` for ordinary assignment, or `do_*` for any public operation.

## Cross-asset authoring

Use `AssetRef[T]` for typed cross-file references, `AssetSet` for a named collection, and `BuildContext` for target and resolution state. Do not pass expanding groups of unrelated `ytyps=`, `ybns=`, `cache=`, `game=`, or shader lookup arguments through every layer.

```python
assets = AssetSet()
assets["stream/harbor_lamp.ydr"] = drawable

context = BuildContext(game=GameTarget.GTA5, assets=assets, strict=True)
drawable_ref = AssetRef("harbor_lamp", Ydr)
resolved = context.resolve(drawable_ref)
```

References preserve names and type intent. Binary writers convert them into the hashes, indices, pointers, or names required by the format.

## Diagnostics

Public validation uses `ValidationReport` and typed `Diagnostic` values. A diagnostic has a stable code, severity, message, asset, and field path. Do not return bare strings, mix warnings with errors, print from validators, or mutate objects while validating.

```python
report = asset.validate(context)
report.raise_for_errors()
```

Errors describe violated invariants. They must not promise runtime behavior that has not been tested in the game.

## Binary boundaries

- Readers decode bytes into typed models and preserve genuinely unknown data when lossless preservation is possible.
- Writers serialize typed models, calculate addresses and fixups, enforce packed limits, and write atomically.
- Builders derive nontrivial structures such as BVHs, bounds, manifests, ownership, and runtime hashes.
- High-level helpers coordinate existing public models; they do not duplicate parsers or writers.
- Edition-specific behavior is selected through `GameTarget`, never inferred from a local machine path.

Never expose raw dictionaries when a stable structure is known. Never guess an unknown field merely to make a fixture pass.

## Duplication and module boundaries

Before adding code, search the full source tree for the operation and its underlying math, hashing, XML, resource, texture, or graph logic.

- Math belongs in the shared math/vector module.
- Hashing belongs in the hashing module and uses the native implementation where available.
- XML primitives belong in the shared XML module.
- Resource layout, pointer, page, and fixup logic belongs in the resource layer.
- Shared drawable behavior belongs in `drawable`, not separately in YDR, YDD, YFT, or CDR.
- Format modules contain only format-specific models and policy.

Do not create a utility for a single call site. Extract behavior when it expresses a stable concept or removes real duplication.

## Simplicity rules

- Prefer data flow over flags that select unrelated behavior.
- Prefer a short typed object over a string-keyed dictionary.
- Prefer iteration over repeated near-identical branches.
- Prefer early validation over defensive fallback chains.
- Delete unreachable branches and superseded APIs instead of deprecating them.
- Do not catch `Exception` unless the boundary explicitly converts arbitrary plugin or file failures into diagnostics.
- Do not retain Python fallbacks for native code solely for obsolete tests.
- Avoid methods that only forward arguments under another name.
- Avoid comments that restate code. Comments explain binary evidence, invariants, or non-obvious constraints.

Line count is not a target by itself, but repeated ceremony is a design defect. If a helper needs many aliases, coercion branches, optional names for the same value, or boolean mode switches, redesign the model.

## Performance rules

- Do not repeat parsing, hashing, decompression, graph traversal, or bounds calculation inside loops.
- Build indexes once for repeated lookup.
- Stream large files and archives where the format permits it.
- Keep large binary buffers as `bytes`, `memoryview`, or native containers rather than lists of Python integers.
- Move measured CPU-heavy loops to the native extension when the ABI can stay small and generic.
- Benchmark before and after optimization; do not claim improvement from code shape alone.

## Compatibility policy

FiveFury favors a coherent current API over compatibility with accidental historical APIs. Breaking refactors must:

1. Remove the old symbol and its internal uses in the same change.
2. Update tests, examples, type exports, and documentation.
3. Avoid aliases, warnings, forwarding wrappers, and hidden fallback behavior.
4. Record the breaking change concisely in the changelog.

Tests validate the intended API. They are not a reason to preserve obsolete code.

## Review checklist

- Is there exactly one public way to perform the operation?
- Does every method name describe domain intent rather than list mechanics?
- Are all inputs typed and are stable game values enums?
- Is validation non-mutating and diagnostic-driven?
- Is serialization atomic and performed only after validation?
- Has shared logic been reused rather than copied?
- Are unknown values preserved or rejected instead of guessed?
- Are hot loops indexed, batched, streamed, or native where justified?
- Were obsolete APIs, tests, exports, and comments deleted?
- Does the implementation remain faithful to both Legacy and Enhanced where the format differs?
