from __future__ import annotations

import dataclasses
import enum
import math
from collections import Counter
from collections.abc import Iterator

from .. import _native as _native_backend
from ..authoring.diagnostics import ValidationReport
from ..resource import ResourcePagesInfo
from ..vector import Aabb3, Vector3
from .materials import (
    BoundMaterialType,
    coerce_bound_material_index,
    get_bound_material_type,
)


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


class BoundAxis(enum.IntEnum):
    X = 0
    Y = 1
    Z = 2

    def component(self, value: Vector3) -> float:
        if self is BoundAxis.X:
            return value.x
        if self is BoundAxis.Y:
            return value.y
        return value.z


class BoundPolygonType(enum.IntEnum):
    TRIANGLE = 0
    SPHERE = 1
    CAPSULE = 2
    BOX = 3
    CYLINDER = 4


@dataclasses.dataclass(slots=True)
class BoundAabb:
    minimum: Vector3
    maximum: Vector3

    def __post_init__(self) -> None:
        if not isinstance(self.minimum, Vector3) or not isinstance(self.maximum, Vector3):
            raise TypeError("BoundAabb minimum and maximum must be Vector3 instances")


def _normalize_aabb(bounds: BoundAabb) -> BoundAabb:
    return BoundAabb(
        minimum=Vector3(
            min(bounds.minimum.x, bounds.maximum.x),
            min(bounds.minimum.y, bounds.maximum.y),
            min(bounds.minimum.z, bounds.maximum.z),
        ),
        maximum=Vector3(
            max(bounds.minimum.x, bounds.maximum.x),
            max(bounds.minimum.y, bounds.maximum.y),
            max(bounds.minimum.z, bounds.maximum.z),
        ),
    )


def _aabb_is_valid(bounds: BoundAabb) -> bool:
    return (
        bounds.minimum.is_finite
        and bounds.maximum.is_finite
        and bounds.minimum.x <= bounds.maximum.x
        and bounds.minimum.y <= bounds.maximum.y
        and bounds.minimum.z <= bounds.maximum.z
    )


def _merge_bounds(bounds: list[BoundAabb], fallback: BoundAabb) -> BoundAabb:
    if not bounds:
        return fallback
    return BoundAabb(
        Vector3.minimum(item.minimum for item in bounds),
        Vector3.maximum(item.maximum for item in bounds),
    )


def _aabb_from_center_size(center: Vector3, size: Vector3) -> BoundAabb:
    bounds = Aabb3.from_center_size(center, size)
    return BoundAabb(bounds.minimum, bounds.maximum)


@dataclasses.dataclass(slots=True)
class BoundTransform:
    column1: Vector3
    column2: Vector3
    column3: Vector3
    column4: Vector3
    flags1: int = 0
    flags2: int = 0
    flags3: int = 0
    flags4: int = 0

    @property
    def translation(self) -> Vector3:
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


class BoundFlag(enum.IntFlag):
    NONE = 0
    OCTANT_MAP_INDEX_IS_U16 = 1 << 0
    GEOMETRY_BOUND_HAS_OCTANT_MAP = 1 << 1
    FORCE_CCD = 1 << 2
    USE_NEW_BACK_FACE_CULL = 1 << 3
    USE_PROJECTION_EDGE_FILTERING = 1 << 4
    USE_CURRENT_INSTANCE_MATRIX_ONLY = 1 << 5


def _transform_point(point: Vector3, transform: BoundTransform | None) -> Vector3:
    if transform is None:
        return point
    return Vector3(
        (transform.column1.x * point.x) + (transform.column2.x * point.y) + (transform.column3.x * point.z) + transform.column4.x,
        (transform.column1.y * point.x) + (transform.column2.y * point.y) + (transform.column3.y * point.z) + transform.column4.y,
        (transform.column1.z * point.x) + (transform.column2.z * point.y) + (transform.column3.z * point.z) + transform.column4.z,
    )


def _transform_bounds(bounds: BoundAabb, transform: BoundTransform | None) -> BoundAabb:
    if transform is None:
        return bounds
    minimum = bounds.minimum
    maximum = bounds.maximum
    corners = [
        _transform_point(Vector3(x, y, z), transform)
        for x in (minimum.x, maximum.x)
        for y in (minimum.y, maximum.y)
        for z in (minimum.z, maximum.z)
    ]
    return BoundAabb(Vector3.minimum(corners), Vector3.maximum(corners))


