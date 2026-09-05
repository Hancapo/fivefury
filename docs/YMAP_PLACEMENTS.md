# YMAP Placements

## Entity Flags

`YmapEntityFlags` preserves all raw 32-bit flags, including unnamed bits. Reading
and writing do not shift or translate the numeric value.

The declared entity-definition flags occupy bits 0–6 and 15–29. For example,
`DRAWABLELODUSEALTFADE` is `0x8000`, and `ONLY_RENDER_IN_WATER_REFLECTIONS` is
`0x08000000`, not `0x80000`.

Two different sets of light flags must not be confused:

| Purpose | Static Shadows | Dynamic Shadows | Ignore Day/Night |
| --- | --- | --- | --- |
| Declared entity-definition names | `LIGHTS_CAST_STATIC_SHADOWS` (`0x80000`) | `LIGHTS_CAST_DYNAMIC_SHADOWS` (`0x100000`) | `LIGHTS_IGNORE_DAY_NIGHT_SETTINGS` (`0x200000`) |
| IPL bits read by the entity runtime | `IPL_LIGHTS_CAST_STATIC_SHADOWS` (`0x80`) | `IPL_LIGHTS_CAST_DYNAMIC_SHADOWS` (`0x100`) | `IPL_LIGHTS_IGNORE_DAY_NIGHT_SETTINGS` (`0x200`) |

`1572864` (`0x180000`) names the two declared shadow flags. It is not a
reflection-only mask, but the labels alone do not mean the runtime reads those
bits for light-shadow behavior. The IPL names express that distinction explicitly.

These layouts are consistent with the Legacy definitions and the inspected
Enhanced entity initialization code. They are not evidence that a particular
flag causes or fixes rendering flicker.

Code using incorrectly positioned symbolic constants from older releases must
be reviewed when regenerating assets. Numeric values already stored in files
remain untouched; FiveFury does not guess their original intent.
