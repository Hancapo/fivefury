from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Sequence

import numpy as np

from ..authoring import ValidationReport
from ..matrix import Matrix4, matrix4
from ..vector import Quaternion, Vector3
from .physics import (
    YftArticulatedBodyType,
    YftPhysicsInertia,
    YftPhysicsJoint1Dof,
    YftPhysicsJoint3Dof,
)
from .resource_headers import PH_ARTICULATED_BODY_TYPE_EUPHORIA_VFT

YFT_MAX_ARTICULATED_LINKS = 23
YFT_MAX_ARTICULATED_JOINTS = 22


class YftJointFrameSpace(enum.Enum):
    WORLD = "world"
    CHILD_LINK = "child_link"


class YftAngularRangePolicy(enum.Enum):
    EXACT = "exact"
    RUNTIME = "runtime"


class YftArticulationIssueCode(enum.Enum):
    INVALID_CARDINALITY = "yft.articulation.invalid_cardinality"
    INVALID_INERTIA = "yft.articulation.invalid_inertia"
    INVALID_JOINT = "yft.articulation.invalid_joint"
    INVALID_RANGE = "yft.articulation.invalid_range"
    INVALID_TRANSFORM = "yft.articulation.invalid_transform"
    UNREPRESENTABLE_RANGE = "yft.articulation.unrepresentable_range"
    UNREPRESENTABLE_TOPOLOGY = "yft.articulation.unrepresentable_topology"


@dataclasses.dataclass(frozen=True, slots=True)
class YftAngularRange:
    minimum: float
    maximum: float

    @property
    def center(self) -> float:
        return 0.5 * (self.minimum + self.maximum)

    @property
    def half_extent(self) -> float:
        return 0.5 * (self.maximum - self.minimum)


@dataclasses.dataclass(frozen=True, slots=True)
class YftArticulationPolicy:
    angular_range: YftAngularRangePolicy = YftAngularRangePolicy.EXACT
    allowed_angle_penetration: float = 0.03
    transform_tolerance: float = 1e-5
    axis_tolerance: float = 1e-5


DEFAULT_YFT_ARTICULATION_POLICY = YftArticulationPolicy()


@dataclasses.dataclass(frozen=True, slots=True)
class YftJoint1DofIntent:
    parent_link_index: int
    child_link_index: int
    pivot: Vector3
    axis: Vector3
    angle: YftAngularRange
    frame_space: YftJointFrameSpace = YftJointFrameSpace.WORLD
    stiffness: float | None = None
    enforce_exceeded_limits: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class YftJoint3DofIntent:
    parent_link_index: int
    child_link_index: int
    pivot: Vector3
    twist_axis: Vector3
    first_lean_axis: Vector3
    first_lean: YftAngularRange
    second_lean: YftAngularRange
    twist: YftAngularRange
    frame_space: YftJointFrameSpace = YftJointFrameSpace.WORLD
    stiffness: float | None = None
    enforce_exceeded_limits: bool = False
    soft_limit_ratio: float = 1.0
    use_child_for_twist_axis: bool = False


YftArticulatedJointIntent = YftJoint1DofIntent | YftJoint3DofIntent


def _issue(
    report: ValidationReport,
    code: YftArticulationIssueCode,
    message: str,
    path: str,
) -> None:
    report.issue(code.value, message, path=path)


def _matrix_tuple(value: np.ndarray) -> Matrix4:
    return tuple(tuple(float(component) for component in row) for row in value)  # type: ignore[return-value]


