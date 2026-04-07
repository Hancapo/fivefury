from __future__ import annotations

import struct
from typing import Callable

from ..binary import read_c_string
from .model import Matrix4, YdrBone, YdrBoneFlags, YdrSkeleton


def _read_matrix_array(pointer: int, count: int, system_data: bytes, *, virtual_offset: Callable[[int, bytes], int]) -> list[Matrix4]:
    if not pointer or count <= 0:
        return []
    offset = virtual_offset(pointer, system_data)
    size = count * 64
    end = offset + size
    if end > len(system_data):
        raise ValueError("skeleton matrix array is truncated")
    values = struct.unpack_from(f"<{count * 16}f", system_data, offset)
    matrices: list[Matrix4] = []
    for index in range(count):
        base = index * 16
        matrices.append(
            (
                tuple(float(v) for v in values[base + 0 : base + 4]),
                tuple(float(v) for v in values[base + 4 : base + 8]),
                tuple(float(v) for v in values[base + 8 : base + 12]),
                tuple(float(v) for v in values[base + 12 : base + 16]),
            )
        )
    return matrices


def _read_short_array(pointer: int, count: int, system_data: bytes, *, virtual_offset: Callable[[int, bytes], int]) -> list[int]:
    if not pointer or count <= 0:
        return []
    offset = virtual_offset(pointer, system_data)
    size = count * 2
    end = offset + size
    if end > len(system_data):
        raise ValueError("skeleton short array is truncated")
    return list(struct.unpack_from(f"<{count}h", system_data, offset))


def _try_read_name(pointer: int, system_data: bytes, *, virtual_offset: Callable[[int, bytes], int]) -> str:
    if not pointer:
        return ""
    return read_c_string(system_data, virtual_offset(pointer, system_data))


def parse_skeleton(
    system_data: bytes,
    pointer: int,
    *,
    virtual_offset: Callable[[int, bytes], int],
    u16: Callable[[bytes, int], int],
    u32: Callable[[bytes, int], int],
    u64: Callable[[bytes, int], int],
    f32: Callable[[bytes, int], float],
) -> YdrSkeleton | None:
    if not pointer:
        return None
    skeleton_off = virtual_offset(pointer, system_data)
    bones_pointer = u64(system_data, skeleton_off + 0x20)
    transformations_inverted_pointer = u64(system_data, skeleton_off + 0x28)
    transformations_pointer = u64(system_data, skeleton_off + 0x30)
    parent_indices_pointer = u64(system_data, skeleton_off + 0x38)
    child_indices_pointer = u64(system_data, skeleton_off + 0x40)
    bone_count = u16(system_data, skeleton_off + 0x5E)
    child_indices_count = u16(system_data, skeleton_off + 0x60)

    parent_indices = _read_short_array(parent_indices_pointer, bone_count, system_data, virtual_offset=virtual_offset)
    child_indices = _read_short_array(child_indices_pointer, child_indices_count, system_data, virtual_offset=virtual_offset)
    transformations = _read_matrix_array(transformations_pointer, bone_count, system_data, virtual_offset=virtual_offset)
    transformations_inverted = _read_matrix_array(
        transformations_inverted_pointer,
        bone_count,
        system_data,
        virtual_offset=virtual_offset,
    )

    bones: list[YdrBone] = []
    if bones_pointer and bone_count:
        bones_off = virtual_offset(bones_pointer, system_data) - 16
        items_off = bones_off + 16
        for bone_index in range(bone_count):
            bone_off = items_off + (bone_index * 80)
            name_pointer = u64(system_data, bone_off + 0x38)
            transform = transformations[bone_index] if bone_index < len(transformations) else None
            inverse_bind = transformations_inverted[bone_index] if bone_index < len(transformations_inverted) else None
            bones.append(
                YdrBone(
                    name=_try_read_name(name_pointer, system_data, virtual_offset=virtual_offset),
                    tag=u16(system_data, bone_off + 0x44),
                    index=struct.unpack_from("<h", system_data, bone_off + 0x42)[0],
                    parent_index=struct.unpack_from("<h", system_data, bone_off + 0x32)[0],
                    next_sibling_index=struct.unpack_from("<h", system_data, bone_off + 0x30)[0],
                    flags=YdrBoneFlags(u16(system_data, bone_off + 0x40)),
                    rotation=(
                        f32(system_data, bone_off + 0x00),
                        f32(system_data, bone_off + 0x04),
                        f32(system_data, bone_off + 0x08),
                        f32(system_data, bone_off + 0x0C),
                    ),
                    translation=(
                        f32(system_data, bone_off + 0x10),
                        f32(system_data, bone_off + 0x14),
                        f32(system_data, bone_off + 0x18),
                    ),
                    scale=(
                        f32(system_data, bone_off + 0x20),
                        f32(system_data, bone_off + 0x24),
                        f32(system_data, bone_off + 0x28),
                    ),
                    transform_unk=(
                        transform[0][3],
                        transform[1][3],
                        transform[2][3],
                        transform[3][3],
                    ) if transform is not None else (0.0, 0.0, 0.0, 0.0),
                    inverse_bind_transform=inverse_bind,
                    unknown_1ch=u32(system_data, bone_off + 0x1C),
                    unknown_2ch=f32(system_data, bone_off + 0x2C),
                    unknown_34h=u32(system_data, bone_off + 0x34),
                    unknown_48h=u64(system_data, bone_off + 0x48),
                )
            )

    return YdrSkeleton(
        bones=bones,
        parent_indices=parent_indices,
        child_indices=child_indices,
        transformations=transformations,
        transformations_inverted=transformations_inverted,
        unknown_1ch=u32(system_data, skeleton_off + 0x1C),
        unknown_50h=u32(system_data, skeleton_off + 0x50),
        unknown_54h=u32(system_data, skeleton_off + 0x54),
        unknown_58h=u32(system_data, skeleton_off + 0x58),
        unknown_5ch=u16(system_data, skeleton_off + 0x5C),
        unknown_62h=u16(system_data, skeleton_off + 0x62),
        unknown_64h=u32(system_data, skeleton_off + 0x64),
        unknown_68h=u64(system_data, skeleton_off + 0x68),
    )


__all__ = ["parse_skeleton"]
