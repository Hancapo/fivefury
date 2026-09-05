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

## Stored And World Transforms

`EntityDef.rotation` is the serialized placement quaternion, not automatically
the world-space orientation. Use `world_rotation(archetype)`,
`world_scale(archetype)` and `world_bounds(local_bounds, archetype)` when deriving
world data; these methods do not mutate the stored values.

- Ordinary entities conjugate the stored quaternion when using a full transform.
- A small X/Y tilt uses the runtime's heading-only path unless `FULLMATRIX` or
  an animated archetype with a clip dictionary requires a full transform.
- The heading-only path uses W and the sign of Z, rather than an Euler yaw
  extracted from a full quaternion. The full-transform threshold is the runtime
  float32 value of 0.05, with a strict greater-than comparison.
- Fragment placements ignore definition scaling. Drawable placements use XY/Z
  scales independently.
- MLO parents use the stored orientation directly and unit scale. MLO child
  entities still use ordinary `EntityDef` decoding before their parent transform.

Provide the archetype to account for animated and fragment-specific behavior.
Without one, ordinary methods describe a static, non-fragment placement.
`Ymap.recalculate_extents(context=...)` resolves loose archetypes from its context
and uses these methods. LOD-light generation uses the same decoded placement;
its optional `archetype=` argument supplies animation and fragment metadata.

Extents cover the placed archetype AABB, not every possible future animated pose.
These rules do not establish that unrelated streaming or rendering artifacts are
caused by placement bounds.