def _sphere_radius_from_bounds(bounds: BoundAabb, center: Vector3) -> float:
    extent = Vector3(
        max(abs(bounds.minimum.x - center.x), abs(bounds.maximum.x - center.x)),
        max(abs(bounds.minimum.y - center.y), abs(bounds.maximum.y - center.y)),
        max(abs(bounds.minimum.z - center.z), abs(bounds.maximum.z - center.z)),
    )
    return extent.length


def _box_volume_distribution(size: Vector3) -> Vector3:
    x, y, z = abs(size.x), abs(size.y), abs(size.z)
    return Vector3(((y * y) + (z * z)) / 12.0, ((x * x) + (z * z)) / 12.0, ((x * x) + (y * y)) / 12.0)


def _sphere_volume_distribution(radius: float) -> Vector3:
    value = 0.4 * float(radius) * float(radius)
    return Vector3(value, value, value)


def _cylinder_volume_distribution(radius: float, length: float) -> Vector3:
    radius2 = float(radius) * float(radius)
    central = (radius2 * 0.25) + ((float(length) * float(length)) / 12.0)
    radial = radius2 * 0.5
    return Vector3(central, radial, central)


def _capsule_volume_distribution(radius: float, length: float) -> Vector3:
    radius = float(radius)
    length = float(length)
    denominator = length + (4.0 / 3.0) * radius
    if denominator <= 0.0:
        return Vector3()
    inverse = 1.0 / denominator
    radius2 = radius * radius
    radial = 0.5 * radius2 * (length + 1.0666666666667 * radius) * inverse
    length2 = length * length
    central = (
        (1.0 / 3.0)
        * (
            0.25 * length * length2
            + radius * length2
            + 2.25 * length * radius2
            + 1.6 * radius * radius2
        )
        * inverse
    )
    return Vector3(central, radial, central)


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
    type: int | BoundMaterialType = 0
    procedural_id: int = 0
    room_id: int = 0
    ped_density: int = 0
    flags: int = 0
    material_color_index: int = 0
    reserved: int = 0
    data1: int = 0
    data2: int = 0

    def __post_init__(self) -> None:
        self.type = coerce_bound_material_index(self.type)

    @property
    def material_type(self) -> BoundMaterialType | None:
        return get_bound_material_type(self.type)

    @material_type.setter
    def material_type(self, value: int | BoundMaterialType) -> None:
        self.type = coerce_bound_material_index(value)

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


BoundResourcePagesInfo = ResourcePagesInfo


def _normalize_octant_items(items: list[list[int]] | tuple[tuple[int, ...], ...] | None) -> list[list[int]]:
    source = list(items or [])
    normalized = [list(map(int, source[index])) if index < len(source) else [] for index in range(8)]
    return normalized


@dataclasses.dataclass(slots=True)
class BoundGeometryOctants:
    items: list[list[int]] = dataclasses.field(default_factory=lambda: [[] for _ in range(8)])

    def __post_init__(self) -> None:
        self.items = _normalize_octant_items(self.items)

    @classmethod
    def from_vertices(
        cls,
        vertices: list[Vector3],
    ) -> BoundGeometryOctants:
        return cls(
            items=_native_backend._bounds_build_octants(
                [vertex.as_tuple() for vertex in vertices]
            )
        )

    @property
    def counts(self) -> tuple[int, int, int, int, int, int, int, int]:
        return tuple(len(items) for items in self.items)  # type: ignore[return-value]

    @property
    def total_items(self) -> int:
        return sum(len(items) for items in self.items)

    @property
    def has_items(self) -> bool:
        return any(self.items)

    def validate(self, vertex_count: int) -> ValidationReport:
        issues = ValidationReport()
        if len(self.items) != 8:
            issues.issue("bounds.octants.count", "octants must contain exactly 8 item lists", path="items")
            return issues
        for octant_index, indices in enumerate(self.items):
            for item_index, vertex_index in enumerate(indices):
                if vertex_index < 0 or vertex_index >= vertex_count:
                    issues.issue(
                        "bounds.octants.vertex_index",
                        f"octant {octant_index} references invalid vertex index {vertex_index}",
                        path=f"items[{octant_index}][{item_index}]",
                    )
        return issues


