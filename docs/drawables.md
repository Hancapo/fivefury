# Drawables and Fragments

YDR, YDD, and YFT workflows for drawable assets and fragment physics.
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
- skeleton helpers for bones, skinning, radial weight generation, rigid bone bindings, and explicit skeleton hash recalculation
- `build()` / `validate()` helpers for authoring flows

### Generate radial skin weights

```python
from fivefury import RadialBoneRigRule, read_ydd, rig_ydd_to_bones_radially

body = read_ydd("tdev_xyuls^lowr_000_u.ydd")
skeleton_source = read_ydd("tdev_xyuls^head_000_u.ydd")

report = rig_ydd_to_bones_radially(
    body,
    [
        RadialBoneRigRule("SM_R_BackSkirtRoll", radius=0.16, strength=0.65),
        RadialBoneRigRule("SM_L_BackSkirtRoll", radius=0.16, strength=0.65),
    ],
    skeleton_source=skeleton_source,
)

print(report.vertices)
body.save("tdev_xyuls^lowr_000_u_rigged.ydd")
```

For body folders where `head_000_u.ydd` carries the skeleton and `uppr/lowr` carry the meshes, use the convenience pass:

```python
from fivefury import rig_body_folder_jiggle_bones

report = rig_body_folder_jiggle_bones(
    r"C:\mods\body",
    output_folder=r"C:\mods\body_rigged",
)
print(report.saved_files)
```

The helper preserves existing skinning and reuses ped-component palettes that already store external skeleton indices. It only adds or adjusts vertex influences around the requested jiggle bones; it does not generate cloth simulation data by itself.

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

These helpers require `impasse` plus a native `assimp` library that is already discoverable by the current process.

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
## YFT

`YFT` fragment support is aimed at practical read/edit/write workflows for objects with drawable variants and physics metadata. It shares the same drawable writer used by `YDR`, and the same bounds model used by `YBN`.

### Read and inspect a fragment

```python
from fivefury import read_yft

yft = read_yft("prop_vehicle_fragment.yft")

print(yft.name)
print(yft.bounding_sphere)
print(yft.geometry_stats())

for issue in yft.validate():
    print(issue.severity, issue.message)

for child in yft.iter_physics_children():
    print(child.owner_group_name, child.undamaged_mass, child.undamaged_ang_inertia)
```

### Create a simple fragment from a drawable

```python
from fivefury import BoundBox, BoundMaterialType, create_yft, read_ydr, save_yft

drawable = read_ydr("crate.ydr")
physics_bound = BoundBox.from_center_size(
    center=(0.0, 0.0, 0.5),
    size=(1.0, 1.0, 1.0),
    material_index=BoundMaterialType.WOOD_SOLID_MEDIUM,
)

yft = create_yft(
    drawable,
    name="crate_fragment",
    physics_bound=physics_bound,
    physics_density=0.65,
)

yft.validate()
save_yft(yft, "crate_fragment.yft")
```

Current `YFT` authoring covers common fragment structure, embedded drawables, geometry and material payloads, fragment flags, bounding sphere metadata, physics LODs, groups, children, damping, articulated body metadata, event refs, mass/inertia helpers, editable composite bounds, and embedded texture dictionaries. Vehicle-specific behavior, advanced damage tuning, and every unknown fragment field are still conservative.
