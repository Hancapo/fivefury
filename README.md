# FiveFury

FiveFury is a Python library for GTA V asset workflows.

It provides practical support for:

- `YDR` read/write for static drawable workflows, including materials, drawable models, and lights
- `YCD` read support for clip dictionaries and animation metadata
- `YMAP` read/write
- `YTYP` read/write
- `RPF7 OPEN` archives and nested `.rpf`
- `ZIP -> RPF`, `RPF -> ZIP`, and `RPF -> folder`
- opening encrypted standalone `.rpf` files without preloading game keys
- fast asset indexing with `GameFileCache`
- texture extraction from `YTD`, `GTXD` parent chains and embedded dictionaries in `YDR`, `YDD`, `YFT` and `YPT`

## Installation

```bash
pip install fivefury
```

For local development from a checkout:

```bash
pip install -e .
```

Python `3.11+` is required.

## Quick Start

### Create a YMAP

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

If you want an internal resource path, set `ymap.resource_name` before saving.

### Load a YMAP

```python
from pathlib import Path

from fivefury import Ymap

ymap = Ymap.from_bytes(Path("example_map.ymap").read_bytes())

print(len(ymap.entities))
print(ymap.flags, ymap.content_flags)
```

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

### Pack Assets into an RPF

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

### Convert between ZIP, RPF, and folders

```python
from fivefury import RpfExportMode, rpf_to_folder, rpf_to_zip, zip_to_rpf

zip_to_rpf("unpacked_mod_folder", "packed_mod.rpf")
rpf_to_zip("packed_mod.rpf", "packed_mod.zip", mode=RpfExportMode.STANDALONE)
rpf_to_folder("packed_mod.rpf", "packed_mod", mode=RpfExportMode.STANDALONE)
```

Directories ending in `.rpf` are packed as nested archives.

### Open an encrypted standalone RPF

```python
from fivefury import RpfArchive

archive = RpfArchive.from_path(r"C:\mods\dlc.rpf")
print(len(archive.all_entries))
```

Encrypted standalone archives can be opened directly. FiveFury initializes the bundled GTA V crypto context automatically.

### Export mode overview

```python
from fivefury import RpfArchive, RpfExportMode

archive = RpfArchive.from_path("packed_mod.rpf")

archive.to_folder("out_standalone", mode=RpfExportMode.STANDALONE)
archive.to_folder("out_logical", mode=RpfExportMode.LOGICAL)
archive.to_zip("out_stored.zip", mode=RpfExportMode.STORED)

print(RpfExportMode.STANDALONE.description)
```

`RpfExportMode` controls what gets written:

- `STORED`: raw entry bytes as stored in the archive
- `STANDALONE`: valid standalone files, including `RSC7` containers for resources
- `LOGICAL`: logical payloads with resource containers removed

## YDR

### Read and edit a YDR

```python
from fivefury import read_ydr

ydr = read_ydr("prop_example.ydr")

print(ydr.model_count)
print(len(ydr.lights))
print(ydr.materials[0].shader_name)

ydr.update_material(
    0,
    shader="spec.sps",
    textures={
        "DiffuseSampler": "prop_example_d",
        "SpecSampler": "prop_example_s",
        "BumpSampler": None,
    },
    parameters={
        "specularIntensityMult": 2.0,
    },
)

ydr.save("prop_example_out.ydr")
```

FiveFury exposes:

- global `ydr.materials`
- per-model views through `ydr.models`
- parsed `ydr.lights`
- editable material shaders, samplers, and numeric parameters

### Create a simple YDR

```python
from fivefury import YdrLight, YdrLightType, YdrMeshInput, create_ydr

ydr = create_ydr(
    meshes=[
        YdrMeshInput(
            positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            indices=[0, 1, 2],
            texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
        )
    ],
    texture="example_diffuse",
    lights=[
        YdrLight(
            position=(0.0, 0.0, 5.0),
            intensity=3.0,
            light_type=YdrLightType.POINT,
        )
    ],
    name="example_drawable",
)

ydr.save("example_drawable.ydr")
```

### Convert OBJ to YDR

```python
from fivefury import obj_to_ydr

obj_to_ydr(
    r"C:\mods\example.obj",
    r"C:\mods\example.ydr",
    generate_ytyp=True,
)
```

This can also emit a companion `YTYP` with lowercase naming and `textureDictionary` set to `<model>_txd`.

## YCD

### Read a YCD clip dictionary