@dataclasses.dataclass(slots=True)
class BoundBvhNode:
    minimum: Vector3
    maximum: Vector3
    item_id: int
    item_count: int

    @property
    def is_leaf(self) -> bool:
        return self.item_count > 0


@dataclasses.dataclass(slots=True)
class BoundBvhTree:
    minimum: Vector3
    maximum: Vector3
    node_index: int
    node_index2: int


@dataclasses.dataclass(slots=True)
class BoundBvh:
    minimum: Vector3
    maximum: Vector3
    center: Vector3
    quantum_inverse: Vector3
    quantum: Vector3
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
    material_index: int | BoundMaterialType = -1

    def __post_init__(self) -> None:
        self.material_index = int(self.material_index)

    @property
    def material_type(self) -> BoundMaterialType | None:
        return get_bound_material_type(self.material_index)

    @material_type.setter
    def material_type(self, value: int | BoundMaterialType) -> None:
        self.material_index = coerce_bound_material_index(value)

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
    box_max: Vector3
    margin: float
    box_min: Vector3
    box_center: Vector3
    sphere_center: Vector3
    file_vft: int = 0
    file_unknown: int = 1
    file_pages_info: BoundResourcePagesInfo | None = None
    flags: BoundFlag | int = BoundFlag.NONE
    part_index: int = 0
    alignment_padding_18h: int = 0
    alignment_padding_1ch: int = 0
    material_index: int | BoundMaterialType = 0
    procedural_id: int = 0
    room_id: int = 0
    ped_density: int = 0
    unk_flags: int = 0
    poly_flags: int = 0
    material_color_index: int = 0
    ref_count: int = 1
    packed_material_hi_bits: int = 0
    angular_inertia: Vector3 = Vector3()
    volume: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "box_max",
            "box_min",
            "box_center",
            "sphere_center",
            "angular_inertia",
        ):
            if not isinstance(getattr(self, name), Vector3):
                raise TypeError(f"Bound.{name} must be a Vector3")

    @property
    def bounds(self) -> BoundAabb:
        return BoundAabb(self.box_min, self.box_max)

    @property
    def enclosing_radius(self) -> float:
        return float(self.sphere_radius)

    @enclosing_radius.setter
    def enclosing_radius(self, value: float) -> None:
        self.sphere_radius = float(value)

    @property
    def aabb_center(self) -> Vector3:
        return (self.box_min + self.box_max) * 0.5

    @property
    def minimum(self) -> Vector3:
        return self.box_min

    @minimum.setter
    def minimum(self, value: Vector3) -> None:
        if not isinstance(value, Vector3):
            raise TypeError("minimum must be a Vector3")
        self.box_min = value

    @property
    def maximum(self) -> Vector3:
        return self.box_max

    @maximum.setter
    def maximum(self, value: Vector3) -> None:
        if not isinstance(value, Vector3):
            raise TypeError("maximum must be a Vector3")
        self.box_max = value

    @property
    def center(self) -> Vector3:
        return self.aabb_center

    @property
    def material_type(self) -> BoundMaterialType | None:
        return get_bound_material_type(self.material_index)

    @material_type.setter
    def material_type(self, value: int | BoundMaterialType) -> None:
        self.material_index = coerce_bound_material_index(value)

    @property
    def half_extents(self) -> Vector3:
        return self.box_max - self.aabb_center

    @property
    def dimensions(self) -> Vector3:
        return self.box_max - self.box_min

    @property
    def size(self) -> Vector3:
        return self.dimensions

    @property
    def width(self) -> float:
        return self.dimensions.x

    @property
    def depth(self) -> float:
        return self.dimensions.y

    @property
    def height(self) -> float:
        return self.dimensions.z

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
                if child.bound is not None:
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

    def compute_volume(self) -> float:
        if self.volume > 0.0 and math.isfinite(self.volume):
            return float(self.volume)
        return abs(self.width * self.depth * self.height)

    def compute_volume_distribution(self) -> Vector3:
        if any(abs(value) > 0.0 for value in self.angular_inertia):
            return self.angular_inertia
        return _box_volume_distribution(self.dimensions)

    def compute_angular_inertia(self, mass: float) -> Vector3:
        distribution = self.compute_volume_distribution()
        return distribution * mass

    def build(self) -> Bound:
        normalized = _normalize_aabb(self.bounds)
        self.box_min = normalized.minimum
        self.box_max = normalized.maximum
        self.box_center = (normalized.minimum + normalized.maximum) * 0.5
        if self.sphere_center == Vector3() and self.box_center != Vector3():
            self.sphere_center = self.box_center
        self.flags = BoundFlag(int(self.flags))
        self.part_index = int(self.part_index) & 0xFFFF
        self.material_index = coerce_bound_material_index(self.material_index)
        self.ref_count = int(self.ref_count)
        self.volume = self.compute_volume()
        self.angular_inertia = self.compute_volume_distribution()
        return self

    def validate(self, *, context: object | None = None) -> ValidationReport:
        del context
        issues = ValidationReport()
        if self.sphere_radius < 0:
            issues.issue("bounds.sphere_radius.negative", f"{self.type_name} has negative sphere_radius", path="sphere_radius")
        if not _aabb_is_valid(self.bounds):
            issues.issue("bounds.aabb.invalid", f"{self.type_name} has non-finite or inverted box bounds", path="bounds")
        return issues


