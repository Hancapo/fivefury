from __future__ import annotations

from ..resource_headers import LEGACY_FRAGMENT_DRAWABLE_HEADERS
from .context import DrawableFixupValidator
from .geometry import audit_lod
from .materials import audit_shader_group
from .skeleton import audit_joints, audit_skeleton


def audit_legacy_fragment_drawable_fixups(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
    *,
    require_shader_group: bool = True,
) -> None:
    root = validator.class_header(
        pointer,
        path,
        size=0x150,
        expected_vft=LEGACY_FRAGMENT_DRAWABLE_HEADERS.drawable,
    )
    if root is None:
        return
    shader_group = validator.u64(root + 0x10)
    if shader_group:
        audit_shader_group(
            validator,
            shader_group,
            f"{path}.shader_group",
        )
    elif require_shader_group:
        validator.error(f"{path}.shader_group", "required resource pointer is null")

    skeleton = validator.u64(root + 0x18)
    if skeleton:
        audit_skeleton(validator, skeleton, f"{path}.skeleton")
    for field_offset, label in (
        (0x50, "high"),
        (0x58, "medium"),
        (0x60, "low"),
        (0x68, "very_low"),
    ):
        lod = validator.u64(root + field_offset)
        if lod:
            audit_lod(validator, lod, f"{path}.lods.{label}")
    joints = validator.u64(root + 0x90)
    if joints:
        audit_joints(validator, joints, f"{path}.joints")
    model_block = validator.u64(root + 0xA0)
    if model_block:
        validator.pointer(model_block, f"{path}.model_block", nullable=False)

    validator.pointer(
        validator.u64(root + 0xF0),
        f"{path}.bound",
    )
    indices_count = validator.u16(root + 0x100)
    matrices_capacity = validator.u16(root + 0x102)
    matrix_count = validator.u16(root + 0x110)
    if matrix_count > matrices_capacity:
        validator.error(
            f"{path}.extra_bound_matrices",
            f"count {matrix_count} exceeds capacity {matrices_capacity}",
        )
    validator.pointer(
        validator.u64(root + 0xF8),
        f"{path}.extra_bound_indices",
        size=indices_count * 8,
        nullable=indices_count == 0,
    )
    validator.pointer(
        validator.u64(root + 0x108),
        f"{path}.extra_bound_matrices",
        size=matrices_capacity * 64,
        nullable=matrices_capacity == 0,
    )
    for field_offset, label in (
        (0x118, "locators"),
        (0x120, "animations"),
        (0x128, "cloned_shader_group"),
    ):
        nested = validator.u64(root + field_offset)
        if nested:
            validator.pointer(nested, f"{path}.{label}", nullable=False)
    name = validator.u64(root + 0x130)
    if name:
        validator.string(name, f"{path}.skeleton_type_name")


__all__ = ["audit_legacy_fragment_drawable_fixups"]
