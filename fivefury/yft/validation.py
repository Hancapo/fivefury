from __future__ import annotations

import dataclasses
import enum
import math
from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fragment import Yft
    from .physics import YftPhysicsLod


class YftValidationSeverity(enum.StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclasses.dataclass(frozen=True, slots=True)
class YftValidationIssue:
    severity: YftValidationSeverity
    path: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.severity == YftValidationSeverity.ERROR

    def format(self) -> str:
        return f"{self.severity.value}: {self.path}: {self.message}"


def _issue(
    issues: list[YftValidationIssue],
    severity: YftValidationSeverity,
    path: str,
    message: str,
) -> None:
    issues.append(YftValidationIssue(severity, path, message))


def _has_models(drawable: object) -> bool:
    try:
        return any(True for _model in drawable.iter_models())  # type: ignore[attr-defined]
    except AttributeError:
        return False


def _finite_values(values: Iterable[float]) -> bool:
    return all(math.isfinite(float(value)) for value in values)


def _validate_lod(
    lod: YftPhysicsLod, path: str, issues: list[YftValidationIssue]
) -> None:
    if lod.num_groups != len(lod.groups):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            f"{path}.groups",
            f"declares {lod.num_groups} groups but parsed {len(lod.groups)}",
        )
    if lod.num_children != len(lod.children):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            f"{path}.children",
            f"declares {lod.num_children} children but parsed {len(lod.children)}",
        )
    if lod.group_names and len(lod.group_names) != len(lod.groups):
        _issue(
            issues,
            YftValidationSeverity.WARNING,
            f"{path}.group_names",
            "group-name count differs from group count",
        )
    if lod.root_group_count > len(lod.groups):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            f"{path}.root_group_count",
            "root-group count is larger than group count",
        )
    if lod.num_bony_children > len(lod.children):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            f"{path}.num_bony_children",
            "bony-child count is larger than child count",
        )

    if lod.min_breaking_impulses and len(lod.min_breaking_impulses) != len(
        lod.children
    ):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            f"{path}.min_breaking_impulses",
            "count must match children",
        )
    if lod.undamaged_ang_inertia and len(lod.undamaged_ang_inertia) != len(
        lod.children
    ):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            f"{path}.undamaged_ang_inertia",
            "count must match children",
        )
    if lod.damaged_ang_inertia and len(lod.damaged_ang_inertia) != len(lod.children):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            f"{path}.damaged_ang_inertia",
            "count must match children",
        )
    if lod.link_attachments.matrices and len(lod.link_attachments.matrices) != len(
        lod.children
    ):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            f"{path}.link_attachments",
            "count must match children",
        )

    for index, group in enumerate(lod.groups):
        group_path = f"{path}.groups[{index}]"
        if group.child_index != 0xFF and group.child_index + group.num_children > len(
            lod.children
        ):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                group_path,
                "child slice points outside the child array",
            )
        if (
            group.parent_group_pointer_index != 0xFF
            and group.parent_group_pointer_index >= len(lod.groups)
        ):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                group_path,
                "parent group index points outside the group array",
            )
        for child_index in group.child_group_indices:
            if child_index >= len(lod.groups):
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    group_path,
                    "child group index points outside the group array",
                )
        if group.total_undamaged_mass < 0.0 or group.total_damaged_mass < 0.0:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                group_path,
                "group mass cannot be negative",
            )

    for index, child in enumerate(lod.children):
        child_path = f"{path}.children[{index}]"
        if child.owner_group_pointer_index >= len(lod.groups):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                child_path,
                "owner group index points outside the group array",
            )
        if child.undamaged_mass < 0.0 or child.damaged_mass < 0.0:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                child_path,
                "child mass cannot be negative",
            )
        if child.min_breaking_impulse < 0.0:
            _issue(
                issues,
                YftValidationSeverity.WARNING,
                child_path,
                "negative breaking impulse is unusual",
            )
        if not _finite_values(
            (
                *child.undamaged_ang_inertia.as_tuple(),
                *child.damaged_ang_inertia.as_tuple(),
            )
        ):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                child_path,
                "angular inertia contains NaN or infinity",
            )

    for index, (first, second) in enumerate(lod.self_collision_pairs):
        if first >= len(lod.groups) or second >= len(lod.groups):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{path}.self_collision_pairs[{index}]",
                "group index points outside the group array",
            )

    if lod.groups and lod.children:
        grouped_undamaged_mass = sum(group.total_undamaged_mass for group in lod.groups)
        grouped_damaged_mass = sum(group.total_damaged_mass for group in lod.groups)
        if grouped_undamaged_mass and not math.isclose(
            grouped_undamaged_mass, lod.total_undamaged_mass, rel_tol=0.05, abs_tol=0.01
        ):
            _issue(
                issues,
                YftValidationSeverity.WARNING,
                f"{path}.groups",
                "group undamaged mass total differs from child mass total",
            )
        if grouped_damaged_mass and not math.isclose(
            grouped_damaged_mass, lod.total_damaged_mass, rel_tol=0.05, abs_tol=0.01
        ):
            _issue(
                issues,
                YftValidationSeverity.WARNING,
                f"{path}.groups",
                "group damaged mass total differs from child mass total",
            )

    if lod.body_type.exists and lod.articulated_body_type is None:
        _issue(
            issues,
            YftValidationSeverity.WARNING,
            f"{path}.body_type",
            "body type pointer exists but was not decoded",
        )
    if lod.phys_damp_undamaged.exists and lod.undamaged_damp_archetype is None:
        _issue(
            issues,
            YftValidationSeverity.WARNING,
            f"{path}.phys_damp_undamaged",
            "undamaged damping archetype pointer exists but was not decoded",
        )
    if lod.phys_damp_damaged.exists and lod.damaged_damp_archetype is None:
        _issue(
            issues,
            YftValidationSeverity.WARNING,
            f"{path}.phys_damp_damaged",
            "damaged damping archetype pointer exists but was not decoded",
        )

    if lod.articulated_body_type is not None:
        body = lod.articulated_body_type
        if body.num_links > 23 or body.num_joints > 22:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{path}.body_type",
                "articulated body exceeds GTA V link/joint limits",
            )
        if body.joints and len(body.joints) != body.num_joints:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{path}.body_type.joints",
                "joint count differs from articulated body metadata",
            )
        if body.num_joints and not body.joints:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{path}.body_type.joints",
                "articulated joints must be decoded or declared before writing",
            )
        for joint_index, joint in enumerate(body.joints):
            joint_path = f"{path}.body_type.joints[{joint_index}]"
            if joint.parent_link_index >= body.num_links:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    joint_path,
                    "parent link index points outside the articulated body",
                )
            if joint.child_link_index >= body.num_links:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    joint_path,
                    "child link index points outside the articulated body",
                )
            if joint.parent_link_index == joint.child_link_index:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    joint_path,
                    "parent and child links must be different",
                )
        if body.num_joints and body.num_joints != max(0, body.num_links - 1):
            _issue(
                issues,
                YftValidationSeverity.WARNING,
                f"{path}.body_type",
                "joint count usually equals link count minus one",
            )


