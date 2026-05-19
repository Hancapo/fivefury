# GameFileCache

Scanning, resolving, and extracting game assets.
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

Available dictionaries include `YdrDict`, `YddDict`, `YtdDict`, `YmapDict`, `YtypDict`, `YftDict`, `YbnDict`, `YcdDict`, `YptDict`, `YndDict`, `YnvDict`, `YedDict`, `YwrDict`, `YvrDict`, `RelDict`, `Gxt2Dict`, and `AwcDict`.

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
