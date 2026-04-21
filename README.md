# FiveFury

FiveFury is a Python library for GTA V asset workflows.

It provides practical support for:

- `YDR` read/write for drawable workflows, including materials, shaders, drawable models, embedded textures, embedded collisions, skeletons, skinning, rigid bone bindings, and lights
- `YDD` read/write support for drawable dictionaries with multiple embedded drawables
- `YCD` read/write support for clip dictionaries, animation metadata, UV animation bindings, object tracks, skeletal tracks, camera tracks, root motion, and facial samples
- `YBN` read/write support for bounds, collision materials, geometry, BVH data, octants, and composite bounds
- `YND` read/write support for path nodes, links, flags, area helpers, and automatic network partitioning
- `YMAP` read/write
- `YTYP` read/write with typed archetype, MLO, portal, room, extension, and flag helpers
- `YTD` read/write and texture extraction helpers
- `RPF7 OPEN` archives and nested `.rpf`
- `ZIP -> RPF`, `RPF -> ZIP`, and `RPF -> folder`
- opening encrypted standalone `.rpf` files without preloading game keys
- fast asset indexing with `GameFileCache`
- texture extraction from `YTD`, `GTXD` parent chains and embedded dictionaries in `YDR`, `YDD`, `YFT` and `YPT`
- shared `RSC7`, `META`, hashing, and binary helper layers used by the resource formats
- optional native acceleration for heavier bounds and archive operations when the compiled extension is available

## Installation

```bash
pip install fivefury
```

For local development from a checkout:

```bash
pip install -e .
```

Python `3.11+` is required.

## API Style

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

## Current Format Coverage

This is the practical coverage exposed by the high-level API:

- `YDR`: read, edit, build, and write drawable resources with materials, shaders, samplers, numeric parameters, drawable models, LODs, render masks, lights, embedded textures, embedded bounds, skeletons, skinning, rigid bone bindings, shader inspection, and skeleton hash recalculation.
- `YDD`: read and write drawable dictionaries, including creating a dictionary from named `YDR` drawables.
- `YCD`: read and write clip dictionaries, preserve parsed metadata, rebuild sequence data, evaluate known track types, create UV clip bindings, and harden skeletal/object animation metadata before export.
- `YBN` and bounds: read and write standalone collision resources, primitive bounds, composite bounds, geometry bounds, BVH bounds, octants, material names, material colors, and generated collision chunks from triangle meshes.
- `YND`: read and write nav/path node resources, preserve node/link metadata, use typed flags/enums, compute area IDs from positions, and split a high-level node network into per-area `YND` resources.
- `YMAP` and `YTYP`: author entities, car generators, timecycle modifiers, occluders, archetypes, extensions, MLO structures, flags, and typed asset metadata.
- `YTD`: read and write texture dictionaries, preserve resource texture payloads, and extract textures through cache and embedded-asset helpers.
- `RPF`: create, read, extract, convert, and pack archives, including nested `.rpf` directories and standalone resource extraction.

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
from fivefury import BoundSphere, BoundType, TextureFormat, read_ydr

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

ydr.add_embedded_texture(
    name="prop_example_d",
    data=bytes([255, 255, 255, 255] * 16),
    width=4,
    height=4,
    format=TextureFormat.A8R8G8B8,
)

ydr.set_bound(
    BoundSphere(
        bound_type=BoundType.SPHERE,
        box_min=(-0.5, -0.5, -0.5),
        box_max=(0.5, 0.5, 0.5),
        box_center=(0.0, 0.0, 0.0),
        sphere_center=(0.0, 0.0, 0.0),
        sphere_radius=0.75,
        margin=0.05,
    )
)

issues = ydr.validate()
print(issues)

ydr.save("prop_example_out.ydr")
```

FiveFury exposes:

- global `ydr.materials`
- per-model views through `ydr.models`
- parsed `ydr.lights`
- editable material shaders, samplers, and numeric parameters
- embedded texture helpers through `add_embedded_texture(...)` and `remove_embedded_texture(...)`
- embedded collision helpers through `set_bound(...)` and `clear_bound()`
- skeleton helpers for bones, skinning, rigid bone bindings, and explicit skeleton hash recalculation
- `build()` / `validate()` helpers for authoring flows

### Skin a YDR model declaratively

```python
from fivefury import read_ydr