def _build_primitive_bound(
    cls: type[Bound],
    bound_type: BoundType,
    minimum: Vector3,
    maximum: Vector3,
    *,
    material_index: int | BoundMaterialType = 0,
    margin: float = 0.0,
    ref_count: int = 1,
    angular_inertia: Vector3 = Vector3(),
    volume: float | None = None,
) -> Bound:
    bounds = _normalize_aabb(BoundAabb(minimum, maximum))
    dimensions = bounds.maximum - bounds.minimum
    center = (bounds.minimum + bounds.maximum) * 0.5
    if volume is None:
        volume = dimensions.x * dimensions.y * dimensions.z
    return cls(
        bound_type=bound_type,
        sphere_radius=_sphere_radius_from_bounds(bounds, center),
        box_max=bounds.maximum,
        margin=float(margin),
        box_min=bounds.minimum,
        box_center=center,
        sphere_center=center,
        material_index=int(material_index),
        ref_count=int(ref_count),
        angular_inertia=angular_inertia,
        volume=float(volume),
    )


@dataclasses.dataclass(slots=True)
class BoundSphere(Bound):
    @property
    def radius(self) -> float:
        return self.enclosing_radius

    @radius.setter
    def radius(self, value: float) -> None:
        self.enclosing_radius = value

    @property
    def diameter(self) -> float:
        return self.radius * 2.0

    def compute_volume(self) -> float:
        return (4.0 / 3.0) * math.pi * (self.radius ** 3)

    def compute_volume_distribution(self) -> Vector3:
        return _sphere_volume_distribution(self.radius)


@dataclasses.dataclass(slots=True)
class BoundBox(Bound):
    def compute_volume_distribution(self) -> Vector3:
        return _box_volume_distribution(self.dimensions)

    @classmethod
    def from_bounds(
        cls,
        minimum: Vector3,
        maximum: Vector3,
        *,
        material_index: int | BoundMaterialType = 0,
        margin: float = 0.0,
        ref_count: int = 1,
        angular_inertia: Vector3 = Vector3(),
        volume: float | None = None,
    ) -> BoundBox:
        return _build_primitive_bound(
            cls,
            BoundType.BOX,
            minimum,
            maximum,
            material_index=material_index,
            margin=margin,
            ref_count=ref_count,
            angular_inertia=angular_inertia,
            volume=volume,
        )

    @classmethod
    def from_center_size(
        cls,
        center: Vector3,
        size: Vector3,
        *,
        material_index: int | BoundMaterialType = 0,
        margin: float = 0.0,
        ref_count: int = 1,
        angular_inertia: Vector3 = Vector3(),
        volume: float | None = None,
    ) -> BoundBox:
        half_size = size * 0.5
        minimum = center - half_size
        maximum = center + half_size
        return cls.from_bounds(
            minimum,
            maximum,
            material_index=material_index,
            margin=margin,
            ref_count=ref_count,
            angular_inertia=angular_inertia,
            volume=volume,
        )


