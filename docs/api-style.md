# API Style

High-level authoring conventions used across FiveFury.
The preferred high-level authoring style is now:

- `add_*` for collections
- `set_*` for single assignments or bindings
- `build()` to normalize derived state before serialization
- `validate()` to collect consistency issues

Enums are preferred where the game format has stable names: shaders, LODs, render masks, archetype asset types, bound material types, YND flags, YCD track formats, and skeleton flag-name mappings all expose typed values on the public API.

Some newer high-level helpers were renamed to match that convention. If you were using recent pre-release `YDR` helpers, notable renames are:

- `create_bone(...)` -> `add_bone(...)`
- `embed_texture(...)` -> `add_embedded_texture(...)`
- `unembed_texture(...)` -> `remove_embedded_texture(...)`
- `use_bound(...)` -> `set_bound(...)`
- `skin_model(...)` -> `set_model_skin(...)`
