# FiveFury

FiveFury is a Python library for authoring, reading, writing, indexing, and packaging GTA V asset files.

It focuses on practical modding workflows: building drawable assets, collision resources, map metadata, animation dictionaries, nav data, texture dictionaries, text tables, audio containers, cutscenes, DLC metadata, and RPF archives from Python without forcing every user to work directly with binary layouts.

## Highlights

- Read, edit, build, and write core GTA V formats such as `YDR`, `YDD`, `YFT`, `YBN`, `YCD`, `YMAP`, `YTYP`, `YMF`, `YMT`, `YTD`, `YND`, `YNV`, `CUT`, `GXT2`, `AWC`, `REL`, and `RPF`.
- Use declarative high-level helpers for common authoring tasks while still keeping access to lower-level binary/resource details.
- Index game installs, loose folders, and archives with `GameFileCache`, including typed lookups by asset name, hash, format, and lazy dictionaries.
- Build DLC metadata, map manifests, cutscenes, navigation cells, collision resources, fragment physics, audio containers, and RPF archives from Python.
- Share common `RSC7`, `META`, `PSO`, `RBF`, XML, hashing, vector math, material, bounds, resource, and archive layers across formats.
- Use optional native acceleration for heavier bounds, hashing, crypto, resource layout, and archive operations when the compiled extension is available.

## Installation

```bash
pip install fivefury
```

For local development from a checkout:

```bash
pip install -e .
```

Python `3.11+` is required.

Assimp-backed import helpers such as `assimp_to_ydr(...)`, `obj_to_ydr(...)`, `fbx_to_ydr(...)`, and `obj_to_nav(...)` also require:

- the Python package `impasse`
- a working native `assimp` library discoverable by the current process

FiveFury does not currently probe common install locations on its own. The native library must already be reachable through the environment, usually via `PATH`.

## Quick Examples

### Create a YMAP

```python
from fivefury import Ymap

ymap = Ymap(name="example_map")
ymap.entity("prop_tree_pine_01", position=(100, 200, 0), lod_dist=150.0)
ymap.car_gen("sultan", (110, 205, 0), heading=90)
ymap.save("example_map.ymap", auto_extents=True)
```

### Convert Audio to AWC

```python
from fivefury import convert_audio_to_awc

convert_audio_to_awc("music/song.flac", "stream/song.awc", channels=2)
```

### Build a YMF Manifest

```python
from fivefury import create_ymf_for_ymaps, read_ymap, read_ytyp

ymap = read_ymap("stream/custom_city.ymap")
ytyp = read_ytyp("stream/custom_city.ytyp")
manifest = create_ymf_for_ymaps([ymap], ytyps=[ytyp], name="_manifest", strict=True)
manifest.save("stream/_manifest.ymf")
```

### Pack an RPF

```python
from fivefury import Ymap, create_rpf

ymap = Ymap(name="packed_map")
ymap.entity("prop_tree_pine_01", position=(0.0, 0.0, 0.0), lod_dist=120.0)

archive = create_rpf("mods.rpf")
archive.add("stream/packed_map.ymap", ymap)
archive.save("mods.rpf")
```

## Documentation

| Topic | Guide |
| --- | --- |
| Supported formats | [docs/format-support.md](docs/format-support.md) |
| Drawables and fragments | [docs/drawables.md](docs/drawables.md) |
| Bounds and collisions | [docs/bounds.md](docs/bounds.md) |
| Animation dictionaries | [docs/animation.md](docs/animation.md) |
| Maps, DLC, and RPF | [docs/maps-dlc-rpf.md](docs/maps-dlc-rpf.md) |
| Cutscenes and CutScript | [docs/cutscenes.md](docs/cutscenes.md) |
| Navigation | [docs/navigation.md](docs/navigation.md) |
| Audio | [docs/audio.md](docs/audio.md) |
| Ped expressions | [docs/ped-expressions.md](docs/ped-expressions.md) |
| Metadata layers | [docs/metadata.md](docs/metadata.md) |
| GameFileCache | [docs/gamefilecache.md](docs/gamefilecache.md) |
| API style | [docs/api-style.md](docs/api-style.md) |

## License

FiveFury is released under the `CC0-1.0` public domain dedication. See [LICENSE](LICENSE).
