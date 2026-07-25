from __future__ import annotations

from ..resource_headers import (
    LEGACY_FRAGMENT_DRAWABLE_HEADERS,
    LEGACY_FRAGMENT_TEXTURE_VFTS,
)
from .context import DrawableFixupValidator


def _audit_texture(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
) -> None:
    offset = validator.class_header(
        pointer,
        path,
        size=0x50,
        expected_vft=LEGACY_FRAGMENT_TEXTURE_VFTS,
    )
    if offset is None:
        return
    name = validator.u64(offset + 0x28)
    if name:
        validator.string(name, f"{path}.name")


def _audit_shader(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
) -> None:
    offset = validator.pointer(pointer, path, size=0x30, nullable=False)
    if offset is None:
        return
    parameter_count = validator.u8(offset + 0x10)
    parameter_size = validator.u16(offset + 0x14)
    parameters = validator.u64(offset)
    params_offset = validator.pointer(
        parameters,
        f"{path}.parameters",
        size=max(parameter_size, parameter_count * 16),
        nullable=parameter_count == 0,
    )
    if params_offset is None:
        return
    for index in range(parameter_count):
        entry_offset = params_offset + index * 16
        data_type = validator.u8(entry_offset)
        data_pointer = validator.u64(entry_offset + 8)
        if data_type == 0:
            if data_pointer:
                _audit_texture(
                    validator,
                    data_pointer,
                    f"{path}.parameters[{index}].texture",
                )
        else:
            validator.pointer(
                data_pointer,
                f"{path}.parameters[{index}].value",
                size=data_type * 16,
                nullable=False,
            )


def audit_shader_group(
    validator: DrawableFixupValidator,
    pointer: int,
    path: str,
) -> None:
    offset = validator.class_header(
        pointer,
        path,
        size=0x40,
        expected_vft=LEGACY_FRAGMENT_DRAWABLE_HEADERS.shader_group,
    )
    if offset is None:
        return
    texture_dictionary = validator.u64(offset + 0x08)
    if texture_dictionary:
        validator.pointer(
            texture_dictionary,
            f"{path}.texture_dictionary",
            nullable=False,
        )
    shader_count = validator.u16(offset + 0x18)
    shader_array = validator.u64(offset + 0x10)
    array_offset = validator.pointer(
        shader_array,
        f"{path}.shaders",
        size=shader_count * 8,
        nullable=shader_count == 0,
    )
    if array_offset is None:
        return
    for index in range(shader_count):
        _audit_shader(
            validator,
            validator.u64(array_offset + index * 8),
            f"{path}.shaders[{index}]",
        )


__all__ = ["audit_shader_group"]
