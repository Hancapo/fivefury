from __future__ import annotations

import dataclasses
import math
from collections.abc import Hashable, Mapping, Sequence

from ..vector import Vector3, vec3
from .model import (
    Ynv,
    YnvAabb,
    YnvAdjacencyType,
    YnvContentFlags,
    YnvEdge,
    YnvEdgeFlags,
    YnvEdgePart,
    YnvPoly,
    YnvPolyFlags0,
    YnvPolyFlags1,
    YnvSector,
    YnvSectorData,
)

YNV_CELL_SIZE = 150.0
YNV_GRID_MIN = -6000.0
YNV_CELL_COUNT = 100
YNV_MAX_ADJACENT_AREAS = 32
YNV_MAX_VERTICES = 0xFFFF
YNV_MAX_POLYGONS = 0x7FFF
YNV_MAX_INDICES = 0x10000
YNV_MAX_POLYGON_VERTICES = 15

_SECTOR_DEPTH = 2
_EDGE_QUANTIZE = 10000.0
_AREA_EPSILON = 1e-6


@dataclasses.dataclass(slots=True)
class YnvSourcePolygon:
    vertices: Sequence[Vector3]
    source_key: Hashable | None = None

    def build(self) -> YnvSourcePolygon:
        vertices = tuple(vec3(vertex) for vertex in self.vertices)
        if len(vertices) < 3:
            raise ValueError("A YNV source polygon requires at least three vertices")
        if any(not all(math.isfinite(value) for value in vertex) for vertex in vertices):
            raise ValueError("YNV source polygon vertices must be finite")
        if self.source_key is not None:
            hash(self.source_key)
        self.vertices = vertices
        return self


@dataclasses.dataclass(slots=True)
class _CellPolygon:
    vertices: list[Vector3]
    source_key: Hashable | None
    cell_x: int
    cell_y: int
    area_id: int
    local_index: int = -1


def _validate_cell(cell_x: int, cell_y: int) -> tuple[int, int]:
    x = int(cell_x)
    y = int(cell_y)
    if not 0 <= x < YNV_CELL_COUNT or not 0 <= y < YNV_CELL_COUNT:
        raise ValueError(
            f"YNV cell coordinates must be in 0..{YNV_CELL_COUNT - 1}, got ({x}, {y})"
        )
    return x, y


def _clamp_cell_index(value: float) -> int:
    index = math.floor((float(value) - YNV_GRID_MIN) / YNV_CELL_SIZE)
    return max(0, min(YNV_CELL_COUNT - 1, index))


def get_ynv_cell_span(minimum: float, maximum: float) -> range:
    minimum = float(minimum)
    maximum = float(maximum)
    if not math.isfinite(minimum) or not math.isfinite(maximum):
        raise ValueError("YNV cell span bounds must be finite")
    if minimum > maximum:
        raise ValueError("YNV cell span minimum cannot exceed maximum")
    start = _clamp_cell_index(minimum)
    finish = _clamp_cell_index(math.nextafter(maximum, -math.inf))
    return range(start, finish + 1)


def get_ynv_area_id(cell_x: int, cell_y: int) -> int:
    x, y = _validate_cell(cell_x, cell_y)
    return x + (y * YNV_CELL_COUNT)


def get_ynv_file_coords(cell_x: int, cell_y: int) -> tuple[int, int]:
    x, y = _validate_cell(cell_x, cell_y)
    return (x * 3, y * 3)


def _cell_bounds(cell_x: int, cell_y: int) -> tuple[float, float, float, float]:
    x, y = _validate_cell(cell_x, cell_y)
    min_x = YNV_GRID_MIN + (x * YNV_CELL_SIZE)
    min_y = YNV_GRID_MIN + (y * YNV_CELL_SIZE)
    return (min_x, min_x + YNV_CELL_SIZE, min_y, min_y + YNV_CELL_SIZE)


def _polygon_area_xy(vertices: Sequence[Vector3]) -> float:
    return 0.5 * sum(
        (current[0] * nxt[1]) - (nxt[0] * current[1])
        for current, nxt in zip(vertices, (*vertices[1:], vertices[0]), strict=True)
    )


