from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..authoring.diagnostics import DiagnosticSeverity, ValidationReport
from ..bounds import BoundComposite, BoundGeometry
from ..vector import Vector2, Vector3
from .articulation import validate_articulated_body
from .bound_profiles import YftPhysicsBoundProfile, validate_bound_profile
from .constants import MAX_EXTRA_BOUNDS
from .geometry import (
    MAX_FRAGMENT_BOUND_MATERIALS,
    MAX_FRAGMENT_BOUND_POLYGONS,
    MAX_FRAGMENT_BOUND_VERTICES,
)
from .glass_selection import iter_bone_meshes, mesh_material, mesh_material_index

if TYPE_CHECKING:
    from ..authoring.context import BuildContext
    from .fragment import Yft
    from .physics import YftPhysicsLod


def _issue(
    issues: ValidationReport,
    severity: DiagnosticSeverity,
    path: str,
    message: str,
    *,
    code: str,
) -> None:
    issues.issue(code, message, severity=severity, path=path)


def _has_models(drawable: object) -> bool:
    try:
        return any(True for _model in drawable.iter_models())  # type: ignore[attr-defined]
    except AttributeError:
        return False


def _finite_values(values: Iterable[float]) -> bool:
    return all(math.isfinite(float(value)) for value in values)


def _validate_fragment_geometry_limits(
    root: object,
    path: str,
    issues: ValidationReport,
) -> None:
    walk = getattr(root, "walk", None)
    if walk is None:
        return
    for bound_index, bound in enumerate(walk()):
        if not isinstance(bound, BoundGeometry):
            continue
        bound_path = f"{path}[{bound_index}]"
        for field, count, limit in (
            ("vertices", len(bound.vertices), MAX_FRAGMENT_BOUND_VERTICES),
            ("polygons", len(bound.polygons), MAX_FRAGMENT_BOUND_POLYGONS),
            ("materials", len(bound.materials), MAX_FRAGMENT_BOUND_MATERIALS),
        ):
            if count > limit:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{bound_path}.{field}",
                    f"count {count} exceeds the fragment bound limit of {limit}",
                    code="yft.fragment_geometry_limits.count_exceeds_fragment_bound_limit",
                )
        if not _finite_values(
            value
            for vertex in (*bound.vertices, *bound.vertices_shrunk)
            for value in vertex
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{bound_path}.vertices",
                "coordinates must be finite",
                code="yft.fragment_geometry_limits.coordinates_must_finite",
            )
        for material_index, material in enumerate(bound.materials):
            material_path = f"{bound_path}.materials[{material_index}]"
            if material.data1 or material.data2:
                if not (
                    0 <= int(material.data1) <= 0xFFFFFFFF
                    and 0 <= int(material.data2) <= 0xFFFFFFFF
                ):
                    _issue(
                        issues,
                        DiagnosticSeverity.ERROR,
                        material_path,
                        "raw material data must fit in unsigned 32-bit fields",
                        code="yft.fragment_geometry_limits.raw_material_data_must_fit_unsigned_32_bit_fields",
                    )
                continue
            for field, value, maximum in (
                ("type", material.type, 0xFF),
                ("procedural_id", material.procedural_id, 0xFF),
                ("room_id", material.room_id, 0x1F),
                ("ped_density", material.ped_density, 0x07),
                ("flags", material.flags, 0xFFFF),
                ("material_color_index", material.material_color_index, 0xFF),
                ("reserved", material.reserved, 0xFFFF),
            ):
                if not 0 <= int(value) <= maximum:
                    _issue(
                        issues,
                        DiagnosticSeverity.ERROR,
                        f"{material_path}.{field}",
                        f"value must be between 0 and {maximum}",
                        code="yft.fragment_geometry_limits.value_must_between_0",
                    )


