# FiveFury

FiveFury is a pure-Python toolkit for working with GTA V resource files.

It focuses on practical asset I/O:

- `YMAP` read/write
- `YTYP` read/write
- `RPF7 OPEN` archives
- nested `.rpf` handling
- `ZIP -> RPF` and `RPF -> ZIP`
- lazy file indexing with `GameFileCache`

The package has no runtime dependencies and does not include any XML layer.

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
cache.scan()  # registers loose-file and archive entry stems in the global resolver

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

cache = GameFileCache("mods_root")
cache.scan()

game_file = cache.get_file("some_archive.rpf/stream/example_map.ymap")
if game_file is not None:
    print(game_file.kind.name)
    print(type(game_file.parsed).__name__)
```

`GameFileCache` indexes both loose files and `.rpf` contents, then parses supported file types lazily on demand.

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