def validate_yft(source: Yft) -> list[YftValidationIssue]:
    issues: list[YftValidationIssue] = []
    if source.main_drawable is None:
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "drawable",
            "common drawable is required",
        )
    elif not _has_models(source.main_drawable):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "drawable",
            "common drawable has no models",
        )

    labels = [entry.label for entry in source.drawables]
    duplicates = sorted(label for label, count in Counter(labels).items() if count > 1)
    for label in duplicates:
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "drawables",
            f"duplicate extra drawable label '{label}'",
        )

    damaged_index = source.state.damaged_drawable_index
    if damaged_index < -1 or damaged_index >= len(source.drawables):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "state.damaged_drawable_index",
            "must be -1 or point into the extra drawable array",
        )

    unsupported_root_sections = {
        "user_data": source.pointers.user_data,
        "collision_event_player": source.pointers.collision_event_player,
    }
    for label, pointer in unsupported_root_sections.items():
        if pointer:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"pointers.{label}",
                "section is readable but cannot yet be rebuilt safely",
            )
    if source.pointers.collision_event_set and source.collision_event_set is None:
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "collision_event_set",
            "event-set pointer could not be decoded",
        )
    if (
        source.collision_event_set is not None
        and not source.collision_event_set.can_rebuild
    ):
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "collision_event_set",
            "event instances and editor pointers cannot yet be rebuilt safely",
        )
    if source.root_child is not None and not source.root_child.events.can_rebuild:
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "root_child.events",
            "event players or populated event sets cannot yet be rebuilt safely",
        )
    for field in source.raw_fields:
        if field.label in {
            "character_cloth",
        }:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"raw_fields.{field.label}",
                "section is readable but cannot yet be rebuilt safely",
            )
    if source.character_cloth_count:
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "character_cloths",
            "character-cloth arrays are not part of the legacy YFT corpus",
        )
    if source.shared_matrix_set is not None:
        matrix_set = source.shared_matrix_set
        if matrix_set.matrix_count > 0xFF:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                "shared_matrix_set",
                "legacy matrix sets support at most 255 matrices",
            )
        for index, matrix in enumerate(matrix_set.matrices):
            if len(matrix) != 12 or not _finite_values(matrix):
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"shared_matrix_set.matrices[{index}]",
                    "must contain 12 finite Matrix43 values",
                )
    if len(source.lights) > 0xFFFF:
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "lights",
            "native light arrays support at most 65535 entries",
        )
    for index, light in enumerate(source.lights):
        vectors = (
            light.position,
            light.culling_plane_normal,
            light.direction,
            light.tangent,
            light.extent,
        )
        if any(len(vector) != 3 or not _finite_values(vector) for vector in vectors):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"lights[{index}]",
                "light vectors must contain three finite values",
            )
    if len(source.glass_panes) > 0xFF:
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "glass_panes",
            "legacy fragments support at most 255 glass panes",
        )
    for index, pane in enumerate(source.glass_panes):
        pane_path = f"glass_panes[{index}]"
        if any(
            len(value) != size
            for value, size in (
                (pane.position_base, 3),
                (pane.position_width, 3),
                (pane.position_height, 3),
                (pane.uv_min, 2),
                (pane.uv_max, 2),
                (pane.tangent, 3),
            )
        ):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                pane_path,
                "vector dimensions do not match the native pane layout",
            )
        if not 0 <= int(pane.glass_type) <= 0xFF:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{pane_path}.glass_type",
                "must fit in one byte",
            )
        if not 0 <= int(pane.shader_index) <= 0xFF:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{pane_path}.shader_index",
                "must fit in one byte",
            )
        declaration = pane.vertex_declaration
        if not 0 < declaration.stride <= 0xFFFF:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{pane_path}.vertex_declaration.stride",
                "must be between 1 and 65535",
            )
        if declaration.count > 0xFF:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{pane_path}.vertex_declaration.component_count",
                "must fit in one byte",
            )
        if not _finite_values(
            (
                *pane.position_base,
                *pane.position_width,
                *pane.position_height,
                *pane.uv_min,
                *pane.uv_max,
                pane.thickness,
                pane.bounds_offset_front,
                pane.bounds_offset_back,
                *pane.tangent,
            )
        ):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                pane_path,
                "contains NaN or infinity",
            )
    vehicle_glass = source.vehicle_glass_windows
    if vehicle_glass is not None:
        component_ids = [window.component_id for window in vehicle_glass.windows]
        if len(component_ids) != len(set(component_ids)):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                "vehicle_glass_windows",
                "component IDs must be unique",
            )
        for index, window in enumerate(vehicle_glass.windows):
            window_path = f"vehicle_glass_windows.windows[{index}]"
            if len(window.basis) != 16:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"{window_path}.basis",
                    "must contain 16 matrix values",
                )
            if not 0 <= window.component_id <= 0xFFFF:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"{window_path}.component_id",
                    "must fit in an unsigned 16-bit integer",
                )
            if not 0 <= window.geometry_index <= 0xFFFF:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"{window_path}.geometry_index",
                    "must fit in an unsigned 16-bit integer",
                )
            if window.row_count != len(window.rows) and window.rows:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"{window_path}.data_rows",
                    "must match the number of RLE rows",
                )
            if window.column_count > 0xFFFF or window.row_count > 0xFFFF:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    window_path,
                    "distance-field dimensions must fit in unsigned 16-bit integers",
                )
            inferred_width = max((row.width for row in window.rows), default=0)
            if window.data_columns and window.data_columns < inferred_width:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"{window_path}.data_columns",
                    "cannot be smaller than the encoded RLE rows",
                )
            if not _finite_values(
                (*window.basis, window.data_min, window.data_max, window.texture_scale)
            ):
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    window_path,
                    "contains NaN or infinity",
                )
            row_data_size = 0
            for row_index, row in enumerate(window.rows):
                if row.first is None and row.second is not None:
                    _issue(
                        issues,
                        YftValidationSeverity.ERROR,
                        f"{window_path}.rows[{row_index}]",
                        "a second span requires a first span",
                    )
                spans = (
                    ()
                    if row.first is None
                    else (
                        (row.first,) if row.second is None else (row.first, row.second)
                    )
                )
                for span_index, span in enumerate(spans):
                    if not span.values or not 0 <= span.start <= span.end <= 0xFF:
                        _issue(
                            issues,
                            YftValidationSeverity.ERROR,
                            (f"{window_path}.rows[{row_index}].spans[{span_index}]"),
                            "span must contain values and remain inside 0..255",
                        )
                if row.first is None:
                    row_data_size += 1
                elif row.second is None:
                    row_data_size += 3 + len(row.first.values)
                else:
                    row_data_size += 4 + len(row.first.values) + len(row.second.values)
                if row_data_size > 0xFFFF:
                    _issue(
                        issues,
                        YftValidationSeverity.ERROR,
                        f"{window_path}.rows[{row_index}]",
                        "RLE row offset exceeds the unsigned 16-bit limit",
                    )
    if len(source.environment_cloths) > 1:
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "environment_cloths",
            "legacy fragments support at most one environment cloth",
        )
    for index, cloth in enumerate(source.environment_cloths):
        cloth_path = f"environment_cloths[{index}]"
        if cloth.controller.bridge is None:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{cloth_path}.controller.bridge",
                "simulation-to-graphics bridge is required",
            )
        if cloth.controller.morph is None:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{cloth_path}.controller.morph",
                "morph controller is required",
            )
        if cloth.controller.verlet_lods[0] is None:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{cloth_path}.controller.verlet_lods",
                "highest-detail Verlet cloth is required",
            )
        bridge = cloth.controller.bridge
        if not cloth.controller.name:
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"{cloth_path}.controller.name",
                "controller name is required",
            )
        for lod_index, verlet in enumerate(cloth.controller.verlet_lods):
            if verlet is None:
                continue
            if verlet.previous_vertices and (
                len(verlet.previous_vertices) != verlet.vertex_count
            ):
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"{cloth_path}.controller.verlet_lods[{lod_index}]",
                    "previous-vertex count must match vertex count",
                )
            if bridge is None:
                continue
            mesh_vertex_count = bridge.mesh_vertex_counts[lod_index]
            display_map = bridge.display_maps[lod_index]
            if display_map and len(display_map) != mesh_vertex_count:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"{cloth_path}.controller.bridge.display_maps[{lod_index}]",
                    "display-map count must match the mesh vertex count",
                )
            for field_name, values in (
                ("pin_radii", bridge.pin_radii[lod_index]),
                ("vertex_weights", bridge.vertex_weights[lod_index]),
                ("inflation_scales", bridge.inflation_scales[lod_index]),
            ):
                if values and len(values) != mesh_vertex_count:
                    _issue(
                        issues,
                        YftValidationSeverity.ERROR,
                        f"{cloth_path}.controller.bridge.{field_name}[{lod_index}]",
                        "array count must match the mesh vertex count",
                    )
            if display_map and max(display_map) >= verlet.vertex_count:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"{cloth_path}.controller.bridge.display_maps[{lod_index}]",
                    "display map references a vertex outside the Verlet cloth",
                )

    for entry in source.iter_drawables():
        drawable = entry.drawable
        indices = getattr(drawable, "extra_bound_indices", ())
        matrices = getattr(drawable, "extra_bound_matrices", ())
        if len(indices) != len(matrices):
            _issue(
                issues,
                YftValidationSeverity.ERROR,
                f"drawables.{entry.label}.extra_bounds",
                "index and matrix counts must match",
            )

    if source.physics_lods.has_physics and not source.physics_lod_details:
        _issue(
            issues,
            YftValidationSeverity.ERROR,
            "physics_lods",
            "physics LOD pointers exist but no LOD could be decoded",
        )
    if (
        len(source.physics_lod_details) != source.physics_lods.active_count
        and source.physics_lods.has_physics
    ):
        _issue(
            issues,
            YftValidationSeverity.WARNING,
            "physics_lods",
            "decoded physics LOD count differs from active pointer count",
        )

    for index, lod in enumerate(source.physics_lod_details):
        _validate_lod(lod, f"physics_lod_details[{index}]", issues)
        for child_index, child in enumerate(lod.children):
            if not child.events.can_rebuild:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"physics_lod_details[{index}].children[{child_index}].events",
                    "event players or populated event sets cannot yet be rebuilt safely",
                )
        for group_index, group in enumerate(lod.groups):
            if not group.events.can_rebuild:
                _issue(
                    issues,
                    YftValidationSeverity.ERROR,
                    f"physics_lod_details[{index}].groups[{group_index}].events",
                    "event players or populated event sets cannot yet be rebuilt safely",
                )
    return issues


def assert_valid_yft(source: Yft) -> None:
    errors = [issue for issue in validate_yft(source) if issue.is_error]
    if errors:
        details = "\n".join(issue.format() for issue in errors)
        raise ValueError(f"Invalid YFT:\n{details}")


__all__ = [
    "YftValidationIssue",
    "YftValidationSeverity",
    "assert_valid_yft",
    "validate_yft",
]