def _validated_link_transforms(
    values: Sequence[Matrix4],
    policy: YftArticulationPolicy,
    report: ValidationReport,
) -> tuple[np.ndarray, ...]:
    result: list[np.ndarray] = []
    for index, value in enumerate(values):
        path = f"link_world_transforms[{index}]"
        try:
            transform = matrix4(value)
        except (TypeError, ValueError) as error:
            _issue(report, YftArticulationIssueCode.INVALID_TRANSFORM, str(error), path)
            continue
        rotation = transform[:3, :3]
        if not np.allclose(
            rotation.T @ rotation,
            np.identity(3),
            atol=policy.transform_tolerance,
            rtol=0.0,
        ) or not math.isclose(
            float(np.linalg.det(rotation)),
            1.0,
            abs_tol=policy.transform_tolerance,
        ):
            _issue(
                report,
                YftArticulationIssueCode.INVALID_TRANSFORM,
                "link transform must contain a right-handed orthonormal rotation",
                path,
            )
        if not np.allclose(
            transform[3],
            (0.0, 0.0, 0.0, 1.0),
            atol=policy.transform_tolerance,
            rtol=0.0,
        ):
            _issue(
                report,
                YftArticulationIssueCode.INVALID_TRANSFORM,
                "link transform must have a homogeneous final row",
                path,
            )
        result.append(transform)
    return tuple(result)


def _validated_range(
    value: YftAngularRange,
    *,
    path: str,
    report: ValidationReport,
) -> bool:
    if not math.isfinite(value.minimum) or not math.isfinite(value.maximum):
        _issue(
            report,
            YftArticulationIssueCode.INVALID_RANGE,
            "angular range endpoints must be finite radians",
            path,
        )
        return False
    if value.minimum > value.maximum:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_RANGE,
            "angular range minimum must not exceed its maximum",
            path,
        )
        return False
    return True


def _normalized_axis(
    value: Vector3,
    *,
    path: str,
    report: ValidationReport,
) -> Vector3 | None:
    if not isinstance(value, Vector3) or not value.is_finite:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_JOINT,
            "joint axes must be finite Vector3 values",
            path,
        )
        return None
    try:
        return value.normalized()
    except ValueError:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_JOINT,
            "joint axes must have non-zero length",
            path,
        )
        return None


def _world_frame(
    intent: YftArticulatedJointIntent,
    child_transform: np.ndarray,
) -> tuple[Vector3, Vector3, Vector3 | None]:
    pivot = intent.pivot
    axis = intent.axis if isinstance(intent, YftJoint1DofIntent) else intent.twist_axis
    lean = intent.first_lean_axis if isinstance(intent, YftJoint3DofIntent) else None
    if intent.frame_space is YftJointFrameSpace.WORLD:
        return pivot, axis, lean
    rotation = child_transform[:3, :3]
    translation = child_transform[:3, 3]
    world_pivot = Vector3.from_iterable(rotation @ np.asarray(pivot) + translation)
    world_axis = Vector3.from_iterable(rotation @ np.asarray(axis))
    world_lean = (
        Vector3.from_iterable(rotation @ np.asarray(lean)) if lean is not None else None
    )
    return world_pivot, world_axis, world_lean


def _orthogonal_axes(axis: Vector3) -> tuple[Vector3, Vector3]:
    if abs(axis.x) > 0.5 or abs(axis.y) > 0.5:
        first = Vector3(axis.y, -axis.x, 0.0).normalized()
    else:
        first = Vector3(0.0, axis.z, -axis.y).normalized()
    return first, axis.cross(first).normalized()


def _set_axis_orientations(
    parent_transform: np.ndarray,
    child_transform: np.ndarray,
    pivot: Vector3,
    first_axis: Vector3,
    second_axis: Vector3,
    twist_axis: Vector3,
) -> tuple[np.ndarray, np.ndarray]:
    axis_coordinates = np.asarray(
        (first_axis.components, second_axis.components, twist_axis.components),
        dtype=np.float64,
    )
    position = np.asarray(pivot, dtype=np.float64)
    orientations = []
    for transform in (parent_transform, child_transform):
        orientation = np.identity(4, dtype=np.float64)
        orientation[:3, :3] = axis_coordinates @ transform[:3, :3].T
        orientation[:3, 3] = transform[:3, :3] @ (position - transform[:3, 3])
        orientations.append(orientation)
    return orientations[0], orientations[1]


