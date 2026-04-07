from __future__ import annotations

import math
import struct

from ..resource import ResourceWriter
from .model import Matrix4, YdrBone, YdrSkeleton

_SKELETON_VFT = 0x40614B80


def _identity_matrix() -> Matrix4:
    return (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def _matrix_with_column4(matrix: Matrix4, column4: tuple[float, float, float, float]) -> Matrix4:
    return (
        (matrix[0][0], matrix[0][1], matrix[0][2], column4[0]),
        (matrix[1][0], matrix[1][1], matrix[1][2], column4[1]),
        (matrix[2][0], matrix[2][1], matrix[2][2], column4[2]),
        (matrix[3][0], matrix[3][1], matrix[3][2], column4[3]),
    )


def _quat_to_matrix3(rotation: tuple[float, float, float, float]) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
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


def _compose_local_transform(bone: YdrBone) -> Matrix4:
    rotation = _quat_to_matrix3(bone.rotation)
    sx, sy, sz = (float(component) for component in bone.scale)
    matrix = (
        (rotation[0][0] * sx, rotation[0][1] * sy, rotation[0][2] * sz, 0.0),
        (rotation[1][0] * sx, rotation[1][1] * sy, rotation[1][2] * sz, 0.0),
        (rotation[2][0] * sx, rotation[2][1] * sy, rotation[2][2] * sz, 0.0),
        (float(bone.translation[0]), float(bone.translation[1]), float(bone.translation[2]), 1.0),
    )
    return _matrix_with_column4(matrix, bone.transform_unk)


def _pack_matrix_array(matrices: list[Matrix4]) -> bytes:
    values: list[float] = []
    for matrix in matrices:
        for row in matrix:
            values.extend(float(component) for component in row)
    return struct.pack(f"<{len(values)}f", *values) if values else b""


def _build_parent_indices(skeleton: YdrSkeleton) -> list[int]:
    if len(skeleton.parent_indices) == skeleton.bone_count:
        return [int(value) for value in skeleton.parent_indices]
    return [int(bone.parent_index) for bone in skeleton.bones]


def _build_child_indices(skeleton: YdrSkeleton) -> list[int]:
    if skeleton.child_indices:
        return [int(value) for value in skeleton.child_indices]
    bones = list(skeleton.bones)
    if not bones:
        return []
    roots = [bone for bone in bones if int(bone.parent_index) < 0]

    def get_children(parent: YdrBone) -> list[YdrBone]:
        return [bone for bone in bones if int(bone.parent_index) == int(parent.index)]

    def get_all_children(items: list[YdrBone]) -> list[YdrBone]:
        result: list[YdrBone] = []
        for item in items:
            result.extend(get_children(item))
        return result

    layers: list[list[YdrBone]] = []
    layer = get_all_children(roots)
    while layer:
        take = min(len(layer), 4)
        current = layer[:take]
        children = get_all_children(current)
        layers.append(current)
        layer = children + layer[take:]

    values: list[int] = []
    for layer_items in layers:
        last: YdrBone | None = None
        for bone in layer_items:
            values.extend((int(bone.index), int(bone.parent_index)))
            last = bone
        if last is None:
            continue
        padding = 8 - (len(values) % 8)
        if padding < 8:
            for _ in range(0, padding, 2):
                values.extend((int(last.index), int(last.parent_index)))
    return values


def _get_num_hash_buckets(hash_count: int) -> int:
    if hash_count < 11:
        return 11
    if hash_count < 29:
        return 29
    if hash_count < 59:
        return 59
    if hash_count < 107:
        return 107
    if hash_count < 191:
        return 191
    if hash_count < 331:
        return 331
    if hash_count < 563:
        return 563
    if hash_count < 953:
        return 953
    if hash_count < 1609:
        return 1609
    if hash_count < 2729:
        return 2729
    if hash_count < 4621:
        return 4621
    if hash_count < 7841:
        return 7841
    if hash_count < 13297:
        return 13297
    if hash_count < 22571:
        return 22571
    if hash_count < 38351:
        return 38351
    if hash_count < 65167:
        return 65167
    return 65521


def _build_bone_tag_block(system: ResourceWriter, skeleton: YdrSkeleton, *, virtual) -> tuple[int, int, int]:
    if skeleton.bone_count < 2:
        return 0, 0, 0
    bucket_count = _get_num_hash_buckets(skeleton.bone_count)
    buckets: list[list[YdrBone]] = [[] for _ in range(bucket_count)]
    for bone in skeleton.bones:
        buckets[int(bone.tag) % bucket_count].append(bone)

    heads = [0] * bucket_count
    for bucket_index, bucket in enumerate(buckets):
        head_pointer = 0
        for bone in reversed(bucket):
            tag_off = system.alloc(16, 16)
            system.pack_into("I", tag_off + 0x00, int(bone.tag))
            system.pack_into("I", tag_off + 0x04, int(bone.index))
            system.pack_into("Q", tag_off + 0x08, head_pointer)
            head_pointer = virtual(tag_off)
        heads[bucket_index] = head_pointer

    tags_off = system.alloc(bucket_count * 8, 16)
    for index, pointer in enumerate(heads):
        system.pack_into("Q", tags_off + (index * 8), pointer)
    return tags_off, bucket_count, min(skeleton.bone_count, bucket_count)


def _build_transformations(skeleton: YdrSkeleton) -> list[Matrix4]:
    if len(skeleton.transformations) == skeleton.bone_count:
        return list(skeleton.transformations)
    return [_compose_local_transform(bone) for bone in skeleton.bones]


def _build_inverse_transformations(skeleton: YdrSkeleton) -> list[Matrix4]:
    if len(skeleton.transformations_inverted) == skeleton.bone_count:
        return list(skeleton.transformations_inverted)
    matrices: list[Matrix4] = []
    for bone in skeleton.bones:
        matrices.append(bone.inverse_bind_transform or _identity_matrix())
    return matrices


def write_skeleton(system: ResourceWriter, skeleton: YdrSkeleton | None, *, virtual) -> int:
    if skeleton is None or not skeleton.bones:
        return 0

    bone_name_offsets = {
        index: system.c_string(bone.name or f"bone_{index}", alignment=8)
        for index, bone in enumerate(skeleton.bones)
    }
    parent_indices = _build_parent_indices(skeleton)
    child_indices = _build_child_indices(skeleton)
    transformations = _build_transformations(skeleton)
    transformations_inverted = _build_inverse_transformations(skeleton)

    parent_indices_off = 0
    if parent_indices:
        parent_indices_data = struct.pack(f"<{len(parent_indices)}h", *parent_indices)
        parent_indices_off = system.alloc(len(parent_indices_data), 16)
        system.write(parent_indices_off, parent_indices_data)

    child_indices_off = 0
    if child_indices:
        child_indices_data = struct.pack(f"<{len(child_indices)}h", *child_indices)
        child_indices_off = system.alloc(len(child_indices_data), 16)
        system.write(child_indices_off, child_indices_data)

    transformations_inverted_off = 0
    if transformations_inverted:
        inv_data = _pack_matrix_array(transformations_inverted)
        transformations_inverted_off = system.alloc(len(inv_data), 16)
        system.write(transformations_inverted_off, inv_data)

    transformations_off = 0
    if transformations:
        transforms_data = _pack_matrix_array(transformations)
        transformations_off = system.alloc(len(transforms_data), 16)
        system.write(transformations_off, transforms_data)

    bones_block_off = system.alloc(16 + (len(skeleton.bones) * 80), 16)
    system.pack_into("I", bones_block_off + 0x00, len(skeleton.bones))
    system.pack_into("I", bones_block_off + 0x04, 0)
    system.pack_into("I", bones_block_off + 0x08, 0)
    system.pack_into("I", bones_block_off + 0x0C, 0)
    bones_pointer = bones_block_off + 16

    for index, bone in enumerate(skeleton.bones):
        bone_off = bones_pointer + (index * 80)
        system.pack_into("4f", bone_off + 0x00, *[float(v) for v in bone.rotation])
        system.pack_into("3f", bone_off + 0x10, *[float(v) for v in bone.translation])
        system.pack_into("I", bone_off + 0x1C, int(bone.unknown_1ch))
        system.pack_into("3f", bone_off + 0x20, *[float(v) for v in bone.scale])
        system.pack_into("f", bone_off + 0x2C, float(bone.unknown_2ch))
        system.pack_into("h", bone_off + 0x30, int(bone.next_sibling_index))
        system.pack_into("h", bone_off + 0x32, int(bone.parent_index))
        system.pack_into("I", bone_off + 0x34, int(bone.unknown_34h))
        system.pack_into("Q", bone_off + 0x38, virtual(bone_name_offsets[index]))
        system.pack_into("H", bone_off + 0x40, int(bone.flags))
        system.pack_into("h", bone_off + 0x42, int(bone.index))
        system.pack_into("H", bone_off + 0x44, int(bone.tag) & 0xFFFF)
        system.pack_into("h", bone_off + 0x46, int(bone.index))
        system.pack_into("Q", bone_off + 0x48, int(bone.unknown_48h))

    bone_tags_off, bone_tags_capacity, bone_tags_count = _build_bone_tag_block(system, skeleton, virtual=virtual)

    skeleton_off = system.alloc(112, 16)
    system.pack_into("I", skeleton_off + 0x00, _SKELETON_VFT)
    system.pack_into("I", skeleton_off + 0x04, 1)
    system.pack_into("Q", skeleton_off + 0x08, 0)
    system.pack_into("Q", skeleton_off + 0x10, virtual(bone_tags_off) if bone_tags_off else 0)
    system.pack_into("H", skeleton_off + 0x18, bone_tags_capacity)
    system.pack_into("H", skeleton_off + 0x1A, bone_tags_count)
    system.pack_into("I", skeleton_off + 0x1C, int(skeleton.unknown_1ch))
    system.pack_into("Q", skeleton_off + 0x20, virtual(bones_pointer))
    system.pack_into("Q", skeleton_off + 0x28, virtual(transformations_inverted_off) if transformations_inverted_off else 0)
    system.pack_into("Q", skeleton_off + 0x30, virtual(transformations_off) if transformations_off else 0)
    system.pack_into("Q", skeleton_off + 0x38, virtual(parent_indices_off) if parent_indices_off else 0)
    system.pack_into("Q", skeleton_off + 0x40, virtual(child_indices_off) if child_indices_off else 0)
    system.pack_into("Q", skeleton_off + 0x48, 0)
    system.pack_into("I", skeleton_off + 0x50, int(skeleton.unknown_50h))
    system.pack_into("I", skeleton_off + 0x54, int(skeleton.unknown_54h))
    system.pack_into("I", skeleton_off + 0x58, int(skeleton.unknown_58h))
    system.pack_into("H", skeleton_off + 0x5C, int(skeleton.unknown_5ch))
    system.pack_into("H", skeleton_off + 0x5E, len(skeleton.bones))
    system.pack_into("H", skeleton_off + 0x60, len(child_indices))
    system.pack_into("H", skeleton_off + 0x62, int(skeleton.unknown_62h))
    system.pack_into("I", skeleton_off + 0x64, int(skeleton.unknown_64h))
    system.pack_into("Q", skeleton_off + 0x68, int(skeleton.unknown_68h))
    return skeleton_off


__all__ = ["write_skeleton"]
