from __future__ import annotations

from ..resource_headers import DrawableRuntimeHeaders
from .context import DrawableFixupValidator


def _audit_bone_tag_table(
    validator: DrawableFixupValidator,
    pointer: int,
    capacity: int,
    path: str,
) -> None:
    buckets_offset = validator.pointer(
        pointer,
        path,
        size=capacity * 8,
        nullable=capacity == 0,
    )
    if buckets_offset is None:
        return
    visited: set[int] = set()
    for bucket_index in range(capacity):
        node = validator.u64(buckets_offset + bucket_index * 8)
        chain_index = 0
        while node:
            if node in visited:
                validator.error(
                    f"{path}[{bucket_index}]",
                    "bone-tag chain contains a cycle or shared node",
                )
                break
            visited.add(node)
            node_offset = validator.pointer(
                node,
                f"{path}[{bucket_index}][{chain_index}]",
                size=16,
                nullable=False,
            )
            if node_offset is None:
                break
            node = validator.u64(node_offset + 8)
            chain_index += 1


def audit_skeleton(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
    *,
    runtime_headers: DrawableRuntimeHeaders,
) -> None:
    offset = validator.class_header(
        pointer,
        path,
        size=0x70,
        expected_vft=runtime_headers.skeleton,
    )
    if offset is None:
        return
    bone_count = validator.u16(offset + 0x5E)
    child_index_count = validator.u16(offset + 0x60)
    tag_capacity = validator.u16(offset + 0x18)
    tag_pointer = validator.u64(offset + 0x10)
    if tag_pointer or tag_capacity:
        _audit_bone_tag_table(
            validator,
            tag_pointer,
            tag_capacity,
            f"{path}.bone_tags",
        )

    bones_pointer = validator.u64(offset + 0x20)
    bones_offset = validator.pointer(
        bones_pointer,
        f"{path}.bones",
        size=bone_count * 80,
        nullable=bone_count == 0,
    )
    if bones_offset is not None:
        for index in range(bone_count):
            name = validator.u64(bones_offset + index * 80 + 0x38)
            validator.string(name, f"{path}.bones[{index}].name")

    for field_offset, item_size, count, label in (
        (0x28, 64, bone_count, "inverse_transformations"),
        (0x30, 64, bone_count, "transformations"),
        (0x38, 2, bone_count, "parent_indices"),
        (0x40, 2, child_index_count, "child_indices"),
    ):
        validator.pointer(
            validator.u64(offset + field_offset),
            f"{path}.{label}",
            size=count * item_size,
            nullable=count == 0,
        )


def audit_joints(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
    *,
    runtime_headers: DrawableRuntimeHeaders,
) -> None:
    offset = validator.class_header(
        pointer,
        path,
        size=0x40,
        expected_vft=runtime_headers.joints,
    )
    if offset is None:
        return
    rotation_count = validator.u16(offset + 0x30)
    translation_count = validator.u16(offset + 0x32)
    validator.pointer(
        validator.u64(offset + 0x10),
        f"{path}.rotation_limits",
        size=rotation_count * 0xC0,
        nullable=rotation_count == 0,
    )
    validator.pointer(
        validator.u64(offset + 0x18),
        f"{path}.translation_limits",
        size=translation_count * 0x40,
        nullable=translation_count == 0,
    )


__all__ = ["audit_joints", "audit_skeleton"]
