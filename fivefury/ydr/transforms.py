from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from ..numeric import Float32Array
from ..skinning import compose_skeleton_matrices
from ..vector import Quaternion, Vector3, Vector4
from .model import Matrix4, YdrBone, YdrSkeleton

_PED_PROCEDURAL_SIBLING_COPIES = (
    ("SKEL_L_Thigh", "RB_L_ThighRoll"),
    ("SKEL_R_Thigh", "RB_R_ThighRoll"),
)


def _affine_matrix4(matrix: Matrix4) -> Matrix4:
    return (
        (float(matrix[0][0]), float(matrix[0][1]), float(matrix[0][2]), 0.0),
        (float(matrix[1][0]), float(matrix[1][1]), float(matrix[1][2]), 0.0),
        (float(matrix[2][0]), float(matrix[2][1]), float(matrix[2][2]), 0.0),
        (float(matrix[3][0]), float(matrix[3][1]), float(matrix[3][2]), 1.0),
    )


def _quaternion_matrix3(
    rotation: Quaternion,
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]:
    x = rotation.x
    y = rotation.y
    z = rotation.z
    w = rotation.w
    length = math.sqrt((x * x) + (y * y) + (z * z) + (w * w))
    if length > 1e-8:
        x /= length
        y /= length
        z /= length
        w /= length
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z
    return (
        (1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)),
        (2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)),
        (2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)),
    )


def compose_local_transform(
    translation: Vector3,
    rotation: Quaternion,
    scale: Vector3 = Vector3(1.0, 1.0, 1.0),
    transform_unk: Vector4 = Vector4(0.0, 0.0, 0.0, 1.0),
) -> Matrix4:
    """Compose a skeleton-local matrix in the serialized RAGE convention."""
    rotation_matrix = _quaternion_matrix3(rotation)
    sx = scale.x
    sy = scale.y
    sz = scale.z
    return (
        (
            rotation_matrix[0][0] * sx,
            rotation_matrix[1][0] * sx,
            rotation_matrix[2][0] * sx,
            transform_unk.x,
        ),
        (
            rotation_matrix[0][1] * sy,
            rotation_matrix[1][1] * sy,
            rotation_matrix[2][1] * sy,
            transform_unk.y,
        ),
        (
            rotation_matrix[0][2] * sz,
            rotation_matrix[1][2] * sz,
            rotation_matrix[2][2] * sz,
            transform_unk.z,
        ),
        (
            translation.x,
            translation.y,
            translation.z,
            transform_unk.w,
        ),
    )


def compose_bone_local_transform(bone: YdrBone) -> Matrix4:
    return compose_local_transform(
        bone.translation,
        bone.rotation,
        bone.scale,
        bone.transform_unk,
    )


def apply_ped_procedural_bone_fallbacks(
    skeleton: YdrSkeleton | None,
    local_transforms: Sequence[Matrix4],
    *,
    animated_bone_tags: Sequence[int] = (),
) -> list[Matrix4]:
    """Apply deterministic fallbacks for untracked procedural ped bones.

    GTA ped thigh-roll bones are siblings of their controlling thigh and have
    an identical bind-local transform. RAGE updates them procedurally after
    animation sampling. Copying the thigh local pose is the non-IK fallback;
    an explicit animation track on the roll bone always takes precedence.
    """
    if skeleton is None:
        return list(local_transforms)
    if len(local_transforms) != len(skeleton.bones):
        raise ValueError("local transform count must match skeleton bone count")
    result = list(local_transforms)
    tracked = {int(tag) for tag in animated_bone_tags}
    for source_name, target_name in _PED_PROCEDURAL_SIBLING_COPIES:
        source = skeleton.get_bone_by_name(source_name)
        target = skeleton.get_bone_by_name(target_name)
        if source is None or target is None or int(target.tag) in tracked:
            continue
        if int(source.parent_index) != int(target.parent_index):
            continue
        source_bind = np.asarray(compose_bone_local_transform(source), np.float32)
        target_bind = np.asarray(compose_bone_local_transform(target), np.float32)
        if not np.allclose(source_bind, target_bind, atol=1e-5):
            continue
        result[int(target.index)] = result[int(source.index)]
    return result


def multiply_matrix4(left: Matrix4, right: Matrix4) -> Matrix4:
    right_0, right_1, right_2, right_3 = right

    def multiply_row(row: tuple[float, float, float, float]) -> tuple[float, ...]:
        x, y, z, w = row
        return (
            x * right_0[0] + y * right_1[0] + z * right_2[0] + w * right_3[0],
            x * right_0[1] + y * right_1[1] + z * right_2[1] + w * right_3[1],
            x * right_0[2] + y * right_1[2] + z * right_2[2] + w * right_3[2],
            x * right_0[3] + y * right_1[3] + z * right_2[3] + w * right_3[3],
        )

    return tuple(multiply_row(row) for row in left)


def _inverse_matrix4(matrix: Matrix4) -> Matrix4:
    augmented = [
        [float(matrix[row][column]) for column in range(4)]
        + [1.0 if row == column else 0.0 for column in range(4)]
        for row in range(4)
    ]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-12:
            raise ValueError("Skeleton transform is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(4):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(
                    augmented[row], augmented[column], strict=True
                )
            ]
    return tuple(tuple(row[4:]) for row in augmented)


