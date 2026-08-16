from __future__ import annotations

import struct
import zlib

from ..authoring import ValidationReport
from ..bounds import Bound, BoundComposite
from ..ydr import YdrLod
from ..yft import Yft, read_yft
from .enums import VehicleType

_PAIRED_VEHICLE_TYPES = frozenset(
    {
        VehicleType.CAR,
        VehicleType.HELICOPTER,
        VehicleType.BIKE,
        VehicleType.BOAT,
        VehicleType.TRAIN,
    }
)
_BASE_LODS = frozenset(YdrLod)
_HIGH_LODS = frozenset({YdrLod.HIGH})
_READ_ERRORS = (
    IndexError,
    KeyError,
    TypeError,
    ValueError,
    struct.error,
    zlib.error,
)
_BoundTopology = tuple[object, ...]


def _read_fragment(source: Yft | bytes, *, path: str) -> Yft:
    return source if isinstance(source, Yft) else read_yft(source, path=path)


def _active_lods(fragment: Yft) -> frozenset[YdrLod]:
    drawable = fragment.main_drawable
    if drawable is None:
        return frozenset()
    return frozenset(lod for lod, models in drawable.lods.items() if models)


def _bound_topology(bound: Bound | None) -> _BoundTopology | None:
    if bound is None:
        return None
    if not isinstance(bound, BoundComposite):
        return (int(bound.bound_type),)
    return (
        int(bound.bound_type),
        bound.child_count,
        bound.child_capacity,
        tuple(
            (
                child.bound is not None,
                child.flags1,
                child.flags2,
                _bound_topology(child.bound),
            )
            for child in bound.children
        ),
    )


def _validate_skeleton_pair(
    report: ValidationReport,
    fragment: Yft,
    high_fragment: Yft,
) -> None:
    base = getattr(fragment.main_drawable, "skeleton", None)
    high = getattr(high_fragment.main_drawable, "skeleton", None)
    if (base is None) != (high is None):
        report.issue(
            "vehicle.yft_pair.skeleton.missing",
            "Base and high-detail fragments must either both contain a skeleton or both omit it",
            path="high_fragment.main_drawable.skeleton",
        )
        return
    if base is None or high is None:
        return
    if len(base.bones) != len(high.bones):
        report.issue(
            "vehicle.yft_pair.skeleton.count_mismatch",
            "Base and high-detail skeleton bone counts differ",
            path="high_fragment.main_drawable.skeleton.bones",
        )
        return
    fields = (
        "name",
        "tag",
        "parent_index",
        "rotation",
        "translation",
        "scale",
        "inverse_bind_transform",
    )
    for index, (base_bone, high_bone) in enumerate(zip(base.bones, high.bones)):
        for field in fields:
            if getattr(base_bone, field) != getattr(high_bone, field):
                report.issue(
                    f"vehicle.yft_pair.skeleton.{field}_mismatch",
                    f"Bone {index} has incompatible {field.replace('_', ' ')} data",
                    path=f"high_fragment.main_drawable.skeleton.bones[{index}].{field}",
                )


def _validate_physics_pair(
    report: ValidationReport,
    fragment: Yft,
    high_fragment: Yft,
) -> None:
    base = fragment.best_physics_lod
    high = high_fragment.best_physics_lod
    if (base is None) != (high is None):
        report.issue(
            "vehicle.yft_pair.physics.missing",
            "Base and high-detail fragments must contain compatible physics LODs",
            path="high_fragment.physics_lod_details",
        )
        return
    if base is None or high is None:
        return
    if len(base.groups) != len(high.groups):
        report.issue(
            "vehicle.yft_pair.physics.group_count_mismatch",
            "Base and high-detail physics group counts differ",
            path="high_fragment.physics_lod_details",
        )
    else:
        group_fields = (
            "name",
            "parent_group_pointer_index",
            "child_groups_pointers_index",
            "child_index",
            "num_children",
            "num_child_groups",
        )
        for index, (base_group, high_group) in enumerate(zip(base.groups, high.groups)):
            if any(
                getattr(base_group, field) != getattr(high_group, field)
                for field in group_fields
            ):
                report.issue(
                    "vehicle.yft_pair.physics.group_topology_mismatch",
                    f"Physics group {index} has incompatible ownership topology",
                    path=f"high_fragment.physics_lod_details.groups[{index}]",
                )
    if len(base.children) != len(high.children):
        report.issue(
            "vehicle.yft_pair.physics.child_count_mismatch",
            "Base and high-detail physics child counts differ",
            path="high_fragment.physics_lod_details",
        )
    else:
        child_fields = (
            "owner_group_pointer_index",
            "owner_group_name",
            "bone_id",
            "bone_controlled",
            "flags",
        )
        for index, (base_child, high_child) in enumerate(
            zip(base.children, high.children)
        ):
            if any(
                getattr(base_child, field) != getattr(high_child, field)
                for field in child_fields
            ):
                report.issue(
                    "vehicle.yft_pair.physics.child_topology_mismatch",
                    f"Physics child {index} has incompatible ownership or bone data",
                    path=f"high_fragment.physics_lod_details.children[{index}]",
                )
    if base.link_attachments.matrices != high.link_attachments.matrices:
        report.issue(
            "vehicle.yft_pair.physics.link_transforms_mismatch",
            "Base and high-detail physics link transforms differ",
            path="high_fragment.physics_lod_details.link_attachments",
        )
    if _bound_topology(base.composite_bound) != _bound_topology(high.composite_bound):
        report.issue(
            "vehicle.yft_pair.physics.bound_topology_mismatch",
            "Base and high-detail composite-bound slot topologies differ",
            path="high_fragment.physics_lod_details.composite_bound",
        )


