from __future__ import annotations

import dataclasses
from typing import Any

from .gen9 import ShaderGen9Definition, ShaderGen9Library, ShaderGen9ParameterDefinition, load_gen9_shader_library, resolve_gen9_shader_reference
from .gen9_shader_enums import YdrGen9Shader, coerce_gen9_shader_name


@dataclasses.dataclass(slots=True, frozen=True)
class YdrGen9ShaderParameterInfo:
    name: str
    kind: str
    index: int = 0
    legacy_name: str | None = None
    sampler_value: int | None = None
    buffer_index: int | None = None
    param_offset: int | None = None
    param_length: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "index": int(self.index),
            "legacy_name": self.legacy_name,
            "sampler_value": self.sampler_value,
            "buffer_index": self.buffer_index,
            "param_offset": self.param_offset,
            "param_length": self.param_length,
        }


@dataclasses.dataclass(slots=True, frozen=True)
class YdrGen9ShaderInfo:
    requested_shader: str
    shader_name: str
    shader_name_hash: int
    resolved_file_name: str
    resolved_file_name_hash: int
    buffer_sizes: tuple[int, ...]
    parameters: tuple[YdrGen9ShaderParameterInfo, ...]

    @property
    def texture_parameters(self) -> tuple[YdrGen9ShaderParameterInfo, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.kind.lower() == "texture")

    @property
    def sampler_parameters(self) -> tuple[YdrGen9ShaderParameterInfo, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.kind.lower() == "sampler")

    @property
    def cbuffer_parameters(self) -> tuple[YdrGen9ShaderParameterInfo, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.kind.lower() == "cbuffer")

    @property
    def unknown_parameters(self) -> tuple[YdrGen9ShaderParameterInfo, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.kind.lower() == "unknown")

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_shader": self.requested_shader,
            "shader_name": self.shader_name,
            "shader_name_hash": int(self.shader_name_hash),
            "resolved_file_name": self.resolved_file_name,
            "resolved_file_name_hash": int(self.resolved_file_name_hash),
            "buffer_sizes": list(self.buffer_sizes),
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "texture_parameters": [parameter.to_dict() for parameter in self.texture_parameters],
            "sampler_parameters": [parameter.to_dict() for parameter in self.sampler_parameters],
            "cbuffer_parameters": [parameter.to_dict() for parameter in self.cbuffer_parameters],
            "unknown_parameters": [parameter.to_dict() for parameter in self.unknown_parameters],
        }


def _parameter_info(definition: ShaderGen9ParameterDefinition) -> YdrGen9ShaderParameterInfo:
    return YdrGen9ShaderParameterInfo(
        name=definition.name,
        kind=definition.kind,
        index=int(definition.index),
        legacy_name=definition.legacy_name,
        sampler_value=definition.sampler_value,
        buffer_index=definition.buffer_index,
        param_offset=definition.param_offset,
        param_length=definition.param_length,
    )


def _build_shader_info(requested_shader: str, shader_definition: ShaderGen9Definition, *, resolved_file_name: str) -> YdrGen9ShaderInfo:
    return YdrGen9ShaderInfo(
        requested_shader=requested_shader,
        shader_name=shader_definition.name,
        shader_name_hash=int(shader_definition.name_hash),
        resolved_file_name=resolved_file_name,
        resolved_file_name_hash=int(shader_definition.file_name_hash),
        buffer_sizes=tuple(int(size) for size in shader_definition.buffer_sizes),
        parameters=tuple(_parameter_info(parameter) for parameter in shader_definition.parameters),
    )


def get_ydr_gen9_shader_info(
    shader: str | YdrGen9Shader,
    *,
    shader_library: ShaderGen9Library | None = None,
) -> YdrGen9ShaderInfo:
    active_shader_library = shader_library if shader_library is not None else load_gen9_shader_library()
    shader_name = coerce_gen9_shader_name(shader)
    shader_definition, resolved_file_name = resolve_gen9_shader_reference(shader_name, active_shader_library)
    return _build_shader_info(shader_name, shader_definition, resolved_file_name=resolved_file_name)


def _format_parameter(parameter: YdrGen9ShaderParameterInfo) -> str:
    suffix: list[str] = [parameter.kind]
    if parameter.legacy_name:
        suffix.append(f"legacy={parameter.legacy_name}")
    if parameter.kind.lower() in {"texture", "sampler"}:
        suffix.append(f"index={parameter.index}")
    if parameter.sampler_value is not None:
        suffix.append(f"sampler={parameter.sampler_value}")
    if parameter.buffer_index is not None:
        suffix.append(f"buffer={parameter.buffer_index}")
    if parameter.param_offset is not None:
        suffix.append(f"offset={parameter.param_offset}")
    if parameter.param_length is not None:
        suffix.append(f"length={parameter.param_length}")
    return f"{parameter.name} ({', '.join(suffix)})"


def format_ydr_gen9_shader_info(
    shader: str | YdrGen9Shader | YdrGen9ShaderInfo,
    *,
    shader_library: ShaderGen9Library | None = None,
) -> str:
    info = shader if isinstance(shader, YdrGen9ShaderInfo) else get_ydr_gen9_shader_info(shader, shader_library=shader_library)
    lines: list[str] = [
        f"Gen9 Shader: {info.shader_name}",
        f"Requested: {info.requested_shader}",
        f"Name Hash: {info.shader_name_hash}",
        f"Resolved File: {info.resolved_file_name}",
        f"Resolved File Hash: {info.resolved_file_name_hash}",
        f"Buffer Sizes: {', '.join(str(size) for size in info.buffer_sizes) if info.buffer_sizes else 'none'}",
    ]

    lines.append("Texture Parameters:")
    if info.texture_parameters:
        for parameter in info.texture_parameters:
            lines.append(f"  - {_format_parameter(parameter)}")
    else:
        lines.append("  - none")

    lines.append("Sampler Parameters:")
    if info.sampler_parameters:
        for parameter in info.sampler_parameters:
            lines.append(f"  - {_format_parameter(parameter)}")
    else:
        lines.append("  - none")

    lines.append("CBuffer Parameters:")
    if info.cbuffer_parameters:
        for parameter in info.cbuffer_parameters:
            lines.append(f"  - {_format_parameter(parameter)}")
    else:
        lines.append("  - none")

    lines.append("Unknown Parameters:")
    if info.unknown_parameters:
        for parameter in info.unknown_parameters:
            lines.append(f"  - {_format_parameter(parameter)}")
    else:
        lines.append("  - none")
    return "\n".join(lines)


def print_ydr_gen9_shader_info(
    shader: str | YdrGen9Shader | YdrGen9ShaderInfo,
    *,
    shader_library: ShaderGen9Library | None = None,
) -> None:
    print(format_ydr_gen9_shader_info(shader, shader_library=shader_library))


__all__ = [
    "YdrGen9ShaderInfo",
    "YdrGen9ShaderParameterInfo",
    "format_ydr_gen9_shader_info",
    "get_ydr_gen9_shader_info",
    "print_ydr_gen9_shader_info",
]