def skeleton_absolute_transforms(
    skeleton: YdrSkeleton | None,
    *,
    local_transforms: Sequence[Matrix4] | None = None,
) -> list[Matrix4]:
    if skeleton is None or not skeleton.bones:
        return []
    if local_transforms is not None:
        if len(local_transforms) != len(skeleton.bones):
            raise ValueError("local transform count must match skeleton bone count")
        local = list(local_transforms)
    else:
        local = (
            list(skeleton.transformations)
            if len(skeleton.transformations) == len(skeleton.bones)
            else [compose_bone_local_transform(bone) for bone in skeleton.bones]
        )
    absolute: list[Matrix4 | None] = [None] * len(skeleton.bones)
    resolving: set[int] = set()

    def resolve(index: int) -> Matrix4:
        cached = absolute[index]
        if cached is not None:
            return cached
        if index in resolving:
            raise ValueError("Skeleton bone hierarchy contains a cycle")
        resolving.add(index)
        matrix = _affine_matrix4(local[index])
        parent = int(skeleton.bones[index].parent_index)
        if 0 <= parent < len(skeleton.bones) and parent != index:
            matrix = multiply_matrix4(matrix, resolve(parent))
        resolving.remove(index)
        absolute[index] = matrix
        return matrix

    return [resolve(index) for index in range(len(skeleton.bones))]


def skeleton_skinning_transforms(
    skeleton: YdrSkeleton | None,
    *,
    local_transforms: Sequence[Matrix4] | None = None,
) -> list[Matrix4]:
    """Return RAGE row-vector skin matrices for each skeleton bone.

    The runtime composes the animated object transform with the cumulative
    inverse joint transform.  In FiveFury's row-vector representation this is
    ``inverse_bind * animated_absolute``.
    """
    if skeleton is None or not skeleton.bones:
        return []
    animated_absolute = skeleton_absolute_transforms(
        skeleton, local_transforms=local_transforms
    )
    if len(skeleton.transformations_inverted) == len(skeleton.bones):
        inverse_bind = [
            _affine_matrix4(matrix) for matrix in skeleton.transformations_inverted
        ]
    else:
        rest_absolute = skeleton_absolute_transforms(skeleton)
        inverse_bind = []
        for bone, absolute in zip(skeleton.bones, rest_absolute, strict=True):
            inverse_bind.append(
                _affine_matrix4(bone.inverse_bind_transform)
                if bone.inverse_bind_transform is not None
                else _inverse_matrix4(absolute)
            )
    return [
        multiply_matrix4(inverse, animated)
        for inverse, animated in zip(inverse_bind, animated_absolute, strict=True)
    ]


def skeleton_absolute_matrices(
    skeleton: YdrSkeleton | None,
    *,
    local_transforms: Sequence[Matrix4] | Float32Array | None = None,
) -> Float32Array:
    """Return cumulative RAGE row-vector transforms as a NumPy matrix array."""
    if skeleton is None or not skeleton.bones:
        return np.empty((0, 4, 4), dtype=np.float32)
    if local_transforms is not None:
        if len(local_transforms) != len(skeleton.bones):
            raise ValueError("local transform count must match skeleton bone count")
        local = np.asarray(
            local_transforms,
            dtype=np.float32,
            copy=True,
        )
    elif len(skeleton.transformations) == len(skeleton.bones):
        local = np.asarray(
            skeleton.transformations,
            dtype=np.float32,
            copy=True,
        )
    else:
        local = np.asarray(
            [compose_bone_local_transform(bone) for bone in skeleton.bones],
            dtype=np.float32,
        )
    local[:, :3, 3] = 0.0
    local[:, 3, 3] = 1.0
    parents = np.fromiter(
        (int(bone.parent_index) for bone in skeleton.bones),
        dtype=np.int32,
        count=len(skeleton.bones),
    )
    return compose_skeleton_matrices(local, parents)


def skeleton_skinning_matrices(
    skeleton: YdrSkeleton | None,
    *,
    local_transforms: Sequence[Matrix4] | Float32Array | None = None,
) -> Float32Array:
    """Return inverse-bind multiplied animated matrices without Python 4x4 loops."""
    if skeleton is None or not skeleton.bones:
        return np.empty((0, 4, 4), dtype=np.float32)
    animated = skeleton_absolute_matrices(skeleton, local_transforms=local_transforms)
    if len(skeleton.transformations_inverted) == len(skeleton.bones):
        inverse_bind = np.asarray(
            skeleton.transformations_inverted,
            dtype=np.float32,
            copy=True,
        )
        inverse_bind[:, :3, 3] = 0.0
        inverse_bind[:, 3, 3] = 1.0
    else:
        rest = skeleton_absolute_matrices(skeleton)
        inverse_bind = np.linalg.inv(rest)
        custom_indices = [
            index
            for index, bone in enumerate(skeleton.bones)
            if bone.inverse_bind_transform is not None
        ]
        if custom_indices:
            inverse_bind[custom_indices] = np.asarray(
                [
                    _affine_matrix4(skeleton.bones[index].inverse_bind_transform)
                    for index in custom_indices
                ],
                dtype=np.float32,
            )
    return inverse_bind @ animated


__all__ = [
    "apply_ped_procedural_bone_fallbacks",
    "compose_bone_local_transform",
    "compose_local_transform",
    "multiply_matrix4",
    "skeleton_absolute_matrices",
    "skeleton_absolute_transforms",
    "skeleton_skinning_matrices",
    "skeleton_skinning_transforms",
]
