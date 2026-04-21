from __future__ import annotations

import dataclasses
import math
from pathlib import Path

from ..ydr.assimp import AssimpScene, read_assimp_scene
from .model import (
    Ynv,
    YnvAabb,
    YnvAdjacencyType,
    YnvContentFlags,
    YnvEdge,
    YnvEdgePart,
    YnvPoly,
    YnvPolyFlags0,
    YnvPolyFlags1,
    YnvSector,
    YnvSectorData,
)

_NAV_CELL_SIZE = 150.0
_NAV_GRID_MIN = -6000.0
_NAV_CELL_COUNT = 100
_SECTOR_DEPTH = 2
_EDGE_QUANTIZE = 10000.0
_AREA_EPSILON = 1e-6


@dataclasses.dataclass(slots=True)
class _NavPolygon:
    vertices: list[tuple[float, float, float]]
    cell_x: int
    cell_y: int
    area_id: int
    file_x: int
    file_y: int
    local_index: int = -1


def _clamp_cell_index(value: float) -> int:
    index = int(math.floor((float(value) - _NAV_GRID_MIN) / _NAV_CELL_SIZE))
    return max(0, min(_NAV_CELL_COUNT - 1, index))


def _cell_span(min_value: float, max_value: float) -> range:
    start = _clamp_cell_index(min_value)
    finish = _clamp_cell_index(math.nextafter(float(max_value), -math.inf))
    return range(start, finish + 1)


def _cell_bounds(cell_x: int, cell_y: int) -> tuple[float, float, float, float]:
    min_x = _NAV_GRID_MIN + (int(cell_x) * _NAV_CELL_SIZE)
    min_y = _NAV_GRID_MIN + (int(cell_y) * _NAV_CELL_SIZE)
    return (min_x, min_x + _NAV_CELL_SIZE, min_y, min_y + _NAV_CELL_SIZE)


def _area_id(cell_x: int, cell_y: int) -> int:
    return int(cell_x) + (int(cell_y) * 100)


def _file_coords(cell_x: int, cell_y: int) -> tuple[int, int]:
    return (int(cell_x) * 3, int(cell_y) * 3)


def _polygon_area_xy(vertices: list[tuple[float, float, float]]) -> float:
    total = 0.0
    for index, current in enumerate(vertices):
        nxt = vertices[(index + 1) % len(vertices)]
        total += (current[0] * nxt[1]) - (nxt[0] * current[1])
    return total * 0.5


def _inside_x_min(vertex: tuple[float, float, float], boundary: float) -> bool:
    return vertex[0] >= boundary - _AREA_EPSILON


def _inside_x_max(vertex: tuple[float, float, float], boundary: float) -> bool:
    return vertex[0] <= boundary + _AREA_EPSILON


def _inside_y_min(vertex: tuple[float, float, float], boundary: float) -> bool:
    return vertex[1] >= boundary - _AREA_EPSILON


def _inside_y_max(vertex: tuple[float, float, float], boundary: float) -> bool:
    return vertex[1] <= boundary + _AREA_EPSILON


def _intersect_x(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    boundary: float,
) -> tuple[float, float, float]:
    delta = end[0] - start[0]
    if abs(delta) <= _AREA_EPSILON:
        return (boundary, start[1], start[2])
    t = (boundary - start[0]) / delta
    return (
        boundary,
        start[1] + ((end[1] - start[1]) * t),
        start[2] + ((end[2] - start[2]) * t),
    )


def _intersect_y(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    boundary: float,
) -> tuple[float, float, float]:
    delta = end[1] - start[1]
    if abs(delta) <= _AREA_EPSILON:
        return (start[0], boundary, start[2])
    t = (boundary - start[1]) / delta
    return (
        start[0] + ((end[0] - start[0]) * t),
        boundary,
        start[2] + ((end[2] - start[2]) * t),
    )


def _clip_polygon(
    vertices: list[tuple[float, float, float]],
    inside,
    intersect,
    boundary: float,
) -> list[tuple[float, float, float]]:
    if not vertices:
        return []
    clipped: list[tuple[float, float, float]] = []
    previous = vertices[-1]
    previous_inside = inside(previous, boundary)
    for current in vertices:
        current_inside = inside(current, boundary)
        if current_inside:
            if not previous_inside:
                clipped.append(intersect(previous, current, boundary))
            clipped.append(current)
        elif previous_inside:
            clipped.append(intersect(previous, current, boundary))
        previous = current
        previous_inside = current_inside
    return clipped


