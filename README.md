# FiveFury

A Python library for **research and education** around GTA V asset formats.

FiveFury provides typed models and binary readers and writers for studying resource structures, inspecting their relationships, and experimenting with data. It supports GTA V Legacy and Enhanced, with coverage depending on the format and edition.

## Installation

```bash
python -m pip install fivefury
```

Requires **Python 3.11+**. Prebuilt wheels are available for Windows x64. Building the native extension from source requires a C++20 compiler.

## Examples

These examples create their own sample data.

### Create a small map

```python
from fivefury import Vector3, Ymap

ymap = Ymap(name="example")
ymap.entity(
    "prop_tree_pine_01",
    position=Vector3(100, 200, 30),
)
ymap.save("example.ymap", auto_extents=True)
```

### Read, inspect and edit it

```python
from fivefury import Vector3, Ymap

ymap = Ymap.from_path("example.ymap")
entity = ymap.entities[0]
print(entity.archetype_name, entity.position)

entity.position = Vector3(110, 200, 30)
ymap.save("edited.ymap", auto_extents=True)
```

For experiments in memory, use `ymap.to_bytes()` and `Ymap.from_bytes(data)`. The `fivefury.meta` module exposes META schemas, data blocks and decoded fields for inspecting the underlying representation.

## Scope

| Area | Formats |
| --- | --- |
| Maps and world data | YMAP, YTYP, YMF, GTXD, `gta5_cache_y.dat`, `heightmap.dat`, `water.xml` |
| Geometry and textures | YDR, YDD, YFT, YTD |
| Collision and navigation | YBN, YND, YNV |
| Animation and scenes | YCD, YED, `.cut` |
| Audio and text | AWC, REL, GXT2 |
| Archives and metadata | RPF7, DLC metadata, YMT, META, PSO, RBF |

Support includes reading, writing and validation for the modeled structures. Some variants remain partially understood, particularly within YFT, REL, YED and YMT. Console CDR and PS3 RPF support is focused on reading and extraction.

Use `GameTarget` where an API exposes edition-specific behavior. Validation checks the implemented binary contracts; newly authored assets still need verification in the target game.

## Development

**0.5.1 is the last planned feature release of the current Python implementation.** Core development is moving to .NET.

The [source code](https://github.com/Hancapo/fivefury/tree/main/fivefury) and [tests](https://github.com/Hancapo/fivefury/tree/main/tests) provide further examples and format-specific contracts. See the [changelog](https://github.com/Hancapo/fivefury/blob/main/CHANGELOG.md) for release history.

Released under [The Unlicense](https://github.com/Hancapo/fivefury/blob/main/LICENSE).
