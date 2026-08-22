import dataclasses
import math

import numpy as np
import pytest

from fivefury import (
    ValidationError,
    Vector3,
    YftAngularRange,
    YftArticulationIssueCode,
    YftJoint1DofIntent,
    YftJoint3DofIntent,
    YftJointFrameSpace,
    YftPhysicsInertia,
    author_articulated_body,
    default_articulated_body_type,
    validate_articulated_body,
)


def transform(*, translation: Vector3 | None = None):
    translation = translation or Vector3()
    return (
        (1.0, 0.0, 0.0, translation.x),
        (0.0, 1.0, 0.0, translation.y),
        (0.0, 0.0, 1.0, translation.z),
        (0.0, 0.0, 0.0, 1.0),
    )


def inertia(value: float) -> YftPhysicsInertia:
    return YftPhysicsInertia(value, value + 1.0, value + 2.0, value + 3.0)


def test_authors_nonidentity_1dof_joint_from_world_axis():
    body = author_articulated_body(
        child_link_indices=(0, 1),
        link_world_transforms=(
            transform(),
            transform(translation=Vector3(2.0, 0.0, 0.0)),
        ),
        joints=(
            YftJoint1DofIntent(
                parent_link_index=0,
                child_link_index=1,
                pivot=Vector3(1.0, 2.0, 3.0),
                axis=Vector3(0.0, 0.0, 2.0),
                angle=YftAngularRange(-0.4, 0.8),
            ),
        ),
        child_mass_properties=(inertia(1.0), inertia(2.0)),
    )

    joint = body.joints[0]
    assert joint.hard_angle_min == pytest.approx(-0.37)
    assert joint.hard_angle_max == pytest.approx(0.77)
    assert np.asarray(joint.orientation_parent)[:3, 3] == pytest.approx((1.0, 2.0, 3.0))
    assert np.asarray(joint.orientation_child)[:3, 3] == pytest.approx((-1.0, 2.0, 3.0))
    assert joint.orientation_parent != transform()
    np.testing.assert_allclose(
        np.asarray(joint.orientation_parent)[:3, :3],
        ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    )


def test_authors_asymmetric_3dof_ranges_with_orientation_offsets():
    body = author_articulated_body(
        child_link_indices=(0, 1),
        link_world_transforms=(transform(), transform()),
        joints=(
            YftJoint3DofIntent(
                parent_link_index=0,
                child_link_index=1,
                pivot=Vector3(),
                twist_axis=Vector3(0.0, 0.0, 1.0),
                first_lean_axis=Vector3(1.0, 0.0, 0.0),
                first_lean=YftAngularRange(-0.2, 0.6),
                second_lean=YftAngularRange(-0.5, 0.3),
                twist=YftAngularRange(-0.1, 0.7),
            ),
        ),
        child_mass_properties=(inertia(1.0), inertia(2.0)),
    )

    joint = body.joints[0]
    assert joint.hard_first_lean_angle_max == pytest.approx(0.37)
    assert joint.hard_second_lean_angle_max == pytest.approx(0.37)
    assert joint.hard_twist_angle_max == pytest.approx(0.37)
    assert not np.allclose(np.asarray(joint.orientation_parent)[:3, :3], np.identity(3))
    assert not np.allclose(np.asarray(joint.orientation_child)[:3, :3], np.identity(3))


def test_authors_branching_links_and_aggregates_multiple_children_per_link():
    body = author_articulated_body(
        child_link_indices=(0, 1, 1, 2),
        link_world_transforms=(transform(), transform(), transform()),
        joints=(
            YftJoint1DofIntent(
                parent_link_index=0,
                child_link_index=1,
                pivot=Vector3(),
                axis=Vector3(0.0, 0.0, 1.0),
                angle=YftAngularRange(-0.5, 0.5),
            ),
            YftJoint1DofIntent(
                parent_link_index=0,
                child_link_index=2,
                pivot=Vector3(),
                axis=Vector3(0.0, 1.0, 0.0),
                angle=YftAngularRange(-0.5, 0.5),
            ),
        ),
        child_mass_properties=(inertia(1.0), inertia(2.0), inertia(3.0), inertia(4.0)),
    )

    assert body.child_link_indices == (0, 1, 1, 2)
    assert body.joint_parent_indices[:2] == (0, 0)
    assert body.resourced_ang_inertia[1] == YftPhysicsInertia(5.0, 7.0, 9.0, 11.0)


def test_transforms_child_local_joint_frames_to_world_space():
    body = author_articulated_body(
        child_link_indices=(0, 1),
        link_world_transforms=(
            transform(),
            transform(translation=Vector3(10.0, 0.0, 0.0)),
        ),
        joints=(
            YftJoint1DofIntent(
                parent_link_index=0,
                child_link_index=1,
                pivot=Vector3(1.0, 0.0, 0.0),
                axis=Vector3(0.0, 0.0, 1.0),
                angle=YftAngularRange(-0.5, 0.5),
                frame_space=YftJointFrameSpace.CHILD_LINK,
            ),
        ),
        child_mass_properties=(inertia(1.0), inertia(2.0)),
    )

    assert np.asarray(body.joints[0].orientation_parent)[:3, 3] == pytest.approx(
        (11.0, 0.0, 0.0)
    )
    assert np.asarray(body.joints[0].orientation_child)[:3, 3] == pytest.approx(
        (1.0, 0.0, 0.0)
    )


