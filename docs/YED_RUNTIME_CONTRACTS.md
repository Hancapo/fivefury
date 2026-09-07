# YED native authoring contracts

CPU expression evaluation and native expression attachment are different checks.
An executable expression with a zero signature can produce numerical results in
the CPU evaluator but is not a valid native authoring result.

## Finalize explicitly

```python
from fivefury import (
    MetaHash,
    YedExpression,
    YedInstruction,
    YedInstructionType as Op,
    YedStream,
    YedTrackFormat,
    create_yed,
)

expression = YedExpression.create("facial_transform")
expression.streams = [
    YedStream(
        name_hash=MetaHash("main"),
        depth=0,
        data1=b"",
        data2=b"",
        data3=b"",
        instructions=[
            YedInstruction(Op.TRACK_VALID, operands={
                "bone_id": 123, "track": 25, "format": YedTrackFormat.VECTOR3,
            }),
            YedInstruction(Op.JUMP_IF_FALSE, operands={"instruction_offset": 2}),
            YedInstruction(Op.TRACK_GET, operands={
                "bone_id": 123, "track": 25, "format": YedTrackFormat.VECTOR3,
            }),
            YedInstruction(Op.TRACK_SET, operands={
                "bone_id": 123, "track": 0, "format": YedTrackFormat.VECTOR3,
            }),
            YedInstruction(Op.END),
        ],
    ),
]

yed = create_yed(expression)
yed.recalculate_runtime_contract()
yed.validate_runtime_contract().raise_for_errors()
yed.save("facial_transform.yed")
```

The same operation is available on `YedExpression` when finalizing one expression.
Finalization prepares detached state first: an error does not leave a partially
rewritten expression or dictionary. Run it again after editing instructions.
It derives:

- Separate input/output tracks and their accelerated operand indices.
- The incremental CRC32 signature, including repeated accesses.
- Variable indices and motion descriptors for supported instructions.
- Stack depth, maximum stream size and rebuilt data/opcode buffers.
- Branch byte offsets from each relative instruction target.

Do not assign a donor signature, hash the expression name, or force a nonzero
placeholder. Identical ordered DOF interfaces can legitimately share a signature
even when expression names or calculations differ.

## Direction and traversal

`YedTrack.is_input` is bit 7; the lower seven bits describe the track format.
It does not request bone remapping. Track factories accept `is_input=True`;
the old `remap` argument and `remap_flag` property are removed.

Track deduplication uses **direction, channel and bone ID**. The CRC includes
every visited access as a little-endian uint32 `(channel << 16) | bone_id`,
with a zero initial CRC. It does not include only unique tracks.

Traversal is parent-before-children, not raw bytecode order. For the guarded
example above, the signature visits VALID, SET, GET. Nested supported stack
expressions and structured forward branches are reconstructed before traversal.
Packed linear sources are returned to their original four-lane source order.

## Validation and preservation

`validate_runtime_contract()` does not mutate anything. It checks native signature,
direction, track/variable indices, branch offsets and stream-buffer consistency.
`validate()` includes these checks together with structural validation. Writers
reject incomplete authored contracts before replacing the destination file.

An unmodified imported resource can retain its original bytes when some operations
or its pre-packing signature cannot be reproduced. This is a **preservation path**,
not certification of native playback. A zero-signature executable expression is
still rejected. Unverifiable original signatures are reported and are not silently
replaced by recalculation.

Unknown opcodes, overlapping/unstructured branches, duplicated computed values
and ambiguous statement/value branch mixtures are not guessed. Preserve those
original programs or provide supported authored instructions. Direct edits to a
read YED invalidate its original-byte fast path; the writer cannot silently discard
them anymore.

## Resource placement

Semantic validity is separate from memory placement. `yed.validate()` also checks
the serialized resource layout of an unchanged import: owned blocks must fit in
individual RSC chunks, pointers and capacities must be valid, streams must be
aligned, and page metadata must reserve all system and graphics allocations.
`validate_runtime_contract()` checks expression semantics, not resource placement.

New exports use the shared block-aware resource packer. Complete streams
(header and all parameter buffers), arrays, expressions and strings are moved as
indivisible allocations. Only declared pointer fields are relocated; hashes,
floating-point literals and other non-pointer data are not scanned for addresses.

Reading an older unsafe resource remains possible for inspection. Saving it
unchanged is rejected before replacing the destination. Regenerate supported,
reproducible expression contracts with the existing API:

