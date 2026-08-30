# FiveFury

FiveFury is a Python toolkit for authoring, inspecting, validating, converting, and packaging GTA V assets. It exposes typed models and declarative builders over the game's binary resource formats, metadata containers, and RPF archives without hiding the lower-level data needed for advanced workflows.

FiveFury is designed for tools that need to do more than convert a single file:

- Read, modify, and rebuild assets while preserving data that is not yet modeled.
- Create maps, collisions, navigation data, drawables, fragments, animations, and archives from Python objects.
- Target GTA V Legacy or Enhanced where their binary layouts differ.
- Validate resource pointers, packed limits, ownership, and format-specific invariants before writing.
- Index a game installation and resolve assets, hashes, textures, parent dictionaries, and map dependencies.
- Run expensive hashing, resource-layout, geometry, collision, and archive operations through the bundled native extension.

## Installation

```bash
pip install fivefury
```

FiveFury requires Python 3.11 or newer.

Static mesh import uses Trimesh and accepts file paths, bytes, `trimesh.Trimesh`, and `trimesh.Scene` objects. Supported source formats depend on Trimesh; call `supported_mesh_formats()` to inspect them at runtime.

## Supported workflows

| Area | Formats | Current coverage |
| --- | --- | --- |
| Drawables | `YDR`, `YDD`, `YTD` | Models and LODs, shader groups and parameters, samplers, embedded textures, lights, bounds, skeletons, skinning, drawable dictionaries, and texture dictionaries |
| Fragments and physics | `YFT` | Fragment drawables, damaged states, physics LODs/groups/children, contextual collision bounds, ownership validation, mass and inertia calculation, breakable glass, and environment cloth |
| World placement | `YMAP`, `YTYP` | Entities, physics dictionaries, MLO instances and definitions, archetypes, rooms, portals, entity sets, car generators, occluders, timecycle modifiers, and LOD lights |
| Streaming metadata | `YMF`, `GTXD`, `gta5_cache_y.dat` | Map/type dependencies, MLO registration, texture-dictionary parent chains, runtime PSO validation, and cache generation from in-memory or loose assets |
| Collision | `YBN` | Primitive, composite, geometry, and BVH bounds; materials, octants, MLO room IDs, and collision generation from triangle meshes |
| Navigation | `YND`, `YNV` | Road nodes and links, area partitioning, junction heightmaps, navmesh sectors/polygons/portals, typed network validation, in-memory cell builders, and Trimesh conversion |
| World data | `heightmap.dat`, `water.xml` | Quantized height grids, row RLE, water masks and queries, water surfaces, wave quads, and calming regions |
| Animation | `YCD`, `YED` | Skeletal, object, UV, camera, root-motion, and bone-scale tracks; clip dictionaries; expression dictionaries and spring data |
| Cutscenes | `.cut` | Binary cutscene read/write, declarative scene and audio authoring, validation, and YCD section generation |
| Audio and text | `AWC`, `REL`, `GXT2` | Audio containers and common codecs, typed audio metadata graphs, synth/curve/category records, and hashed text tables |
| Packaging | `RPF7`, DLC metadata | PC archive creation, nested archives, folder/ZIP conversion, standalone resource extraction, encrypted archive reading, generated DLC metadata, and typed CUT audio registration |
| Generic metadata | `YMT`, META, PSO, RBF | Typed known roots, generic binary containers, PSCH enums, and preservation of unknown schemas or payloads during supported rewrites |
| Console assets | `CDR`, PS3 `RPF7` | Read-only PS3 drawable decoding and automatic PS3 archive detection/extraction |

Additional discovery support is available for embedded `YPT` texture dictionaries. `GameFileCache` can index `YWR` and `YVR`, but FiveFury does not yet expose dedicated parsers for them. `YFD`, `YPDB`, and `MRF` are not implemented.

### Legacy and Enhanced

Target-aware APIs use `GameTarget` instead of loose version labels:

```python
from fivefury import GameTarget, YdrGen9Shader, trimesh_to_ydr

trimesh_to_ydr(
    "source/prop.glb",
    "stream/prop.ydr",
    game=GameTarget.GTA5_ENHANCED,
    shader=YdrGen9Shader.DEFAULT,
)
```

The target changes runtime headers, resource versions, bounds, shader metadata, and vertex layouts only where the format requires it. Readers infer the edition from the asset when possible. Legacy remains the default.

Current target-aware authoring covers the main `YDR`, `YDD`, `YFT`, `YBN`, `YCD`, `YED`, `YND`, and `YNV` paths. Support is format-specific rather than a blanket claim that every GTA V file differs between editions.

## Quick start

### Build and package a map

```python
from fivefury import Vector3, Ymap, create_rpf

ymap = Ymap(name="example_map")
ymap.entity(
    "prop_tree_pine_01",
    position=Vector3(100.0, 200.0, 0.0),
    lod_dist=150.0,
)
ymap.physics_dictionary("example_map")
ymap.car_gen("sultan", Vector3(110.0, 205.0, 0.0), heading=90.0)
ymap.save("example_map.ymap", auto_extents=True)

archive = create_rpf("example_pack.rpf")
archive.file("stream/example_map.ymap", ymap)
archive.save("example_pack.rpf")
```

Factories such as `entity(...)` and `car_gen(...)` append the new object to the owning `Ymap`. Prebuilt objects are inserted directly through the corresponding typed collection, for example `ymap.entities.append(entity)`.

### Assemble an Enhanced vehicle DLC

