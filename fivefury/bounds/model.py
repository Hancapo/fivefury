from __future__ import annotations

import dataclasses
import enum
from collections import Counter
from typing import Iterator


class BoundType(enum.IntEnum):
    SPHERE = 0
    CAPSULE = 1
    BOX = 3
    GEOMETRY = 4
    GEOMETRY_BVH = 8
    COMPOSITE = 10
    DISC = 12
    CYLINDER = 13
    CLOTH = 15


class BoundPolygonType(enum.IntEnum):
    TRIANGLE = 0
    SPHERE = 1
    CAPSULE = 2
    BOX = 3
    CYLINDER = 4


@dataclasses.dataclass(slots=True)
class BoundAabb:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]


@dataclasses.dataclass(slots=True)
class BoundTransform:
    column1: tuple[float, float, float]
    column2: tuple[float, float, float]
    column3: tuple[float, float, float]
    column4: tuple[float, float, float]
    flags1: int = 0
    flags2: int = 0
    flags3: int = 0
    flags4: int = 0

    @property
    def translation(self) -> tuple[float, float, float]:
        return self.column4


@dataclasses.dataclass(slots=True)
class BoundCompositeFlags:
    flags1: int = 0
    flags2: int = 0


@dataclasses.dataclass(slots=True)
class BoundMaterial:
    type: int = 0
    procedural_id: int = 0
    room_id: int = 0
    ped_density: int = 0
    flags: int = 0
    material_color_index: int = 0
    unknown: int = 0
    data1: int = 0
    data2: int = 0

    @property
    def name(self) -> str:
        from .materials import get_bound_material_name

        return get_bound_material_name(self.type)

    @property
    def color(self) -> tuple[int, int, int]:
        from .materials import get_bound_material_color

        return get_bound_material_color(self.type)


@dataclasses.dataclass(slots=True)
class BoundMaterialColor:
    r: int = 0
    g: int = 0
    b: int = 0
    a: int = 0

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        return (self.r, self.g, self.b, self.a)


@dataclasses.dataclass(slots=True)
class BoundBvhNode:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    item_id: int
    item_count: int

    @property
    def is_leaf(self) -> bool:
        return self.item_count > 0


@dataclasses.dataclass(slots=True)
class BoundBvhTree:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    node_index: int
    node_index2: int


@dataclasses.dataclass(slots=True)
class BoundBvh:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    center: tuple[float, float, float]
    quantum_inverse: tuple[float, float, float]
    quantum: tuple[float, float, float]
    nodes: list[BoundBvhNode] = dataclasses.field(default_factory=list)
    trees: list[BoundBvhTree] = dataclasses.field(default_factory=list)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def tree_count(self) -> int:
        return len(self.trees)

    @property
    def leaf_nodes(self) -> list[BoundBvhNode]:
        return [node for node in self.nodes if node.is_leaf]


@dataclasses.dataclass(slots=True)
class BoundPolygon:
    polygon_type: BoundPolygonType
    raw: bytes
    index: int = -1
    material_index: int = -1

    @property
    def vertex_indices(self) -> tuple[int, ...]:
        return ()


@dataclasses.dataclass(slots=True)
class BoundPolygonTriangle(BoundPolygon):
    tri_area: float = 0.0
    tri_index1: int = 0
    tri_index2: int = 0
    tri_index3: int = 0
    edge_index1: int = 0xFFFF
    edge_index2: int = 0xFFFF
    edge_index3: int = 0xFFFF

    @property
    def vert_index1(self) -> int:
        return self.tri_index1 & 0x7FFF

    @property
    def vert_index2(self) -> int:
        return self.tri_index2 & 0x7FFF

    @property
    def vert_index3(self) -> int:
        return self.tri_index3 & 0x7FFF

    @property
    def vert_flag1(self) -> bool:
        return (self.tri_index1 & 0x8000) != 0

    @property
    def vert_flag2(self) -> bool:
        return (self.tri_index2 & 0x8000) != 0

    @property
    def vert_flag3(self) -> bool:
        return (self.tri_index3 & 0x8000) != 0

    @property
    def vertex_indices(self) -> tuple[int, int, int]:
        return (self.vert_index1, self.vert_index2, self.vert_index3)


@dataclasses.dataclass(slots=True)
class BoundPolygonSphere(BoundPolygon):
    sphere_type: int = 0
    sphere_index: int = 0
    sphere_radius: float = 0.0
    unused0: int = 0
    unused1: int = 0

    @property
    def vertex_indices(self) -> tuple[int]:
        return (self.sphere_index,)


@dataclasses.dataclass(slots=True)
class BoundPolygonCapsule(BoundPolygon):
    capsule_type: int = 0
    capsule_index1: int = 0
    capsule_radius: float = 0.0
    capsule_index2: int = 0
    unused0: int = 0
    unused1: int = 0

    @property
    def vertex_indices(self) -> tuple[int, int]:
        return (self.capsule_index1, self.capsule_index2)


@dataclasses.dataclass(slots=True)
class BoundPolygonBox(BoundPolygon):
    box_type: int = 0
    box_index1: int = 0
    box_index2: int = 0
    box_index3: int = 0
    box_index4: int = 0
    unused0: int = 0

    @property
    def vertex_indices(self) -> tuple[int, int, int, int]:
        return (self.box_index1, self.box_index2, self.box_index3, self.box_index4)


@dataclasses.dataclass(slots=True)
class BoundPolygonCylinder(BoundPolygon):
    cylinder_type: int = 0
    cylinder_index1: int = 0
    cylinder_radius: float = 0.0
    cylinder_index2: int = 0
    unused0: int = 0
    unused1: int = 0

    @property
    def vertex_indices(self) -> tuple[int, int]:
        return (self.cylinder_index1, self.cylinder_index2)


