from __future__ import annotations

from ..resource_headers import LEGACY_FRAGMENT_DRAWABLE_HEADERS
from .context import DrawableFixupValidator


def _audit_vertex_buffer(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
) -> None:
    offset = validator.class_header(
        pointer,
        path,
        size=0x80,
        expected_vft=LEGACY_FRAGMENT_DRAWABLE_HEADERS.vertex_buffer,
    )
    if offset is None:
        return
    stride = validator.u16(offset + 0x08)
    count = validator.u32(offset + 0x18)
    data_size = stride * count
    for field_offset, label in ((0x10, "data"), (0x20, "lock_data")):
        data_pointer = validator.u64(offset + field_offset)
        if data_pointer:
            validator.pointer(
                data_pointer,
                f"{path}.{label}",
                size=data_size,
                section=None,
                nullable=False,
            )
    validator.pointer(
        validator.u64(offset + 0x30),
        f"{path}.declaration",
        size=0x10,
        nullable=False,
    )


def _audit_index_buffer(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
) -> None:
    offset = validator.class_header(
        pointer,
        path,
        size=0x60,
        expected_vft=LEGACY_FRAGMENT_DRAWABLE_HEADERS.index_buffer,
    )
    if offset is None:
        return
    count = validator.u32(offset + 0x08)
    validator.pointer(
        validator.u64(offset + 0x10),
        f"{path}.data",
        size=count * 2,
        section=None,
        nullable=count == 0,
    )


def _audit_geometry(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
) -> None:
    offset = validator.class_header(
        pointer,
        path,
        size=0x98,
        expected_vft=LEGACY_FRAGMENT_DRAWABLE_HEADERS.geometry,
    )
    if offset is None:
        return
    _audit_vertex_buffer(
        validator,
        validator.u64(offset + 0x18),
        f"{path}.vertex_buffer",
    )
    _audit_index_buffer(
        validator,
        validator.u64(offset + 0x38),
        f"{path}.index_buffer",
    )
    bone_count = validator.u16(offset + 0x72)
    validator.pointer(
        validator.u64(offset + 0x68),
        f"{path}.bone_ids",
        size=bone_count * 2,
        nullable=bone_count == 0,
    )
    vertex_count = validator.u16(offset + 0x60)
    stride = validator.u16(offset + 0x70)
    vertex_data = validator.u64(offset + 0x78)
    if vertex_data:
        validator.pointer(
            vertex_data,
            f"{path}.vertex_data",
            size=vertex_count * stride,
            section=None,
            nullable=False,
        )


def _audit_model(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
) -> None:
    offset = validator.class_header(
        pointer,
        path,
        size=0x30,
        expected_vft=LEGACY_FRAGMENT_DRAWABLE_HEADERS.model,
    )
    if offset is None:
        return
    geometry_count = validator.u16(offset + 0x10)
    geometries_pointer = validator.u64(offset + 0x08)
    geometries_offset = validator.pointer(
        geometries_pointer,
        f"{path}.geometries",
        size=geometry_count * 8,
        nullable=geometry_count == 0,
    )
    bounds_count = geometry_count if geometry_count <= 1 else geometry_count + 1
    validator.pointer(
        validator.u64(offset + 0x18),
        f"{path}.bounds",
        size=bounds_count * 32,
        nullable=bounds_count == 0,
    )
    validator.pointer(
        validator.u64(offset + 0x20),
        f"{path}.shader_mapping",
        size=geometry_count * 2,
        nullable=geometry_count == 0,
    )
    if geometries_offset is None:
        return
    for index in range(geometry_count):
        _audit_geometry(
            validator,
            validator.u64(geometries_offset + index * 8),
            f"{path}.geometries[{index}]",
        )


def audit_lod(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
) -> None:
    offset = validator.pointer(pointer, path, size=0x10, nullable=False)
    if offset is None:
        return
    model_count = validator.u16(offset + 0x08)
    models_pointer = validator.u64(offset)
    models_offset = validator.pointer(
        models_pointer,
        f"{path}.models",
        size=model_count * 8,
        nullable=model_count == 0,
    )
    if models_offset is None:
        return
    for index in range(model_count):
        _audit_model(
            validator,
            validator.u64(models_offset + index * 8),
            f"{path}.models[{index}]",
        )


__all__ = ["audit_lod"]