def _validate_glass_geometry_relationship(
    child: object,
    pane: object,
    path: str,
    issues: ValidationReport,
    *,
    common_drawable: object | None,
) -> None:
    entity = getattr(child, "undamaged_entity", None)
    child_drawable = getattr(entity, "drawable", None)
    if child_drawable is None:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.child.undamaged_entity.drawable",
            "glass physics requires an intact child drawable",
            code="yft.glass_geometry_relationship.glass_physics_requires_intact_child_drawable",
        )
    elif getattr(child_drawable, "bound", None) is None:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.child.undamaged_entity.drawable.bound",
            "glass physics requires an intact drawable bound",
            code="yft.glass_geometry_relationship.glass_physics_requires_intact_drawable_bound",
        )

    if common_drawable is None:
        return
    materials = getattr(common_drawable, "materials", ())
    shader_index = int(getattr(pane, "shader_index", 0))
    material_indices = {
        int(getattr(material, "index", index))
        for index, material in enumerate(materials)
    }
    if shader_index not in material_indices:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.glass_pane.shader_index",
            "does not point into the common drawable shader group",
            code="yft.glass_geometry_relationship.does_not_point_common_drawable_shader_group",
        )
        return

    skeleton = getattr(common_drawable, "skeleton", None)
    iter_models = getattr(common_drawable, "iter_models", None)
    if skeleton is None or iter_models is None:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.child.bone_id",
            "glass physics requires a common drawable skeleton",
            code="yft.glass_geometry_relationship.glass_physics_requires_common_drawable_skeleton",
        )
        return
    bone_id = int(getattr(child, "bone_id", 0))
    bone = skeleton.get_bone_by_tag(bone_id) or skeleton.get_bone_by_index(bone_id)
    if bone is None:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.child.bone_id",
            "does not resolve in the common drawable skeleton",
            code="yft.glass_geometry_relationship.does_not_resolve_common_drawable_skeleton",
        )
        return

    candidates = tuple(
        item for model in iter_models() for item in iter_bone_meshes(model, bone)
    )
    if not candidates:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.child.bone_id",
            "does not select render geometry in the common drawable",
            code="yft.glass_geometry_relationship.does_not_select_render_geometry_common_drawable",
        )
        return
    if not any(
        material is not None
        and mesh_material_index(common_drawable, mesh, material) == shader_index
        for mesh, _binding in candidates
        for material in (mesh_material(common_drawable, mesh),)
    ):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.glass_pane.shader_index",
            "does not match geometry selected by the glass child bone",
            code="yft.glass_geometry_relationship.does_not_match_geometry_selected_glass_child_bone",
        )


def _validate_glass_group(
    lod: YftPhysicsLod,
    group_index: int,
    path: str,
    issues: ValidationReport,
    *,
    glass_panes: list[object],
    common_drawable: object | None,
) -> None:
    group = lod.groups[group_index]
    if not group.is_glass:
        if group.glass_pane_model_info_index != 0:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{path}.glass_pane_model_info_index",
                "non-glass groups cannot reference glass pane metadata",
                code="yft.glass_group.non_glass_groups_cannot_reference_glass_pane_metadata",
            )
        return

    if group.child_index == 0xFF or group.num_children == 0:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.children",
            "glass groups require at least one physics child",
            code="yft.glass_group.glass_groups_require_at_least_one_physics_child",
        )
        return
    if group.child_index >= len(lod.children):
        return

    pane_index = int(group.glass_pane_model_info_index)
    if pane_index >= len(glass_panes):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.glass_pane_model_info_index",
            "does not point into the fragment glass pane array",
            code="yft.glass_group.does_not_point_fragment_glass_pane_array",
        )
        return
    _validate_glass_geometry_relationship(
        lod.children[group.child_index],
        glass_panes[pane_index],
        path,
        issues,
        common_drawable=common_drawable,
    )