def _intersect_axis(
    start: Vector3,
    end: Vector3,
    boundary: float,
    axis: int,
) -> Vector3:
    delta = end[axis] - start[axis]
    if abs(delta) <= _AREA_EPSILON:
        result = list(start)
        result[axis] = boundary
        return (result[0], result[1], result[2])
    t = (boundary - start[axis]) / delta
    result = tuple(
        start[index] + ((end[index] - start[index]) * t) for index in range(3)
    )
    return (result[0], result[1], result[2])


def _clip_half_plane(
    vertices: list[Vector3],
    *,
    axis: int,
    boundary: float,
    keep_greater: bool,
) -> list[Vector3]:
    if not vertices:
        return []

    def inside(vertex: Vector3) -> bool:
        if keep_greater:
            return vertex[axis] >= boundary - _AREA_EPSILON
        return vertex[axis] <= boundary + _AREA_EPSILON

    clipped: list[Vector3] = []
    previous = vertices[-1]
    previous_inside = inside(previous)
    for current in vertices:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                clipped.append(_intersect_axis(previous, current, boundary, axis))
            clipped.append(current)
        elif previous_inside:
            clipped.append(_intersect_axis(previous, current, boundary, axis))
        previous = current
        previous_inside = current_inside
    return clipped


def _remove_duplicate_vertices(vertices: Sequence[Vector3]) -> list[Vector3]:
    result: list[Vector3] = []
    for vertex in vertices:
        if not result or any(
            abs(vertex[index] - result[-1][index]) > _AREA_EPSILON
            for index in range(3)
        ):
            result.append(vertex)
    if len(result) > 1 and all(
        abs(result[0][index] - result[-1][index]) <= _AREA_EPSILON
        for index in range(3)
    ):
        result.pop()
    return result


def clip_ynv_polygon_to_cell(
    vertices: Sequence[Vector3],
    cell_x: int,
    cell_y: int,
) -> list[Vector3]:
    polygon = [vec3(vertex) for vertex in vertices]
    if any(not all(math.isfinite(value) for value in vertex) for vertex in polygon):
        raise ValueError("YNV polygon vertices must be finite")
    min_x, max_x, min_y, max_y = _cell_bounds(cell_x, cell_y)
    polygon = _clip_half_plane(
        polygon, axis=0, boundary=min_x, keep_greater=True
    )
    polygon = _clip_half_plane(
        polygon, axis=0, boundary=max_x, keep_greater=False
    )
    polygon = _clip_half_plane(
        polygon, axis=1, boundary=min_y, keep_greater=True
    )
    polygon = _clip_half_plane(
        polygon, axis=1, boundary=max_y, keep_greater=False
    )
    polygon = _remove_duplicate_vertices(polygon)
    if len(polygon) < 3 or abs(_polygon_area_xy(polygon)) <= _AREA_EPSILON:
        return []
    return polygon


def _point_in_triangle_xy(
    point: Vector3,
    a: Vector3,
    b: Vector3,
    c: Vector3,
) -> bool:
    def cross(first: Vector3, second: Vector3, third: Vector3) -> float:
        return (
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        )

    d1 = cross(point, a, b)
    d2 = cross(point, b, c)
    d3 = cross(point, c, a)
    has_negative = d1 < -_AREA_EPSILON or d2 < -_AREA_EPSILON or d3 < -_AREA_EPSILON
    has_positive = d1 > _AREA_EPSILON or d2 > _AREA_EPSILON or d3 > _AREA_EPSILON
    return not (has_negative and has_positive)


