from __future__ import annotations

import dataclasses
import enum


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


@dataclasses.dataclass(slots=True)
class BoundMaterialColor:
    r: int = 0
    g: int = 0
    b: int = 0
    a: int = 0


@dataclasses.dataclass(slots=True)
class BoundPolygon:
    polygon_type: BoundPolygonType
    raw: bytes


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


@dataclasses.dataclass(slots=True)
class BoundBVH(BoundGeometry):
    bvh_pointer: int = 0


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
