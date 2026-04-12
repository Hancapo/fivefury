from __future__ import annotations

import dataclasses
import enum
import math
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


def _normalize_aabb(bounds: BoundAabb) -> BoundAabb:
    return BoundAabb(
        minimum=tuple(min(bounds.minimum[axis], bounds.maximum[axis]) for axis in range(3)),
        maximum=tuple(max(bounds.minimum[axis], bounds.maximum[axis]) for axis in range(3)),
    )


def _aabb_is_valid(bounds: BoundAabb) -> bool:
    return all(bounds.minimum[axis] <= bounds.maximum[axis] for axis in range(3))


def _merge_bounds(bounds: list[BoundAabb], fallback: BoundAabb) -> BoundAabb:
    if not bounds:
        return fallback
    minimum = tuple(min(item.minimum[axis] for item in bounds) for axis in range(3))
    maximum = tuple(max(item.maximum[axis] for item in bounds) for axis in range(3))
    return BoundAabb(minimum, maximum)


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


class BoundCompositeFlag(enum.IntFlag):
    NONE = 0
    UNKNOWN = 1 << 0
    MAP_WEAPON = 1 << 1
    MAP_DYNAMIC = 1 << 2
    MAP_ANIMAL = 1 << 3
    MAP_COVER = 1 << 4
    MAP_VEHICLE = 1 << 5
    VEHICLE_NOT_BVH = 1 << 6
    VEHICLE_BVH = 1 << 7
    VEHICLE_BOX = 1 << 8
    PED = 1 << 9
    RAGDOLL = 1 << 10
    ANIMAL = 1 << 11
    ANIMAL_RAGDOLL = 1 << 12
    OBJECT = 1 << 13
    OBJECT_ENV_CLOTH = 1 << 14
    PLANT = 1 << 15
    PROJECTILE = 1 << 16
    EXPLOSION = 1 << 17
    PICKUP = 1 << 18
    FOLIAGE = 1 << 19
    FORKLIFT_FORKS = 1 << 20
    TEST_WEAPON = 1 << 21
    TEST_CAMERA = 1 << 22
    TEST_AI = 1 << 23
    TEST_SCRIPT = 1 << 24
    TEST_VEHICLE_WHEEL = 1 << 25
    GLASS = 1 << 26
    MAP_RIVER = 1 << 27
    SMOKE = 1 << 28
    UNSMASHED = 1 << 29
    MAP_STAIRS = 1 << 30
    MAP_DEEP_SURFACE = 1 << 31


def _transform_point(point: tuple[float, float, float], transform: BoundTransform | None) -> tuple[float, float, float]:
    if transform is None:
        return point
    return (
        (transform.column1[0] * point[0]) + (transform.column2[0] * point[1]) + (transform.column3[0] * point[2]) + transform.column4[0],
        (transform.column1[1] * point[0]) + (transform.column2[1] * point[1]) + (transform.column3[1] * point[2]) + transform.column4[1],
        (transform.column1[2] * point[0]) + (transform.column2[2] * point[1]) + (transform.column3[2] * point[2]) + transform.column4[2],
    )


def _transform_bounds(bounds: BoundAabb, transform: BoundTransform | None) -> BoundAabb:
    if transform is None:
        return bounds
    minimum = bounds.minimum
    maximum = bounds.maximum
    corners = [
        _transform_point((x, y, z), transform)
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    ]
    transformed_minimum = tuple(min(point[axis] for point in corners) for axis in range(3))
    transformed_maximum = tuple(max(point[axis] for point in corners) for axis in range(3))
    return BoundAabb(transformed_minimum, transformed_maximum)


def _sphere_radius_from_bounds(bounds: BoundAabb, center: tuple[float, float, float]) -> float:
    return math.sqrt(
        max(abs(bounds.minimum[0] - center[0]), abs(bounds.maximum[0] - center[0])) ** 2
        + max(abs(bounds.minimum[1] - center[1]), abs(bounds.maximum[1] - center[1])) ** 2
        + max(abs(bounds.minimum[2] - center[2]), abs(bounds.maximum[2] - center[2])) ** 2
    )