def _split_polygon_for_binary_limit(vertices: list[Vector3]) -> list[list[Vector3]]:
    if len(vertices) <= YNV_MAX_POLYGON_VERTICES:
        return [vertices]
    orientation = 1.0 if _polygon_area_xy(vertices) > 0.0 else -1.0
    remaining = list(range(len(vertices)))
    triangles: list[list[Vector3]] = []
    while len(remaining) > 3:
        for cursor, current in enumerate(remaining):
            previous = remaining[cursor - 1]
            following = remaining[(cursor + 1) % len(remaining)]
            a, b, c = vertices[previous], vertices[current], vertices[following]
            cross = (
                (b[0] - a[0]) * (c[1] - b[1])
                - (b[1] - a[1]) * (c[0] - b[0])
            )
            if cross * orientation <= _AREA_EPSILON:
                continue
            if any(
                _point_in_triangle_xy(vertices[index], a, b, c)
                for index in remaining
                if index not in (previous, current, following)
            ):
                continue
            triangles.append([a, b, c])
            del remaining[cursor]
            break
        else:
            raise ValueError(
                "YNV source polygon exceeds 15 vertices and cannot be triangulated; "
                "the polygon must be simple and non-self-intersecting"
            )
    triangles.append([vertices[index] for index in remaining])
    return triangles