def _quaternion_matrix(value: Quaternion) -> np.ndarray:
    quaternion = value.normalized_strict()
    x, y, z, w = quaternion.components
    return np.asarray(
        (
            (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
            (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
            (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
        ),
        dtype=np.float64,
    )


def _lean_center_rotation(first: float, second: float) -> Quaternion:
    tangent_y = math.tan(first * 0.25)
    tangent_z = math.tan(second * 0.25)
    factor = 2.0 / (1.0 + tangent_y * tangent_y + tangent_z * tangent_z)
    source_x = factor - 1.0
    source_y = 0.0
    source_z = factor * tangent_z
    source_w = -factor * tangent_y
    return Quaternion(source_z, source_w, source_y, source_x).normalized_strict()


def _build_1dof_joint(
    intent: YftJoint1DofIntent,
    transforms: tuple[np.ndarray, ...],
    policy: YftArticulationPolicy,
    report: ValidationReport,
    index: int,
) -> YftPhysicsJoint1Dof | None:
    path = f"joints[{index}]"
    if not _validated_range(intent.angle, path=f"{path}.angle", report=report):
        return None
    pivot, axis_value, _ = _world_frame(intent, transforms[intent.child_link_index])
    axis = _normalized_axis(axis_value, path=f"{path}.axis", report=report)
    if axis is None or not pivot.is_finite:
        if not pivot.is_finite:
            _issue(
                report,
                YftArticulationIssueCode.INVALID_JOINT,
                "joint pivot must be finite",
                f"{path}.pivot",
            )
        return None
    minimum = intent.angle.minimum
    maximum = intent.angle.maximum
    penetration = policy.allowed_angle_penetration
    if maximum - minimum < 2.0 * penetration:
        _issue(
            report,
            YftArticulationIssueCode.UNREPRESENTABLE_RANGE,
            "1DOF range is narrower than the runtime penetration allowance",
            f"{path}.angle",
        )
        return None
    if maximum - minimum > 1.99 * math.pi:
        if policy.angular_range is YftAngularRangePolicy.EXACT:
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_RANGE,
                "1DOF ranges wider than 1.99 pi are converted to free rotation by the runtime",
                f"{path}.angle",
            )
            return None
        minimum, maximum = -2.0 * math.pi, 2.0 * math.pi
    first, second = _orthogonal_axes(axis)
    parent, child = _set_axis_orientations(
        transforms[intent.parent_link_index],
        transforms[intent.child_link_index],
        pivot,
        first,
        second,
        axis,
    )
    return YftPhysicsJoint1Dof(
        parent_link_index=intent.parent_link_index,
        child_link_index=intent.child_link_index,
        orientation_parent=_matrix_tuple(parent),
        orientation_child=_matrix_tuple(child),
        default_stiffness=0.825 if intent.stiffness is None else intent.stiffness,
        enforce_exceeded_limits=intent.enforce_exceeded_limits,
        hard_angle_min=minimum + penetration,
        hard_angle_max=maximum - penetration,
    )


def _build_3dof_joint(
    intent: YftJoint3DofIntent,
    transforms: tuple[np.ndarray, ...],
    policy: YftArticulationPolicy,
    report: ValidationReport,
    index: int,
) -> YftPhysicsJoint3Dof | None:
    path = f"joints[{index}]"
    ranges = (intent.first_lean, intent.second_lean, intent.twist)
    if not all(
        _validated_range(value, path=f"{path}.{name}", report=report)
        for name, value in zip(
            ("first_lean", "second_lean", "twist"), ranges, strict=True
        )
    ):
        return None
    pivot, axis_value, lean_value = _world_frame(
        intent, transforms[intent.child_link_index]
    )
    axis = _normalized_axis(axis_value, path=f"{path}.twist_axis", report=report)
    lean = _normalized_axis(
        lean_value or Vector3(), path=f"{path}.first_lean_axis", report=report
    )
    if axis is None or lean is None or not pivot.is_finite:
        if not pivot.is_finite:
            _issue(
                report,
                YftArticulationIssueCode.INVALID_JOINT,
                "joint pivot must be finite",
                f"{path}.pivot",
            )
        return None
    if abs(axis.dot(lean)) > policy.axis_tolerance:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_JOINT,
            "first lean axis must be orthogonal to the twist axis",
            f"{path}.first_lean_axis",
        )
        return None
    half_extents = tuple(value.half_extent for value in ranges)
    penetration = policy.allowed_angle_penetration
    if any(extent <= penetration or extent >= math.pi for extent in half_extents):
        _issue(
            report,
            YftArticulationIssueCode.UNREPRESENTABLE_RANGE,
            "3DOF half-ranges must be greater than penetration and less than pi",
            path,
        )
        return None
    second = axis.cross(lean).normalized()
    parent, child = _set_axis_orientations(
        transforms[intent.parent_link_index],
        transforms[intent.child_link_index],
        pivot,
        lean,
        second,
        axis,
    )
    parent[:3, :3] = parent[:3, :3] @ _quaternion_matrix(
        _lean_center_rotation(intent.first_lean.center, intent.second_lean.center)
    )
    child[:3, :3] = child[:3, :3] @ _quaternion_matrix(
        Quaternion(
            0.0,
            0.0,
            math.sin(intent.twist.center * 0.5),
            math.cos(intent.twist.center * 0.5),
        )
    )
    return YftPhysicsJoint3Dof(
        parent_link_index=intent.parent_link_index,
        child_link_index=intent.child_link_index,
        orientation_parent=_matrix_tuple(parent),
        orientation_child=_matrix_tuple(child),
        default_stiffness=0.825 if intent.stiffness is None else intent.stiffness,
        enforce_exceeded_limits=intent.enforce_exceeded_limits,
        hard_first_lean_angle_max=half_extents[0] - penetration,
        hard_second_lean_angle_max=half_extents[1] - penetration,
        hard_twist_angle_max=half_extents[2] - penetration,
        soft_limit_ratio=intent.soft_limit_ratio,
        use_child_for_twist_axis=intent.use_child_for_twist_axis,
    )


def _aggregate_link_inertia(
    child_link_indices: Sequence[int],
    child_mass_properties: Sequence[YftPhysicsInertia],
    link_count: int,
    report: ValidationReport,
) -> tuple[YftPhysicsInertia, ...]:
    totals = [[0.0, 0.0, 0.0, 0.0] for _ in range(link_count)]
    populated = [False] * link_count
    for index, (link_index, inertia) in enumerate(
        zip(child_link_indices, child_mass_properties, strict=True)
    ):
        path = f"child_mass_properties[{index}]"
        values = inertia.as_tuple()
        if not all(math.isfinite(value) and value >= 0.0 for value in values):
            _issue(
                report,
                YftArticulationIssueCode.INVALID_INERTIA,
                "mass and diagonal angular inertia must be finite and non-negative",
                path,
            )
            continue
        populated[link_index] = True
        for component, value in enumerate(values):
            totals[link_index][component] += value
    for link_index, present in enumerate(populated):
        if not present:
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                "every articulated link must own at least one physics child",
                f"child_link_indices[{link_index}]",
            )
    return tuple(YftPhysicsInertia(*values) for values in totals)


