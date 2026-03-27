# FiveFury

FiveFury is a Python toolkit with a bundled native backend for working with GTA V resource files.

It focuses on practical asset I/O:

- `YMAP` read/write
- `YTYP` read/write
- `RPF7 OPEN` archives
- nested `.rpf` handling
- `ZIP -> RPF` and `RPF -> ZIP`
- lazy file indexing with `GameFileCache`

The package does not include any XML layer. `GameFileCache` requires the bundled native extension and is not available without it.

## Status

FiveFury is usable today for controlled asset pipelines, add-ons and tooling that need to create, inspect and rewrite `YMAP`, `YTYP` and `RPF` content from Python.

Current strengths:

- declarative APIs for building `YMAP` and `YTYP` files
- direct support for loose files, not only `.rpf` archives
- typed support for common `YMAP` surfaces and extensions
- generated files validated against a native loader during development

Current limits:

- partial format coverage by design
- some less common structures still roundtrip as passthrough data
- no XML import/export

## Installation

Python `3.11+` is required.

Install from the project root:

```bash
pip install .
```

For local development:

```bash
pip install -e .
```

## Quick Start

### Create and save a YMAP

```python
from fivefury import Entity, Ymap

ymap = Ymap(name="example_map")
ymap.add_entity(
    Entity(
        archetype_name="prop_tree_pine_01",
        guid=1,
        position=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
        lod_dist=150.0,
    )
)
ymap.recalculate_extents()
ymap.recalculate_flags()
ymap.save("example_map.ymap")
```

If you want to set an internal resource path, assign `ymap.resource_name = "stream/example_map.ymap"` before saving.

### Load an existing YMAP

```python
from pathlib import Path

from fivefury import Ymap

ymap = Ymap.from_bytes(Path("example_map.ymap").read_bytes())

print(ymap.meta_name)
print(len(ymap.entities))
print(ymap.flags, ymap.content_flags)
```

### Resolve hashes globally

```python
from fivefury import GameFileCache, jenk_hash, register_name, register_names_file, resolve_hash

register_name("prop_tree_pine_01")
register_names_file("common_names.txt")

cache = GameFileCache("mods_root")
cache.scan()
cache.populate_resolver()

print(resolve_hash(jenk_hash("prop_tree_pine_01")))
```

The resolver is global and optional. It does not change parsed values in place; it gives you a shared `hash <-> name` registry that tools can query.

### Create a YTYP

```python
from fivefury import Archetype, ParticleEffectExtension, Ytyp

ytyp = Ytyp(name="example_types")

archetype = Archetype(
    name="prop_tree_pine_01",
    lod_dist=150.0,
    asset_type=0,
    bb_min=(-1.5, -1.5, -0.5),
    bb_max=(1.5, 1.5, 8.0),
    bs_centre=(0.0, 0.0, 3.5),
    bs_radius=5.0,
)
archetype.add_extension(
    ParticleEffectExtension(
        name="fx_tree",
        fx_name="scr_wheel_burnout",
        fx_type=2,
        scale=0.8,
    )
)

ytyp.add_archetype(archetype)
ytyp.save("example_types.ytyp")
```

### Pack assets into an RPF

```python
from fivefury import Entity, Ymap, create_rpf

ymap = Ymap(name="packed_map")
ymap.add_entity(Entity(archetype_name="prop_tree_pine_01", position=(0.0, 0.0, 0.0), lod_dist=120.0))
ymap.recalculate_extents()
ymap.recalculate_flags()

archive = create_rpf("mods.rpf")
archive.add("stream/packed_map.ymap", ymap)
archive.add("docs/readme.txt", b"hello from fivefury")
archive.save("mods.rpf")
```

The archive layer accepts bytes-like objects and higher-level asset objects that expose `to_bytes()`.

### Convert between ZIP and RPF

```python
from fivefury import rpf_to_zip, zip_to_rpf

zip_to_rpf("unpacked_mod_folder", "packed_mod.rpf")
rpf_to_zip("packed_mod.rpf", "packed_mod.zip")
```

If a directory contains folders ending in `.rpf`, they are packed as nested RPF archives.

### Index loose files and archives with GameFileCache

```python
from fivefury import GameFileCache

cache = GameFileCache("mods_root", scan_workers=8, max_loaded_files=16)
cache.scan(use_index_cache=True)

print(cache.scan_ok)
print(cache.asset_count)
print(cache.summary())

asset = cache.get_asset("example_map")
data = cache.read_bytes("some_archive.rpf/stream/example_map.ymap")
game_file = cache.get_file("some_archive.rpf/stream/example_map.ymap")
```

`GameFileCache` indexes both loose files and `.rpf` contents, then parses supported file types lazily on demand. The easiest way to reason about its state is:

- `cache.scan_complete`: a scan has run
- `cache.scan_ok`: the last scan finished without recorded archive errors
- `cache.has_scan_errors`: one or more sources failed during scan
- `cache.has_assets`: the cache contains indexed assets
- `cache.summary()`: compact dict with counts, cache flags and scan timings

### Restrict DLC level and ignore folders

```python
from fivefury import GameFileCache

cache = GameFileCache(
    r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V",
    dlc_level="mpbattle",
    exclude_folders="mods;scratch",
)

cache.scan_game(use_index_cache=True)

print(cache.active_dlc_names[-1])
print(cache.ignored_folders)
```

You can also configure it after construction:

```python
cache = GameFileCache(r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V")
cache.use_dlc("mpbattle")
cache.ignore_folders("mods", "scratch")
cache.scan_game()
```

## API

Core types:

- `Ymap`, `Entity`, `MloInstance`, `CarGenerator`
- `Ytyp`, `Archetype`, `TimeArchetype`, `MloArchetype`
- `Room`, `Portal`, `EntitySet`
- `GrassBatch`, `InstancedData`, `LodLights`, `DistantLodLights`
- `create_rpf`, `load_rpf`

Useful `YMAP` helpers:

- `ymap.entity(...)`
- `ymap.mlo_instance(...)`
- `ymap.box_occluder(...)`
- `ymap.occlude_model(...)`
- `ymap.grass_batch(...)`
- `ymap.lod_light(...)`
- direct classes such as `ParticleEffectExtension`

Common save/load entry points:

- `Ymap.from_bytes(...)`
- `Ytyp.from_bytes(...)`
- `Ymap.save(...)`
- `Ytyp.save(...)`
- `save_ymap(...)`
- `save_ytyp(...)`

## Sample Assets

The repository includes a generator for sample assets:

```bash
python examples/generate_samples.py
```

Generated examples are written to `examples/generated/`.
