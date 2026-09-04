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
entity = EntityDef(
    archetype_name="harbor_lamp",
    position=Vector3(10.0, 20.0, 5.0),
)
ymap.entities.append(entity)
```

An aggregate may expose a singular noun as a convenience factory. The factory constructs, registers, and returns the object.

```python
entity = ymap.entity("harbor_lamp", position=Vector3(10.0, 20.0, 5.0))
bone = skeleton.bone("root")
physics = ymap.physics_dictionary("harbor_collision")
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
report = context.validate(asset)
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
- Values with named mathematical components use the shared nominal types
  (`Vector2`, `Vector3`, `Vector4`, `Quaternion`, `Aabb2`, and `Aabb3`), never
  anonymous float tuples or local aliases. Public models, readers, builders,
  and writers must preserve those types end to end.
- Mathematical code uses named fields and domain operations such as `value.x`,
  `value.normalized()`, `left.cross(right)`, and `rotation.rotate(position)`.
  Positional component access is reserved for binary, NumPy, and foreign-function
  boundaries where the external representation is inherently indexed. The nominal
  value objects themselves are iterable for those boundaries but are not indexable
  sequences.
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

## Native ABI verification

An `abi3` wheel must be tested on the minimum supported Python, even when built
with newer headers. Run `tests/test_native_abi_buffers.py` against the built wheel
with `FIVEFURY_ABI_TEST_PYTHON` pointing to Python 3.11. Build-host tests alone do
not verify the compatibility promised by the wheel tag.

## Test contracts

- Unit tests must run without a game installation or private asset corpus. Generate
  synthetic inputs for general contracts; retain independent binary assertions
  and real-file tests where format fidelity needs external evidence.
- Import the current API directly. Do not search alternative symbol names, catch
  missing API errors, or condition assertions on a method being present.
- Mark external tests with `integration`, cross-interpreter checks with `abi`,
  and timing measurements with `performance`. Selection is explicit through
  `--suite`; a selected test must fail if its prerequisite is missing.
- Do not use `skip`, `skipif`, `importorskip`, or empty parameter sets to hide a
  missing requirement. Platform-specific tests use `requires_platform`.
- Functional tests assert observable results and call counts, not relative wall
  time or artificial sleeps. Performance measurements belong in benchmarks.
- Source and wheel runs exercise the same test files. Subprocess tests must use
  the same package installation as their parent, not an incidental editable copy.
- Track all test sources and synthetic fixtures. Never commit private game assets
  or local paths; configure external data through the documented environment.

## Compatibility policy

FiveFury favors a coherent current API over compatibility with accidental historical APIs. Breaking refactors must:

1. Remove the old symbol and its internal uses in the same change.
2. Update tests, examples, type exports, and documentation.
3. Avoid aliases, warnings, forwarding wrappers, and hidden fallback behavior.
4. Record the breaking change concisely in the changelog.

Tests validate the intended API. They are not a reason to preserve obsolete code.

## Migration examples

The removed forms below are shown only to make the API change explicit. They are not compatibility aliases.

### Typed collections and noun factories

Before, a YMAP mixed generic dispatch, format-specific insertion methods, and duplicate factories:

```python
ymap.add(entity)
ymap.add_entity(entity)
created = ymap.create_entity("harbor_lamp", position=(10.0, 20.0, 5.0))
```

Now existing values use the collection and convenience construction uses one singular noun:

```python
ymap.entities.append(entity)
created = ymap.entity(
    "harbor_lamp",
    position=Vector3(10.0, 20.0, 5.0),
)
```

### Relationships and ordinary assignment

Before, relationship setters and insertion verbs obscured ordinary object ownership:

```python
ydr.set_bound(collision)
skeleton.add_bone(Bone("root"))
ydr.add_light(light)
```

Now assignment expresses ownership, while singular nouns construct or register children:

```python
ydr.bound = collision
root = skeleton.bone("root")
ydr.light(light)
```

### Cross-asset operations

Before, every layer forwarded an expanding parameter group:

```python
ymap.to_bytes(ytyps=[ytyp], ybns={"interior": ybn})
manifest = build_ymf_for_ymaps(ymaps, cache=cache, ytyps=[ytyp], ybns=ybns)
```

Now assets and resolution state travel together:

```python
assets = AssetSet()
assets["stream/interior.ytyp"] = ytyp
assets["stream/interior.ybn"] = ybn
context = BuildContext(assets=assets, cache=cache)

data = ymap.to_bytes(context=context)
manifest = build_ymf_for_ymaps(ymaps, context=context)
```

### CUT authoring

Before, construction mixed `add_*`, `create_*`, and generic dispatch:

```python
scene.add_prop("stage", model="stage01")
scene.add_camera("main_camera")
scene.add_event(camera_cut)
```

Now domain nouns and an explicit timeline operation describe the same scene:

```python
stage = scene.prop("stage", model="stage01")
camera = scene.camera("main_camera")
scene.timeline_event(camera_cut)
```

### Archives and validation

Before, archives had multiple insertion aliases and validators exposed unrelated result shapes:

```python
archive.add_file("stream/model.ydr", data)
archive.add_asset("stream/model.ydr", data)
issues = asset.validate()
```

Now archive insertion has one name and validation has one structured result:

```python
archive.file("stream/model.ydr", data)
report = context.validate(asset)
report.raise_for_errors()
```

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
