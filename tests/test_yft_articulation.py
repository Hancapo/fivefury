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
        (0, 1),
        (transform(), transform(translation=Vector3(2.0, 0.0, 0.0))),
        (
            YftJoint1DofIntent(
                parent_link_index=0,
                child_link_index=1,
                pivot=Vector3(1.0, 2.0, 3.0),
                axis=Vector3(0.0, 0.0, 2.0),
                angle=YftAngularRange(-0.4, 0.8),
            ),
        ),
        (inertia(1.0), inertia(2.0)),
    )

    joint = body.joints[0]
    assert joint.hard_angle_min == pytest.approx(-0.37)
    assert joint.hard_angle_max == pytest.approx(0.77)
    assert np.asarray(joint.orientation_parent)[:3, 3] == pytest.approx((1.0, 2.0, 3.0))
    assert np.asarray(joint.orientation_child)[:3, 3] == pytest.approx((-1.0, 2.0, 3.0))
    assert joint.orientation_parent != transform()


def test_authors_asymmetric_3dof_ranges_with_orientation_offsets():
    body = author_articulated_body(
        (0, 1),
        (transform(), transform()),
        (
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
        (inertia(1.0), inertia(2.0)),
    )

    joint = body.joints[0]
    assert joint.hard_first_lean_angle_max == pytest.approx(0.37)
    assert joint.hard_second_lean_angle_max == pytest.approx(0.37)
    assert joint.hard_twist_angle_max == pytest.approx(0.37)
    assert not np.allclose(np.asarray(joint.orientation_parent)[:3, :3], np.identity(3))
    assert not np.allclose(np.asarray(joint.orientation_child)[:3, :3], np.identity(3))


def test_authors_branching_links_and_aggregates_multiple_children_per_link():
    body = author_articulated_body(
        (0, 1, 1, 2),
        (transform(), transform(), transform()),
        (
            YftJoint1DofIntent(
                0, 1, Vector3(), Vector3(0.0, 0.0, 1.0), YftAngularRange(-0.5, 0.5)
            ),
            YftJoint1DofIntent(
                0, 2, Vector3(), Vector3(0.0, 1.0, 0.0), YftAngularRange(-0.5, 0.5)
            ),
        ),
        (inertia(1.0), inertia(2.0), inertia(3.0), inertia(4.0)),
    )

    assert body.child_link_indices == (0, 1, 1, 2)
    assert body.joint_parent_indices[:2] == (0, 0)
    assert body.resourced_ang_inertia[1] == YftPhysicsInertia(5.0, 7.0, 9.0, 11.0)


def test_transforms_child_local_joint_frames_to_world_space():
    body = author_articulated_body(
        (0, 1),
        (transform(), transform(translation=Vector3(10.0, 0.0, 0.0))),
        (
            YftJoint1DofIntent(
                0,
                1,
                Vector3(1.0, 0.0, 0.0),
                Vector3(0.0, 0.0, 1.0),
                YftAngularRange(-0.5, 0.5),
                frame_space=YftJointFrameSpace.CHILD_LINK,
            ),
        ),
        (inertia(1.0), inertia(2.0)),
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
            (0, 1),
            (transform(), transform()),
            (YftJoint1DofIntent(0, 1, Vector3(), axis, YftAngularRange(-0.5, 0.5)),),
            (inertia(1.0), inertia(2.0)),
        )

    assert caught.value.report.errors[0].code == code.value


def test_rejects_unrepresentable_3dof_range():
    with pytest.raises(ValidationError) as caught:
        author_articulated_body(
            (0, 1),
            (transform(), transform()),
            (
                YftJoint3DofIntent(
                    0,
                    1,
                    Vector3(),
                    Vector3(0.0, 0.0, 1.0),
                    Vector3(1.0, 0.0, 0.0),
                    YftAngularRange(-math.pi, math.pi),
                    YftAngularRange(-0.5, 0.5),
                    YftAngularRange(-0.5, 0.5),
                ),
            ),
            (inertia(1.0), inertia(2.0)),
        )

    assert (
        caught.value.report.errors[0].code
        == YftArticulationIssueCode.UNREPRESENTABLE_RANGE.value
    )


def test_rejects_cyclic_topology():
    with pytest.raises(ValidationError) as caught:
        author_articulated_body(
            (0, 1, 2),
            (transform(), transform(), transform()),
            (
                YftJoint1DofIntent(
                    2, 1, Vector3(), Vector3(0.0, 0.0, 1.0), YftAngularRange(-0.5, 0.5)
                ),
                YftJoint1DofIntent(
                    1, 2, Vector3(), Vector3(0.0, 0.0, 1.0), YftAngularRange(-0.5, 0.5)
                ),
            ),
            (inertia(1.0), inertia(2.0), inertia(3.0)),
        )

    assert any(
        issue.code == YftArticulationIssueCode.UNREPRESENTABLE_TOPOLOGY.value
        for issue in caught.value.report.errors
    )
