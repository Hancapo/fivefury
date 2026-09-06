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

## Frame indices and CPU diagnostics

`YedFrameDof` and `expression.resolve_frame_indices(...)` describe frame binding.
A matching **typed** DOF supplies its frame offset; an absent or differently typed
DOF uses `read_only_offset` for input tracks and `write_only_offset` for outputs.
Those two sentinel roles must not be confused with bone-ID remapping.

`evaluate_yed(...).issues` describes numerical/VM problems.
`evaluate_yed(...).native_diagnostics` separately reports the zero-signature
attachment gate. That fast check is not full contract validation: use
`validate_runtime_contract()` before export, including after any edits.

Passing these checks does not establish skeleton compatibility, animation routing,
frame availability or in-game playback. Runtime replay is still required.