def _clip_triangle_to_cell(
    triangle: list[tuple[float, float, float]],
    cell_x: int,
    cell_y: int,
) -> list[tuple[float, float, float]]:
    min_x, max_x, min_y, max_y = _cell_bounds(cell_x, cell_y)
    polygon = list(triangle)
    polygon = _clip_polygon(polygon, _inside_x_min, _intersect_x, min_x)
    polygon = _clip_polygon(polygon, _inside_x_max, _intersect_x, max_x)
    polygon = _clip_polygon(polygon, _inside_y_min, _intersect_y, min_y)
    polygon = _clip_polygon(polygon, _inside_y_max, _intersect_y, max_y)
    if len(polygon) < 3:
        return []
    if abs(_polygon_area_xy(polygon)) <= _AREA_EPSILON:
        return []
    return polygon


def _iter_scene_triangles(scene: AssimpScene) -> list[list[tuple[float, float, float]]]:
    triangles: list[list[tuple[float, float, float]]] = []
    for mesh in scene.meshes:
        for index in range(0, len(mesh.indices), 3):
            triangle_indices = mesh.indices[index : index + 3]
            if len(triangle_indices) != 3:
                continue
            triangles.append([mesh.positions[int(vertex_index)] for vertex_index in triangle_indices])
    return triangles


