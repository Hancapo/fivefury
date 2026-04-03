# CUT Format Notes

This document describes the current understanding of GTA V `.cut` cutscene files as implemented in `fivefury`.

## Container

`.cut` files are not `RSC7` resources. They are PSO/PSIN containers with at least these sections:

- `PSIN`: binary payload
- `PMAP`: block map
- `PSCH`: structure/type schema
- `PSIG`, `STRE`, `CHKS`: auxiliary metadata

For the current sample `mp_int_mcs_18_a1.cut`, the root PMAP block points to `rage__cutfCutsceneFile2`.

## High-Level Model

The format is table-driven more than scene-graph-driven. A cutscene is effectively:

1. Root header/config object
2. Object table
3. Load event table
4. Runtime event table
5. Event-args table
6. Several timing/helper arrays

That means authoring cutscenes is mostly about maintaining stable indexes and references, not just nesting XML nodes.

## Root Fields

Important root fields observed in the sample:

- `fTotalDuration`
- `cFaceDir`
- `iCutsceneFlags`
- `vOffset`
- `fRotation`
- `vTriggerOffset`
- `pCutsceneObjects`
- `pCutsceneLoadEventList`
- `pCutsceneEventList`
- `pCutsceneEventArgsList`
- `attributes`
- `cutfAttributes`
- `cameraCutList`
- `sectionSplitList`
- `concatDataList`
- `discardFrameList`

## Relationships

The key references are:

- object references by `iObjectId`
- event-arg references by `iEventArgsIndex`
- optional child event references through `pChildEvents`

In other words:

- objects are the resource/actor layer
- event args are reusable payloads
- events reference both object ids and arg indexes

This is the main thing to preserve in any future writer.

## Strings

Strings appear in several forms:

- inline fixed-size strings
- pointer-based strings
- hash-only strings

`fivefury` currently exposes hash-only strings as `CutHashedString`.

## Arrays

Arrays can be:

- external pointer-backed arrays
- embedded arrays with inline capacity

One important detail from the sample: inline arrays may encode capacity, not real logical length. `concatDataList` exposed `40` slots in binary but only `1` real populated item. The parser trims trailing empty structs for this reason.

## Current Coverage

Implemented now:

- `.cut` binary reader
- `.cutxml` reader
- root/object/event/event-arg traversal
- object lookup by `iObjectId`
- event-arg lookup by `iEventArgsIndex`
- event resolution helper via `CutFile.iter_resolved_events()`
- summary helper via `CutFile.summary()` / `analyze_cut(...)`

Not implemented yet:

- `.cut` writer
- `.cutxml` writer
- round-trip preservation guarantees
- full PSO type coverage
- semantic classes per cut object/event type

## Recommended Authoring Workflow

For creating cutscenes, the most defensible workflow is:

1. Parse `.cut` into a neutral model.
2. Convert or maintain an editable high-level representation.
3. Edit objects, event args, and events separately.
4. Rebuild cross references:
   - `iObjectId`
   - `iEventArgsIndex`
   - child-event relationships
5. Recompute derived helper arrays and ranges.
6. Emit `.cutxml` first.
7. Only then emit binary `.cut`.

This is safer than trying to write PSO directly from a loose tree because the binary format is schema-driven and index-heavy.

## Proposed Future Writer Shape

The likely clean write pipeline is:

1. `CutBuilder`
   - owns objects, args, events, metadata
2. `CutCompiler`
   - resolves ids/indexes
   - normalizes hashes/strings
   - trims/compacts arrays
3. `CutXmlWriter`
   - debug/export/oracle format
4. `CutPsoWriter`
   - emits `PSIN/PMAP/PSCH/...`

The important design rule is to treat `.cutxml` as the authoring/debug layer and `.cut` as a compiled layer.

## Immediate Next Steps

If the goal is cutscene creation, the next useful implementation steps are:

1. add richer typed wrappers for common object/event/event-arg kinds
2. add `.cutxml` writer
3. add a high-level builder API
4. only after that, implement binary `.cut` writing
