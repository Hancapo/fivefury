# Ped Expressions

YED expression dictionary workflows.
## YED

`YED` files are expression dictionaries used by peds through expression set metadata. FiveFury exposes expressions, typed tracks, streams, semantic instruction operands, variables, and spring blocks:

```python
from fivefury import YedTrackFormat, read_yed

yed = read_yed("ambient.yed")
breasts = yed.require_expression("breasts")

print(breasts.spring_bone_ids)
print([track.format for track in breasts.tracks])
for stream in breasts.streams:
    for instruction in stream.instructions:
        print(instruction.name, instruction.operands)
```

Small spring dictionaries can be built declaratively:

```python
from fivefury import YedTrackFormat, create_yed, save_yed

yed = create_yed("breasts")
expr = yed.require_expression("breasts")
expr.ensure_spring(0xFC8E)
expr.ensure_spring(0x885F)
expr.ensure_track(0xFC8E, format=YedTrackFormat.VECTOR3)

yed.validate()
save_yed(yed, "ambient_custom.yed")
```

Existing spring descriptions can be cloned when a custom skeleton keeps the same physics shape but adds new bone tags:

```python
yed.clone_breast_springs_to_glutes(
    left_breast=0xFC8E,
    right_breast=0x885F,
    left_glute=0x40B2,
    right_glute=0xC141,
)
```

Complex expression streams are currently preserved and decoded at opcode level. Full semantic editing of every stream instruction is intentionally more conservative because those bytecode operands need to stay 1:1 with the game VM.
Streams can also be authored with semantic instructions for the supported VM layouts:

```python
from fivefury import YedInstruction, YedInstructionType, YedStream

expr = yed.ensure_expression("face")
expr.streams.append(YedStream.raw_stream("main", depth=2, data3=b""))
expr.streams[0].instructions = [
    YedInstruction(YedInstructionType.PUSH_FLOAT, operands={"value": 1.0}),
    YedInstruction(YedInstructionType.PUSH_VECTOR, operands={"value": (1.0, 0.0, 0.0, 0.0)}),
    YedInstruction(YedInstructionType.END),
]
```

The supported semantic layouts currently cover empty stack/vector ops, float/vector constants, bone track ops, variables, jumps, springs, look-at, and blend op payloads. Unknown or malformed bytecode is still preserved from existing files, but validation reports it before semantic rebuilds.