def _edge_key(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    start_key = tuple(int(round(component * _EDGE_QUANTIZE)) for component in start)
    end_key = tuple(int(round(component * _EDGE_QUANTIZE)) for component in end)
    return (start_key, end_key) if start_key <= end_key else (end_key, start_key)


def _build_sector(
    min_corner: tuple[float, float, float],
    max_corner: tuple[float, float, float],
    polys: list[YnvPoly],
    depth: int,
) -> YnvSector:
    sector = YnvSector(
        aabb_min=min_corner,
        aabb_max=max_corner,
        aabb_min_w=float("nan"),
        aabb_max_w=float("nan"),
        cell_aabb=YnvAabb(min=min_corner, max=max_corner),
    )
    if depth <= 0:
        box = sector.cell_aabb
        poly_ids = [
            index
            for index, poly in enumerate(polys)
            if poly.cell_aabb.max[0] >= box.min[0]
            and poly.cell_aabb.min[0] <= box.max[0]
            and poly.cell_aabb.max[1] >= box.min[1]
            and poly.cell_aabb.min[1] <= box.max[1]
        ]
        sector.data = YnvSectorData(poly_ids=poly_ids)
        return sector
    cen_x = (min_corner[0] + max_corner[0]) * 0.5
    cen_y = (min_corner[1] + max_corner[1]) * 0.5
    cen_z = (min_corner[2] + max_corner[2]) * 0.5
    sector.subtree1 = _build_sector((cen_x, cen_y, cen_z), (max_corner[0], max_corner[1], max_corner[2]), polys, depth - 1)
    sector.subtree2 = _build_sector((cen_x, min_corner[1], 0.0), (max_corner[0], cen_y, 0.0), polys, depth - 1)
    sector.subtree3 = _build_sector((min_corner[0], min_corner[1], min_corner[2]), (cen_x, cen_y, cen_z), polys, depth - 1)
    sector.subtree4 = _build_sector((min_corner[0], cen_y, 0.0), (cen_x, max_corner[1], 0.0), polys, depth - 1)
    return sector


def _build_cell_ynv(polygons: list[_NavPolygon], *, source_path: str = "") -> Ynv:
    if not polygons:
        raise ValueError("Cannot build a YNV without polygons")
    cell_x = polygons[0].cell_x
    cell_y = polygons[0].cell_y
    area_id = polygons[0].area_id
    file_x = polygons[0].file_x
    file_y = polygons[0].file_y
    min_x, max_x, min_y, max_y = _cell_bounds(cell_x, cell_y)
    z_values = [vertex[2] for polygon in polygons for vertex in polygon.vertices]
    z_min = min(z_values) if z_values else 0.0
    z_max = max(z_values) if z_values else 0.0

    for index, polygon in enumerate(polygons):
        polygon.local_index = index

    edge_map: dict[tuple[tuple[int, int, int], tuple[int, int, int]], list[tuple[_NavPolygon, int]]] = {}
    for polygon in polygons:
        for edge_index, start in enumerate(polygon.vertices):
            end = polygon.vertices[(edge_index + 1) % len(polygon.vertices)]
            edge_map.setdefault(_edge_key(start, end), []).append((polygon, edge_index))

    vertices: list[tuple[float, float, float]] = []
    indices: list[int] = []
    edges: list[YnvEdge] = []
    polys: list[YnvPoly] = []
    vertex_lookup: dict[tuple[int, int, int], int] = {}

    for polygon in polygons:
        index_id = len(indices)
        has_cross_area_edge = False
        for edge_index, vertex in enumerate(polygon.vertices):
            vertex_key = tuple(int(round(component * _EDGE_QUANTIZE)) for component in vertex)
            vertex_id = vertex_lookup.get(vertex_key)
            if vertex_id is None:
                vertex_id = len(vertices)
                vertex_lookup[vertex_key] = vertex_id
                vertices.append(vertex)
            indices.append(vertex_id)

            next_vertex = polygon.vertices[(edge_index + 1) % len(polygon.vertices)]
            candidates = edge_map.get(_edge_key(vertex, next_vertex), [])
            neighbour = next(((poly, idx) for poly, idx in candidates if poly is not polygon or idx != edge_index), None)
            poly1 = YnvEdgePart(area_id=polygon.area_id, poly_id=polygon.local_index, adjacency_type=YnvAdjacencyType.NORMAL)
            poly2 = YnvEdgePart()
            if neighbour is not None:
                neighbour_poly, _ = neighbour
                poly2 = YnvEdgePart(
                    area_id=neighbour_poly.area_id,
                    poly_id=neighbour_poly.local_index,
                    adjacency_type=YnvAdjacencyType.NORMAL,
                    detail_flags=4 if neighbour_poly.area_id != polygon.area_id else 0,
                )
                if neighbour_poly.area_id != polygon.area_id:
                    has_cross_area_edge = True
            edges.append(YnvEdge(poly1=poly1, poly2=poly2))

        poly_min = (
            min(vertex[0] for vertex in polygon.vertices),
            min(vertex[1] for vertex in polygon.vertices),
            min(vertex[2] for vertex in polygon.vertices),
        )
        poly_max = (
            max(vertex[0] for vertex in polygon.vertices),
            max(vertex[1] for vertex in polygon.vertices),
            max(vertex[2] for vertex in polygon.vertices),
        )
        poly_flags0 = YnvPolyFlags0.SMALL if len(polygon.vertices) <= 4 else YnvPolyFlags0.LARGE
        poly_flags1 = YnvPolyFlags1.IS_CELL_EDGE if has_cross_area_edge else YnvPolyFlags1.NONE
        polys.append(
            YnvPoly(
                poly_flags0=poly_flags0,
                index_id=index_id,
                index_count=len(polygon.vertices),
                area_id=area_id,
                cell_aabb=YnvAabb(min=poly_min, max=poly_max),
                poly_flags1=poly_flags1,
            )
        )

    sector_tree = _build_sector((min_x, min_y, z_min), (max_x, max_y, z_max), polys, _SECTOR_DEPTH)
    name = f"navmesh[{file_x}][{file_y}]"
    return Ynv(
        path=source_path,
        content_flags=YnvContentFlags.POLYGONS,
        aabb_size=(max_x - min_x, max_y - min_y, z_max - z_min),
        vertices=vertices,
        indices=indices,
        edges=edges,
        polys=polys,
        sector_tree=sector_tree,
        area_id=area_id,
    ).build()


def assimp_to_ynvs(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    processing: int | None = None,
) -> list[Ynv] | list[Path]:
    scene = read_assimp_scene(source, processing=processing)
    grouped: dict[tuple[int, int], list[_NavPolygon]] = {}

    for triangle in _iter_scene_triangles(scene):
        xs = [vertex[0] for vertex in triangle]
        ys = [vertex[1] for vertex in triangle]
        for cell_x in _cell_span(min(xs), max(xs)):
            for cell_y in _cell_span(min(ys), max(ys)):
                clipped = _clip_triangle_to_cell(triangle, cell_x, cell_y)
                if not clipped:
                    continue
                area_id = _area_id(cell_x, cell_y)
                file_x, file_y = _file_coords(cell_x, cell_y)
                grouped.setdefault((cell_x, cell_y), []).append(
                    _NavPolygon(
                        vertices=clipped,
                        cell_x=cell_x,
                        cell_y=cell_y,
                        area_id=area_id,
                        file_x=file_x,
                        file_y=file_y,
                    )
                )

    ynvs = [
        _build_cell_ynv(grouped[key], source_path=str(source))
        for key in sorted(grouped)
        if grouped[key]
    ]
    if destination is None:
        return ynvs

    output_dir = Path(destination)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for ynv in ynvs:
        path = output_dir / f"navmesh[{(ynv.area_id % 100) * 3}][{(ynv.area_id // 100) * 3}].ynv"
        ynv.save(path)
        saved_paths.append(path)
    return saved_paths


def obj_to_nav(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    processing: int | None = None,
) -> list[Ynv] | list[Path]:
    return assimp_to_ynvs(source, destination, processing=processing)


__all__ = ["assimp_to_ynvs", "obj_to_nav"]