```python
from fivefury import VehiclePackBuilder

pack = VehiclePackBuilder(
    "example_cars",
    vehicles_meta,
    handling_meta,
    variations_meta,
    carcols_meta,
)
pack.vehicle("example_car", vehicle_yft, textures=vehicle_ytd)
result = pack.save("build")
```

The builder cross-validates the four metadata documents, registers their runtime file types, packages streamed YFT/YTD assets in a nested RPF, rereads the complete DLC, and only then atomically writes `build/example_cars/dlc.rpf`.

### Build a drawable from memory

```python
from fivefury import YdrMeshInput, YdrShader, create_ydr

ydr = create_ydr(
    name="example_drawable",
    shader=YdrShader.DEFAULT,
    meshes=[
        YdrMeshInput(
            positions=[
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
            ],
            indices=[0, 1, 2],
            texcoords=[[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]],
        )
    ],
    material_textures={"DiffuseSampler": "example_diffuse"},
)
ydr.save("example_drawable.ydr")
```

`read_ydr(...)` returns an editable asset with material, texture, bound, light, skeleton, and skinning helpers. Render geometry can also be converted into an embedded collision bound with `ydr.ensure_bound_from_render_geometry()`.

### Skin vertices on the GPU

```python
from fivefury import GpuShaderLanguage, GpuSkinning

gpu = GpuSkinning(
    positions,
    blend_indices,
    blend_weights,
    normals=normals,
)

# Upload these immutable streams when the mesh is created.
positions = gpu.streams.positions
influences = gpu.streams.influences
normals = gpu.streams.normals

# Reuse the palette and upload only its contents each frame.
palette = gpu.palette(bone_count)
gpu.pack_palette(skinning_matrices, output=palette)

shader = gpu.compute_shader(GpuShaderLanguage.GLSL)
groups = gpu.dispatch_groups()
```

`GpuSkinning` packs four bone indices and normalized weights into eight bytes per vertex and exposes specialized GLSL or HLSL vertex and compute sources. Compute output remains GPU-resident; renderers should bind the returned streams and palette using `GpuSkinningBindings` and avoid reading deformed vertices back to Python.

### Generate collision

```python
from fivefury import (
    BoundMaterial,
    BoundMaterialType,
    build_bound_from_triangles,
    save_ybn,
)

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

The builder chunks oversized geometry, builds BVHs and octants, and validates packed limits before serialization. The same bounds model is shared by standalone `YBN`, embedded `YDR` collision, MLO collision, and `YFT` physics.

### Build the runtime map cache from loose assets

```python
from fivefury import build_gta5_cache_y_from_directory

cache = build_gta5_cache_y_from_directory("build/stream")
cache.save("build/gta5_cache_y.dat")
```

The builder reads loose `YMAP`, `YTYP`, and `YBN` files, derives map and interior records, validates the result, and writes the binary cache atomically.

### Index a game installation

```python
from fivefury import GameFileCache

cache = GameFileCache("path/to/Grand Theft Auto V")
cache.scan_game(use_index_cache=True)

asset = cache.get_asset("prop_tree_pine_01", kind=".ydr")
cache.extract_asset(asset, "out/prop_tree_pine_01.ydr")
cache.extract_asset_textures(asset, "out/textures")
```

`GameFileCache` scans loose files and nested archives, performs lazy typed loading, resolves names and hashes, follows `YTD`/`GTXD` texture relationships, and supplies the dependency context used by map-manifest tooling.

## API conventions

FiveFury keeps the authoring layer close to the data model:

- Typed collections use ordinary `append(...)` and `extend(...)` operations; there is no generic dispatcher that guesses the destination from a runtime type.
- Singular noun factories such as `entity(...)`, `bone(...)`, `light(...)`, and `car_gen(...)` construct, register, and return one domain object.
- One-to-one relationships use assignment, such as `ydr.bound = collision`; verbs are reserved for real operations such as `ensure_*`, `derive_*`, `normalize_*`, `bind_*`, and `resolve_*`.
- `AssetRef`, `AssetSet`, and `BuildContext` provide one typed path for resolving dependencies between assets and selecting Legacy or Enhanced behavior.
- `ValidationReport` carries stable diagnostic codes, severity, asset, and field paths instead of relying on unstructured output.
- `build()` derives normalized state, `validate()` inspects it, and `save()` validates and performs atomic binary serialization.
- Stable game-side values use enums for targets, shaders, LODs, flags, render masks, materials, and track formats.
- Core writers use atomic replacement and reject known invalid references, ownership, pointers, or packed ranges before replacing the destination.

The full naming, module-boundary, compatibility, performance, and review rules are normative in [`docs/STYLE_GUIDE.md`](docs/STYLE_GUIDE.md).

## Scope and guarantees

FiveFury aims for runtime-compatible binary output, but GTA V formats contain edition-specific and asset-specific structures. Passing validation proves the modeled binary invariants; it is not a substitute for testing newly authored content in the target game.

`YFT`, `REL`, `YED`, and `YMT` expose substantial read/write functionality, but not every runtime subtype is modeled semantically. Unknown metadata is preserved where the container supports lossless rewriting instead of being guessed. PS3 `CDR` and RPF support is currently focused on reading and extraction, while PC RPF7 supports authoring.

## License

FiveFury is released under [The Unlicense](LICENSE).

See [CHANGELOG.md](CHANGELOG.md) for release history and compatibility notes.

## Credits

Thomas Vanini — GTA V Enhanced PT-BR dubbing project creator, workflow coordinator, and in-game runtime validation — https://linktr.ee/ThomasVanini