@dataclasses.dataclass(slots=True)
class Bound:
    bound_type: BoundType
    sphere_radius: float
    box_max: tuple[float, float, float]
    margin: float
    box_min: tuple[float, float, float]
    box_center: tuple[float, float, float]
    sphere_center: tuple[float, float, float]
    material_index: int = 0
    procedural_id: int = 0
    room_id: int = 0
    ped_density: int = 0
    unk_flags: int = 0
    poly_flags: int = 0
    material_color_index: int = 0
    unknown_3ch: int = 1
    unknown_60h: tuple[float, float, float] = (0.0, 0.0, 0.0)
    volume: float = 0.0

    @property
    def bounds(self) -> BoundAabb:
        return BoundAabb(self.box_min, self.box_max)

    @property
    def type_name(self) -> str:
        return self.bound_type.name

    @property
    def is_geometry(self) -> bool:
        return self.bound_type in {BoundType.GEOMETRY, BoundType.GEOMETRY_BVH}

    @property
    def is_composite(self) -> bool:
        return self.bound_type is BoundType.COMPOSITE

    def walk(self) -> Iterator[Bound]:
        yield self
        if isinstance(self, BoundComposite):
            for child in self.children:
                yield from child.bound.walk()

    def iter_geometries(self) -> Iterator[BoundGeometry]:
        for bound in self.walk():
            if isinstance(bound, BoundGeometry):
                yield bound

    @property
    def geometries(self) -> list[BoundGeometry]:
        return list(self.iter_geometries())

    @property
    def geometry_count(self) -> int:
        return len(self.geometries)

    @property
    def leaf_bounds(self) -> list[Bound]:
        return [bound for bound in self.walk() if not isinstance(bound, BoundComposite)]


@dataclasses.dataclass(slots=True)
class BoundSphere(Bound):
    pass


@dataclasses.dataclass(slots=True)
class BoundBox(Bound):
    pass


@dataclasses.dataclass(slots=True)
class BoundCapsule(Bound):
    unknown_70h: int = 0
    unknown_74h: int = 0
    unknown_78h: int = 0
    unknown_7ch: int = 0


@dataclasses.dataclass(slots=True)
class BoundDisc(Bound):
    unknown_70h: int = 0
    unknown_74h: int = 0
    unknown_78h: int = 0
    unknown_7ch: int = 0


@dataclasses.dataclass(slots=True)
class BoundCylinder(Bound):
    unknown_70h: int = 0
    unknown_74h: int = 0
    unknown_78h: int = 0
    unknown_7ch: int = 0


@dataclasses.dataclass(slots=True)
class BoundCloth(Bound):
    unknown_70h: int = 0
    unknown_74h: int = 0
    unknown_78h: int = 0
    unknown_7ch: int = 0


@dataclasses.dataclass(slots=True)
class BoundGeometry(Bound):
    quantum: tuple[float, float, float] = (1.0, 1.0, 1.0)
    center_geom: tuple[float, float, float] = (0.0, 0.0, 0.0)
    vertices: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    vertices_shrunk: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    polygons: list[BoundPolygon] = dataclasses.field(default_factory=list)
    polygon_material_indices: list[int] = dataclasses.field(default_factory=list)
    materials: list[BoundMaterial] = dataclasses.field(default_factory=list)
    material_colours: list[BoundMaterialColor] = dataclasses.field(default_factory=list)
    vertex_colours: list[BoundMaterialColor] = dataclasses.field(default_factory=list)

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def polygon_count(self) -> int:
        return len(self.polygons)

    def get_material(self, index: int) -> BoundMaterial | None:
        if 0 <= index < len(self.materials):
            return self.materials[index]
        return None

    def get_polygon_material(self, polygon: BoundPolygon | int) -> BoundMaterial | None:
        poly = self.polygons[int(polygon)] if isinstance(polygon, int) else polygon
        return self.get_material(poly.material_index)

    @property
    def polygon_type_counts(self) -> dict[BoundPolygonType, int]:
        counts = Counter(polygon.polygon_type for polygon in self.polygons)
        return dict(counts)

    @property
    def has_vertex_colours(self) -> bool:
        return bool(self.vertex_colours)


@dataclasses.dataclass(slots=True)
class BoundBVH(BoundGeometry):
    bvh_pointer: int = 0
    bvh: BoundBvh | None = None

    @property
    def has_bvh(self) -> bool:
        return self.bvh is not None


@dataclasses.dataclass(slots=True)
class BoundChild:
    bound: Bound
    transform: BoundTransform | None = None
    bounds: BoundAabb | None = None
    flags1: BoundCompositeFlags | None = None
    flags2: BoundCompositeFlags | None = None


@dataclasses.dataclass(slots=True)
class BoundComposite(Bound):
    children: list[BoundChild] = dataclasses.field(default_factory=list)
    bvh_pointer: int = 0

    @property
    def child_count(self) -> int:
        return len(self.children)

    def iter_children(self) -> Iterator[BoundChild]:
        yield from self.children


__all__ = [
    'Bound',
    'BoundAabb',
    'BoundBvh',
    'BoundBvhNode',
    'BoundBvhTree',
    'BoundBox',
    'BoundBVH',
    'BoundCapsule',
    'BoundChild',
    'BoundCloth',
    'BoundComposite',
    'BoundCompositeFlags',
    'BoundCylinder',
    'BoundDisc',
    'BoundGeometry',
    'BoundMaterial',
    'BoundMaterialColor',
    'BoundPolygon',
    'BoundPolygonBox',
    'BoundPolygonCapsule',
    'BoundPolygonCylinder',
    'BoundPolygonSphere',
    'BoundPolygonTriangle',
    'BoundPolygonType',
    'BoundSphere',
    'BoundTransform',
    'BoundType',
]
