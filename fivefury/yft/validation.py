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
    if (
        lod.link_attachments.matrices
        and len(lod.link_attachments.matrices) != len(lod.children)
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
