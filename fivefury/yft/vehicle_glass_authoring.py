from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence

import numpy as np

from ..authoring import ValidationReport
from ..bounds import BoundGeometry
from ..game_target import GameTarget, coerce_game_target
from ..mesh_math import triangle_array
from ..numeric import float64_rows
from ..ydr import YdrBone, YdrLod
from .glass import (
    YftVehicleGlassFlag,
    YftVehicleGlassRow,
    YftVehicleGlassSpan,
    YftVehicleGlassWindow,
    YftVehicleGlassWindows,
)
from .glass_selection import material_shader_name, mesh_material

_CELL_SIZE = 0.025
_BLUR_PASSES = 20
_EXTRA_MARGIN = 1
_THRESHOLD_MIN = -0.025
_THRESHOLD_MAX = 0.050
_MAX_COLUMNS = 800
_MAX_ROWS = 256
_CAR_GLASS_MATERIAL_NAMES = frozenset(
    {
        "CAR_GLASS_WEAK",
        "CAR_GLASS_MEDIUM",
        "CAR_GLASS_STRONG",
        "CAR_GLASS_BULLETPROOF",
        "CAR_GLASS_OPAQUE",
    }
)


@dataclasses.dataclass(frozen=True, slots=True)
class YftVehicleGlassAssignment:
    component_id: int
    geometry_index: int
    bone: str | int
    name: str = ""
    triangle_indices: tuple[int, ...] = ()

    @classmethod
    def declare(
        cls,
        component_id: int,
        geometry_index: int,
        bone: str | int | YdrBone,
        *,
        name: str = "",
        triangle_indices: Sequence[int] = (),
    ) -> YftVehicleGlassAssignment:
        return cls(
            component_id=int(component_id),
            geometry_index=int(geometry_index),
            bone=int(bone.tag) if isinstance(bone, YdrBone) else bone,
            name=str(name),
            triangle_indices=tuple(int(index) for index in triangle_indices),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class YftVehicleGlassMeshChannel:
    geometry_index: int
    texcoord2: tuple[tuple[float, float], ...]


@dataclasses.dataclass(slots=True)
class YftVehicleGlassBuild:
    target: GameTarget
    windows: YftVehicleGlassWindows = dataclasses.field(
        default_factory=YftVehicleGlassWindows
    )
    mesh_channels: list[YftVehicleGlassMeshChannel] = dataclasses.field(
        default_factory=list
    )
    report: ValidationReport = dataclasses.field(default_factory=ValidationReport)


@dataclasses.dataclass(frozen=True, slots=True)
class _PaneProjection:
    normalised: np.ndarray
    axis_x: np.ndarray
    axis_y: np.ndarray
    axis_z: np.ndarray
    centre: np.ndarray
    extent: np.ndarray


def _issue(
    report: ValidationReport,
    code: str,
    message: str,
    *,
    path: str,
) -> None:
    report.issue(code, message, path=path)


def _target_version(target: GameTarget) -> int:
    return 171 if target is GameTarget.GTA5_ENHANCED else 162


def _high_model(source, report: ValidationReport):
    drawable = source.main_drawable
    if drawable is None:
        _issue(
            report,
            "yft.vehicle_glass.drawable_missing",
            "vehicle glass requires a common drawable",
            path="main_drawable",
        )
        return None
    models = list(drawable.iter_models(YdrLod.HIGH))
    if len(models) != 1:
        _issue(
            report,
            "yft.vehicle_glass.high_model_count",
            "vehicle glass requires exactly one high-detail drawable model",
            path="main_drawable.lods[high]",
        )
        return None
    return models[0]


def _resolve_bone(source, value: str | int, report: ValidationReport, path: str):
    drawable = source.main_drawable
    skeleton = getattr(drawable, "skeleton", None)
    if skeleton is None:
        _issue(
            report,
            "yft.vehicle_glass.skeleton_missing",
            "vehicle glass assignments require a drawable skeleton",
            path=path,
        )
        return None
    bone = skeleton.get_bone_by_name(value) if isinstance(value, str) else None
    if bone is None and not isinstance(value, str):
        bone = skeleton.get_bone_by_tag(int(value))
        if bone is None:
            bone = skeleton.get_bone_by_index(int(value))
    if bone is None:
        _issue(
            report,
            "yft.vehicle_glass.bone_unresolved",
            f"bone {value!r} does not resolve in the drawable skeleton",
            path=path,
        )
    return bone


def _mesh_bone_index(mesh, bone: YdrBone, vertex_index: int) -> int | None:
    if vertex_index >= len(mesh.blend_indices):
        return None
    indices = mesh.blend_indices[vertex_index]
    weights = (
        mesh.blend_weights[vertex_index] if mesh.blend_weights else (1.0, 0.0, 0.0, 0.0)
    )
    active = [
        (int(index), float(weight))
        for index, weight in zip(indices, weights, strict=True)
        if float(weight) > 1e-6
    ]
    if len(active) != 1 or not math.isclose(active[0][1], 1.0, abs_tol=1e-5):
        return None
    binding = active[0][0]
    if mesh.bone_ids:
        if not 0 <= binding < len(mesh.bone_ids):
            return None
        bone_id = int(mesh.bone_ids[binding])
        if bone_id in (int(bone.index), int(bone.tag)):
            return binding
        return None
    return binding if binding in (int(bone.index), int(bone.tag)) else None


def _bound_uses_car_glass_material(bound) -> bool:
    if bound is None:
        return False
    if isinstance(bound, BoundGeometry):
        polygon_materials = list(bound.iter_polygon_materials())
        if polygon_materials:
            return any(
                material.name in _CAR_GLASS_MATERIAL_NAMES
                for material in polygon_materials
            )
    material_type = getattr(bound, "material_type", None)
    return getattr(material_type, "name", "") in _CAR_GLASS_MATERIAL_NAMES


def _assigned_triangles(
    mesh,
    bone: YdrBone,
    assignment: YftVehicleGlassAssignment,
    report: ValidationReport,
    path: str,
) -> np.ndarray:
    triangles = triangle_array(mesh.indices, len(mesh.positions))
    requested = set(assignment.triangle_indices)
    if requested and (min(requested) < 0 or max(requested) >= len(triangles)):
        _issue(
            report,
            "yft.vehicle_glass.triangle_index",
            "triangle_indices references a triangle outside the geometry",
            path=f"{path}.triangle_indices",
        )
        return np.empty((0, 3), dtype=np.int64)
    selected: list[np.ndarray] = []
    for index, triangle in enumerate(triangles):
        if requested and index not in requested:
            continue
        bindings = [_mesh_bone_index(mesh, bone, int(vertex)) for vertex in triangle]
        if all(binding is not None for binding in bindings):
            selected.append(triangle)
        elif requested:
            _issue(
                report,
                "yft.vehicle_glass.not_hard_skinned",
                "assigned triangles must be hard-skinned entirely to the declared bone",
                path=f"{path}.triangle_indices",
            )
            return np.empty((0, 3), dtype=np.int64)
    if not selected:
        _issue(
            report,
            "yft.vehicle_glass.empty_assignment",
            "assignment does not select any hard-skinned triangle",
            path=path,
        )
        return np.empty((0, 3), dtype=np.int64)
    return np.asarray(selected, dtype=np.int64)


def _pane_projection(points: np.ndarray) -> _PaneProjection:
    unique = np.unique(points, axis=0)
    if len(unique) < 3:
        raise ValueError("pane must contain at least three unique vertices")
    centre = unique.mean(axis=0)
    covariance = (unique - centre).T @ (unique - centre)
    values, vectors = np.linalg.eigh(covariance)
    if values[-1] <= 1e-12 or values[-2] <= 1e-12:
        raise ValueError("pane geometry is degenerate")
    axis_z = vectors[:, 0]
    dominant = int(np.argmax(np.abs(axis_z)))
    if axis_z[dominant] < 0.0:
        axis_z = -axis_z
    up = np.array((0.0, 0.0, 1.0))
    if abs(float(np.dot(axis_z, up))) > 0.999:
        up = np.array((1.0, 0.0, 0.0))
    axis_x = np.cross(up, axis_z)
    axis_x /= np.linalg.norm(axis_x)
    axis_y = np.cross(axis_x, axis_z)
    projected = np.column_stack((points @ axis_x, points @ axis_y, points @ axis_z))
    minimum = projected.min(axis=0)
    maximum = projected.max(axis=0)
    extent = (maximum - minimum) * 0.5
    if extent[0] <= 1e-6 or extent[1] <= 1e-6:
        raise ValueError("pane has no usable planar extent")
    basis_centre = (minimum + maximum) * 0.5
    normalised = np.column_stack(
        (
            (projected[:, 0] - basis_centre[0]) / (extent[0] * 2.0) + 0.5,
            (projected[:, 1] - basis_centre[1]) / (extent[1] * 2.0) + 0.5,
        )
    )
    return _PaneProjection(
        normalised=normalised,
        axis_x=axis_x,
        axis_y=axis_y,
        axis_z=axis_z,
        centre=basis_centre,
        extent=extent,
    )


def _rasterise(triangles: np.ndarray, columns: int, rows: int) -> np.ndarray:
    mask = np.zeros((rows, columns), dtype=bool)
    for triangle in triangles:
        minimum = np.floor(triangle.min(axis=0)).astype(int)
        maximum = np.ceil(triangle.max(axis=0)).astype(int)
        x0, y0 = np.maximum(minimum, 0)
        x1, y1 = np.minimum(maximum, (columns - 1, rows - 1))
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(
            np.arange(x0, x1 + 1, dtype=np.float64) + 0.5,
            np.arange(y0, y1 + 1, dtype=np.float64) + 0.5,
        )
        p = np.stack((xs, ys), axis=-1)
        a, b, c = triangle
        area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(float(area)) <= 1e-12:
            continue
        w0 = (
            (b[0] - p[..., 0]) * (c[1] - p[..., 1])
            - (b[1] - p[..., 1]) * (c[0] - p[..., 0])
        ) / area
        w1 = (
            (c[0] - p[..., 0]) * (a[1] - p[..., 1])
            - (c[1] - p[..., 1]) * (a[0] - p[..., 0])
        ) / area
        w2 = 1.0 - w0 - w1
        mask[y0 : y1 + 1, x0 : x1 + 1] |= (w0 >= -1e-8) & (w1 >= -1e-8) & (w2 >= -1e-8)
    return mask


def _distance_transform_1d(values: np.ndarray) -> np.ndarray:
    count = len(values)
    sites = np.empty(count, dtype=np.int64)
    boundaries = np.empty(count + 1, dtype=np.float64)
    k = 0
    sites[0] = 0
    boundaries[0] = -np.inf
    boundaries[1] = np.inf
    for q in range(1, count):
        while True:
            p = sites[k]
            separation = ((values[q] + q * q) - (values[p] + p * p)) / (2 * q - 2 * p)
            if separation > boundaries[k] or k == 0:
                break
            k -= 1
        if separation <= boundaries[k]:
            separation = -np.inf
        k += 1
        sites[k] = q
        boundaries[k] = separation
        boundaries[k + 1] = np.inf
    result = np.empty(count, dtype=np.float64)
    k = 0
    for q in range(count):
        while boundaries[k + 1] < q:
            k += 1
        delta = q - sites[k]
        result[q] = delta * delta + values[sites[k]]
    return result


def _distance_transform(mask: np.ndarray) -> np.ndarray:
    infinity = float(mask.shape[0] * mask.shape[0] + mask.shape[1] * mask.shape[1] + 1)
    source = np.where(mask, infinity, 0.0)
    rows = np.vstack([_distance_transform_1d(row) for row in source])
    return np.vstack([_distance_transform_1d(column) for column in rows.T]).T


def _blur(values: np.ndarray, passes: int) -> np.ndarray:
    current = values
    for _ in range(passes):
        padded = np.pad(current, 1, mode="edge")
        current = (
            sum(
                padded[y : y + values.shape[0], x : x + values.shape[1]]
                for y in range(3)
                for x in range(3)
            )
            / 9.0
        )
    return current


def _local_extrema(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    padded = np.pad(values, 1, mode="edge")
    neighbourhood = np.stack(
        [
            padded[y : y + values.shape[0], x : x + values.shape[1]]
            for y in range(3)
            for x in range(3)
        ]
    )
    return neighbourhood.min(axis=0), neighbourhood.max(axis=0)


def _row_spans(active: np.ndarray, quantised: np.ndarray) -> YftVehicleGlassRow:
    indices = np.flatnonzero(active)
    if not len(indices):
        return YftVehicleGlassRow.empty()
    runs: list[tuple[int, int]] = []
    start = previous = int(indices[0])
    for index in indices[1:]:
        value = int(index)
        if value != previous + 1:
            runs.append((start, previous))
            start = value
        previous = value
    runs.append((start, previous))
    if len(runs) > 2:
        gaps = [
            runs[index + 1][0] - runs[index][1] - 1 for index in range(len(runs) - 1)
        ]
        split = int(np.argmax(gaps))
        runs = [(runs[0][0], runs[split][1]), (runs[split + 1][0], runs[-1][1])]
    spans = [
        YftVehicleGlassSpan(int(start), bytes(quantised[start : end + 1]))
        for start, end in runs
    ]
    return YftVehicleGlassRow(spans[0], spans[1] if len(spans) == 2 else None)


def _texture_scale(points: np.ndarray, triangles: np.ndarray, uv: np.ndarray) -> float:
    values: list[float] = []
    for triangle in triangles:
        p0, p1, p2 = points[triangle]
        uv0, uv1, uv2 = uv[triangle]
        edge1 = p1 - p0
        edge2 = p2 - p0
        delta1 = uv1 - uv0
        delta2 = uv2 - uv0
        determinant = float(delta1[0] * delta2[1] - delta1[1] * delta2[0])
        if abs(determinant) <= 1e-12:
            continue
        tangent = (delta2[1] * edge1 - delta1[1] * edge2) / determinant
        bitangent = (-delta2[0] * edge1 + delta1[0] * edge2) / determinant
        values.append(
            math.sqrt((float(tangent @ tangent) + float(bitangent @ bitangent)) * 0.5)
        )
    return float(np.mean(values)) if values else 2.0


def _window_from_geometry(
    assignment: YftVehicleGlassAssignment,
    mesh,
    triangles: np.ndarray,
) -> tuple[YftVehicleGlassWindow, dict[int, tuple[float, float]]]:
    points = float64_rows(mesh.positions, 3, name="vehicle glass positions")
    used_vertices = np.unique(triangles.reshape(-1))
    pane_points = points[used_vertices]
    projection = _pane_projection(pane_points)
    min_cell_x = 2.0 * projection.extent[0] / (_MAX_COLUMNS - 1) + 0.001
    min_cell_y = 2.0 * projection.extent[1] / (_MAX_ROWS - 1) + 0.001
    cell_size = max(_CELL_SIZE, float(min_cell_x), float(min_cell_y))
    margin = _EXTRA_MARGIN + _BLUR_PASSES
    columns = math.ceil(2.0 * projection.extent[0] / cell_size) + 1 + margin * 2
    rows = math.ceil(2.0 * projection.extent[1] / cell_size) + 1 + margin * 2
    scale = np.array((columns - (1 + margin * 2), rows - (1 + margin * 2)))
    offset = 0.5 * (1 + margin * 2)
    grid_points = projection.normalised * scale + offset
    local_index = {int(vertex): index for index, vertex in enumerate(used_vertices)}
    grid_triangles = np.asarray(
        [
            [grid_points[local_index[int(vertex)]] for vertex in triangle]
            for triangle in triangles
        ],
        dtype=np.float64,
    )
    mask = _rasterise(grid_triangles, columns, rows)
    signed = (
        np.sqrt(_distance_transform(~mask)) - np.sqrt(_distance_transform(mask))
    ) * cell_size
    signed = _blur(signed, _BLUR_PASSES)
    local_min, local_max = _local_extrema(signed)
    active = (local_max >= _THRESHOLD_MIN) & (local_min <= _THRESHOLD_MAX)
    active[:_BLUR_PASSES, :] = False
    active[-_BLUR_PASSES:, :] = False
    active[:, :_BLUR_PASSES] = False
    active[:, -_BLUR_PASSES:] = False
    active_rows, active_columns = np.nonzero(active)
    if not len(active_rows):
        raise ValueError("pane distance field contains no serializable cells")
    row_first, row_last = int(active_rows.min()), int(active_rows.max())
    column_first, column_last = int(active_columns.min()), int(active_columns.max())
    cropped = signed[row_first : row_last + 1, column_first : column_last + 1]
    cropped_active = active[row_first : row_last + 1, column_first : column_last + 1]
    selected_values = cropped[cropped_active]
    data_min = float(selected_values.min())
    data_max = float(selected_values.max())
    span = data_max - data_min
    quantised = np.zeros(cropped.shape, dtype=np.uint8)
    if span > 1e-12:
        quantised = np.rint(
            np.clip((cropped - data_min) / span, 0.0, 1.0) * 255.0
        ).astype(np.uint8)
    encoded_rows = [
        _row_spans(row_active, row_values)
        for row_active, row_values in zip(cropped_active, quantised, strict=True)
    ]

    row_matrix = np.eye(4, dtype=np.float64)
    row_matrix[0, :3] = projection.axis_x * (scale[0] / (projection.extent[0] * 2.0))
    row_matrix[1, :3] = projection.axis_y * (scale[1] / (projection.extent[1] * 2.0))
    row_matrix[2, :3] = projection.axis_z
    row_matrix[0, 3] = (
        offset
        + 0.5 * scale[0]
        - column_first
        - projection.centre[0] * scale[0] / (projection.extent[0] * 2.0)
    )
    row_matrix[1, 3] = (
        offset
        + 0.5 * scale[1]
        - row_first
        - projection.centre[1] * scale[1] / (projection.extent[1] * 2.0)
    )
    row_matrix[2, 3] = -projection.centre[2]

    uv1 = float64_rows(mesh.texcoords[1], 2, name="vehicle glass UV1")
    window = YftVehicleGlassWindow(
        component_id=assignment.component_id,
        geometry_index=assignment.geometry_index,
        rows=encoded_rows,
        basis=tuple(float(value) for value in row_matrix.flatten(order="F")),
        data_min=data_min,
        data_max=data_max,
        flags=YftVehicleGlassFlag.VERSION_2 | YftVehicleGlassFlag.FROM_HIGH_DETAIL_MESH,
        texture_scale=_texture_scale(points, triangles, uv1),
        data_columns=column_last - column_first + 1,
        data_rows=row_last - row_first + 1,
    )
    texcoord2 = {
        int(vertex): (float(grid_points[index, 0]), float(grid_points[index, 1]))
        for index, vertex in enumerate(used_vertices)
    }
    return window, texcoord2


def derive_yft_vehicle_glass(
    source,
    assignments: Sequence[YftVehicleGlassAssignment],
    *,
    game: GameTarget | str,
) -> YftVehicleGlassBuild:
    target = coerce_game_target(game)
    result = YftVehicleGlassBuild(target=target)
    expected_version = _target_version(target)
    if int(source.version) != expected_version:
        _issue(
            result.report,
            "yft.vehicle_glass.edition_version",
            f"{target.value} vehicle glass requires YFT version {expected_version}",
            path="version",
        )
    model = _high_model(source, result.report)
    if model is None:
        return result
    if not assignments:
        _issue(
            result.report,
            "yft.vehicle_glass.assignments_empty",
            "at least one explicit pane assignment is required",
            path="vehicle_glass_assignments",
        )
        return result

    component_ids: set[int] = set()
    claimed_triangles: dict[tuple[int, int], int] = {}
    channels: dict[int, list[tuple[float, float] | None]] = {}
    windows: list[YftVehicleGlassWindow] = []
    for assignment_index, assignment in enumerate(assignments):
        path = f"vehicle_glass_assignments[{assignment_index}]"
        if assignment.component_id in component_ids:
            _issue(
                result.report,
                "yft.vehicle_glass.component_duplicate",
                "component_id must be unique",
                path=f"{path}.component_id",
            )
            continue
        component_ids.add(assignment.component_id)
        if not 0 <= assignment.geometry_index < len(model.meshes):
            _issue(
                result.report,
                "yft.vehicle_glass.geometry_index",
                "geometry_index does not resolve in the high-detail model",
                path=f"{path}.geometry_index",
            )
            continue
        mesh = model.meshes[assignment.geometry_index]
        material = mesh_material(source.main_drawable, mesh)
        shader = material_shader_name(material) if material is not None else ""
        bucket = (
            int(getattr(material, "render_bucket", -1)) if material is not None else -1
        )
        if shader.lower().removesuffix(".sps") != "vehicle_vehglass" or bucket != 1:
            _issue(
                result.report,
                "yft.vehicle_glass.material",
                "outer vehicle glass geometry must use vehicle_vehglass.sps in render bucket 1",
                path=f"{path}.geometry_index",
            )
        vertex_count = len(mesh.positions)
        if (
            len(mesh.tangents) != vertex_count
            or len(mesh.texcoords) < 2
            or any(len(channel) != vertex_count for channel in mesh.texcoords[:2])
        ):
            _issue(
                result.report,
                "yft.vehicle_glass.vertex_channels",
                "vehicle glass geometry requires tangents and two complete source UV channels",
                path=f"main_drawable.lods[high].meshes[{assignment.geometry_index}]",
            )
            continue
        bone = _resolve_bone(source, assignment.bone, result.report, f"{path}.bone")
        if bone is None:
            continue
        triangles = _assigned_triangles(mesh, bone, assignment, result.report, path)
        if not len(triangles):
            continue
        all_triangles = triangle_array(mesh.indices, vertex_count)
        triangle_lookup = {
            tuple(int(value) for value in triangle): index
            for index, triangle in enumerate(all_triangles)
        }
        overlap = False
        for triangle in triangles:
            triangle_index = triangle_lookup[tuple(int(value) for value in triangle)]
            key = (assignment.geometry_index, triangle_index)
            if key in claimed_triangles:
                _issue(
                    result.report,
                    "yft.vehicle_glass.assignment_overlap",
                    f"triangle is already assigned to pane {claimed_triangles[key]}",
                    path=path,
                )
                overlap = True
            claimed_triangles[key] = assignment_index
        if overlap:
            continue
        try:
            window, values = _window_from_geometry(assignment, mesh, triangles)
        except ValueError as exc:
            _issue(
                result.report,
                "yft.vehicle_glass.geometry",
                str(exc),
                path=path,
            )
            continue
        channel = channels.setdefault(assignment.geometry_index, [None] * vertex_count)
        for vertex, value in values.items():
            if channel[vertex] is not None:
                _issue(
                    result.report,
                    "yft.vehicle_glass.vertex_overlap",
                    "a vertex belongs to more than one pane assignment",
                    path=path,
                )
            channel[vertex] = value
        windows.append(window)

    for geometry_index, channel in channels.items():
        if any(value is None for value in channel):
            _issue(
                result.report,
                "yft.vehicle_glass.geometry_unassigned",
                "every vertex in an outer vehicle-glass geometry must belong to one pane",
                path=f"main_drawable.lods[high].meshes[{geometry_index}]",
            )
            continue
        result.mesh_channels.append(
            YftVehicleGlassMeshChannel(
                geometry_index,
                tuple(value for value in channel if value is not None),
            )
        )
    result.windows = YftVehicleGlassWindows(
        sorted(windows, key=lambda item: item.component_id)
    )
    return result


def recalculate_yft_vehicle_glass(
    source,
    assignments: Sequence[YftVehicleGlassAssignment],
    *,
    game: GameTarget | str,
) -> YftVehicleGlassBuild:
    result = derive_yft_vehicle_glass(source, assignments, game=game)
    if not result.report.valid:
        return result
    model = next(source.main_drawable.iter_models(YdrLod.HIGH))
    for channel in result.mesh_channels:
        mesh = model.meshes[channel.geometry_index]
        texcoords = [list(values) for values in mesh.texcoords[:2]]
        texcoords.append(list(channel.texcoord2))
        mesh.texcoords = texcoords
    source.vehicle_glass_windows = result.windows
    return result


def validate_yft_vehicle_glass(source) -> ValidationReport:
    report = ValidationReport()
    vehicle_glass = source.vehicle_glass_windows
    if vehicle_glass is None:
        return report
    model = _high_model(source, report)
    if model is None:
        return report
    lod = source.best_physics_lod
    composite = getattr(lod, "composite_bound", None) if lod is not None else None
    skeleton = getattr(source.main_drawable, "skeleton", None)
    for index, window in enumerate(vehicle_glass.windows):
        path = f"vehicle_glass_windows.windows[{index}]"
        if not 0 <= window.geometry_index < len(model.meshes):
            _issue(
                report,
                "yft.vehicle_glass.geometry_index",
                "geometry_index does not resolve in the high-detail model",
                path=f"{path}.geometry_index",
            )
            continue
        mesh = model.meshes[window.geometry_index]
        material = mesh_material(source.main_drawable, mesh)
        shader = material_shader_name(material) if material is not None else ""
        if (
            shader.lower().removesuffix(".sps") != "vehicle_vehglass"
            or int(getattr(material, "render_bucket", -1)) != 1
        ):
            _issue(
                report,
                "yft.vehicle_glass.material",
                "referenced geometry must use vehicle_vehglass.sps in render bucket 1",
                path=f"{path}.geometry_index",
            )
        if len(mesh.texcoords) < 3 or len(mesh.texcoords[2]) != len(mesh.positions):
            _issue(
                report,
                "yft.vehicle_glass.texcoord2",
                "referenced geometry requires a complete TexCoord2 channel",
                path=f"{path}.geometry_index",
            )
        if window.column_count > _MAX_COLUMNS or window.row_count > _MAX_ROWS:
            _issue(
                report,
                "yft.vehicle_glass.grid_dimensions",
                f"vehicle glass grids are limited to {_MAX_COLUMNS} columns and {_MAX_ROWS} rows",
                path=path,
            )
        if lod is None or not 0 <= window.component_id < len(lod.children):
            _issue(
                report,
                "yft.vehicle_glass.component_id",
                "component_id does not resolve in the high physics LOD",
                path=f"{path}.component_id",
            )
            continue
        child = lod.children[window.component_id]
        bone = None
        if skeleton is not None:
            bone = skeleton.get_bone_by_tag(child.bone_id)
            if bone is None:
                bone = skeleton.get_bone_by_index(child.bone_id)
        if bone is None:
            _issue(
                report,
                "yft.vehicle_glass.component_bone",
                "physics component bone does not resolve in the drawable skeleton",
                path=f"{path}.component_id",
            )
        else:
            _assigned_triangles(
                mesh,
                bone,
                YftVehicleGlassAssignment(
                    component_id=window.component_id,
                    geometry_index=window.geometry_index,
                    bone=bone.tag,
                ),
                report,
                path,
            )
        bound = None
        if (
            composite is not None
            and hasattr(composite, "active_children")
            and window.component_id < len(composite.active_children)
        ):
            bound = composite.active_children[window.component_id].bound
        if not _bound_uses_car_glass_material(bound):
            _issue(
                report,
                "yft.vehicle_glass.physics_material",
                "physics component must reference a car-glass collision material",
                path=f"{path}.component_id",
            )
    return report


__all__ = [
    "YftVehicleGlassAssignment",
    "YftVehicleGlassBuild",
    "YftVehicleGlassMeshChannel",
    "derive_yft_vehicle_glass",
    "recalculate_yft_vehicle_glass",
    "validate_yft_vehicle_glass",
]
