# Bounds and Collisions

YBN and shared bounds authoring examples.
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