@dataclasses.dataclass(slots=True)
class BoundCapsule(Bound):
    capsule_half_height: float = 0.0
    padding_74h: int = 0
    padding_78h: int = 0
    padding_7ch: int = 0

    @property
    def radius(self) -> float:
        return max(0.0, min(self.half_extents.x, self.half_extents.z))

    @property
    def shaft_half_height(self) -> float:
        if self.capsule_half_height > 0.0:
            return float(self.capsule_half_height)
        return max(0.0, self.half_extents.y - self.radius)

    @property
    def shaft_length(self) -> float:
        return self.shaft_half_height * 2.0

    @property
    def total_height(self) -> float:
        return self.shaft_length + (self.radius * 2.0)

    def compute_volume(self) -> float:
        radius = self.radius
        return math.pi * radius * radius * (self.shaft_length + (4.0 / 3.0) * radius)

    def compute_volume_distribution(self) -> Vector3:
        return _capsule_volume_distribution(self.radius, self.shaft_length)


@dataclasses.dataclass(slots=True)
class BoundDisc(Bound):
    padding_70h: int = 0
    padding_74h: int = 0
    padding_78h: int = 0
    padding_7ch: int = 0

    @classmethod
    def from_bounds(
        cls,
        minimum: Vector3,
        maximum: Vector3,
        *,
        material_index: int | BoundMaterialType = 0,
        margin: float = 0.0,
        ref_count: int = 1,
        angular_inertia: Vector3 = Vector3(),
        volume: float | None = None,
    ) -> BoundDisc:
        return _build_primitive_bound(
            cls,
            BoundType.DISC,
            minimum,
            maximum,
            material_index=material_index,
            margin=margin,
            ref_count=ref_count,
            angular_inertia=angular_inertia,
            volume=volume,
        )

    @classmethod
    def from_center_size(
        cls,
        center: Vector3,
        size: Vector3,
        **kwargs: float | Vector3,
    ) -> BoundDisc:
        bounds = _aabb_from_center_size(center, size)
        return cls.from_bounds(bounds.minimum, bounds.maximum, **kwargs)

    @classmethod
    def from_center_radius(
        cls,
        center: Vector3,
        radius: float,
        *,
        thickness: float = 0.0,
        thickness_axis: BoundAxis = BoundAxis.Y,
        material_index: int | BoundMaterialType = 0,
        margin: float = 0.0,
        ref_count: int = 1,
        angular_inertia: Vector3 = Vector3(),
        volume: float | None = None,
    ) -> BoundDisc:
        resolved_axis = BoundAxis(thickness_axis)
        diameter = radius * 2.0
        size = Vector3(
            thickness if resolved_axis is BoundAxis.X else diameter,
            thickness if resolved_axis is BoundAxis.Y else diameter,
            thickness if resolved_axis is BoundAxis.Z else diameter,
        )
        disc = cls.from_center_size(
            center,
            size,
            material_index=material_index,
            margin=margin,
            ref_count=ref_count,
            angular_inertia=angular_inertia,
            volume=volume,
        )
        disc.sphere_radius = max(0.0, float(radius))
        return disc

    @classmethod
    def vehicle_wheel(
        cls,
        center: Vector3,
        radius: float,
        thickness: float,
        *,
        material_index: int | BoundMaterialType = 0,
        ref_count: int = 1,
    ) -> BoundDisc:
        radius = float(radius)
        thickness = float(thickness)
        if not math.isfinite(radius) or radius <= 0.0:
            raise ValueError("wheel radius must be a finite positive value")
        if not math.isfinite(thickness) or thickness <= 0.0:
            raise ValueError("wheel thickness must be a finite positive value")
        return cls.from_center_radius(
            center,
            radius,
            thickness=thickness,
            thickness_axis=BoundAxis.X,
            material_index=material_index,
            margin=thickness * 0.5,
            ref_count=ref_count,
        ).build()

    @property
    def thickness_axis(self) -> BoundAxis:
        extents = self.half_extents
        return min(
            (BoundAxis.Y, BoundAxis.X, BoundAxis.Z),
            key=lambda axis: axis.component(extents),
        )

    @property
    def radial_axes(self) -> tuple[BoundAxis, BoundAxis]:
        return tuple(axis for axis in BoundAxis if axis is not self.thickness_axis)

    @property
    def radius(self) -> float:
        extents = self.half_extents
        return max(
            0.0,
            min(axis.component(extents) for axis in self.radial_axes),
        )

    @property
    def diameter(self) -> float:
        return self.radius * 2.0

    @property
    def half_thickness(self) -> float:
        return max(0.0, self.thickness_axis.component(self.half_extents))

    @property
    def thickness(self) -> float:
        return self.half_thickness * 2.0

    def compute_volume(self) -> float:
        return math.pi * self.radius * self.radius * self.thickness

    def compute_volume_distribution(self) -> Vector3:
        return _cylinder_volume_distribution(self.radius, self.thickness)