def validate_vehicle_yft_pair(
    name: str,
    fragment: Yft | bytes,
    high_fragment: Yft | bytes | None,
    *,
    vehicle_type: VehicleType | int = VehicleType.CAR,
) -> ValidationReport:
    report = ValidationReport()
    stem = str(name).strip()
    if not stem:
        report.issue(
            "vehicle.yft_pair.name.required",
            "Vehicle YFT pair name cannot be empty",
            path="name",
        )
    elif stem.casefold().endswith("_hi"):
        report.issue(
            "vehicle.yft_pair.name.high_detail",
            "The pair name must identify the base vehicle, not its _hi companion",
            path="name",
        )
    resolved: dict[str, Yft] = {}
    for role, source, filename in (
        ("fragment", fragment, f"{stem}.yft"),
        ("high_fragment", high_fragment, f"{stem}_hi.yft"),
    ):
        if source is None:
            continue
        try:
            value = _read_fragment(source, path=filename)
        except _READ_ERRORS as exc:
            report.issue(
                f"vehicle.yft_pair.{role}.invalid",
                str(exc),
                path=role,
            )
            continue
        resolved[role] = value
        if value.version != 171:
            report.issue(
                f"vehicle.yft_pair.{role}.target_invalid",
                f"Enhanced vehicle YFT version must be 171, got {value.version}",
                path=f"{role}.version",
            )
        report.extend(value.validate(), path=role)

    resolved_vehicle_type = VehicleType(int(vehicle_type))
    required = resolved_vehicle_type in _PAIRED_VEHICLE_TYPES
    if high_fragment is None:
        if required:
            report.issue(
                "vehicle.yft_pair.high_fragment.required",
                f"Vehicle type {resolved_vehicle_type.name} requires a high-detail YFT companion",
                path="high_fragment",
            )
        return report

    base = resolved.get("fragment")
    high = resolved.get("high_fragment")
    if base is None or high is None:
        return report

    base_lods = _active_lods(base)
    if required and base_lods != _BASE_LODS:
        report.issue(
            "vehicle.yft_pair.fragment.lod_chain_invalid",
            "Base vehicle YFT must contain High, Medium, Low, and Very Low drawable LODs",
            path="fragment.main_drawable.lods",
        )
    high_lods = _active_lods(high)
    if high_lods != _HIGH_LODS:
        report.issue(
            "vehicle.yft_pair.high_fragment.lod_chain_invalid",
            "High-detail vehicle YFT must contain only a High drawable LOD",
            path="high_fragment.main_drawable.lods",
        )
    if high.vehicle_glass_windows is not None:
        report.issue(
            "vehicle.yft_pair.high_fragment.vehicle_glass_invalid",
            "Vehicle-glass window ownership belongs to the base fragment",
            path="high_fragment.vehicle_glass_windows",
        )

    expected_tunes = {
        "fragment": f"pack:/{stem}",
        "high_fragment": f"pack:/{stem}_hi",
    }
    for role, value in (("fragment", base), ("high_fragment", high)):
        expected = expected_tunes[role]
        if value.tune_name.casefold() != expected.casefold():
            report.issue(
                f"vehicle.yft_pair.{role}.tune_name_invalid",
                f"Expected tune name {expected!r}, got {value.tune_name!r}",
                path=f"{role}.tune_name",
            )

    _validate_skeleton_pair(report, base, high)
    _validate_physics_pair(report, base, high)
    return report


__all__ = [
    "validate_vehicle_yft_pair",
]
