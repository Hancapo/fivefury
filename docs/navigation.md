# Navigation

YND path nodes and YNV navmesh workflows.
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

### Generate a junction heightmap

```python
from fivefury import YndNode

node = YndNode(position=(0.0, 0.0, 0.0))
node.ensure_junction_heightmap(
    triangles=[
        ((-1.0, -1.0, 0.0), (1.0, -1.0, 0.25), (-1.0, 1.0, 0.25)),
        ((1.0, -1.0, 0.25), (1.0, 1.0, 0.5), (-1.0, 1.0, 0.25)),
    ],
    bounds=((-1.0, -1.0), (1.0, 1.0)),
    dim_x=2,
    dim_y=2,
)
```

YND junction heightmaps follow the runtime layout used by GTA V virtual junctions: `position` stores the minimum X/Y sample origin, samples are row-major, the default grid spacing is `2.0` world units, and byte values decode as `min_z + byte * ((max_z - min_z) / 256.0)`.
## YNV

### Read and validate a YNV

```python
from fivefury import read_ynv

ynv = read_ynv("navmesh[120][120].ynv")

print(ynv.area_id)
print(len(ynv.polys))
print(len(ynv.vertices))
print(ynv.validate())
```

`YNV` support currently includes:

- typed `YnvAdjacencyType`, `YnvPointType`, and `YnvPortalType`
- editable `vertices`, `indices`, `edges`, `polys`, `portals`, and `sector_tree`
- `build()` to normalize derived fields such as `points_start_id` and content flags
- `validate()` to catch invalid poly spans, portal-link spans, and sector metadata mismatches before writing

### Split an OBJ into per-cell navmeshes

```python
from fivefury import obj_to_nav

paths = obj_to_nav(
    "test.obj",
    "out_navmeshes",
)

print(len(paths))
print(paths[0].name)
```

`obj_to_nav(...)` is a simple Assimp-backed helper that:

- reads geometry through the shared Assimp pipeline
- clips triangles against GTA V navmesh cells
- writes one `YNV` per touched cell
- names outputs as `navmesh[file_x][file_y].ynv`

This is intentionally a basic geometry partitioner, not a full navgen pipeline. It does not yet generate advanced navigation semantics such as cover, climb/drop adjacencies, portals, or point placement.
