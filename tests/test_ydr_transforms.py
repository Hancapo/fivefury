from fivefury.ydr import (
    YdrSkeleton,
    compose_bone_local_transform,
    multiply_matrix4,
    skeleton_absolute_transforms,
)


def test_skeleton_absolute_transforms_compose_parent_translation() -> None:
    skeleton = YdrSkeleton.create()
    root = skeleton.add_bone("root", translation=(2.0, 0.0, 0.0))
    child = skeleton.add_bone(
        "child",
        parent=root,
        translation=(0.0, 0.0, 1.0),
    )

    local_child = compose_bone_local_transform(child)
    absolute = skeleton_absolute_transforms(skeleton)

    assert local_child[3] == (0.0, 0.0, 1.0, 0.0)
    assert absolute[0][3] == (2.0, 0.0, 0.0, 1.0)
    assert absolute[1][3] == (2.0, 0.0, 1.0, 1.0)
    local_affine = (*local_child[:3], (*local_child[3][:3], 1.0))
    assert multiply_matrix4(local_affine, absolute[0]) == absolute[1]


def test_skeleton_absolute_transforms_reject_cycles() -> None:
    skeleton = YdrSkeleton.create()
    root = skeleton.add_bone("root")
    child = skeleton.add_bone("child", parent=root)
    root.parent_index = child.index

    try:
        skeleton_absolute_transforms(skeleton)
    except ValueError as exc:
        assert str(exc) == "Skeleton bone hierarchy contains a cycle"
    else:
        raise AssertionError("Expected cyclic skeleton hierarchy to be rejected")