def validate_articulated_body(
    body: YftArticulatedBodyType,
    *,
    physics_child_count: int | None = None,
) -> ValidationReport:
    report = ValidationReport()
    if not 1 <= body.num_links <= YFT_MAX_ARTICULATED_LINKS:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_CARDINALITY,
            f"articulated bodies require 1 to {YFT_MAX_ARTICULATED_LINKS} links",
            "num_links",
        )
    expected_joints = max(0, body.num_links - 1)
    if body.num_joints != expected_joints or len(body.joints) != expected_joints:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_CARDINALITY,
            "joint metadata and declarations must equal link count minus one",
            "joints",
        )
    if len(body.resourced_ang_inertia) != body.num_links:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_CARDINALITY,
            "resourced angular inertia must contain one value per link",
            "resourced_ang_inertia",
        )
    for index, inertia in enumerate(body.resourced_ang_inertia):
        if not all(
            math.isfinite(value) and value >= 0.0 for value in inertia.as_tuple()
        ):
            _issue(
                report,
                YftArticulationIssueCode.INVALID_INERTIA,
                "mass and diagonal angular inertia must be finite and non-negative",
                f"resourced_ang_inertia[{index}]",
            )
    parents = tuple(body.joint_parent_indices)
    if len(parents) < expected_joints:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_CARDINALITY,
            "joint parent array is shorter than the declared joint count",
            "joint_parent_indices",
        )
    for index, joint in enumerate(body.joints):
        path = f"joints[{index}]"
        expected_child = index + 1
        if joint.child_link_index != expected_child:
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                "joint order must correspond to child links 1 through num_links - 1",
                f"{path}.child_link_index",
            )
        if not 0 <= joint.parent_link_index < body.num_links:
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                "joint parent must reference an existing link",
                f"{path}.parent_link_index",
            )
        if index < len(parents) and parents[index] != joint.parent_link_index:
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                "joint parent array must match the joint declaration",
                f"joint_parent_indices[{index}]",
            )
        for field_name, value in (
            ("orientation_parent", joint.orientation_parent),
            ("orientation_child", joint.orientation_child),
        ):
            try:
                matrix4(value)
            except (TypeError, ValueError) as error:
                _issue(
                    report,
                    YftArticulationIssueCode.INVALID_JOINT,
                    str(error),
                    f"{path}.{field_name}",
                )
        if not math.isfinite(joint.default_stiffness):
            _issue(
                report,
                YftArticulationIssueCode.INVALID_JOINT,
                "joint stiffness must be finite",
                f"{path}.default_stiffness",
            )
        if isinstance(joint, YftPhysicsJoint1Dof):
            if not (
                math.isfinite(joint.hard_angle_min)
                and math.isfinite(joint.hard_angle_max)
                and joint.hard_angle_min <= joint.hard_angle_max
            ):
                _issue(
                    report,
                    YftArticulationIssueCode.INVALID_RANGE,
                    "1DOF hard limits must be finite and ordered",
                    path,
                )
        elif isinstance(joint, YftPhysicsJoint3Dof):
            limits = (
                joint.hard_first_lean_angle_max,
                joint.hard_second_lean_angle_max,
                joint.hard_twist_angle_max,
            )
            if not all(
                math.isfinite(value) and 0.0 < value < math.pi for value in limits
            ):
                _issue(
                    report,
                    YftArticulationIssueCode.INVALID_RANGE,
                    "3DOF hard limits must be finite, positive, and less than pi",
                    path,
                )
    for child in range(1, min(body.num_links, len(parents) + 1)):
        visited = {child}
        current = child
        while current:
            parent_index = current - 1
            if not 0 <= parent_index < len(parents):
                break
            current = parents[parent_index]
            if current in visited:
                _issue(
                    report,
                    YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                    "joint graph must be acyclic and rooted at link 0",
                    f"joint_parent_indices[{parent_index}]",
                )
                break
            visited.add(current)
    if body.child_link_indices:
        if (
            physics_child_count is not None
            and len(body.child_link_indices) != physics_child_count
        ):
            _issue(
                report,
                YftArticulationIssueCode.INVALID_CARDINALITY,
                "child-to-link mapping must contain one entry per physics child",
                "child_link_indices",
            )
        if any(not 0 <= value < body.num_links for value in body.child_link_indices):
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                "child-to-link mapping references a missing link",
                "child_link_indices",
            )
        missing = set(range(body.num_links)) - set(body.child_link_indices)
        if missing:
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                "every articulated link must own at least one physics child",
                "child_link_indices",
            )
    elif physics_child_count is not None and body.num_links > physics_child_count:
        _issue(
            report,
            YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
            "articulated link count cannot exceed physics child count",
            "num_links",
        )
    return report


