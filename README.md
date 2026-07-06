# FiveFury

FiveFury is a Python library for reading, writing, and packaging GTA V asset files: drawables, collisions, map metadata, animations, navigation data, texture dictionaries, text tables, audio containers, cutscenes, DLC metadata, and RPF archives.

It targets practical modding workflows — declarative high-level helpers for common authoring tasks, with access to the underlying binary and resource layers when you need them. Heavy operations (vertex packing, collision generation, hashing, crypto, resource layout, archive scanning) run in a bundled native extension.

## Installation

```bash
pip install fivefury
```

Python 3.11+ is required.

The Assimp-backed import helpers (`assimp_to_ydr`, `obj_to_ydr`, `fbx_to_ydr`, `obj_to_nav`) additionally require the `impasse` package and a native `assimp` library reachable through the environment (usually via `PATH`).

## Format support

| Format | Status | Scope |
| --- | --- | --- |
| `YDR` | Full | Drawables: models, LODs, materials, shaders, lights, embedded textures and bounds, skeletons, skinning |
| `YDD` | Full | Drawable dictionaries, creation from named drawables, ped-component rigging helpers |
| `YBN` | Full | Primitive, composite, geometry, and BVH bounds; collision generation from triangle meshes |
| `YCD` | Full | Clip dictionaries: skeletal, object, UV, camera, and root-motion tracks |
| `YMAP` | Full | Entities, car generators, occluders, timecycle modifiers, LOD/distant lights |
| `YTYP` | Full | Base/time/MLO archetypes, extensions, rooms, portals, entity sets |
| `YMF` | Full | Map manifests, IMAP/ITYP dependencies, generation from YMAP sets |
| `YTD` | Full | Texture dictionaries: read/write, extraction, embedded-asset helpers |
| `YND` | Full | Path nodes, links, area partitioning, junction heightmaps |
| `YNV` | Full | Navmeshes: sectors, polys, portals, validation, basic OBJ partitioning |
| `CUT` | Full | Cutscenes, plus the readable `.cuts` script format for round-trip authoring |
| `GXT2` | Full | Hashed text tables with binary read/write and text import/export |
| `AWC` | Full | Audio containers: PCM/WAV extraction, authoring from WAV/MP3/OGG/FLAC |
| `RPF` | Full | RPF7 archives: nested archives, folder/ZIP conversion, encrypted archive reading |
| DLC metadata | Full | `setup2.xml`, `content.xml`, `dlclist.xml`, title-update patch overlays |
| `GTXD` | Full | Parent texture dictionary metadata (XML and binary RBF) |
| `YFT` | Partial | Fragment read/write: drawables, physics LODs/groups/children, composite bounds |
| `REL` | Partial | Audio metadata banks; typed models for synths, curves, categories, and common sound graphs |
| `YED` | Partial | Expression dictionaries: inspection, spring editing, small dictionaries from scratch |
| `YMT` | Partial | META/PSO/RBF read/write with typed helpers for known roots; unknown payloads preserved |
| `YPT` | Partial | Embedded texture dictionary discovery/extraction only |
| `YWR`, `YVR` | Indexed | Detected by `GameFileCache` and RPF tooling; no dedicated parser yet |
| `YFD`, `YPDB`, `MRF` | — | Not implemented |

## Quick start

### Create a YMAP and pack it into an RPF

```python
from fivefury import Ymap, create_rpf

ymap = Ymap(name="example_map")
ymap.entity("prop_tree_pine_01", position=(100, 200, 0), lod_dist=150.0)
ymap.car_gen("sultan", (110, 205, 0), heading=90)
ymap.save("example_map.ymap", auto_extents=True)

archive = create_rpf("mods.rpf")
archive.add("stream/example_map.ymap", ymap)
archive.save("mods.rpf")
```

### Build a drawable

```python
from fivefury import YdrMeshInput, create_ydr

ydr = create_ydr(
    meshes=[
        YdrMeshInput(
            positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            indices=[0, 1, 2],
            texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
        )
    ],
    material_textures={"DiffuseSampler": "example_diffuse"},
    name="example_drawable",
)
ydr.save("example_drawable.ydr")
```

Existing drawables can be read with `read_ydr(...)`, then edited through `update_material(...)`, `add_embedded_texture(...)`, `set_bound(...)`, skeleton and skinning helpers, and saved back. `assimp_to_ydr(...)` imports any mesh format Assimp can read.

### Generate collision

```python
from fivefury import BoundMaterial, BoundMaterialType, build_bound_from_triangles, save_ybn

triangles = [
    ((0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, 4.0, 0.0)),
    ((4.0, 0.0, 0.0), (4.0, 4.0, 0.0), (0.0, 4.0, 0.0)),
]

bound = build_bound_from_triangles(
    triangles,
    material=BoundMaterial(type=BoundMaterialType.CONCRETE),
)
save_ybn(bound, "floor_collision.ybn")
```

Generated geometry is chunked as needed and gets BVH and octant data. The same bounds model backs standalone `YBN` files, embedded `YDR` collisions, and `YFT` physics — a drawable's render mesh can also be converted directly with `ydr.ensure_bound_from_render_geometry()`.

### Convert audio to AWC

```python
from fivefury import convert_audio_to_awc

convert_audio_to_awc("music/song.flac", "stream/song.awc", channels=2)
```

### Work with RPF archives

```python
from fivefury import RpfArchive, RpfExportMode, rpf_to_zip, zip_to_rpf

zip_to_rpf("unpacked_mod_folder", "packed_mod.rpf")
rpf_to_zip("packed_mod.rpf", "packed_mod.zip", mode=RpfExportMode.STANDALONE)

with RpfArchive.from_path("packed_mod.rpf") as archive:
    archive.to_folder("out", mode=RpfExportMode.STANDALONE)
```

Encrypted standalone archives open directly; FiveFury initializes the bundled crypto context automatically. Export modes: `STORED` (raw bytes), `STANDALONE` (valid standalone files with `RSC7` containers), `LOGICAL` (inner payloads).

### Index a game installation

```python
from fivefury import GameFileCache

cache = GameFileCache(r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V")
cache.scan_game(use_index_cache=True)

asset = cache.get_asset("prop_tree_pine_01", kind=".ydr")
cache.extract_asset(asset, "prop_tree_pine_01.ydr")
cache.extract_asset_textures("prop_tree_pine_01.ydr", "textures")
```

`GameFileCache` indexes loose files and archives, loads supported formats lazily, exposes typed lookups by name/hash/kind, resolves textures through `YTD`, `GTXD` parent chains, and embedded dictionaries, and can generate `YMF` manifests for custom maps. Scan scope is configurable (`dlc_level`, `exclude_folders`, `load_audio`, `load_vehicles`, `load_peds`).

### Author DLC metadata

```python
from fivefury import write_dlc_folder_metadata

write_dlc_folder_metadata("build/my_pack", pack_name="my_pack", order=60)
```

Scans the extracted DLC folder, infers common entries (nested `.rpf`, `.ityp` requests, audio data, text metadata), and writes `setup2.xml` and `content.xml`. `DlcPatch` builds `update.rpf` title-update overlays.

## API conventions

High-level objects follow a consistent shape: `add_*` for collections, `set_*` for single assignments, `build()` to normalize derived state, and `validate()` to collect consistency issues before writing. Formats with stable game-side names expose typed enums (shaders, LODs, render masks, archetype asset types, bound materials, track formats).

## License

FiveFury is released under the `CC0-1.0` public domain dedication. See [LICENSE](LICENSE).

Release notes live in [CHANGELOG.md](CHANGELOG.md).
