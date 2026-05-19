# Maps, DLC, and RPF

Common map metadata, DLC metadata, manifest, and archive workflows.
## Quick Start

### Create a YMAP

```python
from fivefury import Ymap

ymap = Ymap(name="example_map")

# Entities
ymap.entity("prop_tree_pine_01", position=(100, 200, 0), lod_dist=150.0)
ymap.entity("prop_bench_01a", position=(105, 200, 0), lod_dist=80.0)

# Car generators
ymap.car_gen("sultan", (110, 205, 0), heading=90)
ymap.car_gen("adder", (115, 205, 0), heading=90, body_colors=(5, 10), livery=2)

# Time cycle modifiers (center + size)
ymap.time_cycle_modifier("interior_dark", (100, 200, 5), (50, 50, 20), hours=(20, 6))

# Box occluders (position + size + angle in degrees)
ymap.box_occluder(position=(100, 200, 0), size=(10, 10, 10), angle=45)

# Occlude models
ymap.occlude_box((-5, -5, 0), (5, 5, 10))
ymap.occlude_quad([(0, 0, 0), (10, 0, 0), (10, 0, 10), (0, 0, 10)])

ymap.save("example_map.ymap", auto_extents=True)
```

If you want an internal resource path, set `ymap.resource_name` before saving.

### Load a YMAP

```python
from pathlib import Path

from fivefury import Ymap

ymap = Ymap.from_bytes(Path("example_map.ymap").read_bytes())

print(len(ymap.entities))
print(len(ymap.car_generators))
print(ymap.flags, ymap.content_flags)

for cg in ymap.car_generators:
    print(cg.car_model, cg.heading, cg.body_colors)
```

### Create a YTYP

```python
from fivefury import Archetype, ArchetypeAssetType, ParticleEffectExtension, Ytyp

ytyp = Ytyp(name="example_types")

archetype = Archetype(
    name="prop_tree_pine_01",
    lod_dist=150.0,
    asset_type=ArchetypeAssetType.DRAWABLE,
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
from fivefury import Ymap, create_rpf

ymap = Ymap(name="packed_map")
ymap.entity("prop_tree_pine_01", position=(0.0, 0.0, 0.0), lod_dist=120.0)

archive = create_rpf("mods.rpf")
archive.add("stream/packed_map.ymap", ymap)
archive.add("docs/readme.txt", b"hello from fivefury")
archive.save("mods.rpf")
```

### Infer DLC Metadata from a Folder

```python
from fivefury import write_dlc_folder_metadata

# The folder is the extracted root that will become dlc.rpf.
metadata = write_dlc_folder_metadata(
    "build/my_pack",
    pack_name="my_pack",
    order=60,
)

print(metadata.setup.device_name)
print(len(metadata.content.data_files))
```

The helper scans the folder, ignores dot-prefixed folders, infers common DLC entries such as nested `.rpf` files, `.ityp` requests, audio `.dat` files, `overlayinfo.xml`, `interiorProxies.meta`, `dlctext.meta`, and `gtxd.meta`, then writes `setup2.xml` and `content.xml`.

`content.xml` is the retail GTA V name. If a toolchain needs a different metadata filename, pass `dat_file="context.xml"`; `setup2.xml` will point to that file.

```python
write_dlc_folder_metadata("build/my_pack", dat_file="context.xml")
```

### Create a DLC Patch Overlay

```python
from fivefury import DlcContentGroup, DlcPatch

patch = DlcPatch("my_pack")
patch.content.rpf("dlc_my_pack:/x64/levels/gta5/LODLights.rpf", map_data=True)
patch.change_set("MY_PACK_PATCH_MAP", group=DlcContentGroup.MAP)
patch.save_update_rpf("update.rpf")
```

`DlcPatch` writes `update:/dlc_patch/<pack>/setup2.xml`, `content.xml`, patch payloads, and a matching `common/data/extratitleupdatedata.meta` mount entry. The patch mount uses the original DLC `deviceName`, matching the title-update overlay behavior used by the game.

### Generate a YMF Manifest for YMAPs

```python
from fivefury import GameFileCache, create_ymf_for_ymaps, read_ymap, read_ytyp

ymap = read_ymap("stream/custom_city.ymap")
ytyp = read_ytyp("stream/custom_city.ytyp")

manifest = create_ymf_for_ymaps(
    [ymap],
    ytyps=[ytyp],
    name="_manifest",
    strict=True,
)
manifest.save("stream/_manifest.ymf")
```

If your custom map uses vanilla archetypes, pass a scanned `GameFileCache` so FiveFury can resolve the IMAP to ITYP relationships from the indexed game data:

```python
cache = GameFileCache(r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V")
cache.scan_game(use_index_cache=True)

manifest = cache.create_ymf_for_ymaps(["stream/custom_city.ymap"], name="_manifest")
manifest.save("stream/_manifest.ymf")
```

The default manifest name is `_manifest`, matching the convention used by streamed map packs.

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