def author_articulated_body(
    child_link_indices: Sequence[int],
    link_world_transforms: Sequence[Matrix4],
    joints: Sequence[YftArticulatedJointIntent],
    child_mass_properties: Sequence[YftPhysicsInertia],
    policy: YftArticulationPolicy = DEFAULT_YFT_ARTICULATION_POLICY,
) -> YftArticulatedBodyType:
    report = ValidationReport()
    link_count = len(link_world_transforms)
    if not 1 <= link_count <= YFT_MAX_ARTICULATED_LINKS:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_CARDINALITY,
            f"articulated bodies require 1 to {YFT_MAX_ARTICULATED_LINKS} links",
            "link_world_transforms",
        )
    if len(child_link_indices) != len(child_mass_properties):
        _issue(
            report,
            YftArticulationIssueCode.INVALID_CARDINALITY,
            "child-to-link mapping and child mass properties must have equal length",
            "child_link_indices",
        )
    if len(joints) > YFT_MAX_ARTICULATED_JOINTS:
        _issue(
            report,
            YftArticulationIssueCode.INVALID_CARDINALITY,
            f"articulated bodies support at most {YFT_MAX_ARTICULATED_JOINTS} joints",
            "joints",
        )
    valid_child_links = all(
        0 <= int(value) < link_count for value in child_link_indices
    )
    if not valid_child_links:
        _issue(
            report,
            YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
            "every physics child must map to an existing articulated link",
            "child_link_indices",
        )
    transforms = _validated_link_transforms(link_world_transforms, policy, report)
    if len(transforms) != link_count:
        report.raise_for_errors()
    by_child: dict[int, tuple[int, YftArticulatedJointIntent]] = {}
    for index, intent in enumerate(joints):
        parent = int(intent.parent_link_index)
        child = int(intent.child_link_index)
        if (
            not 0 <= parent < link_count
            or not 1 <= child < link_count
            or parent == child
        ):
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                "joint parent and non-root child must reference different existing links",
                f"joints[{index}]",
            )
        elif child in by_child:
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                "each non-root link must have exactly one incoming joint",
                f"joints[{index}].child_link_index",
            )
        else:
            by_child[child] = (index, intent)
    if set(by_child) != set(range(1, link_count)):
        _issue(
            report,
            YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
            "joint graph must connect every non-root link exactly once",
            "joints",
        )
    for child in range(1, link_count):
        visited = {child}
        current = child
        while current in by_child:
            current = int(by_child[current][1].parent_link_index)
            if current in visited:
                _issue(
                    report,
                    YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                    "joint graph must be acyclic",
                    f"joints[{child - 1}]",
                )
                break
            visited.add(current)
        if current != 0:
            _issue(
                report,
                YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY,
                "every articulated link must be reachable from root link 0",
                f"joints[{child - 1}]",
            )
    if (
        not math.isfinite(policy.allowed_angle_penetration)
        or policy.allowed_angle_penetration < 0.0
    ):
        _issue(
            report,
            YftArticulationIssueCode.INVALID_RANGE,
            "allowed angle penetration must be finite and non-negative",
            "policy.allowed_angle_penetration",
        )
    report.raise_for_errors()
    inertia = _aggregate_link_inertia(
        child_link_indices, child_mass_properties, link_count, report
    )
    built_joints = []
    for child in range(1, link_count):
        source_index, intent = by_child[child]
        if isinstance(intent, YftJoint1DofIntent):
            joint = _build_1dof_joint(intent, transforms, policy, report, source_index)
        else:
            joint = _build_3dof_joint(intent, transforms, policy, report, source_index)
        if joint is not None:
            built_joints.append(joint)
    report.raise_for_errors()
    parent_indices = [
        int(by_child[child][1].parent_link_index) for child in range(1, link_count)
    ]
    parent_indices.extend([-1] * (YFT_MAX_ARTICULATED_LINKS - len(parent_indices)))
    body = YftArticulatedBodyType(
        vft=PH_ARTICULATED_BODY_TYPE_EUPHORIA_VFT,
        joint_parent_indices=tuple(parent_indices),
        joints=tuple(built_joints),
        resourced_ang_inertia=inertia,
        num_links=link_count,
        num_joints=len(built_joints),
        joint_types=tuple(joint.joint_type for joint in built_joints),
        locally_owned=True,
        child_link_indices=tuple(int(value) for value in child_link_indices),
    )
    validate_articulated_body(
        body, physics_child_count=len(child_mass_properties)
    ).raise_for_errors()
    return body


__all__ = [
    "DEFAULT_YFT_ARTICULATION_POLICY",
    "YFT_MAX_ARTICULATED_JOINTS",
    "YFT_MAX_ARTICULATED_LINKS",
    "YftAngularRange",
    "YftAngularRangePolicy",
    "YftArticulatedJointIntent",
    "YftArticulationIssueCode",
    "YftArticulationPolicy",
    "YftJoint1DofIntent",
    "YftJoint3DofIntent",
    "YftJointFrameSpace",
    "author_articulated_body",
    "validate_articulated_body",
]