@dataclasses.dataclass(slots=True)
class BoundCylinder(Bound):
    padding_70h: int = 0
    padding_74h: int = 0
    padding_78h: int = 0
    padding_7ch: int = 0

    @classmethod
    def from_bounds(
        cls,
        minimum: Vector3,
        maximum: Vector3,
        *,
        material_index: int | BoundMaterialType = 0,
        margin: float = 0.0,
        ref_count: int = 1,
        angular_inertia: Vector3 = Vector3(),
        volume: float | None = None,
    ) -> BoundCylinder:
        return _build_primitive_bound(
            cls,
            BoundType.CYLINDER,
            minimum,
            maximum,
            material_index=material_index,
            margin=margin,
            ref_count=ref_count,
            angular_inertia=angular_inertia,
            volume=volume,
        )

    @classmethod
    def from_center_size(
        cls,
        center: Vector3,
        size: Vector3,
        **kwargs: float | Vector3,
    ) -> BoundCylinder:
        bounds = _aabb_from_center_size(center, size)
        return cls.from_bounds(bounds.minimum, bounds.maximum, **kwargs)

    @classmethod
    def from_center_radius_height(
        cls,
        center: Vector3,
        radius: float,
        height: float,
        **kwargs: float | Vector3,
    ) -> BoundCylinder:
        return cls.from_center_size(
            center, Vector3(radius * 2.0, height, radius * 2.0), **kwargs
        )

    @property
    def radius(self) -> float:
        return max(0.0, min(self.half_extents.x, self.half_extents.z))

    @property
    def half_height(self) -> float:
        return max(0.0, self.half_extents.y)

    @property
    def height(self) -> float:
        return self.half_height * 2.0

    def compute_volume(self) -> float:
        return math.pi * self.radius * self.radius * self.height

    def compute_volume_distribution(self) -> Vector3:
        return _cylinder_volume_distribution(self.radius, self.height)


@dataclasses.dataclass(slots=True)
class BoundCloth(Bound):
    padding_70h: int = 0
    padding_74h: int = 0
    padding_78h: int = 0
    padding_7ch: int = 0

    @classmethod
    def from_bounds(
        cls,
        minimum: Vector3,
        maximum: Vector3,
        *,
        material_index: int | BoundMaterialType = 0,
        margin: float = 0.0,
        ref_count: int = 1,
        angular_inertia: Vector3 = Vector3(),
        volume: float | None = None,
    ) -> BoundCloth:
        return _build_primitive_bound(
            cls,
            BoundType.CLOTH,
            minimum,
            maximum,
            material_index=material_index,
            margin=margin,
            ref_count=ref_count,
            angular_inertia=angular_inertia,
            volume=volume,
        )

    @classmethod
    def from_center_size(
        cls,
        center: Vector3,
        size: Vector3,
        **kwargs: float | Vector3,
    ) -> BoundCloth:
        bounds = _aabb_from_center_size(center, size)
        return cls.from_bounds(bounds.minimum, bounds.maximum, **kwargs)


