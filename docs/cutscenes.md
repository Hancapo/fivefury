# Cutscenes

CutScript and CUT authoring examples.
## CutScript Conversion

`.cuts` is FiveFury's readable cutscene authoring format. It can compile back to `.cut`, and existing `.cut` files can be exported to `.cuts` for inspection or editing.

```python
from fivefury import GameFileCache, save_cut_as_cutscript, save_cutscript

# Export a binary cutscene to a readable script.
save_cut_as_cutscript("stream/sample.cut", "stream/sample.cuts")

# Optional: resolve more hashes by scanning a game/resource folder first.
cache = GameFileCache("stream")
cache.scan()
cache.populate_resolver()
save_cut_as_cutscript("stream/sample.cut", "stream/sample_resolved.cuts")

# Compile the script back to a binary .cut.
save_cutscript("stream/sample.cuts", destination="stream/sample_from_script.cut")
```

The exporter resolves known hashes through `HashResolver` and automatically registers sibling filenames when the source is a path. Unknown hashes stay as safe `0x????????` tokens. It also preserves cutscene flags, camera quaternions, and high-level streamed-model metadata such as `CNAME`, `ANIM_BASE`, `ANIM_STREAMING_BASE`, animation export specs, and `typeFile`/`YTYP`.

CutScript distinguishes static and animated cutscene props:

```text
STATIC_PROP stage:
  MODEL stage01
  YTYP sample_meta

ANIMATED_PROP miku:
  MODEL miku_hatsune_metal
  YTYP sample_meta
  CNAME mmd_model_001
  ANIM_BASE miku_hatsune_metal
  PRESET COMMON_PROP
```

`MODEL` is the streamed `.ydr` asset. `CNAME` is the logical cutscene/YCD binding name; it may match `MODEL`, but only when the YCD was authored with the same object name.