def _edge_key(
    start: Vector3,
    end: Vector3,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    start_key = tuple(round(component * _EDGE_QUANTIZE) for component in start)
    end_key = tuple(round(component * _EDGE_QUANTIZE) for component in end)
    return (start_key, end_key) if start_key <= end_key else (end_key, start_key)


def _build_sector(
    minimum: Vector3,
    maximum: Vector3,
    polys: list[YnvPoly],
    depth: int,
) -> YnvSector:
    sector = YnvSector(
        aabb_min=minimum,
        aabb_max=maximum,
        aabb_min_w=float("nan"),
        aabb_max_w=float("nan"),
        cell_aabb=YnvAabb(min=minimum, max=maximum),
    )
    if depth <= 0:
        box = sector.cell_aabb
        sector.data = YnvSectorData(
            poly_ids=[
                index
                for index, poly in enumerate(polys)
                if poly.cell_aabb.max[0] >= box.min[0]
                and poly.cell_aabb.min[0] <= box.max[0]
                and poly.cell_aabb.max[1] >= box.min[1]
                and poly.cell_aabb.min[1] <= box.max[1]
            ]
        )
        return sector
    center_x = (minimum[0] + maximum[0]) * 0.5
    center_y = (minimum[1] + maximum[1]) * 0.5
    center_z = (minimum[2] + maximum[2]) * 0.5
    sector.subtree1 = _build_sector(
        (center_x, center_y, center_z), maximum, polys, depth - 1
    )
    sector.subtree2 = _build_sector(
        (center_x, minimum[1], 0.0),
        (maximum[0], center_y, 0.0),
        polys,
        depth - 1,
    )
    sector.subtree3 = _build_sector(
        minimum, (center_x, center_y, center_z), polys, depth - 1
    )
    sector.subtree4 = _build_sector(
        (minimum[0], center_y, 0.0),
        (center_x, maximum[1], 0.0),
        polys,
        depth - 1,
    )
    return sector


def _build_edge_map(
    groups: Mapping[tuple[int, int], list[_CellPolygon]],
) -> dict[
    tuple[tuple[int, int, int], tuple[int, int, int]],
    list[tuple[_CellPolygon, int]],
]:
    edge_map: dict[
        tuple[tuple[int, int, int], tuple[int, int, int]],
        list[tuple[_CellPolygon, int]],
    ] = {}
    for cell_polygons in groups.values():
        for polygon in cell_polygons:
            for edge_index, start in enumerate(polygon.vertices):
                end = polygon.vertices[(edge_index + 1) % len(polygon.vertices)]
                edge_map.setdefault(_edge_key(start, end), []).append(
                    (polygon, edge_index)
                )
    return edge_map


def _build_cell(
    polygons: list[_CellPolygon],
    edge_map: Mapping[
        tuple[tuple[int, int, int], tuple[int, int, int]],
        list[tuple[_CellPolygon, int]],
    ],
    *,
    source_path: str,
) -> tuple[Ynv, Mapping[Hashable, Sequence[int]]]:
    if not polygons:
        raise ValueError("Cannot build a YNV without polygons")
    cell_x, cell_y = polygons[0].cell_x, polygons[0].cell_y
    area_id = get_ynv_area_id(cell_x, cell_y)
    min_x, max_x, min_y, max_y = _cell_bounds(cell_x, cell_y)
    z_values = [vertex[2] for polygon in polygons for vertex in polygon.vertices]
    z_min, z_max = min(z_values), max(z_values)
    vertices: list[Vector3] = []
    indices: list[int] = []
    edges: list[YnvEdge] = []
    polys: list[YnvPoly] = []
    provenance: dict[Hashable, list[int]] = {}
    vertex_lookup: dict[tuple[int, int, int], int] = {}

    for polygon in polygons:
        index_id = len(indices)
        has_cross_area_edge = False
        for edge_index, vertex in enumerate(polygon.vertices):
            vertex_key = tuple(
                round(component * _EDGE_QUANTIZE) for component in vertex
            )
            vertex_id = vertex_lookup.get(vertex_key)
            if vertex_id is None:
                vertex_id = len(vertices)
                vertex_lookup[vertex_key] = vertex_id
                vertices.append(vertex)
            indices.append(vertex_id)
            next_vertex = polygon.vertices[(edge_index + 1) % len(polygon.vertices)]
            neighbour = next(
                (
                    candidate
                    for candidate in edge_map.get(_edge_key(vertex, next_vertex), ())
                    if candidate[0] is not polygon or candidate[1] != edge_index
                ),
                None,
            )
            poly2 = YnvEdgePart()
            if neighbour is not None:
                neighbour_polygon, _ = neighbour
                poly2 = YnvEdgePart(
                    area_id=neighbour_polygon.area_id,
                    poly_id=neighbour_polygon.local_index,
                    adjacency_type=YnvAdjacencyType.NORMAL,
                )
                has_cross_area_edge |= neighbour_polygon.area_id != area_id
            edge = YnvEdge(
                poly1=YnvEdgePart(
                    area_id=area_id,
                    poly_id=polygon.local_index,
                    adjacency_type=YnvAdjacencyType.NORMAL,
                ),
                poly2=poly2,
            )
            if neighbour is not None and neighbour[0].area_id != area_id:
                edge.flags |= YnvEdgeFlags.EXTERNAL_EDGE
            edges.append(edge)

        poly_min = tuple(min(vertex[axis] for vertex in polygon.vertices) for axis in range(3))
        poly_max = tuple(max(vertex[axis] for vertex in polygon.vertices) for axis in range(3))
        polys.append(
            YnvPoly(
                poly_flags0=(
                    YnvPolyFlags0.SMALL
                    if len(polygon.vertices) <= 4
                    else YnvPolyFlags0.LARGE
                ),
                index_id=index_id,
                index_count=len(polygon.vertices),
                area_id=area_id,
                cell_aabb=YnvAabb(min=poly_min, max=poly_max),
                poly_flags1=(
                    YnvPolyFlags1.IS_CELL_EDGE
                    if has_cross_area_edge
                    else YnvPolyFlags1.NONE
                ),
            )
        )
        if polygon.source_key is not None:
            provenance.setdefault(polygon.source_key, []).append(polygon.local_index)

    if len(vertices) > YNV_MAX_VERTICES:
        raise ValueError(f"YNV cell exceeds the {YNV_MAX_VERTICES}-vertex limit")
    if len(polys) > YNV_MAX_POLYGONS:
        raise ValueError(f"YNV cell exceeds the {YNV_MAX_POLYGONS}-polygon limit")
    if len(indices) > YNV_MAX_INDICES:
        raise ValueError(f"YNV cell exceeds the {YNV_MAX_INDICES}-index limit")

    ynv = Ynv(
        path=source_path,
        content_flags=YnvContentFlags.POLYGONS,
        aabb_size=(max_x - min_x, max_y - min_y, z_max - z_min),
        vertices=vertices,
        indices=indices,
        edges=edges,
        polys=polys,
        sector_tree=_build_sector(
            (min_x, min_y, z_min),
            (max_x, max_y, z_max),
            polys,
            _SECTOR_DEPTH,
        ),
        area_id=area_id,
    ).build()
    issues = ynv.validate()
    if issues:
        raise ValueError("Invalid authored YNV:\n" + "\n".join(issues))
    return ynv, {key: tuple(value) for key, value in provenance.items()}


def _prepare_groups(
    polygons: Sequence[YnvSourcePolygon],
    *,
    clip_to_grid: bool,
) -> dict[tuple[int, int], list[_CellPolygon]]:
    groups: dict[tuple[int, int], list[_CellPolygon]] = {}
    for source in polygons:
        source.build()
        xs = [vertex[0] for vertex in source.vertices]
        ys = [vertex[1] for vertex in source.vertices]
        cell_pairs = (
            (
                (cell_x, cell_y)
                for cell_x in get_ynv_cell_span(min(xs), max(xs))
                for cell_y in get_ynv_cell_span(min(ys), max(ys))
            )
            if clip_to_grid
            else (
                (
                    _clamp_cell_index((min(xs) + max(xs)) * 0.5),
                    _clamp_cell_index((min(ys) + max(ys)) * 0.5),
                ),
            )
        )
        for cell_x, cell_y in cell_pairs:
            vertices = (
                clip_ynv_polygon_to_cell(source.vertices, cell_x, cell_y)
                if clip_to_grid
                else list(source.vertices)
            )
            if not vertices:
                continue
            min_x, max_x, min_y, max_y = _cell_bounds(cell_x, cell_y)
            if not all(
                min_x - _AREA_EPSILON <= vertex[0] <= max_x + _AREA_EPSILON
                and min_y - _AREA_EPSILON <= vertex[1] <= max_y + _AREA_EPSILON
                for vertex in vertices
            ):
                raise ValueError("build_ynv_cell received a polygon outside its inferred cell")
            for part in _split_polygon_for_binary_limit(vertices):
                groups.setdefault((cell_x, cell_y), []).append(
                    _CellPolygon(
                        vertices=part,
                        source_key=source.source_key,
                        cell_x=cell_x,
                        cell_y=cell_y,
                        area_id=get_ynv_area_id(cell_x, cell_y),
                    )
                )
    for cell_polygons in groups.values():
        for local_index, polygon in enumerate(cell_polygons):
            polygon.local_index = local_index
    return groups


def build_ynv_cells(
    polygons: Sequence[YnvSourcePolygon],
    *,
    source_path: str = "",
) -> list[tuple[Ynv, Mapping[Hashable, Sequence[int]]]]:
    groups = _prepare_groups(polygons, clip_to_grid=True)
    edge_map = _build_edge_map(groups)
    return [
        _build_cell(groups[key], edge_map, source_path=source_path)
        for key in sorted(groups)
    ]


def build_ynv_cell(
    polygons: Sequence[YnvSourcePolygon],
    *,
    source_path: str = "",
) -> tuple[Ynv, Mapping[Hashable, Sequence[int]]]:
    groups = _prepare_groups(polygons, clip_to_grid=False)
    if len(groups) != 1:
        raise ValueError("build_ynv_cell requires polygons from exactly one YNV cell")
    edge_map = _build_edge_map(groups)
    return _build_cell(next(iter(groups.values())), edge_map, source_path=source_path)


__all__ = [
    "YNV_CELL_COUNT",
    "YNV_CELL_SIZE",
    "YNV_GRID_MIN",
    "YNV_MAX_ADJACENT_AREAS",
    "YNV_MAX_INDICES",
    "YNV_MAX_POLYGONS",
    "YNV_MAX_POLYGON_VERTICES",
    "YNV_MAX_VERTICES",
    "YnvSourcePolygon",
    "build_ynv_cell",
    "build_ynv_cells",
    "clip_ynv_polygon_to_cell",
    "get_ynv_area_id",
    "get_ynv_cell_span",
    "get_ynv_file_coords",
]
