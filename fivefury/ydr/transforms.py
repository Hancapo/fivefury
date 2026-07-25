from __future__ import annotations

import math

from .model import Matrix4, YdrBone, YdrSkeleton


def _affine_matrix4(matrix: Matrix4) -> Matrix4:
    return (
        (float(matrix[0][0]), float(matrix[0][1]), float(matrix[0][2]), 0.0),
        (float(matrix[1][0]), float(matrix[1][1]), float(matrix[1][2]), 0.0),
        (float(matrix[2][0]), float(matrix[2][1]), float(matrix[2][2]), 0.0),
        (float(matrix[3][0]), float(matrix[3][1]), float(matrix[3][2]), 1.0),
    )


def _quaternion_matrix3(
    rotation: tuple[float, float, float, float],
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]:
    x, y, z, w = (float(component) for component in rotation)
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


def compose_bone_local_transform(bone: YdrBone) -> Matrix4:
    rotation = _quaternion_matrix3(bone.rotation)
    sx, sy, sz = (float(component) for component in bone.scale)
    unknown = tuple(float(component) for component in bone.transform_unk)
    return (
        (
            rotation[0][0] * sx,
            rotation[0][1] * sy,
            rotation[0][2] * sz,
            unknown[0],
        ),
        (
            rotation[1][0] * sx,
            rotation[1][1] * sy,
            rotation[1][2] * sz,
            unknown[1],
        ),
        (
            rotation[2][0] * sx,
            rotation[2][1] * sy,
            rotation[2][2] * sz,
            unknown[2],
        ),
        (
            float(bone.translation[0]),
            float(bone.translation[1]),
            float(bone.translation[2]),
            unknown[3],
        ),
    )


def multiply_matrix4(left: Matrix4, right: Matrix4) -> Matrix4:
    return tuple(
        tuple(
            sum(left[row][inner] * right[inner][column] for inner in range(4))
            for column in range(4)
        )
        for row in range(4)
    )


def skeleton_absolute_transforms(
    skeleton: YdrSkeleton | None,
) -> list[Matrix4]:
    if skeleton is None or not skeleton.bones:
        return []
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


__all__ = [
    "compose_bone_local_transform",
    "multiply_matrix4",
    "skeleton_absolute_transforms",
]