@dataclasses.dataclass(slots=True)
class BoundGeometry(Bound):
    quantum: Vector3 = Vector3(1.0, 1.0, 1.0)
    center_geom: Vector3 = Vector3()
    vertices: list[Vector3] = dataclasses.field(default_factory=list)
    vertices_shrunk: list[Vector3] = dataclasses.field(default_factory=list)
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

    def polygon_material_index(self, polygon: BoundPolygon | int) -> int | None:
        if not isinstance(polygon, int) and polygon.material_index >= 0:
            return int(polygon.material_index)
        polygon_index = int(polygon) if isinstance(polygon, int) else polygon.index
        if not 0 <= polygon_index < len(self.polygons):
            return None
        value = self.polygons[polygon_index]
        if value.material_index >= 0:
            return int(value.material_index)
        if polygon_index < len(self.polygon_material_indices):
            return int(self.polygon_material_indices[polygon_index])
        return None

    def get_polygon_material(self, polygon: BoundPolygon | int) -> BoundMaterial | None:
        material_index = self.polygon_material_index(polygon)
        return self.get_material(material_index) if material_index is not None else None

    def iter_polygon_materials(self) -> Iterator[BoundMaterial]:
        for polygon_index in range(len(self.polygons)):
            material = self.get_polygon_material(polygon_index)
            if material is not None:
                yield material

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

    def vertex(self, vertex: Vector3) -> Vector3:
        if not isinstance(vertex, Vector3):
            raise TypeError("vertex must be a Vector3")
        self.vertices.append(vertex)
        return vertex

    def polygon(self, polygon: BoundPolygon) -> BoundPolygon:
        if polygon.index < 0:
            polygon.index = len(self.polygons)
        self.polygons.append(polygon)
        if polygon.material_index >= 0:
            self.polygon_material_indices.append(int(polygon.material_index))
        return polygon

    def material(self, material: BoundMaterial) -> BoundMaterial:
        self.materials.append(material)
        return material

    def build(self) -> BoundGeometry:
        Bound.build(self)
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

    def validate(self, *, context: object | None = None) -> ValidationReport:
        issues = Bound.validate(self, context=context)
        if len(self.polygon_material_indices) != len(self.polygons):
            issues.issue("bounds.geometry.material_index_count", "polygon_material_indices length does not match polygon count", path="polygon_material_indices")
        for polygon_index, polygon in enumerate(self.polygons):
            for vertex_slot, vertex_index in enumerate(polygon.vertex_indices):
                if vertex_index < 0 or vertex_index >= self.vertex_count:
                    issues.issue(
                        "bounds.geometry.vertex_index",
                        f"polygon {polygon_index} references invalid vertex index {vertex_index}",
                        path=f"polygons[{polygon_index}].vertex_indices[{vertex_slot}]",
                    )
            if isinstance(polygon, BoundPolygonTriangle):
                for edge_slot, edge_polygon_index in enumerate(polygon.adjacent_polygon_indices, start=1):
                    if edge_polygon_index >= self.polygon_count:
                        issues.issue(
                            "bounds.geometry.adjacent_polygon_index",
                            f"polygon {polygon_index} edge {edge_slot} references invalid polygon index {edge_polygon_index}",
                            path=f"polygons[{polygon_index}].edges[{edge_slot - 1}]",
                        )
            material_index = (
                int(polygon.material_index)
                if polygon.material_index >= 0
                else int(self.polygon_material_indices[polygon_index])
                if polygon_index < len(self.polygon_material_indices)
                else -1
            )
            if material_index < 0:
                issues.issue("bounds.geometry.material_index.missing", f"polygon {polygon_index} has no valid material index", path=f"polygons[{polygon_index}].material_index")
            elif self.materials and material_index >= len(self.materials):
                issues.issue(
                    "bounds.geometry.material_index.invalid",
                    f"polygon {polygon_index} references invalid material index {material_index}",
                    path=f"polygons[{polygon_index}].material_index",
                )
        if self.octants is not None:
            issues.extend(self.octants.validate(self.vertex_count), path="octants")
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
    bound: Bound | None
    transform: BoundTransform | None = None
    bounds: BoundAabb | None = None
    flags1: BoundCompositeFlags | None = None
    flags2: BoundCompositeFlags | None = None