@dataclasses.dataclass(slots=True)
class BoundCompositeFlags:
    flags1: BoundCompositeFlag = BoundCompositeFlag.NONE
    flags2: BoundCompositeFlag = BoundCompositeFlag.NONE

    @property
    def type_flags(self) -> BoundCompositeFlag:
        return self.flags1

    @type_flags.setter
    def type_flags(self, value: BoundCompositeFlag | int) -> None:
        self.flags1 = BoundCompositeFlag(int(value))

    @property
    def include_flags(self) -> BoundCompositeFlag:
        return self.flags2

    @include_flags.setter
    def include_flags(self, value: BoundCompositeFlag | int) -> None:
        self.flags2 = BoundCompositeFlag(int(value))


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
class BoundResourcePagesInfo:
    unknown_0h: int = 0
    unknown_4h: int = 0
    system_pages_count: int = 0
    graphics_pages_count: int = 0
    unknown_ah: int = 0
    unknown_ch: int = 0

    @property
    def total_page_count(self) -> int:
        return int(self.system_pages_count) + int(self.graphics_pages_count)


_OCTANT_SIGNS: tuple[tuple[int, int, int], ...] = (
    (1, 1, 1),
    (-1, 1, 1),
    (1, -1, 1),
    (-1, -1, 1),
    (1, 1, -1),
    (-1, 1, -1),
    (1, -1, -1),
    (-1, -1, -1),
)


def _normalize_octant_items(items: list[list[int]] | tuple[tuple[int, ...], ...] | None) -> list[list[int]]:
    source = list(items or [])
    normalized = [list(map(int, source[index])) if index < len(source) else [] for index in range(8)]
    return normalized


def _octant_shadowed(
    vertex1: tuple[float, float, float],
    vertex2: tuple[float, float, float],
    signs: tuple[int, int, int],
) -> bool:
    direction = (
        (vertex2[0] - vertex1[0]) * signs[0],
        (vertex2[1] - vertex1[1]) * signs[1],
        (vertex2[2] - vertex1[2]) * signs[2],
    )
    return direction[0] >= 0.0 and direction[1] >= 0.0 and direction[2] >= 0.0