@pytest.mark.parametrize(
    ("axis", "code"),
    (
        (Vector3(), YftArticulationIssueCode.INVALID_JOINT),
        (Vector3(math.nan, 0.0, 0.0), YftArticulationIssueCode.INVALID_JOINT),
    ),
)
def test_rejects_invalid_joint_axes(axis, code):
    with pytest.raises(ValidationError) as caught:
        author_articulated_body(
            child_link_indices=(0, 1),
            link_world_transforms=(transform(), transform()),
            joints=(
                YftJoint1DofIntent(
                    parent_link_index=0,
                    child_link_index=1,
                    pivot=Vector3(),
                    axis=axis,
                    angle=YftAngularRange(-0.5, 0.5),
                ),
            ),
            child_mass_properties=(inertia(1.0), inertia(2.0)),
        )

    assert caught.value.report.errors[0].code == code.value


def test_rejects_unrepresentable_3dof_range():
    with pytest.raises(ValidationError) as caught:
        author_articulated_body(
            child_link_indices=(0, 1),
            link_world_transforms=(transform(), transform()),
            joints=(
                YftJoint3DofIntent(
                    parent_link_index=0,
                    child_link_index=1,
                    pivot=Vector3(),
                    twist_axis=Vector3(0.0, 0.0, 1.0),
                    first_lean_axis=Vector3(1.0, 0.0, 0.0),
                    first_lean=YftAngularRange(-0.1, 2.0 * math.pi),
                    second_lean=YftAngularRange(-0.5, 0.5),
                    twist=YftAngularRange(-0.5, 0.5),
                ),
            ),
            child_mass_properties=(inertia(1.0), inertia(2.0)),
        )

    assert (
        caught.value.report.errors[0].code
        == YftArticulationIssueCode.UNREPRESENTABLE_RANGE.value
    )


def test_rejects_cyclic_topology():
    with pytest.raises(ValidationError) as caught:
        author_articulated_body(
            child_link_indices=(0, 1, 2),
            link_world_transforms=(transform(), transform(), transform()),
            joints=(
                YftJoint1DofIntent(
                    parent_link_index=2,
                    child_link_index=1,
                    pivot=Vector3(),
                    axis=Vector3(0.0, 0.0, 1.0),
                    angle=YftAngularRange(-0.5, 0.5),
                ),
                YftJoint1DofIntent(
                    parent_link_index=1,
                    child_link_index=2,
                    pivot=Vector3(),
                    axis=Vector3(0.0, 0.0, 1.0),
                    angle=YftAngularRange(-0.5, 0.5),
                ),
            ),
            child_mass_properties=(inertia(1.0), inertia(2.0), inertia(3.0)),
        )

    assert any(
        issue.code == YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY.value
        for issue in caught.value.report.errors
    )


def test_validates_parent_array_against_canonical_joint_order():
    body = author_articulated_body(
        child_link_indices=(0, 1),
        link_world_transforms=(transform(), transform()),
        joints=(
            YftJoint1DofIntent(
                parent_link_index=0,
                child_link_index=1,
                pivot=Vector3(),
                axis=Vector3(0.0, 0.0, 1.0),
                angle=YftAngularRange(-0.5, 0.5),
            ),
        ),
        child_mass_properties=(inertia(1.0), inertia(2.0)),
    )
    invalid = dataclasses.replace(
        body, joint_parent_indices=(1, *body.joint_parent_indices[1:])
    )

    report = validate_articulated_body(invalid, physics_child_count=2)

    assert not report.valid
    assert any(
        issue.code == YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY.value
        for issue in report.errors
    )


def test_identity_fixture_uses_joint_indexed_parent_array():
    body = default_articulated_body_type(link_count=4)

    assert body.joint_parent_indices[:3] == (0, 1, 2)


def test_accepts_native_link_and_joint_limits():
    link_count = 23
    body = author_articulated_body(
        child_link_indices=tuple(range(link_count)),
        link_world_transforms=tuple(transform() for _ in range(link_count)),
        joints=tuple(
            YftJoint1DofIntent(
                parent_link_index=child - 1,
                child_link_index=child,
                pivot=Vector3(),
                axis=Vector3(0.0, 0.0, 1.0),
                angle=YftAngularRange(-0.5, 0.5),
            )
            for child in range(1, link_count)
        ),
        child_mass_properties=tuple(
            inertia(float(index + 1)) for index in range(link_count)
        ),
    )

    assert body.num_links == 23
    assert body.num_joints == 22
    assert validate_articulated_body(body, physics_child_count=23).valid