ydr = read_ydr("weapon_example.ydr")

root = ydr.add_bone("root", tag=0)
child = ydr.add_bone("child", parent=root, tag=1)
ydr.ensure_skeleton().build()

ydr.set_model_skin(0, bone_index=0, palette_size=0xFF)
mesh = ydr.meshes[0]
mesh.set_skin(
    bone_ids=[root, child],
    weights=[
        (1.0, 0.0, 0.0, 0.0),
        (0.5, 0.5, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
    ],
    indices=[
        (0, 0, 0, 0),
        (0, 1, 0, 0),
        (1, 0, 0, 0),
    ],
)

print(ydr.validate())
ydr.save("weapon_example_out.ydr")
```

### Write skeleton hashes for animated YDRs

Some animated YDRs, especially rigid object rigs where drawable models are bound to bones without vertex weights, need skeleton hash fields derived from bone tags, flags, and transforms. FiveFury preserves existing values by default for safe read/edit/write roundtrips. When authoring a skeleton from scratch, opt in explicitly:

```python
from fivefury import YdrBoneFlags, YdrSkeleton, YdrSkeletonBinding, create_ydr

skeleton = YdrSkeleton.create()
root = skeleton.add_bone(
    "root",
    tag=0,
    flags=YdrBoneFlags.ROT_X | YdrBoneFlags.ROT_Y | YdrBoneFlags.ROT_Z,
)
skeleton.add_bone(
    "moving_part",
    parent=root,
    tag=1,
    flags=YdrBoneFlags.ROT_X | YdrBoneFlags.TRANS_Y,
    translation=(0.0, 0.25, 0.0),
)
skeleton.build()

build = create_ydr(
    meshes=[...],
    material_textures={"DiffuseSampler": "animated_prop_d"},
    skeleton=skeleton,
    skeleton_binding=YdrSkeletonBinding.rigid(bone_index=0),
    name="animated_prop",
)

# Recalculate only for this write. The in-memory skeleton is not mutated.
build.save("animated_prop.ydr", recalculate_skeleton_hashes=True)
```

If you want to store the values on the skeleton object before writing:

```python
from fivefury import calculate_skeleton_unknown_hashes

hashes = calculate_skeleton_unknown_hashes(skeleton)
print(hashes)

skeleton.recalculate_unknown_hashes()
build.save("animated_prop.ydr")
```

The formal flag-name mapping used by the hash helper is exposed through `YdrBoneFlagName` and `skeleton_bone_flag_names(...)`.

### Create a simple YDR

```python
from fivefury import YdrLight, YdrMeshInput, create_ydr

ydr = create_ydr(
    meshes=[
        YdrMeshInput(
            positions=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            indices=[0, 1, 2],
            texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
        )
    ],
    material_textures={"DiffuseSampler": "example_diffuse"},
    lights=[YdrLight.point(position=(0.0, 0.0, 5.0), intensity=3.0)],
    name="example_drawable",
)

ydr.add_light(YdrLight.spot(
    position=(0.0, 2.0, 5.0),
    direction=(0.0, 0.0, -1.0),
    cone_outer_angle=0.6,
))

ydr.save("example_drawable.ydr")
```

### Convert Assimp-supported meshes to YDR

```python
from fivefury import assimp_to_ydr, obj_to_ydr

assimp_to_ydr(
    r"C:\mods\example.fbx",
    r"C:\mods\example.ydr",
    generate_ytyp=True,
)

obj_to_ydr(
    r"C:\mods\example.obj",
    r"C:\mods\example_obj.ydr",
)
```

`assimp_to_ydr(...)` is now the unified import path for any source format that Assimp can read. `obj_to_ydr(...)` and `fbx_to_ydr(...)` are thin wrappers over that same pipeline.

This can also emit a companion `YTYP` with lowercase naming and `textureDictionary` set to `<model>_txd`.

### Inspect and choose YDR shaders

```python
from fivefury import YdrShader, print_ydr_shader_info, read_ydr

print_ydr_shader_info(YdrShader.NORMAL_SPEC_CUTOUT)

ydr = read_ydr("prop_example.ydr")
ydr.update_material(
    0,
    shader=YdrShader.NORMAL_SPEC_CUTOUT,
    textures={
        "DiffuseSampler": "prop_example_d",
        "BumpSampler": "prop_example_n",
        "SpecSampler": "prop_example_s",
    },
)
ydr.save("prop_example_cutout.ydr")
```

`YdrShader` is generated from the bundled shader definitions, so IDEs can autocomplete known `.sps` names. Shader info helpers expose render bucket, vertex layout, texture slots, and numeric parameters. If an authoring path provides `SpecularSampler`, FiveFury normalizes it to the drawable slot name `SpecSampler`.

### Read and write a YDD

```python
from fivefury import Ydd, read_ydd

ydd = read_ydd("uppr_001_u.ydd")

for entry in ydd.iter_drawables():
    drawable = entry.drawable
    print(entry.name, drawable.model_count, len(drawable.materials))

out = Ydd.from_drawables({ydd.drawables[0].name: ydd.drawables[0].drawable}, version=165)
out.save("single_drawable.ydd")
```

## YBN and Bounds

### Create primitive bounds

```python
from fivefury import BoundBox, BoundMaterialType, Ybn

bound = BoundBox.from_center_size(
    center=(0.0, 0.0, 1.0),
    size=(4.0, 4.0, 2.0),
    material_index=BoundMaterialType.CONCRETE,
)

ybn = Ybn.from_bound(bound)
print(ybn.validate())
ybn.save("simple_collision.ybn")
```

Primitive helpers are available for `BoundSphere`, `BoundBox`, `BoundDisc`, `BoundCylinder`, and `BoundCloth`. Material indices accept `BoundMaterialType` enum values instead of requiring raw integers.

### Build collision from triangles

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

Generated geometry is chunked when needed, gets BVH data, and includes octants for `BoundGeometry` children. The same bounds model is used by standalone `YBN` files and embedded `YDR` collisions.

## YCD

### Read and write a YCD clip dictionary

```python
from fivefury import read_ycd

ycd = read_ycd("maude_mcs_1-0.ycd")

print(len(ycd.clips))
print(len(ycd.animations))
print(ycd.clips[0].short_name)
print(ycd.animations[0].duration)

ycd.build()
ycd.save("maude_mcs_1-0_roundtrip.ycd")
```

FiveFury preserves parsed clip and animation metadata, rebuilds sequence data through typed channels, and hardens known skeletal/object animation fields before export. UV clips use the runtime binding convention `<object>_uv_<slot_index>` and `MetaHash(object) + slot_index + 1`.

### Create or inspect UV clip bindings

```python
from fivefury import build_ycd_uv_clip_hash, build_ycd_uv_clip_name, create_ycd_uv_clip

clip_name = build_ycd_uv_clip_name("prop_sign", 0)
clip_hash = build_ycd_uv_clip_hash("prop_sign", 0)
clip = create_ycd_uv_clip(object_name="prop_sign", slot_index=0, start_time=0.0, end_time=1.0)

print(clip_name, clip_hash, clip.short_name)
```

## YND

### Build path nodes and partition by area

```python
from fivefury import YndLink, YndNetwork, YndNode

node_a = YndNode(key="a", position=(0.0, 0.0, 0.0))
node_b = YndNode(key="b", position=(600.0, 0.0, 0.0))

node_a.links.append(YndLink(target_key="b"))
node_b.links.append(YndLink(target_key="a"))

for ynd in YndNetwork.from_nodes([node_a, node_b]).build_ynds():
    ynd.save(f"nodes_{ynd.area_id}.ynd")
```

`YndNetwork` computes each node's `area_id` from its world position, assigns local node IDs per area, and resolves links by `target_key`. Use `Ynd.from_nodes(...)` directly when you already know all nodes belong to one area.

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