@dataclasses.dataclass(slots=True)
class BoundGeometryOctants:
    items: list[list[int]] = dataclasses.field(default_factory=lambda: [[] for _ in range(8)])

    def __post_init__(self) -> None:
        self.items = _normalize_octant_items(self.items)

    @classmethod
    def from_vertices(
        cls,
        vertices: list[tuple[float, float, float]],
    ) -> "BoundGeometryOctants":
        octant_items: list[list[int]] = [[] for _ in range(8)]
        for octant_index, signs in enumerate(_OCTANT_SIGNS):
            indices: list[int] = []
            for vertex_index, vertex in enumerate(vertices):
                should_add = True
                next_indices: list[int] = []
                for other_index in indices:
                    other_vertex = vertices[other_index]
                    if _octant_shadowed(vertex, other_vertex, signs):
                        should_add = False
                        next_indices = indices
                        break
                    if not _octant_shadowed(other_vertex, vertex, signs):
                        next_indices.append(other_index)
                if should_add:
                    next_indices.append(vertex_index)
                indices = next_indices
            octant_items[octant_index] = indices
        return cls(items=octant_items)

    @property
    def counts(self) -> tuple[int, int, int, int, int, int, int, int]:
        return tuple(len(items) for items in self.items)  # type: ignore[return-value]

    @property
    def total_items(self) -> int:
        return sum(len(items) for items in self.items)

    @property
    def has_items(self) -> bool:
        return any(self.items)

    def validate(self, vertex_count: int) -> list[str]:
        issues: list[str] = []
        if len(self.items) != 8:
            issues.append("octants must contain exactly 8 item lists")
            return issues
        for octant_index, indices in enumerate(self.items):
            for vertex_index in indices:
                if vertex_index < 0 or vertex_index >= vertex_count:
                    issues.append(f"octant {octant_index} references invalid vertex index {vertex_index}")
        return issues


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

    @staticmethod
    def pack_edge_index(polygon_index: int) -> int:
        if polygon_index < 0 or polygon_index > 0xFFFF:
            return 0xFFFF
        return int(polygon_index)

    @staticmethod
    def unpack_edge_index(edge_index: int) -> int:
        if edge_index == 0xFFFF:
            return -1
        return int(edge_index)

    @property
    def adjacent_polygon_indices(self) -> tuple[int, int, int]:
        return (
            self.unpack_edge_index(self.edge_index1),
            self.unpack_edge_index(self.edge_index2),
            self.unpack_edge_index(self.edge_index3),
        )


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
    file_vft: int = 0
    file_unknown: int = 1
    file_pages_info: BoundResourcePagesInfo | None = None
    unknown_11h: int = 0
    unknown_12h: int = 0
    unknown_18h: int = 0
    unknown_1ch: int = 0
    material_index: int = 0
    procedural_id: int = 0
    room_id: int = 0
    ped_density: int = 0
    unk_flags: int = 0
    poly_flags: int = 0
    material_color_index: int = 0
    unknown_3ch: int = 1
    unknown_5eh: int = 0
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

    def build(self) -> "Bound":
        normalized = _normalize_aabb(self.bounds)
        self.box_min = normalized.minimum
        self.box_max = normalized.maximum
        self.box_center = tuple((normalized.minimum[axis] + normalized.maximum[axis]) * 0.5 for axis in range(3))
        return self

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.sphere_radius < 0:
            issues.append(f"{self.type_name} has negative sphere_radius")
        if not _aabb_is_valid(self.bounds):
            issues.append(f"{self.type_name} has inverted box bounds")
        return issues


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
    octants: BoundGeometryOctants | None = None

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

    @property
    def has_octants(self) -> bool:
        return self.octants is not None and self.octants.has_items

    def add_vertex(self, vertex: tuple[float, float, float]) -> tuple[float, float, float]:
        value = (float(vertex[0]), float(vertex[1]), float(vertex[2]))
        self.vertices.append(value)
        return value

    def add_polygon(self, polygon: BoundPolygon) -> BoundPolygon:
        if polygon.index < 0:
            polygon.index = len(self.polygons)
        self.polygons.append(polygon)
        if polygon.material_index >= 0:
            self.polygon_material_indices.append(int(polygon.material_index))
        return polygon

    def add_material(self, material: BoundMaterial) -> BoundMaterial:
        self.materials.append(material)
        return material

    def build(self) -> "BoundGeometry":
        super().build()
        for index, polygon in enumerate(self.polygons):
            polygon.index = index
            if isinstance(polygon, BoundPolygonTriangle):
                polygon.edge_index1 = BoundPolygonTriangle.pack_edge_index(
                    BoundPolygonTriangle.unpack_edge_index(polygon.edge_index1)
                )
                polygon.edge_index2 = BoundPolygonTriangle.pack_edge_index(
                    BoundPolygonTriangle.unpack_edge_index(polygon.edge_index2)
                )
                polygon.edge_index3 = BoundPolygonTriangle.pack_edge_index(
                    BoundPolygonTriangle.unpack_edge_index(polygon.edge_index3)
                )
        if len(self.polygon_material_indices) != len(self.polygons):
            self.polygon_material_indices = [max(0, int(polygon.material_index)) for polygon in self.polygons]
        if self.bound_type is BoundType.GEOMETRY:
            if not self.vertices_shrunk and self.vertices:
                self.vertices_shrunk = list(self.vertices)
            if self.octants is None and self.vertices_shrunk:
                self.octants = BoundGeometryOctants.from_vertices(self.vertices_shrunk)
        else:
            self.octants = None
        return self

    def validate(self) -> list[str]:
        issues = super().validate()
        if len(self.polygon_material_indices) != len(self.polygons):
            issues.append("polygon_material_indices length does not match polygon count")
        for polygon_index, polygon in enumerate(self.polygons):
            for vertex_index in polygon.vertex_indices:
                if vertex_index < 0 or vertex_index >= self.vertex_count:
                    issues.append(
                        f"polygon {polygon_index} references invalid vertex index {vertex_index}"
                    )
            if isinstance(polygon, BoundPolygonTriangle):
                for edge_slot, edge_polygon_index in enumerate(polygon.adjacent_polygon_indices, start=1):
                    if edge_polygon_index >= self.polygon_count:
                        issues.append(
                            f"polygon {polygon_index} edge {edge_slot} references invalid polygon index {edge_polygon_index}"
                        )
            material_index = (
                int(polygon.material_index)
                if polygon.material_index >= 0
                else int(self.polygon_material_indices[polygon_index])
                if polygon_index < len(self.polygon_material_indices)
                else -1
            )
            if material_index < 0:
                issues.append(f"polygon {polygon_index} has no valid material index")
            elif self.materials and material_index >= len(self.materials):
                issues.append(
                    f"polygon {polygon_index} references invalid material index {material_index}"
                )
        if self.octants is not None:
            issues.extend(self.octants.validate(self.vertex_count))
        return issues


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
    bvh: BoundBvh | None = None

    @property
    def child_count(self) -> int:
        return len(self.children)

    @property
    def has_bvh(self) -> bool:
        return self.bvh is not None

    def iter_children(self) -> Iterator[BoundChild]:
        yield from self.children

    def add_child(
        self,
        bound: Bound,
        *,
        transform: BoundTransform | None = None,
        bounds: BoundAabb | None = None,
        flags1: BoundCompositeFlags | None = None,
        flags2: BoundCompositeFlags | None = None,
    ) -> BoundChild:
        child = BoundChild(bound=bound, transform=transform, bounds=bounds, flags1=flags1, flags2=flags2)
        self.children.append(child)
        return child

    def build(self) -> "BoundComposite":
        super().build()
        for child in self.children:
            child.bound.build()
            if child.bounds is None or not _aabb_is_valid(child.bounds):
                child.bounds = child.bound.bounds
        if self.children:
            transformed_bounds = [
                _transform_bounds(child.bounds if child.bounds is not None else child.bound.bounds, child.transform)
                for child in self.children
            ]
            overall = _merge_bounds(transformed_bounds, self.bounds)
            center = tuple((overall.minimum[axis] + overall.maximum[axis]) * 0.5 for axis in range(3))
            self.box_min = overall.minimum
            self.box_max = overall.maximum
            self.box_center = center
            self.sphere_center = center
            self.sphere_radius = _sphere_radius_from_bounds(overall, center)
            if len(self.children) <= 5:
                self.bvh = None
        else:
            self.bvh = None
        return self

    def validate(self) -> list[str]:
        issues = super().validate()
        if not self.children:
            issues.append("Composite bound has no children")
        for index, child in enumerate(self.children):
            if child.bounds is not None and not _aabb_is_valid(child.bounds):
                issues.append(f"child {index} has inverted local bounds")
            issues.extend(child.bound.validate())
        return issues


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
    'BoundCompositeFlag',
    'BoundCompositeFlags',
    'BoundCylinder',
    'BoundDisc',
    'BoundGeometry',
    'BoundGeometryOctants',
    'BoundMaterial',
    'BoundMaterialColor',
    'BoundPolygon',
    'BoundPolygonBox',
    'BoundPolygonCapsule',
    'BoundPolygonCylinder',
    'BoundPolygonSphere',
    'BoundPolygonTriangle',
    'BoundPolygonType',
    'BoundResourcePagesInfo',
    'BoundSphere',
    'BoundTransform',
    'BoundType',
]
