from __future__ import annotations

import dataclasses
from typing import Any

from .shader_enums import YdrShader, coerce_shader_name
from .shaders import (
    ShaderDefinition,
    ShaderLayoutDefinition,
    ShaderLibrary,
    ShaderParameterDefinition,
    load_shader_library,
    resolve_shader_reference,
)


@dataclasses.dataclass(slots=True, frozen=True)
class YdrShaderParameterInfo:
    name: str
    type_name: str
    subtype: str | None = None
    uv_index: int | None = None
    count: int = 1
    hidden: bool = False
    defaults: dict[str, str] = dataclasses.field(default_factory=dict)
    default_value: float | tuple[float, ...] | None = None

    @property
    def is_texture(self) -> bool:
        return self.type_name.lower() == "texture"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type_name": self.type_name,
            "subtype": self.subtype,
            "uv_index": self.uv_index,
            "count": int(self.count),
            "hidden": bool(self.hidden),
            "defaults": dict(self.defaults),
            "default_value": self.default_value,
            "is_texture": self.is_texture,
        }


@dataclasses.dataclass(slots=True, frozen=True)
class YdrShaderLayoutInfo:
    type_name: str
    semantics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_name": self.type_name,
            "semantics": list(self.semantics),
        }


@dataclasses.dataclass(slots=True, frozen=True)
class YdrShaderInfo:
    requested_shader: str
    shader_name: str
    shader_name_hash: int
    resolved_file_name: str | None
    resolved_render_bucket: int | None
    file_names_by_bucket: dict[int, tuple[str, ...]]
    layouts: tuple[YdrShaderLayoutInfo, ...]
    parameters: tuple[YdrShaderParameterInfo, ...]

    @property
    def render_buckets(self) -> tuple[int, ...]:
        return tuple(sorted(int(bucket) for bucket in self.file_names_by_bucket))

    @property
    def texture_parameters(self) -> tuple[YdrShaderParameterInfo, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.is_texture)

    @property
    def numeric_parameters(self) -> tuple[YdrShaderParameterInfo, ...]:
        return tuple(parameter for parameter in self.parameters if not parameter.is_texture)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_shader": self.requested_shader,
            "shader_name": self.shader_name,
            "shader_name_hash": int(self.shader_name_hash),
            "resolved_file_name": self.resolved_file_name,
            "resolved_render_bucket": self.resolved_render_bucket,
            "render_buckets": list(self.render_buckets),
            "file_names_by_bucket": {
                int(bucket): list(file_names)
                for bucket, file_names in sorted(self.file_names_by_bucket.items())
            },
            "layouts": [layout.to_dict() for layout in self.layouts],
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "texture_parameters": [parameter.to_dict() for parameter in self.texture_parameters],
            "numeric_parameters": [parameter.to_dict() for parameter in self.numeric_parameters],
        }


def _parameter_info(definition: ShaderParameterDefinition) -> YdrShaderParameterInfo:
    return YdrShaderParameterInfo(
        name=definition.name,
        type_name=definition.type_name,
        subtype=definition.subtype,
        uv_index=definition.uv_index,
        count=int(definition.count),
        hidden=bool(definition.hidden),
        defaults=dict(definition.defaults),
        default_value=definition.default_value,
    )


def _layout_info(definition: ShaderLayoutDefinition) -> YdrShaderLayoutInfo:
    return YdrShaderLayoutInfo(
        type_name=definition.type_name,
        semantics=tuple(definition.semantics),
    )


def _build_shader_info(
    requested_shader: str,
    shader_definition: ShaderDefinition,
    *,
    resolved_file_name: str | None,
    resolved_render_bucket: int | None,
) -> YdrShaderInfo:
    return YdrShaderInfo(
        requested_shader=requested_shader,
        shader_name=shader_definition.name,
        shader_name_hash=int(shader_definition.name_hash),
        resolved_file_name=resolved_file_name,
        resolved_render_bucket=resolved_render_bucket,
        file_names_by_bucket={int(bucket): tuple(file_names) for bucket, file_names in shader_definition.file_names_by_bucket.items()},
        layouts=tuple(_layout_info(layout) for layout in shader_definition.layouts),
        parameters=tuple(_parameter_info(parameter) for parameter in shader_definition.parameters),
    )