def _validate_lod(
    lod: YftPhysicsLod,
    path: str,
    issues: ValidationReport,
    *,
    bound_profile: YftPhysicsBoundProfile,
    glass_panes: list[object],
    common_drawable: object | None,
) -> None:
    for field, value in (
        ("num_groups", len(lod.groups)),
        ("root_group_count", lod.root_group_count),
        ("num_root_damage_regions", lod.num_root_damage_regions),
        ("num_bony_children", lod.num_bony_children),
        ("num_children", len(lod.children)),
        ("num_self_collisions", len(lod.self_collision_pairs)),
        ("max_num_self_collisions", lod.max_num_self_collisions),
    ):
        if not 0 <= int(value) <= 0xFF:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{path}.{field}",
                "must fit in an unsigned 8-bit field",
                code="yft.lod.must_fit_unsigned_8_bit_field",
            )
    if lod.num_groups != len(lod.groups):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.groups",
            f"declares {lod.num_groups} groups but parsed {len(lod.groups)}",
            code="yft.lod.declares_groups_parsed",
        )
    if lod.num_children != len(lod.children):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.children",
            f"declares {lod.num_children} children but parsed {len(lod.children)}",
            code="yft.lod.declares_children_parsed",
        )
    if lod.group_names and len(lod.group_names) != len(lod.groups):
        _issue(
            issues,
            DiagnosticSeverity.WARNING,
            f"{path}.group_names",
            "group-name count differs from group count",
            code="yft.lod.group_name_count_differs_group_count",
        )
    if lod.root_group_count > len(lod.groups):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.root_group_count",
            "root-group count is larger than group count",
            code="yft.lod.root_group_count_larger_than_group_count",
        )
    if lod.num_bony_children > len(lod.children):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.num_bony_children",
            "bony-child count is larger than child count",
            code="yft.lod.bony_child_count_larger_than_child_count",
        )
    for index, child in enumerate(lod.children):
        if not 0 <= int(child.owner_group_pointer_index) <= 0xFF:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{path}.children[{index}].owner_group_pointer_index",
                "must fit in an unsigned 8-bit field",
                code="yft.lod.must_fit_unsigned_8_bit_field",
            )
        if not 0 <= int(child.flags) <= 0xFF:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{path}.children[{index}].flags",
                "must fit in an unsigned 8-bit field",
                code="yft.lod.must_fit_unsigned_8_bit_field",
            )
        if not 0 <= int(child.bone_id) <= 0xFFFF:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{path}.children[{index}].bone_id",
                "must fit in an unsigned 16-bit field",
                code="yft.lod.must_fit_unsigned_16_bit_field",
            )
        if child.bone_controlled is not None and child.bone_controlled != (
            index < lod.num_bony_children
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{path}.children[{index}].bone_controlled",
                "must agree with the leading bony-child range",
                code="yft.lod.must_agree_leading_bony_child_range",
            )

    if lod.min_breaking_impulses and len(lod.min_breaking_impulses) != len(
        lod.children
    ):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.min_breaking_impulses",
            "count must match children",
            code="yft.lod.count_must_match_children",
        )
    if lod.undamaged_ang_inertia and len(lod.undamaged_ang_inertia) != len(
        lod.children
    ):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.undamaged_ang_inertia",
            "count must match children",
            code="yft.lod.count_must_match_children",
        )
    if lod.damaged_ang_inertia and len(lod.damaged_ang_inertia) != len(lod.children):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.damaged_ang_inertia",
            "count must match children",
            code="yft.lod.count_must_match_children",
        )
    if lod.link_attachments.matrices and len(lod.link_attachments.matrices) != len(
        lod.children
    ):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.link_attachments",
            "count must match children",
            code="yft.lod.count_must_match_children",
        )

    for index, group in enumerate(lod.groups):
        group_path = f"{path}.groups[{index}]"
        for field, value in (
            ("child_groups_pointers_index", group.child_groups_pointers_index),
            ("parent_group_pointer_index", group.parent_group_pointer_index),
            ("child_index", group.child_index),
            ("num_children", group.num_children),
            ("num_child_groups", group.num_child_groups),
            ("glass_model_and_type", group.glass_model_and_type),
            (
                "glass_pane_model_info_index",
                group.glass_pane_model_info_index,
            ),
            ("flags", group.flags),
        ):
            if not 0 <= int(value) <= 0xFF:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{group_path}.{field}",
                    "must fit in an unsigned 8-bit field",
                    code="yft.lod.must_fit_unsigned_8_bit_field",
                )
        if group.child_index != 0xFF and group.child_index + group.num_children > len(
            lod.children
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                group_path,
                "child slice points outside the child array",
                code="yft.lod.child_slice_points_outside_child_array",
            )
        if (
            group.parent_group_pointer_index != 0xFF
            and group.parent_group_pointer_index >= len(lod.groups)
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                group_path,
                "parent group index points outside the group array",
                code="yft.lod.parent_group_index_points_outside_group_array",
            )
        for child_index in group.child_group_indices:
            if child_index >= len(lod.groups):
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    group_path,
                    "child group index points outside the group array",
                    code="yft.lod.child_group_index_points_outside_group_array",
                )
        if group.total_undamaged_mass < 0.0 or (
            group.total_damaged_mass is not None and group.total_damaged_mass < 0.0
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                group_path,
                "group mass cannot be negative",
                code="yft.lod.group_mass_cannot_negative",
            )
        if (
            bound_profile is not YftPhysicsBoundProfile.PRESERVE
            and group.total_damaged_mass is not None
            and group.total_damaged_mass <= 0.0
            and any(child.has_damage_state for child in group.children)
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{group_path}.total_damaged_mass",
                "authored damaged groups require positive total damaged mass",
                code="yft.lod.authored_damaged_group_requires_positive_mass",
            )
        _validate_glass_group(
            lod,
            index,
            group_path,
            issues,
            glass_panes=glass_panes,
            common_drawable=common_drawable,
        )

    claimed_children: set[int] = set()
    for group_index, group in enumerate(lod.groups):
        if group.child_index == 0xFF:
            continue
        for child_index in range(
            group.child_index,
            group.child_index + group.num_children,
        ):
            if child_index >= len(lod.children):
                continue
            if child_index in claimed_children:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{path}.groups[{group_index}]",
                    f"physics child {child_index} belongs to multiple groups",
                    code="yft.lod.physics_child_belongs_multiple_groups",
                )
            claimed_children.add(child_index)
            if lod.children[child_index].owner_group_pointer_index != group_index:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{path}.children[{child_index}]",
                    "owner group does not match the ordered group slice",
                    code="yft.lod.owner_group_does_not_match_ordered_group_slice",
                )
    if lod.children and claimed_children != set(range(len(lod.children))):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.groups",
            "group slices must cover every physics child exactly once",
            code="yft.lod.group_slices_must_cover_every_physics_child_exactly_once",
        )

    actual_root_groups = sum(1 for group in lod.groups if group.is_root_group)
    if lod.root_group_count != actual_root_groups:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.root_group_count",
            f"declares {lod.root_group_count} root groups but has {actual_root_groups}",
            code="yft.lod.declares_root_groups",
        )
    if lod.composite_bound is None:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.composite_bound",
            "physics LOD requires a bound",
            code="yft.lod.physics_lod_requires_bound",
        )
    else:
        issues.extend(
            validate_bound_profile(
                lod.composite_bound,
                bound_profile,
                expected_slots=len(lod.children),
            ),
            path=f"{path}.composite_bound",
        )
        _validate_fragment_geometry_limits(
            lod.composite_bound,
            f"{path}.composite_bound",
            issues,
        )
        if bound_profile is YftPhysicsBoundProfile.PROP and isinstance(
            lod.composite_bound, BoundComposite
        ):
            for index, (slot, child) in enumerate(
                zip(
                    lod.composite_bound.active_children,
                    lod.children,
                    strict=False,
                )
            ):
                if slot.bound is not None:
                    continue
                if child.undamaged_bound is not None:
                    _issue(
                        issues,
                        DiagnosticSeverity.ERROR,
                        f"{path}.composite_bound.children[{index}]",
                        "null intact slot conflicts with the intact drawable bound",
                        code="yft.lod.null_intact_slot_conflicts_intact_drawable_bound",
                    )
                if child.damaged_bound is None:
                    _issue(
                        issues,
                        DiagnosticSeverity.ERROR,
                        f"{path}.children[{index}]",
                        "physical child has no collision in either state",
                        code="yft.lod.physical_child_no_collision_either_state",
                    )
    if (
        bound_profile is not YftPhysicsBoundProfile.PRESERVE
        and lod.undamaged_damp_archetype is None
    ):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            f"{path}.undamaged_damp_archetype",
            "authored physics LOD requires an undamaged archetype",
            code="yft.lod.authored_physics_lod_requires_undamaged_archetype",
        )

    for index, child in enumerate(lod.children):
        child_path = f"{path}.children[{index}]"
        if child.owner_group_pointer_index >= len(lod.groups):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                child_path,
                "owner group index points outside the group array",
                code="yft.lod.owner_group_index_points_outside_group_array",
            )
        masses = tuple(
            mass
            for mass in (child.undamaged_mass, child.damaged_mass)
            if mass is not None
        )
        if any(
            not math.isfinite(mass) or (mass < 0.0 and mass != -1.0) for mass in masses
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                child_path,
                "child mass must be -1 or a finite nonnegative value",
                code="yft.lod.child_mass_must_1_finite_nonnegative_value",
            )
        if (
            bound_profile is not YftPhysicsBoundProfile.PRESERVE
            and child.has_damage_state
            and child.damaged_mass is not None
            and child.damaged_mass <= 0.0
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{child_path}.damaged_mass",
                "authored damaged entities require positive damaged mass",
                code="yft.lod.authored_damaged_entity_requires_positive_mass",
            )
        if child.min_breaking_impulse < 0.0:
            _issue(
                issues,
                DiagnosticSeverity.WARNING,
                child_path,
                "negative breaking impulse is unusual",
                code="yft.lod.negative_breaking_impulse_unusual",
            )
        inertias = tuple(
            inertia
            for inertia in (child.undamaged_ang_inertia, child.damaged_ang_inertia)
            if inertia is not None
        )
        if any(
            not inertia.is_unavailable and not _finite_values(inertia.as_tuple())
            for inertia in inertias
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                child_path,
                "angular inertia contains NaN or infinity",
                code="yft.lod.angular_inertia_contains_nan_infinity",
            )
        if (
            bound_profile is not YftPhysicsBoundProfile.PRESERVE
            and child.has_damage_state
            and child.damaged_ang_inertia is not None
            and not child.damaged_ang_inertia.is_unavailable
            and child.damaged_ang_inertia.mass <= 0.0
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{child_path}.damaged_ang_inertia",
                "authored damaged entities require positive damaged inertia mass",
                code="yft.lod.authored_damaged_entity_requires_positive_inertia_mass",
            )

    for index, (first, second) in enumerate(lod.self_collision_pairs):
        if first >= len(lod.groups) or second >= len(lod.groups):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{path}.self_collision_pairs[{index}]",
                "group index points outside the group array",
                code="yft.lod.group_index_points_outside_group_array",
            )

    if lod.groups and lod.children:
        grouped_undamaged_mass = sum(group.total_undamaged_mass for group in lod.groups)
        grouped_damaged_mass = sum(
            group.total_damaged_mass
            for group in lod.groups
            if group.total_damaged_mass is not None
        )
        if grouped_undamaged_mass and not math.isclose(
            grouped_undamaged_mass, lod.total_undamaged_mass, rel_tol=0.05, abs_tol=0.01
        ):
            _issue(
                issues,
                DiagnosticSeverity.WARNING,
                f"{path}.groups",
                "group undamaged mass total differs from child mass total",
                code="yft.lod.group_undamaged_mass_total_differs_child_mass_total",
            )
        if grouped_damaged_mass and not math.isclose(
            grouped_damaged_mass, lod.total_damaged_mass, rel_tol=0.05, abs_tol=0.01
        ):
            _issue(
                issues,
                DiagnosticSeverity.WARNING,
                f"{path}.groups",
                "group damaged mass total differs from child mass total",
                code="yft.lod.group_damaged_mass_total_differs_child_mass_total",
            )

    if lod.body_type.exists and lod.articulated_body_type is None:
        _issue(
            issues,
            DiagnosticSeverity.WARNING,
            f"{path}.body_type",
            "body type pointer exists but was not decoded",
            code="yft.lod.body_type_pointer_exists_was_not_decoded",
        )
    if lod.phys_damp_undamaged.exists and lod.undamaged_damp_archetype is None:
        _issue(
            issues,
            DiagnosticSeverity.WARNING,
            f"{path}.phys_damp_undamaged",
            "undamaged damping archetype pointer exists but was not decoded",
            code="yft.lod.undamaged_damping_archetype_pointer_exists_was_not_decoded",
        )
    if lod.phys_damp_damaged.exists and lod.damaged_damp_archetype is None:
        _issue(
            issues,
            DiagnosticSeverity.WARNING,
            f"{path}.phys_damp_damaged",
            "damaged damping archetype pointer exists but was not decoded",
            code="yft.lod.damaged_damping_archetype_pointer_exists_was_not_decoded",
        )

    if lod.articulated_body_type is not None:
        issues.extend(
            validate_articulated_body(
                lod.articulated_body_type,
                physics_child_count=len(lod.children),
            ),
            path=f"{path}.body_type",
        )