@dataclasses.dataclass(slots=True)
class BoundComposite(Bound):
    children: list[BoundChild] = dataclasses.field(default_factory=list)
    active_child_count: int | None = None
    bvh_pointer: int = 0
    bvh: BoundBvh | None = None

    @property
    def child_count(self) -> int:
        return (
            len(self.children)
            if self.active_child_count is None
            else self.active_child_count
        )

    @property
    def child_capacity(self) -> int:
        return len(self.children)

    @property
    def active_children(self) -> list[BoundChild]:
        return self.children[: self.child_count]

    @property
    def has_bvh(self) -> bool:
        return self.bvh is not None

    def iter_children(self) -> Iterator[BoundChild]:
        yield from self.children

    def child(
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

    def compute_volume(self) -> float:
        if self.active_children:
            return sum(
                child.bound.compute_volume()
                for child in self.active_children
                if child.bound is not None
            )
        return Bound.compute_volume(self)

    def compute_center_of_gravity(
        self,
        masses: list[float] | tuple[float, ...] | None = None,
    ) -> Vector3:
        weighted = Vector3()
        total_weight = 0.0
        for index, child in enumerate(self.active_children):
            if child.bound is None:
                continue
            weight = (
                float(masses[index])
                if masses is not None and index < len(masses)
                else child.bound.compute_volume()
            )
            if weight <= 0.0:
                continue
            child_center = _transform_point(child.bound.sphere_center, child.transform)
            weighted = weighted + (child_center * weight)
            total_weight += weight
        return weighted / total_weight if total_weight > 0.0 else Vector3()

    def compute_composite_angular_inertia(
        self,
        mass: float,
        *,
        masses: list[float] | tuple[float, ...] | None = None,
        inertias: list[Vector3] | tuple[Vector3, ...] | None = None,
    ) -> Vector3:
        total_mass = float(mass)
        total_volume = self.compute_volume()
        density = total_mass / total_volume if total_volume > 0.0 else 0.0
        center_of_gravity = self.compute_center_of_gravity(masses)
        total = Vector3()
        for index, child in enumerate(self.active_children):
            if child.bound is None:
                continue
            part_mass = (
                float(masses[index])
                if masses is not None and index < len(masses)
                else density * child.bound.compute_volume()
            )
            if inertias is not None and index < len(inertias):
                part_inertia = inertias[index]
            else:
                part_inertia = child.bound.compute_angular_inertia(part_mass)
            offset = _transform_point(child.bound.sphere_center, child.transform) - center_of_gravity
            parallel_axis = Vector3(
                part_mass * ((offset.y * offset.y) + (offset.z * offset.z)),
                part_mass * ((offset.x * offset.x) + (offset.z * offset.z)),
                part_mass * ((offset.x * offset.x) + (offset.y * offset.y)),
            )
            total = total + part_inertia + parallel_axis
        return total

    def compute_volume_distribution(self) -> Vector3:
        volume = self.compute_volume()
        if volume <= 0.0:
            return Vector3()
        return self.compute_composite_angular_inertia(volume) / volume

    def compute_angular_inertia(self, mass: float) -> Vector3:
        return self.compute_composite_angular_inertia(mass)

    def build(self) -> BoundComposite:
        Bound.build(self)
        for child in self.active_children:
            if child.bound is None:
                continue
            child.bound.build()
            if child.bounds is None or not _aabb_is_valid(child.bounds):
                child.bounds = child.bound.bounds
        active_children = [
            child for child in self.active_children if child.bound is not None
        ]
        if active_children:
            transformed_bounds = [
                _transform_bounds(child.bounds if child.bounds is not None else child.bound.bounds, child.transform)
                for child in active_children
            ]
            overall = _merge_bounds(transformed_bounds, self.bounds)
            center = (overall.minimum + overall.maximum) * 0.5
            self.box_min = overall.minimum
            self.box_max = overall.maximum
            self.box_center = center
            self.sphere_center = self.compute_center_of_gravity()
            self.sphere_radius = _sphere_radius_from_bounds(overall, center)
            self.volume = self.compute_volume()
            self.angular_inertia = self.compute_volume_distribution()
            if len(self.children) <= 5:
                self.bvh = None
        else:
            self.bvh = None
        return self

    def validate(self, *, context: object | None = None) -> ValidationReport:
        issues = Bound.validate(self, context=context)
        if not self.children:
            issues.issue("bounds.composite.children.empty", "Composite bound has no children", path="children")
        if not 0 <= self.child_count <= self.child_capacity:
            issues.issue(
                "bounds.composite.child_count.invalid",
                "Composite bound active child count exceeds its capacity",
                path="active_child_count",
            )
        for index, child in enumerate(self.children):
            if child.bounds is not None and not _aabb_is_valid(child.bounds):
                issues.issue("bounds.composite.child_bounds.invalid", f"child {index} has non-finite or inverted local bounds", path=f"children[{index}].bounds")
            if child.bound is None:
                flags = (child.flags1, child.flags2)
                if any(
                    value is not None
                    and (int(value.flags1) != 0 or int(value.flags2) != 0)
                    for value in flags
                ):
                    issues.issue("bounds.composite.null_child.active_flags", f"null child {index} has active composite flags", path=f"children[{index}]")
            if child.bound is not None:
                issues.extend(child.bound.validate(context=context), path=f"children[{index}].bound")
        return issues


__all__ = [
    'Bound',
    'BoundAabb',
    'BoundAxis',
    'BoundBVH',
    'BoundBox',
    'BoundBvh',
    'BoundBvhNode',
    'BoundBvhTree',
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
