from __future__ import annotations

from ..resource_headers import DrawableRuntimeHeaders
from .context import DrawableFixupValidator
from .geometry import audit_lod
from .materials import audit_shader_group
from .skeleton import audit_joints, audit_skeleton


def audit_fragment_drawable_fixups(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
    *,
    require_shader_group: bool = True,
    runtime_headers: DrawableRuntimeHeaders,
    enhanced: bool,
) -> None:
    root = validator.class_header(
        pointer,
        path,
        size=0x150,
        expected_vft=runtime_headers.drawable,
    )
    if root is None:
        return
    shader_group = validator.u64(root + 0x10)
    if shader_group:
        audit_shader_group(
            validator,
            shader_group,
            f"{path}.shader_group",
            runtime_headers=runtime_headers,
            enhanced=enhanced,
        )

    skeleton = validator.u64(root + 0x18)
    if skeleton:
        audit_skeleton(
            validator,
            skeleton,
            f"{path}.skeleton",
            runtime_headers=runtime_headers,
        )
    has_models = False
    for field_offset, label in (
        (0x50, "high"),
        (0x58, "medium"),
        (0x60, "low"),
        (0x68, "very_low"),
    ):
        lod = validator.u64(root + field_offset)
        if lod:
            has_models |= audit_lod(
                validator,
                lod,
                f"{path}.lods.{label}",
                runtime_headers=runtime_headers,
                enhanced=enhanced,
            )
    if not shader_group and require_shader_group and has_models:
        validator.error(f"{path}.shader_group", "required resource pointer is null")
    joints = validator.u64(root + 0x90)
    if joints:
        audit_joints(
            validator,
            joints,
            f"{path}.joints",
            runtime_headers=runtime_headers,
        )
    model_block = validator.u64(root + 0xA0)
    if model_block:
        validator.pointer(model_block, f"{path}.model_block", nullable=False)

    validator.pointer(
        validator.u64(root + 0xF0),
        f"{path}.bound",
    )
    bounds_count = validator.u16(root + 0x100)
    bounds_capacity = validator.u16(root + 0x102)
    active_bound_count = validator.u16(root + 0x110)
    if bounds_count > bounds_capacity:
        validator.error(
            f"{path}.extra_bounds",
            f"count {bounds_count} exceeds capacity {bounds_capacity}",
        )
    if active_bound_count > bounds_count:
        validator.error(
            f"{path}.extra_bounds",
            f"active count {active_bound_count} exceeds array count {bounds_count}",
        )
    bounds_array = validator.pointer(
        validator.u64(root + 0xF8),
        f"{path}.extra_bounds",
        size=bounds_count * 8,
        nullable=bounds_count == 0,
    )
    if bounds_array is not None:
        for index in range(bounds_count):
            validator.pointer(
                validator.u64(bounds_array + index * 8),
                f"{path}.extra_bounds[{index}]",
            )
    validator.pointer(
        validator.u64(root + 0x108),
        f"{path}.extra_bound_matrices",
        size=active_bound_count * 64,
        nullable=active_bound_count == 0,
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


__all__ = ["audit_fragment_drawable_fixups"]