def validate_yft(
    source: Yft,
    *,
    context: BuildContext | None = None,
) -> ValidationReport:
    del context
    issues = ValidationReport()
    if source.main_drawable is None:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "drawable",
            "common drawable is required",
            code="yft.common_drawable_required",
        )
    elif not _has_models(source.main_drawable):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "drawable",
            "common drawable has no models",
            code="yft.common_drawable_no_models",
        )

    labels = [entry.label for entry in source.drawables]
    duplicates = sorted(label for label, count in Counter(labels).items() if count > 1)
    for label in duplicates:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "drawables",
            f"duplicate extra drawable label '{label}'",
            code="yft.duplicate_extra_drawable_label",
        )

    damaged_index = source.state.damaged_drawable_index
    if damaged_index < -1 or damaged_index >= len(source.drawables):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "state.damaged_drawable_index",
            "must be -1 or point into the extra drawable array",
            code="yft.must_1_point_extra_drawable_array",
        )

    unsupported_root_sections = {
        "collision_event_player": source.pointers.collision_event_player,
    }
    for label, pointer in unsupported_root_sections.items():
        if pointer:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"pointers.{label}",
                "section is readable but cannot yet be rebuilt safely",
                code="yft.section_readable_cannot_yet_rebuilt_safely",
            )
    if not 0 <= int(source.user_data) <= 0xFFFFFFFFFFFFFFFF:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "user_data",
            "application user data must fit the native 64-bit field",
            code="yft.application_user_data_must_fit_native_64_bit_field",
        )
    if source.pointers.collision_event_set and source.collision_event_set is None:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "collision_event_set",
            "event-set pointer could not be decoded",
            code="yft.event_set_pointer_could_not_decoded",
        )
    if (
        source.collision_event_set is not None
        and not source.collision_event_set.can_rebuild
    ):
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "collision_event_set",
            "event instances and editor pointers cannot yet be rebuilt safely",
            code="yft.event_instances_editor_pointers_cannot_yet_rebuilt_safely",
        )
    if source.root_child is not None and not source.root_child.events.can_rebuild:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "root_child.events",
            "event players or populated event sets cannot yet be rebuilt safely",
            code="yft.event_players_populated_event_sets_cannot_yet_rebuilt_safely",
        )
    for field in source.raw_fields:
        if field.label in {
            "character_cloth",
        }:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"raw_fields.{field.label}",
                "section is readable but cannot yet be rebuilt safely",
                code="yft.section_readable_cannot_yet_rebuilt_safely",
            )
    if source.character_cloth_count:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "character_cloths",
            "character-cloth arrays are not part of the legacy YFT corpus",
            code="yft.character_cloth_arrays_not_part_legacy_yft_corpus",
        )
    if source.shared_matrix_set is not None:
        matrix_set = source.shared_matrix_set
        if matrix_set.matrix_count > 0xFF:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                "shared_matrix_set",
                "legacy matrix sets support at most 255 matrices",
                code="yft.legacy_matrix_sets_support_at_most_255_matrices",
            )
        for index, matrix in enumerate(matrix_set.matrices):
            if len(matrix) != 12 or not _finite_values(matrix):
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"shared_matrix_set.matrices[{index}]",
                    "must contain 12 finite Matrix43 values",
                    code="yft.must_contain_12_finite_matrix43_values",
                )
    if len(source.lights) > 0xFFFF:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "lights",
            "native light arrays support at most 65535 entries",
            code="yft.native_light_arrays_support_at_most_65535_entries",
        )
    for index, light in enumerate(source.lights):
        vectors = (
            light.position,
            light.culling_plane_normal,
            light.direction,
            light.tangent,
            light.extent,
        )
        if any(
            not isinstance(vector, Vector3) or not vector.is_finite
            for vector in vectors
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"lights[{index}]",
                "light vectors must contain three finite values",
                code="yft.light_vectors_must_contain_three_finite_values",
            )
    if len(source.glass_panes) > 0xFF:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "glass_panes",
            "legacy fragments support at most 255 glass panes",
            code="yft.legacy_fragments_support_at_most_255_glass_panes",
        )
    for index, pane in enumerate(source.glass_panes):
        pane_path = f"glass_panes[{index}]"
        if not (
            isinstance(pane.position_base, Vector3)
            and isinstance(pane.position_width, Vector3)
            and isinstance(pane.position_height, Vector3)
            and isinstance(pane.uv_min, Vector2)
            and isinstance(pane.uv_max, Vector2)
            and isinstance(pane.tangent, Vector3)
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                pane_path,
                "vector dimensions do not match the native pane layout",
                code="yft.vector_dimensions_do_not_match_native_pane_layout",
            )
        if not 0 <= int(pane.glass_type) <= 0xFF:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{pane_path}.glass_type",
                "must fit in one byte",
                code="yft.must_fit_one_byte",
            )
        if not 0 <= int(pane.shader_index) <= 0xFF:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{pane_path}.shader_index",
                "must fit in one byte",
                code="yft.must_fit_one_byte",
            )
        material_count = (
            len(source.main_drawable.materials)
            if source.main_drawable is not None
            else 0
        )
        if material_count and int(pane.shader_index) >= material_count:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{pane_path}.shader_index",
                f"references shader {pane.shader_index} outside the {material_count}-entry shader group",
                code="yft.references_shader_outside_entry_shader_group",
            )
        declaration = pane.vertex_declaration
        if not 0 < declaration.stride <= 0xFFFF:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{pane_path}.vertex_declaration.stride",
                "must be between 1 and 65535",
                code="yft.must_between_1_65535",
            )
        if declaration.count > 0xFF:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{pane_path}.vertex_declaration.component_count",
                "must fit in one byte",
                code="yft.must_fit_one_byte",
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
                DiagnosticSeverity.ERROR,
                pane_path,
                "contains NaN or infinity",
                code="yft.contains_nan_infinity",
            )
    vehicle_glass = source.vehicle_glass_windows
    if vehicle_glass is not None:
        component_ids = [window.component_id for window in vehicle_glass.windows]
        if len(component_ids) != len(set(component_ids)):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                "vehicle_glass_windows",
                "component IDs must be unique",
                code="yft.component_ids_must_unique",
            )
        for index, window in enumerate(vehicle_glass.windows):
            window_path = f"vehicle_glass_windows.windows[{index}]"
            if len(window.basis) != 16:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{window_path}.basis",
                    "must contain 16 matrix values",
                    code="yft.must_contain_16_matrix_values",
                )
            if not 0 <= window.component_id <= 0xFFFF:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{window_path}.component_id",
                    "must fit in an unsigned 16-bit integer",
                    code="yft.must_fit_unsigned_16_bit_integer",
                )
            if not 0 <= window.geometry_index <= 0xFFFF:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{window_path}.geometry_index",
                    "must fit in an unsigned 16-bit integer",
                    code="yft.must_fit_unsigned_16_bit_integer",
                )
            if window.row_count != len(window.rows) and window.rows:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{window_path}.data_rows",
                    "must match the number of RLE rows",
                    code="yft.must_match_number_rle_rows",
                )
            if window.column_count > 0xFFFF or window.row_count > 0xFFFF:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    window_path,
                    "distance-field dimensions must fit in unsigned 16-bit integers",
                    code="yft.distance_field_dimensions_must_fit_unsigned_16_bit_integers",
                )
            inferred_width = max((row.width for row in window.rows), default=0)
            if window.data_columns and window.data_columns < inferred_width:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{window_path}.data_columns",
                    "cannot be smaller than the encoded RLE rows",
                    code="yft.cannot_smaller_than_encoded_rle_rows",
                )
            if not _finite_values(
                (*window.basis, window.data_min, window.data_max, window.texture_scale)
            ):
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    window_path,
                    "contains NaN or infinity",
                    code="yft.contains_nan_infinity",
                )
            row_data_size = 0
            for row_index, row in enumerate(window.rows):
                if row.first is None and row.second is not None:
                    _issue(
                        issues,
                        DiagnosticSeverity.ERROR,
                        f"{window_path}.rows[{row_index}]",
                        "a second span requires a first span",
                        code="yft.second_span_requires_first_span",
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
                            DiagnosticSeverity.ERROR,
                            (f"{window_path}.rows[{row_index}].spans[{span_index}]"),
                            "span must contain values and remain inside 0..255",
                            code="yft.span_must_contain_values_remain_inside_0_255",
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
                        DiagnosticSeverity.ERROR,
                        f"{window_path}.rows[{row_index}]",
                        "RLE row offset exceeds the unsigned 16-bit limit",
                        code="yft.rle_row_offset_exceeds_unsigned_16_bit_limit",
                    )
    if len(source.environment_cloths) > 1:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "environment_cloths",
            "legacy fragments support at most one environment cloth",
            code="yft.legacy_fragments_support_at_most_one_environment_cloth",
        )
    for index, cloth in enumerate(source.environment_cloths):
        cloth_path = f"environment_cloths[{index}]"
        if cloth.controller.bridge is None:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{cloth_path}.controller.bridge",
                "simulation-to-graphics bridge is required",
                code="yft.simulation_graphics_bridge_required",
            )
        if cloth.controller.morph is None:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{cloth_path}.controller.morph",
                "morph controller is required",
                code="yft.morph_controller_required",
            )
        if cloth.controller.verlet_lods[0] is None:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{cloth_path}.controller.verlet_lods",
                "highest-detail Verlet cloth is required",
                code="yft.highest_detail_verlet_cloth_required",
            )
        bridge = cloth.controller.bridge
        if not cloth.controller.name:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"{cloth_path}.controller.name",
                "controller name is required",
                code="yft.controller_name_required",
            )
        for lod_index, verlet in enumerate(cloth.controller.verlet_lods):
            if verlet is None:
                continue
            if verlet.previous_vertices and (
                len(verlet.previous_vertices) != verlet.vertex_count
            ):
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{cloth_path}.controller.verlet_lods[{lod_index}]",
                    "previous-vertex count must match vertex count",
                    code="yft.previous_vertex_count_must_match_vertex_count",
                )
            if bridge is None:
                continue
            mesh_vertex_count = bridge.mesh_vertex_counts[lod_index]
            display_map = bridge.display_maps[lod_index]
            if display_map and len(display_map) != mesh_vertex_count:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{cloth_path}.controller.bridge.display_maps[{lod_index}]",
                    "display-map count must match the mesh vertex count",
                    code="yft.display_map_count_must_match_mesh_vertex_count",
                )
            for field_name, values in (
                ("pin_radii", bridge.pin_radii[lod_index]),
                ("vertex_weights", bridge.vertex_weights[lod_index]),
                ("inflation_scales", bridge.inflation_scales[lod_index]),
            ):
                if values and len(values) != mesh_vertex_count:
                    _issue(
                        issues,
                        DiagnosticSeverity.ERROR,
                        f"{cloth_path}.controller.bridge.{field_name}[{lod_index}]",
                        "array count must match the mesh vertex count",
                        code="yft.array_count_must_match_mesh_vertex_count",
                    )
            if display_map and max(display_map) >= verlet.vertex_count:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"{cloth_path}.controller.bridge.display_maps[{lod_index}]",
                    "display map references a vertex outside the Verlet cloth",
                    code="yft.display_map_references_vertex_outside_verlet_cloth",
                )

    drawable_entries = [*source.iter_drawables(), *source.iter_physics_drawables()]
    seen_drawables: set[int] = set()
    for entry in drawable_entries:
        drawable = entry.drawable
        if id(drawable) in seen_drawables:
            continue
        seen_drawables.add(id(drawable))
        validate_drawable = getattr(drawable, "validate", None)
        drawable_issues = validate_drawable() if validate_drawable is not None else ()
        for drawable_issue in drawable_issues:
            if drawable_issue.code != "invalid_material_index":
                continue
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"drawables.{entry.label}.{drawable_issue.path or drawable_issue.code}",
                drawable_issue.message,
                code="yft.drawable.material_index_invalid",
            )
        extra_bounds = getattr(drawable, "extra_bounds", ())
        matrices = getattr(drawable, "extra_bound_matrices", ())
        if len(extra_bounds) > MAX_EXTRA_BOUNDS:
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"drawables.{entry.label}.extra_bounds",
                f"cannot contain more than {MAX_EXTRA_BOUNDS} bounds",
                code="yft.cannot_contain_more_than_bounds",
            )
        if len(extra_bounds) != len(matrices):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"drawables.{entry.label}.extra_bounds",
                "bound and matrix counts must match",
                code="yft.bound_matrix_counts_must_match",
            )
        for index, bound in enumerate(extra_bounds):
            if bound is None:
                continue
            issues.extend(
                bound.validate(),
                path=f"drawables.{entry.label}.extra_bounds[{index}]",
            )

    if source.physics_lods.has_physics and not source.physics_lod_details:
        _issue(
            issues,
            DiagnosticSeverity.ERROR,
            "physics_lods",
            "physics LOD pointers exist but no LOD could be decoded",
            code="yft.physics_lod_pointers_exist_no_lod_could_decoded",
        )
    if (
        len(source.physics_lod_details) != source.physics_lods.active_count
        and source.physics_lods.has_physics
    ):
        _issue(
            issues,
            DiagnosticSeverity.WARNING,
            "physics_lods",
            "decoded physics LOD count differs from active pointer count",
            code="yft.decoded_physics_lod_count_differs_active_pointer_count",
        )

    physics_drawable_owners: dict[int, str] = {}
    for index, lod in enumerate(source.physics_lod_details):
        lod_path = f"physics_lod_details[{index}]"
        _validate_lod(
            lod,
            lod_path,
            issues,
            bound_profile=source.physics_bound_profile,
            glass_panes=source.glass_panes,
            common_drawable=source.main_drawable,
        )
        if lod.composite_bound is not None:
            from .bound_ownership import (
                calculate_physics_lod_bound_ref_counts,
                iter_bound_graph,
            )

            expected_ref_counts = calculate_physics_lod_bound_ref_counts(
                lod,
                fragment_drawable_fallback=source.main_drawable is not None,
            )
            for bound_index, bound in enumerate(iter_bound_graph(lod.composite_bound)):
                expected = expected_ref_counts.get(id(bound), 0)
                if bound.ref_count != expected:
                    _issue(
                        issues,
                        DiagnosticSeverity.ERROR,
                        f"{lod_path}.composite_bound[{bound_index}].ref_count",
                        (
                            f"declares {bound.ref_count} owners but the serialized "
                            f"graph contains {expected}"
                        ),
                        code="yft.declares_owners_serialized_graph_contains",
                    )
        is_root_lod = index == 0 and lod.label.lower() == "high"
        for child_index, child in enumerate(lod.children):
            for state, entity in (
                ("undamaged", child.undamaged_entity),
                ("damaged", child.damaged_entity),
            ):
                if entity is None or entity.drawable is None:
                    if not is_root_lod and state == "undamaged":
                        _issue(
                            issues,
                            DiagnosticSeverity.ERROR,
                            (
                                f"physics_lod_details[{index}].children"
                                f"[{child_index}].{state}_entity"
                            ),
                            "non-high physics LODs require their own drawable",
                            code="yft.non_high_physics_lods_require_their_own_drawable",
                        )
                    continue
                drawable_id = id(entity.drawable)
                owner = (
                    f"physics_lod_details[{index}].children[{child_index}]"
                    f".{state}_entity"
                )
                previous_owner = physics_drawable_owners.get(drawable_id)
                if previous_owner is not None and previous_owner != owner:
                    _issue(
                        issues,
                        DiagnosticSeverity.ERROR,
                        owner,
                        (
                            "physics drawable is shared with "
                            f"{previous_owner}; each state and LOD must own "
                            "its drawable-bound link"
                        ),
                        code="yft.physics_drawable_shared_each_state_lod_must_own_its",
                    )
                else:
                    physics_drawable_owners[drawable_id] = owner
        if (
            lod.damaged_damp_archetype is not None
            and damaged_index < 0
            and not any(child.has_damage_state for child in lod.children)
        ):
            _issue(
                issues,
                DiagnosticSeverity.ERROR,
                f"physics_lod_details[{index}].damaged_damp_archetype",
                (
                    "damaged archetype requires a damaged fragment drawable "
                    "or at least one damaged physics-child entity"
                ),
                code="yft.damaged_archetype_requires_damaged_fragment_drawable_at_least_one",
            )
        for child_index, child in enumerate(lod.children):
            if not child.events.can_rebuild:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"physics_lod_details[{index}].children[{child_index}].events",
                    "event players or populated event sets cannot yet be rebuilt safely",
                    code="yft.event_players_populated_event_sets_cannot_yet_rebuilt_safely",
                )
        for group_index, group in enumerate(lod.groups):
            if not group.events.can_rebuild:
                _issue(
                    issues,
                    DiagnosticSeverity.ERROR,
                    f"physics_lod_details[{index}].groups[{group_index}].events",
                    "event players or populated event sets cannot yet be rebuilt safely",
                    code="yft.event_players_populated_event_sets_cannot_yet_rebuilt_safely",
                )
    from .vehicle_glass_authoring import validate_yft_vehicle_glass

    issues.extend(validate_yft_vehicle_glass(source))
    if source.path:
        issues.issues = [issue.for_asset(source.path) for issue in issues]
    return issues


__all__ = [
    "validate_yft",
]
