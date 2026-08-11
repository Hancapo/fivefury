import numpy as np

from fivefury.ydr import (
    YdrSkeleton,
    apply_ped_procedural_bone_fallbacks,
    compose_bone_local_transform,
    compose_local_transform,
    multiply_matrix4,
    skeleton_absolute_matrices,
    skeleton_absolute_transforms,
    skeleton_skinning_matrices,
    skeleton_skinning_transforms,
)


def test_ped_thigh_roll_fallback_copies_untracked_sibling_pose() -> None:
    skeleton = YdrSkeleton.create()
    pelvis = skeleton.add_bone("SKEL_Pelvis")
    thigh = skeleton.add_bone(
        "SKEL_L_Thigh",
        parent=pelvis,
        translation=(0.1, 0.0, -0.1),
    )
    thigh_roll = skeleton.add_bone(
        "RB_L_ThighRoll",
        parent=pelvis,
        translation=(0.1, 0.0, -0.1),
    )
    local = [compose_bone_local_transform(bone) for bone in skeleton.bones]
    local[thigh.index] = compose_local_transform(
        thigh.translation,
        (0.0, 0.0, 0.7071067812, 0.7071067812),
    )

    resolved = apply_ped_procedural_bone_fallbacks(skeleton, local)

    assert resolved[thigh_roll.index] == resolved[thigh.index]


def test_explicit_ped_thigh_roll_track_wins_over_procedural_fallback() -> None:
    skeleton = YdrSkeleton.create()
    pelvis = skeleton.add_bone("SKEL_Pelvis")
    thigh = skeleton.add_bone("SKEL_R_Thigh", parent=pelvis)
    thigh_roll = skeleton.add_bone("RB_R_ThighRoll", parent=pelvis)
    local = [compose_bone_local_transform(bone) for bone in skeleton.bones]
    explicit_roll = compose_local_transform(
        thigh_roll.translation,
        (0.0, 0.7071067812, 0.0, 0.7071067812),
    )
    local[thigh.index] = compose_local_transform(
        thigh.translation,
        (0.0, 0.0, 0.7071067812, 0.7071067812),
    )
    local[thigh_roll.index] = explicit_roll

    resolved = apply_ped_procedural_bone_fallbacks(
        skeleton,
        local,
        animated_bone_tags=(thigh_roll.tag,),
    )

    assert resolved[thigh_roll.index] == explicit_roll


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


def test_skeleton_skinning_transforms_use_cumulative_inverse_bind_pose() -> None:
    skeleton = YdrSkeleton.create()
    root = skeleton.add_bone("root", translation=(2.0, 0.0, 0.0))
    child = skeleton.add_bone("child", parent=root, translation=(0.0, 0.0, 1.0))

    rest_skin = skeleton_skinning_transforms(skeleton)
    for matrix in rest_skin:
        assert matrix == (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )

    animated = [
        compose_bone_local_transform(root),
        (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 2.0, 1.0),
        ),
    ]
    animated_skin = skeleton_skinning_transforms(
        skeleton, local_transforms=animated
    )
    assert animated_skin[child.index][3] == (0.0, 0.0, 1.0, 1.0)


def test_composed_rotated_locals_preserve_the_serialized_rest_pose() -> None:
    skeleton = YdrSkeleton.create()
    root = skeleton.add_bone(
        "root",
        rotation=(0.0, 0.0, 0.3826834324, 0.9238795325),
        translation=(1.0, 2.0, 3.0),
    )
    child = skeleton.add_bone(
        "child",
        parent=root,
        rotation=(0.2588190451, 0.0, 0.0, 0.9659258263),
        translation=(0.0, 0.0, 1.0),
    )
    local = [
        compose_local_transform(bone.translation, bone.rotation, bone.scale)
        for bone in skeleton.bones
    ]

    skinning = skeleton_skinning_transforms(
        skeleton, local_transforms=local
    )

    identity = (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    for matrix in skinning:
        for actual_row, expected_row in zip(matrix, identity, strict=True):
            for actual, expected in zip(actual_row, expected_row, strict=True):
                assert abs(actual - expected) < 1e-6
    assert child.parent_index == root.index


def test_compose_local_transform_matches_rage_row_rotation_convention() -> None:
    matrix = compose_local_transform(
        (1.0, 2.0, 3.0),
        (0.0, 0.0, 0.7071067812, 0.7071067812),
    )

    expected = (
        (0.0, 1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (1.0, 2.0, 3.0, 1.0),
    )
    for actual_row, expected_row in zip(matrix, expected, strict=True):
        for actual, wanted in zip(actual_row, expected_row, strict=True):
            assert abs(actual - wanted) < 1e-6


def test_numpy_skeleton_matrices_match_scalar_transform_contract() -> None:
    skeleton = YdrSkeleton.create()
    root = skeleton.add_bone(
        "root",
        rotation=(0.0, 0.0, 0.3826834324, 0.9238795325),
        translation=(1.0, 2.0, 3.0),
    )
    skeleton.add_bone(
        "child",
        parent=root,
        rotation=(0.2588190451, 0.0, 0.0, 0.9659258263),
        translation=(0.0, 0.0, 1.0),
    )
    animated = [
        compose_bone_local_transform(bone) for bone in skeleton.bones
    ]
    animated[1] = compose_local_transform(
        (0.0, 0.0, 2.0), skeleton.bones[1].rotation
    )

    scalar_absolute = skeleton_absolute_transforms(
        skeleton, local_transforms=animated
    )
    scalar_skinning = skeleton_skinning_transforms(
        skeleton, local_transforms=animated
    )

    assert np.allclose(
        skeleton_absolute_matrices(skeleton, local_transforms=animated),
        scalar_absolute,
        atol=1e-6,
    )
    assert np.allclose(
        skeleton_skinning_matrices(skeleton, local_transforms=animated),
        scalar_skinning,
        atol=1e-6,
    )
