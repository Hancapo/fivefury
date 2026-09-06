from __future__ import annotations

import struct
from collections.abc import Iterable, Sequence

from ....buckets import at_hash_bucket_capacity
from ....hashing import crc32
from .bone import YdrBone
from .flags import YdrBoneFlags
from .hierarchy import YdrSkeleton


def calculate_skeleton_unknown_hashes(skeleton: YdrSkeleton) -> tuple[int, int, int]:
    signature = 0
    comprehensive = 0
    for bone in skeleton.bones:
        id_and_dofs = _skeleton_id_and_dofs(bone)
        signature = _crc32_u64(signature, id_and_dofs)
        comprehensive = _crc32_u64(comprehensive, id_and_dofs)
        comprehensive = _crc32_floats(
            comprehensive, (*bone.translation, float(bone.unknown_1ch))
        )
        comprehensive = _crc32_floats(comprehensive, bone.rotation)
        comprehensive = _crc32_floats(
            comprehensive, (*bone.scale, float(bone.unknown_2ch))
        )
    return (
        signature,
        _calculate_skeleton_non_chiral_signature(skeleton),
        comprehensive,
    )


def _crc32_u64(seed: int, value: int) -> int:
    return (
        crc32(struct.pack("<Q", int(value) & 0xFFFFFFFFFFFFFFFF), int(seed))
        & 0xFFFFFFFF
    )


def _crc32_floats(seed: int, values: Iterable[float]) -> int:
    components = tuple(float(value) for value in values)
    return (
        crc32(
            struct.pack(f"<{len(components)}f", *components),
            int(seed),
        )
        & 0xFFFFFFFF
    )


def _skeleton_id_and_dofs(bone: YdrBone) -> int:
    return (int(bone.tag) << 32) | (int(bone.flags) & 0xFFFF)


def _skeleton_non_chiral_id_and_dofs(bone: YdrBone) -> int:
    flags = int(bone.flags)
    dofs = 0
    if flags & int(YdrBoneFlags.TRANS_X | YdrBoneFlags.TRANS_Y | YdrBoneFlags.TRANS_Z):
        dofs |= 0x1
    if flags & int(YdrBoneFlags.ROT_X | YdrBoneFlags.ROT_Y | YdrBoneFlags.ROT_Z):
        dofs |= 0x2
    if flags & int(YdrBoneFlags.SCALE_X | YdrBoneFlags.SCALE_Y | YdrBoneFlags.SCALE_Z):
        dofs |= 0x4
    return (int(bone.tag) << 32) | dofs


def _calculate_skeleton_non_chiral_signature(skeleton: YdrSkeleton) -> int:
    if not skeleton.bones:
        return 0
    has_bone_ids = any(
        int(bone.tag) != index for index, bone in enumerate(skeleton.bones)
    )
    bones = (
        _skeleton_at_map_bone_order(skeleton.bones)
        if has_bone_ids
        else list(skeleton.bones)
    )
    signature = 0
    for bone in bones:
        signature = _crc32_u64(signature, _skeleton_non_chiral_id_and_dofs(bone))
    return signature


def _skeleton_at_map_bone_order(bones: Sequence[YdrBone]) -> list[YdrBone]:
    bucket_count = at_hash_bucket_capacity(len(bones))
    buckets: list[list[YdrBone]] = [[] for _ in range(bucket_count)]
    for bone in bones:
        buckets[int(bone.tag) % bucket_count].insert(0, bone)
    return [bone for bucket in buckets for bone in bucket]