```python
from fivefury import read_yed

yed = read_yed("original.yed")
report = yed.validate()
yed.recalculate_runtime_contract()
yed.save("regenerated.yed")
```

This preserves track semantics while rebuilding resource placement. Unknown or
unverifiable imported programs are not guessed: their original bytes may only be
preserved when the resource layout is safe. A target-edition override does not
bypass validation. No consumer should patch runtime indices or remove aliases to
compensate for an unsafe serialized layout.

## Frame indices and CPU diagnostics

`YedFrameLayout` describes the complete runtime frame, not a skeleton palette.
Derive it from the union of actual frame channels (skeleton DOFs, animation and
expression extras), or inspect a complete captured layout using `YedFrameDof`:

```python
from fivefury import YedFrameLayout, YedTrack

frame = YedFrameLayout.derive([
    YedTrack.vector3(7, 0),
    YedTrack.quaternion(7, 1),
    YedTrack.vector3(7, 25),
])
frame.validate().raise_for_errors()
indices = expression.resolve_frame_indices(frame)
```

`derive` merges input/output references to the same physical DOF, rejects format
conflicts, sorts channels by track and bone ID, and packs each format with its
runtime padding. The final two 16-byte slots are reserved for read/write sentinels.
`buffer_size` includes these slots and must fit uint16. Validation rejects
misaligned, overlapping, noncanonical and out-of-frame DOFs rather than repairing
them. An empty frame still occupies 32 bytes.

A matching **typed** DOF supplies its frame offset; an absent or differently typed
DOF uses `read_only_offset` for input tracks and `write_only_offset` for outputs.
Those two sentinel roles must not be confused with bone-ID remapping.
They are offsets of real storage, not `0xFFFF`. A missing channel does not by
itself imply an invalid accelerator address. This API describes layout only;
the runtime must initialize frame values and sentinel contents.

Full `TRACK_GET`/`TRACK_SET` operations access 16 bytes; declaring their format as
`FLOAT` does not change the native instruction's access width. Scalar channels
must use `TRACK_GET_COMP`/`TRACK_SET_COMP` with component zero. Relative full-vector
operations are likewise not scalar operations. Quaternion component operations
use Euler XYZ components 0 through 2, not a fourth quaternion component.
These invariants are checked during contract derivation, validation and export,
including unchanged imports; preservation does not authorize an unsafe access.

`frame.signature` is the runtime checksum of the sorted DOFs. Its value is not
proof of identity: caches must retain the full layout and invalidate on changes.
Do not pass an incomplete dump as a complete layout or infer absent DOF records.
The previous `resolve_frame_indices(dofs, read_only_offset=..., write_only_offset=...)`
form is removed; pass a validated `YedFrameLayout` instead.

Inspect a previously cached or captured accelerator with
`expression.validate_frame_binding(frame, indices)`. It checks the expression's
global track contract, logical table length, alignment, bounds and every expected
DOF/sentinel offset. Stream operands index this global table; do not restart or
concatenate index numbering for each stream. Alias expressions with identical
track contracts may use the same mapping; names alone are not cache identities.

The runtime cache lookup combines the frame signature in the upper 32 bits and
the expression signature in the lower 32 bits. Both are checksums, not unique
identifiers. Retain the complete frame DOFs and directional expression tracks
when caching in a consumer. Invalidate when either changes, even if the signature
or table length happens to remain the same. This validator recomputes the
expected mapping; an aligned, in-range offset is still wrong if it selects a
different channel or the wrong sentinel.

For captures, supply only the logical expression entries, not allocator padding.
`None` marks unavailable captured entries and produces an explicit diagnostic;
it does not substitute a sentinel. A valid report certifies only the supplied
layout and table, not the lifetime of a pointer, contents of uncaptured memory,
or the values initialized by the game. Offline YED validation cannot certify
an accelerator which is allocated later by the runtime.

The synthetic binding regressions cover both editions, large multi-stream
expressions and alias names. To test an external Enhanced YED with at least
500 tracks and five streams, set `FIVEFURY_TEST_YED_FRAME_CORPUS` to a directory of such YEDs
and select `tests/animation/yed/test_yed_frame_integration.py --suite integration`.
That test checks the expression-derived layout, not a captured creature frame.

`evaluate_yed(...).issues` describes numerical/VM problems.
`evaluate_yed(...).native_diagnostics` separately reports the zero-signature
attachment gate. That fast check is not full contract validation: use
`validate_runtime_contract()` before export, including after any edits.

Passing these checks does not establish skeleton compatibility, animation routing,
frame availability or in-game playback. Runtime replay is still required.