def get_ydr_shader_info(
    shader: str | YdrShader,
    *,
    shader_library: ShaderLibrary | None = None,
) -> YdrShaderInfo:
    active_shader_library = shader_library if shader_library is not None else load_shader_library()
    shader_name = coerce_shader_name(shader)
    if shader_name.lower().endswith(".sps"):
        shader_definition, resolved_file_name, resolved_render_bucket = resolve_shader_reference(shader_name, 0, active_shader_library)
        return _build_shader_info(
            shader_name,
            shader_definition,
            resolved_file_name=resolved_file_name,
            resolved_render_bucket=resolved_render_bucket,
        )

    shader_definition = active_shader_library.resolve_shader(shader_name=shader_name, shader_file_name=shader_name)
    if shader_definition is None:
        raise ValueError(f"Unknown YDR shader '{shader_name}'")
    return _build_shader_info(
        shader_name,
        shader_definition,
        resolved_file_name=None,
        resolved_render_bucket=None,
    )


def _format_parameter(parameter: YdrShaderParameterInfo) -> str:
    suffix: list[str] = [parameter.type_name]
    if parameter.subtype:
        suffix.append(f"subtype={parameter.subtype}")
    if parameter.uv_index is not None:
        suffix.append(f"uv={parameter.uv_index}")
    if int(parameter.count) > 1:
        suffix.append(f"count={parameter.count}")
    if parameter.hidden:
        suffix.append("hidden")
    if parameter.default_value is not None:
        suffix.append(f"default={parameter.default_value}")
    return f"{parameter.name} ({', '.join(suffix)})"


def format_ydr_shader_info(
    shader: str | YdrShader | YdrShaderInfo,
    *,
    shader_library: ShaderLibrary | None = None,
) -> str:
    info = shader if isinstance(shader, YdrShaderInfo) else get_ydr_shader_info(shader, shader_library=shader_library)
    lines: list[str] = [
        f"Shader: {info.shader_name}",
        f"Requested: {info.requested_shader}",
        f"Name Hash: {info.shader_name_hash}",
    ]
    if info.resolved_file_name is not None:
        lines.append(f"Resolved File: {info.resolved_file_name}")
    if info.resolved_render_bucket is not None:
        lines.append(f"Resolved Render Bucket: {info.resolved_render_bucket}")

    lines.append("Render Buckets:")
    for bucket in info.render_buckets:
        file_names = ", ".join(info.file_names_by_bucket[int(bucket)])
        lines.append(f"  [{bucket}] {file_names}")

    lines.append("Layouts:")
    for layout in info.layouts:
        lines.append(f"  - {layout.type_name}: {', '.join(layout.semantics)}")

    lines.append("Texture Parameters:")
    if info.texture_parameters:
        for parameter in info.texture_parameters:
            lines.append(f"  - {_format_parameter(parameter)}")
    else:
        lines.append("  - none")

    lines.append("Numeric Parameters:")
    if info.numeric_parameters:
        for parameter in info.numeric_parameters:
            lines.append(f"  - {_format_parameter(parameter)}")
    else:
        lines.append("  - none")
    return "\n".join(lines)


def print_ydr_shader_info(
    shader: str | YdrShader | YdrShaderInfo,
    *,
    shader_library: ShaderLibrary | None = None,
) -> None:
    print(format_ydr_shader_info(shader, shader_library=shader_library))


__all__ = [
    "YdrShaderInfo",
    "YdrShaderLayoutInfo",
    "YdrShaderParameterInfo",
    "format_ydr_shader_info",
    "get_ydr_shader_info",
    "print_ydr_shader_info",
]