```python
from fivefury import read_ycd

ycd = read_ycd("maude_mcs_1-0.ycd")

print(len(ycd.clips))
print(len(ycd.animations))
print(ycd.clips[0].short_name)
print(ycd.animations[0].duration)
```

## GameFileCache

### Scan a Game Installation

```python
from fivefury import GameFileCache

cache = GameFileCache(
    r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V",
    scan_workers=8,
    max_loaded_files=16,
)
cache.scan_game(use_index_cache=True)

print(cache.asset_count)
print(cache.stats_by_kind())
```

`GameFileCache` indexes loose files and archive contents, then loads supported formats lazily.

### Control DLC and Scan Scope

```python
from fivefury import GameFileCache

cache = GameFileCache(
    r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V",
    dlc_level="mpbattle",
    exclude_folders="mods;scratch",
    load_audio=False,
    load_vehicles=True,
    load_peds=True,
)
cache.scan_game(use_index_cache=True)
```

Useful scan options:

- `dlc_level`: limit active DLCs
- `exclude_folders`: ignore folders by prefix
- `load_audio`: skip audio-related assets during scan
- `load_vehicles`: skip vehicle-related assets during scan
- `load_peds`: skip ped-related assets during scan
- `use_index_cache`: reuse the persisted scan index for faster startup

### Look Up Assets by Name and Type

```python
asset = cache.get_asset("prop_tree_pine_01", kind=".ydr")
print(asset.path)
print(asset.short_name_hash)
```

You can iterate the cache directly:

```python
for asset in cache:
    print(asset.path, asset.kind)
```

Or iterate a specific kind:

```python
for ydr in cache.iter_kind(".ydr"):
    print(ydr.path)
```

### Read and Extract Assets

```python
from pathlib import Path

asset = cache.get_asset("prop_tree_pine_01", kind=".ydr")
data = cache.read_bytes(asset, logical=True)
out_path = cache.extract_asset(asset, Path("prop_tree_pine_01.ydr"))

print(len(data))
print(out_path)
```

Common access patterns:

- `get_asset(...)`: resolve one asset by path, name or hash
- `read_bytes(...)`: get bytes directly
- `get_file(...)`: build a lazy `GameFile` wrapper
- `extract_asset(...)`: write the asset to disk

Extraction defaults to standalone file output.
For resource assets such as `YDR`, `YDD`, `YFT`, `YTD`, `YMAP` and `YTYP`, this produces a valid standalone `RSC7` file.

If you want the logical payload instead:

```python
cache.extract_asset("prop_tree_pine_01", "prop_tree_pine_01_payload.ydr", logical=True)
```

### Extract Textures for an Asset

`GameFileCache` can resolve textures from:

- direct `YTD` files
- `texture_dictionary` references from `YTYP` archetypes
- parent relationships from `gtxd.meta`
- embedded texture dictionaries inside `YDR`, `YDD`, `YFT` and `YPT`

```python
from pathlib import Path

paths = cache.extract_asset_textures(
    "stt_prop_stunt_bowling_pin.yft",
    Path("bowling_pin_textures"),
)

for path in paths:
    print(path)
```

You can inspect the texture refs first:

```python
for ref in cache.list_asset_textures("uppr_001_u.ydd"):
    print(ref.origin, ref.container_name, ref.texture.name)
```

### Type Dictionaries

`GameFileCache` exposes lazy type dictionaries keyed by `shortNameHash`.

```python
from fivefury import jenk_hash

ydr = cache.YdrDict[jenk_hash("prop_tree_pine_01")]
ytd = cache.YtdDict[jenk_hash("vehshare")]
ybn = cache.YbnDict[jenk_hash("v_carshowroom")]
```

Available dictionaries include `YdrDict`, `YddDict`, `YtdDict`, `YmapDict`, `YtypDict`, `YftDict`, `YbnDict`, `YcdDict`, `YptDict`, `YndDict`, `YnvDict`, `YedDict`, `YwrDict`, `YvrDict`, `RelDict` and `Gxt2Dict`.

### Archetype Lookup

`GameFileCache` also builds a lazy global archetype lookup from indexed `YTYP` files.

```python
archetype = cache.get_archetype("prop_tree_pine_01")
print(archetype.name)

for archetype in cache.iter_archetypes():
    print(archetype.name)
```

## Global Hash Resolver

```python
from fivefury import register_name, register_names_file, resolve_hash, jenk_hash

register_name("prop_tree_pine_01")
register_names_file("common_names.txt")

print(resolve_hash(jenk_hash("prop_tree_pine_01")))
```

The resolver is shared and optional. It is useful for display, lookups and tooling.
