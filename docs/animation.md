# Animation Dictionaries

YCD clip dictionary notes and helpers.
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
