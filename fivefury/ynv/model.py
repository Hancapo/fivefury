from __future__ import annotations

import dataclasses
import math
from enum import IntFlag
from pathlib import Path

from ..common import FlexibleIntEnum



def identity_4x4() -> tuple[float, ...]:
    return (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


class YnvContentFlags(IntFlag):
    NONE = 0
    POLYGONS = 1 << 0
    PORTALS = 1 << 1
    VEHICLE = 1 << 2
    UNKNOWN_8 = 1 << 3
    UNKNOWN_16 = 1 << 4


class YnvAdjacencyType(FlexibleIntEnum):
    NORMAL = 0
    CLIMB_LOW = 1
    CLIMB_HIGH = 2
    DROPDOWN = 3


class YnvPointType(FlexibleIntEnum):
    TYPE_0 = 0
    TYPE_1 = 1
    TYPE_2 = 2
    TYPE_3 = 3
    TYPE_4 = 4
    TYPE_5 = 5
    UNUSED = 125
    SPECIAL_LINK_ENDPOS = 126
    CENTROID = 127
    TYPE_128 = 128
    TYPE_171 = 171
    TYPE_254 = 254


class YnvPortalType(FlexibleIntEnum):
    TYPE_1 = 1
    TYPE_2 = 2
    TYPE_3 = 3


class YnvPolyFlags0(IntFlag):
    NONE = 0
    SMALL = 1 << 0
    LARGE = 1 << 1
    IS_PAVEMENT = 1 << 2
    IN_SHELTER = 1 << 3
    RESERVED1 = 1 << 4
    RESERVED2 = 1 << 5
    TOO_STEEP_TO_WALK_ON = 1 << 6
    IS_WATER = 1 << 7


class YnvPolyFlags1(IntFlag):
    NONE = 0
    UNDERGROUND_UNK0 = 1 << 0
    UNDERGROUND_UNK1 = 1 << 1
    UNDERGROUND_UNK2 = 1 << 2
    UNDERGROUND_UNK3 = 1 << 3
    UNUSED_4 = 1 << 4
    HAS_PATH_NODE = 1 << 5
    IS_INTERIOR = 1 << 6
    INTERACTION_UNK = 1 << 7
    UNUSED_8 = 1 << 8
    IS_FLAT_GROUND = 1 << 9
    IS_ROAD = 1 << 10
    IS_CELL_EDGE = 1 << 11
    IS_TRAIN_TRACK = 1 << 12
    IS_SHALLOW_WATER = 1 << 13
    FOOTPATH_UNK1 = 1 << 14
    FOOTPATH_UNK2 = 1 << 15
    FOOTPATH_MALL = 1 << 16


class YnvPolySlopeDirectionFlags(IntFlag):
    NONE = 0
    SOUTH = 1 << 0
    SOUTHEAST = 1 << 1
    EAST = 1 << 2
    NORTHEAST = 1 << 3
    NORTH = 1 << 4
    NORTHWEST = 1 << 5
    WEST = 1 << 6
    SOUTHWEST = 1 << 7


@dataclasses.dataclass(slots=True)
class YnvListInfo:
    vft: int
    unknown_04h: int = 1
    unknown_0ch: int = 0
    unknown_24h: int = 0
    unknown_28h: int = 0
    unknown_2ch: int = 0


@dataclasses.dataclass(slots=True)
class YnvAabb:
    min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    max: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @classmethod
    def from_packed(
        cls,
        min_x: int,
        max_x: int,
        min_y: int,
        max_y: int,
        min_z: int,
        max_z: int,
    ) -> "YnvAabb":
        return cls(
            min=(float(min_x) / 4.0, float(min_y) / 4.0, float(min_z) / 4.0),
            max=(float(max_x) / 4.0, float(max_y) / 4.0, float(max_z) / 4.0),
        )

    def build(self) -> "YnvAabb":
        self.min = (float(self.min[0]), float(self.min[1]), float(self.min[2]))
        self.max = (float(self.max[0]), float(self.max[1]), float(self.max[2]))
        return self

    def to_packed(self) -> tuple[int, int, int, int, int, int]:
        self.build()
        scaled_min = tuple(float(value) * 4.0 for value in self.min)
        scaled_max = tuple(float(value) * 4.0 for value in self.max)
        return (
            math.floor(scaled_min[0]),
            math.ceil(scaled_max[0]),
            math.floor(scaled_min[1]),
            math.ceil(scaled_max[1]),
            math.floor(scaled_min[2]),
            math.ceil(scaled_max[2]),
        )


@dataclasses.dataclass(slots=True)
class YnvEdgePart:
    area_id: int = 0x3FFF
    poly_id: int = 0x3FFF
    adjacency_type: YnvAdjacencyType = YnvAdjacencyType.NORMAL
    detail_flags: int = 0

    @classmethod
    def from_value(cls, value: int, adjacent_area_ids: list[int]) -> "YnvEdgePart":
        area_index = int(value) & 0x1F
        area_id = int(adjacent_area_ids[area_index]) if 0 <= area_index < len(adjacent_area_ids) else 0x3FFF
        return cls(
            area_id=area_id,
            poly_id=(int(value) >> 5) & 0x3FFF,
            adjacency_type=YnvAdjacencyType((int(value) >> 19) & 0x3),
            detail_flags=(int(value) >> 21) & 0x7FF,
        )

    @property
    def space_around_vertex(self) -> int:
        return self.detail_flags & 0x1F

    @space_around_vertex.setter
    def space_around_vertex(self, value: int) -> None:
        self.detail_flags = (self.detail_flags & ~0x1F) | (int(value) & 0x1F)

    @property
    def space_beyond_edge(self) -> int:
        return (self.detail_flags >> 5) & 0x1F

    @space_beyond_edge.setter
    def space_beyond_edge(self, value: int) -> None:
        self.detail_flags = (self.detail_flags & ~(0x1F << 5)) | ((int(value) & 0x1F) << 5)

    @property
    def detail_reserved(self) -> int:
        return (self.detail_flags >> 10) & 0x1

    @detail_reserved.setter
    def detail_reserved(self, value: int) -> None:
        self.detail_flags = (self.detail_flags & ~(1 << 10)) | ((int(value) & 0x1) << 10)

    def build(self) -> "YnvEdgePart":
        self.area_id = int(self.area_id) & 0x3FFF
        self.poly_id = int(self.poly_id) & 0x3FFF
        self.adjacency_type = YnvAdjacencyType(int(self.adjacency_type) & 0x3)
        self.detail_flags = int(self.detail_flags) & 0x7FF
        return self

    def to_value(self, area_lookup: dict[int, int]) -> int:
        self.build()
        area_index = int(area_lookup.get(int(self.area_id), area_lookup.get(0x3FFF, 0))) & 0x1F
        return (
            area_index
            | ((int(self.poly_id) & 0x3FFF) << 5)
            | ((int(self.adjacency_type) & 0x3) << 19)
            | ((int(self.detail_flags) & 0x7FF) << 21)
        )


@dataclasses.dataclass(slots=True)
class YnvEdge:
    poly1: YnvEdgePart = dataclasses.field(default_factory=YnvEdgePart)
    poly2: YnvEdgePart = dataclasses.field(default_factory=YnvEdgePart)

    def build(self) -> "YnvEdge":
        self.poly1 = self.poly1.build()
        self.poly2 = self.poly2.build()
        return self


@dataclasses.dataclass(slots=True)
class YnvPoly:
    poly_flags0: YnvPolyFlags0 = YnvPolyFlags0.NONE
    index_id: int = 0
    index_count: int = 0
    area_id: int = 0
    unknown_08h: int = 0
    unknown_0ch: int = 0
    unknown_10h: int = 0
    unknown_14h: int = 0
    cell_aabb: YnvAabb = dataclasses.field(default_factory=YnvAabb)
    poly_flags1: YnvPolyFlags1 = YnvPolyFlags1.NONE
    poly_flags2: int = 0
    part_id: int = 0
    portal_link_count: int = 0
    portal_link_id: int = 0

    @classmethod
    def from_packed(
        cls,
        *,
        poly_flags0: int,
        index_flags: int,
        index_id: int,
        area_id: int,
        unknown_08h: int,
        unknown_0ch: int,
        unknown_10h: int,
        unknown_14h: int,
        cell_aabb: YnvAabb,
        poly_flags1: int,
        poly_flags2: int,
        part_flags: int,
    ) -> "YnvPoly":
        return cls(
            poly_flags0=YnvPolyFlags0(int(poly_flags0)),
            index_id=int(index_id) & 0xFFFF,
            index_count=(int(index_flags) >> 5) & 0x7FF,
            area_id=int(area_id) & 0xFFFF,
            unknown_08h=int(unknown_08h) & 0xFFFFFFFF,
            unknown_0ch=int(unknown_0ch) & 0xFFFFFFFF,
            unknown_10h=int(unknown_10h) & 0xFFFFFFFF,
            unknown_14h=int(unknown_14h) & 0xFFFFFFFF,
            cell_aabb=cell_aabb,
            poly_flags1=YnvPolyFlags1(int(poly_flags1)),
            poly_flags2=int(poly_flags2) & 0xFFFFFFFF,
            part_id=(int(part_flags) >> 4) & 0xFF,
            portal_link_count=(int(part_flags) >> 12) & 0x7,
            portal_link_id=(int(part_flags) >> 15) & 0x1FFFF,
        )

    @property
    def index_flags(self) -> int:
        return (int(self.index_count) & 0x7FF) << 5

    @property
    def part_flags(self) -> int:
        return (
            ((int(self.part_id) & 0xFF) << 4)
            | ((int(self.portal_link_count) & 0x7) << 12)
            | ((int(self.portal_link_id) & 0x1FFFF) << 15)
        )

    @property
    def slope_directions(self) -> YnvPolySlopeDirectionFlags:
        return YnvPolySlopeDirectionFlags((int(self.poly_flags2) >> 16) & 0xFF)

    @slope_directions.setter
    def slope_directions(self, value: YnvPolySlopeDirectionFlags | int) -> None:
        self.poly_flags2 = (int(self.poly_flags2) & 0xFF00FFFF) | ((int(value) & 0xFF) << 16)

    @property
    def poly_flags2_low(self) -> int:
        return int(self.poly_flags2) & 0xFFFF

    def build(self) -> "YnvPoly":
        self.poly_flags0 = YnvPolyFlags0(int(self.poly_flags0) & 0xFFFF)
        self.index_id = int(self.index_id) & 0xFFFF
        self.index_count = int(self.index_count) & 0x7FF
        self.area_id = int(self.area_id) & 0xFFFF
        self.unknown_08h = int(self.unknown_08h) & 0xFFFFFFFF
        self.unknown_0ch = int(self.unknown_0ch) & 0xFFFFFFFF
        self.unknown_10h = int(self.unknown_10h) & 0xFFFFFFFF
        self.unknown_14h = int(self.unknown_14h) & 0xFFFFFFFF
        self.cell_aabb = self.cell_aabb.build()
        self.poly_flags1 = YnvPolyFlags1(int(self.poly_flags1) & 0xFFFFFFFF)
        self.poly_flags2 = int(self.poly_flags2) & 0xFFFFFFFF
        self.part_id = int(self.part_id) & 0xFF
        self.portal_link_count = int(self.portal_link_count) & 0x7
        self.portal_link_id = int(self.portal_link_id) & 0x1FFFF
        return self


def _angle_byte_to_radians(value: int) -> float:
    return (float(int(value) & 0xFF) / 255.0) * math.tau


def _radians_to_angle_byte(value: float) -> int:
    if not math.isfinite(value):
        raise ValueError("YNV direction must be finite")
    return int(round((float(value) % math.tau) * 255.0 / math.tau)) & 0xFF


@dataclasses.dataclass(slots=True)
class YnvPoint:
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    angle: int = 0
    type: YnvPointType = YnvPointType.TYPE_0

    @property
    def direction(self) -> float:
        return _angle_byte_to_radians(self.angle)

    @direction.setter
    def direction(self, value: float) -> None:
        self.angle = _radians_to_angle_byte(value)

    def build(self) -> "YnvPoint":
        self.position = (float(self.position[0]), float(self.position[1]), float(self.position[2]))
        self.angle = int(self.angle) & 0xFF
        self.type = YnvPointType(int(self.type) & 0xFF)
        return self


@dataclasses.dataclass(slots=True)
class YnvPortal:
    type: YnvPortalType = YnvPortalType.TYPE_1
    angle: int = 0
    flags_unk: int = 0
    position_from: tuple[float, float, float] = (0.0, 0.0, 0.0)
    position_to: tuple[float, float, float] = (0.0, 0.0, 0.0)
    poly_id_from1: int = 0
    poly_id_from2: int = 0
    poly_id_to1: int = 0
    poly_id_to2: int = 0
    area_id_from: int = 0
    area_id_to: int = 0
    area_unk: int = 0

    @property
    def direction(self) -> float:
        return _angle_byte_to_radians(self.angle)

    @direction.setter
    def direction(self, value: float) -> None:
        self.angle = _radians_to_angle_byte(value)

    @property
    def area_flags(self) -> int:
        return (
            (int(self.area_id_from) & 0x3FFF)
            | ((int(self.area_id_to) & 0x3FFF) << 14)
            | ((int(self.area_unk) & 0xF) << 28)
        )

    def build(self) -> "YnvPortal":
        self.type = YnvPortalType(int(self.type) & 0xFF)
        self.angle = int(self.angle) & 0xFF
        self.flags_unk = int(self.flags_unk) & 0xFFFF
        self.position_from = (float(self.position_from[0]), float(self.position_from[1]), float(self.position_from[2]))
        self.position_to = (float(self.position_to[0]), float(self.position_to[1]), float(self.position_to[2]))
        self.poly_id_from1 = int(self.poly_id_from1) & 0xFFFF
        self.poly_id_from2 = int(self.poly_id_from2) & 0xFFFF
        self.poly_id_to1 = int(self.poly_id_to1) & 0xFFFF
        self.poly_id_to2 = int(self.poly_id_to2) & 0xFFFF
        self.area_id_from = int(self.area_id_from) & 0x3FFF
        self.area_id_to = int(self.area_id_to) & 0x3FFF
        self.area_unk = int(self.area_unk) & 0xF
        return self


@dataclasses.dataclass(slots=True)
class YnvSectorData:
    points_start_id: int = 0
    unused_04h: int = 0
    poly_ids: list[int] = dataclasses.field(default_factory=list)
    points: list[YnvPoint] = dataclasses.field(default_factory=list)
    unused_1ch: int = 0

    def build(self) -> "YnvSectorData":
        self.points_start_id = int(self.points_start_id) & 0xFFFFFFFF
        self.unused_04h = int(self.unused_04h) & 0xFFFFFFFF
        self.poly_ids = [int(value) & 0xFFFF for value in self.poly_ids]
        self.points = [point.build() for point in self.points]
        self.unused_1ch = int(self.unused_1ch) & 0xFFFFFFFF
        return self


@dataclasses.dataclass(slots=True)
class YnvSector:
    aabb_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    aabb_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    aabb_min_w: float = float("nan")
    aabb_max_w: float = float("nan")
    cell_aabb: YnvAabb = dataclasses.field(default_factory=YnvAabb)
    data: YnvSectorData | None = None
    subtree1: YnvSector | None = None
    subtree2: YnvSector | None = None
    subtree3: YnvSector | None = None
    subtree4: YnvSector | None = None
    unused_54h: int = 0
    unused_58h: int = 0
    unused_5ch: int = 0

    def build(self) -> "YnvSector":
        self.aabb_min = (float(self.aabb_min[0]), float(self.aabb_min[1]), float(self.aabb_min[2]))
        self.aabb_max = (float(self.aabb_max[0]), float(self.aabb_max[1]), float(self.aabb_max[2]))
        self.aabb_min_w = float(self.aabb_min_w)
        self.aabb_max_w = float(self.aabb_max_w)
        self.cell_aabb = self.cell_aabb.build()
        self.data = self.data.build() if self.data is not None else None
        self.subtree1 = self.subtree1.build() if self.subtree1 is not None else None
        self.subtree2 = self.subtree2.build() if self.subtree2 is not None else None
        self.subtree3 = self.subtree3.build() if self.subtree3 is not None else None
        self.subtree4 = self.subtree4.build() if self.subtree4 is not None else None
        self.unused_54h = int(self.unused_54h) & 0xFFFFFFFF
        self.unused_58h = int(self.unused_58h) & 0xFFFFFFFF
        self.unused_5ch = int(self.unused_5ch) & 0xFFFFFFFF
        return self


@dataclasses.dataclass(slots=True)
class Ynv:
    version: int = 2
    path: str = ""
    content_flags: YnvContentFlags = YnvContentFlags.NONE
    version_unk1: int = 0x00010011
    unused_018h: int = 0
    unused_01ch: int = 0
    transform: tuple[float, ...] = dataclasses.field(default_factory=identity_4x4)
    aabb_size: tuple[float, float, float] = (0.0, 0.0, 0.0)
    aabb_unk: int = 0x7F800001
    vertices: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    indices: list[int] = dataclasses.field(default_factory=list)
    edges: list[YnvEdge] = dataclasses.field(default_factory=list)
    polys: list[YnvPoly] = dataclasses.field(default_factory=list)
    sector_tree: YnvSector | None = None
    portals: list[YnvPortal] = dataclasses.field(default_factory=list)
    portal_links: list[int] = dataclasses.field(default_factory=list)
    adjacent_area_ids: list[int] = dataclasses.field(default_factory=list)
    vertices_info: YnvListInfo = dataclasses.field(default_factory=lambda: YnvListInfo(vft=1080158456))
    indices_info: YnvListInfo = dataclasses.field(default_factory=lambda: YnvListInfo(vft=1080158424))
    edges_info: YnvListInfo = dataclasses.field(default_factory=lambda: YnvListInfo(vft=1080158440))
    polys_info: YnvListInfo = dataclasses.field(default_factory=lambda: YnvListInfo(vft=1080158408))
    area_id: int = 0
    total_bytes: int = 0
    points_count: int = 0
    unused_154h: int = 0
    unused_158h: int = 0
    unused_15ch: int = 0
    version_unk2: int = 0x85CB3561
    unused_164h: int = 0
    unused_168h: int = 0
    unused_16ch: int = 0
    system_pages_count: int = 0
    graphics_pages_count: int = 0
    points: list[YnvPoint] = dataclasses.field(default_factory=list)

    @property
    def cell_x(self) -> int:
        return int(self.area_id) % 100

    @property
    def cell_y(self) -> int:
        return int(self.area_id) // 100

    def _collect_points(self, sector: YnvSector | None, sink: list[YnvPoint]) -> None:
        if sector is None:
            return
        if sector.data is not None:
            sink.extend(point.build() for point in sector.data.points)
        self._collect_points(sector.subtree1, sink)
        self._collect_points(sector.subtree2, sink)
        self._collect_points(sector.subtree3, sink)
        self._collect_points(sector.subtree4, sink)

    def _reindex_sector_points(self, sector: YnvSector | None, start_id: int = 0) -> int:
        if sector is None:
            return start_id
        if sector.data is not None:
            sector.data.points_start_id = int(start_id)
            start_id += len(sector.data.points)
        start_id = self._reindex_sector_points(sector.subtree1, start_id)
        start_id = self._reindex_sector_points(sector.subtree2, start_id)
        start_id = self._reindex_sector_points(sector.subtree3, start_id)
        start_id = self._reindex_sector_points(sector.subtree4, start_id)
        return start_id

    def recalculate_content_flags(self) -> YnvContentFlags:
        preserved = self.content_flags & (
            YnvContentFlags.VEHICLE | YnvContentFlags.UNKNOWN_8 | YnvContentFlags.UNKNOWN_16
        )
        if self.polys:
            preserved |= YnvContentFlags.POLYGONS
        if self.portals:
            preserved |= YnvContentFlags.PORTALS
        self.content_flags = YnvContentFlags(int(preserved) & 0xFFFFFFFF)
        return self.content_flags

    def _validate_sector(
        self,
        sector: YnvSector | None,
        errors: list[str],
        *,
        poly_count: int,
        points_cursor: int = 0,
        label: str = "sector_tree",
    ) -> int:
        if sector is None:
            return points_cursor
        if sector.data is not None:
            sector_data = sector.data
            if int(sector_data.points_start_id) != int(points_cursor):
                errors.append(
                    f"{label}.data.points_start_id={sector_data.points_start_id} does not match expected {points_cursor}"
                )
            for poly_id in sector_data.poly_ids:
                if int(poly_id) >= int(poly_count):
                    errors.append(f"{label}.data.poly_ids contains out-of-range poly id {poly_id}")
            points_cursor += len(sector_data.points)
        points_cursor = self._validate_sector(
            sector.subtree1,
            errors,
            poly_count=poly_count,
            points_cursor=points_cursor,
            label=f"{label}.subtree1",
        )
        points_cursor = self._validate_sector(
            sector.subtree2,
            errors,
            poly_count=poly_count,
            points_cursor=points_cursor,
            label=f"{label}.subtree2",
        )
        points_cursor = self._validate_sector(
            sector.subtree3,
            errors,
            poly_count=poly_count,
            points_cursor=points_cursor,
            label=f"{label}.subtree3",
        )
        points_cursor = self._validate_sector(
            sector.subtree4,
            errors,
            poly_count=poly_count,
            points_cursor=points_cursor,
            label=f"{label}.subtree4",
        )
        return points_cursor

    def validate(self) -> list[str]:
        errors: list[str] = []
        vertex_count = len(self.vertices)
        poly_count = len(self.polys)
        portal_link_count = len(self.portal_links)

        if self.sector_tree is None:
            errors.append("YNV requires a sector_tree")
        if len(self.transform) != 16:
            errors.append("YNV transform must contain 16 floats")
        if len(self.adjacent_area_ids) > 32:
            errors.append("YNV supports at most 32 adjacent area ids")
        if vertex_count > 0xFFFF:
            errors.append(f"YNV supports at most 65535 vertices, got {vertex_count}")
        if len(self.indices) != len(self.edges):
            errors.append(f"YNV requires len(indices) == len(edges), got {len(self.indices)} and {len(self.edges)}")

        for index, vertex in enumerate(self.vertices):
            if len(vertex) != 3:
                errors.append(f"vertex {index} must contain exactly 3 components")

        for index, vertex_id in enumerate(self.indices):
            if int(vertex_id) >= int(vertex_count):
                errors.append(f"indices[{index}]={vertex_id} is out of range for {vertex_count} vertices")

        for index, poly in enumerate(self.polys):
            if not 3 <= int(poly.index_count) <= 16:
                errors.append(f"polys[{index}].index_count={poly.index_count} is outside the supported range 3..16")
            if int(poly.index_id) + int(poly.index_count) > len(self.indices):
                errors.append(
                    f"polys[{index}] index span [{poly.index_id}, {poly.index_id + poly.index_count}) exceeds indices length {len(self.indices)}"
                )
            if int(poly.index_id) + int(poly.index_count) > len(self.edges):
                errors.append(
                    f"polys[{index}] edge span [{poly.index_id}, {poly.index_id + poly.index_count}) exceeds edges length {len(self.edges)}"
                )
            if int(poly.area_id) != int(self.area_id):
                errors.append(f"polys[{index}].area_id={poly.area_id} does not match YNV area_id={self.area_id}")
            if int(poly.portal_link_id) + int(poly.portal_link_count) > int(portal_link_count):
                errors.append(
                    f"polys[{index}] portal link span [{poly.portal_link_id}, {poly.portal_link_id + poly.portal_link_count}) exceeds portal_links length {portal_link_count}"
                )

        for index, portal in enumerate(self.portals):
            for attr in ("poly_id_from1", "poly_id_from2", "poly_id_to1", "poly_id_to2"):
                value = int(getattr(portal, attr))
                if value != 0xFFFF and value >= int(poly_count):
                    errors.append(f"portals[{index}].{attr}={value} is out of range for {poly_count} polys")

        if self.sector_tree is not None:
            collected_points = self._validate_sector(self.sector_tree, errors, poly_count=poly_count)
            if collected_points != len(self.points):
                errors.append(f"sector_tree point count {collected_points} does not match flattened points length {len(self.points)}")
            if collected_points != int(self.points_count):
                errors.append(f"sector_tree point count {collected_points} does not match points_count={self.points_count}")

        return errors

    def build(self) -> "Ynv":
        self.version = int(self.version)
        self.path = str(self.path)
        self.content_flags = YnvContentFlags(int(self.content_flags) & 0xFFFFFFFF)
        self.version_unk1 = int(self.version_unk1) & 0xFFFFFFFF
        self.unused_018h = int(self.unused_018h) & 0xFFFFFFFF
        self.unused_01ch = int(self.unused_01ch) & 0xFFFFFFFF
        if len(self.transform) != 16:
            raise ValueError("YNV transform must contain 16 floats")
        self.transform = tuple(float(value) for value in self.transform)
        self.aabb_size = (float(self.aabb_size[0]), float(self.aabb_size[1]), float(self.aabb_size[2]))
        self.aabb_unk = int(self.aabb_unk) & 0xFFFFFFFF
        self.vertices = [tuple(float(component) for component in vertex) for vertex in self.vertices]
        self.indices = [int(value) & 0xFFFF for value in self.indices]
        self.edges = [edge.build() for edge in self.edges]
        self.polys = [poly.build() for poly in self.polys]
        self.sector_tree = self.sector_tree.build() if self.sector_tree is not None else None
        self.portals = [portal.build() for portal in self.portals]
        self.portal_links = [int(value) & 0xFFFF for value in self.portal_links]
        self.adjacent_area_ids = [int(value) & 0xFFFFFFFF for value in self.adjacent_area_ids[:32]]
        self.vertices_info = dataclasses.replace(self.vertices_info)
        self.indices_info = dataclasses.replace(self.indices_info)
        self.edges_info = dataclasses.replace(self.edges_info)
        self.polys_info = dataclasses.replace(self.polys_info)
        self.area_id = int(self.area_id) & 0xFFFFFFFF
        self.total_bytes = int(self.total_bytes) & 0xFFFFFFFF
        self.points_count = int(self.points_count) & 0xFFFFFFFF
        self.unused_154h = int(self.unused_154h) & 0xFFFFFFFF
        self.unused_158h = int(self.unused_158h) & 0xFFFFFFFF
        self.unused_15ch = int(self.unused_15ch) & 0xFFFFFFFF
        self.version_unk2 = int(self.version_unk2) & 0xFFFFFFFF
        self.unused_164h = int(self.unused_164h) & 0xFFFFFFFF
        self.unused_168h = int(self.unused_168h) & 0xFFFFFFFF
        self.unused_16ch = int(self.unused_16ch) & 0xFFFFFFFF
        self.system_pages_count = int(self.system_pages_count)
        self.graphics_pages_count = int(self.graphics_pages_count)
        self._reindex_sector_points(self.sector_tree)
        flattened_points: list[YnvPoint] = []
        self._collect_points(self.sector_tree, flattened_points)
        self.points = flattened_points
        self.points_count = len(self.points)
        if self.sector_tree is not None and all(abs(component) < 1e-8 for component in self.aabb_size):
            self.aabb_size = (
                float(self.sector_tree.aabb_max[0] - self.sector_tree.aabb_min[0]),
                float(self.sector_tree.aabb_max[1] - self.sector_tree.aabb_min[1]),
                float(self.sector_tree.aabb_max[2] - self.sector_tree.aabb_min[2]),
            )
        self.recalculate_content_flags()
        return self

    def to_bytes(self) -> bytes:
        from .writer import build_ynv_bytes

        return build_ynv_bytes(self)

    def save(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.write_bytes(self.to_bytes())
        self.path = str(target)
        return target


__all__ = [
    "Ynv",
    "YnvAabb",
    "YnvAdjacencyType",
    "YnvContentFlags",
    "YnvEdge",
    "YnvEdgePart",
    "YnvListInfo",
    "YnvPoint",
    "YnvPointType",
    "YnvPoly",
    "YnvPolyFlags0",
    "YnvPolyFlags1",
    "YnvPolySlopeDirectionFlags",
    "YnvPortal",
    "YnvPortalType",
    "YnvSector",
    "YnvSectorData",
    "identity_4x4",
]
