from __future__ import annotations

from ..drawable.shaders import (
    ShaderDefinition,
    ShaderLayoutDefinition,
    ShaderLibrary,
    ShaderParameterDefinition,
    load_shader_library,
    read_shader_library,
)
from .shader_enums import YdrShader, coerce_shader_name


def resolve_shader_reference(
    shader_value: str | YdrShader,
    render_bucket: int,
    shader_library: ShaderLibrary,
) -> tuple[ShaderDefinition, str, int]:
    shader_name = coerce_shader_name(shader_value)
    shader_definition = shader_library.resolve_shader(shader_name=shader_name, shader_file_name=shader_name)
    if shader_definition is None:
        raise ValueError(f"Unknown YDR shader '{shader_name}'")

    if shader_name.lower().endswith(".sps"):
        lowered = shader_name.lower()
        for bucket, file_names in shader_definition.file_names_by_bucket.items():
            for file_name in file_names:
                if file_name.lower() == lowered:
                    return shader_definition, file_name, int(bucket)
        raise ValueError(f"Shader file '{shader_name}' is not registered in shader library")

    shader_file_name = shader_definition.pick_file_name(render_bucket)
    if shader_file_name is None:
        raise ValueError(f"Shader '{shader_definition.name}' has no file for render bucket {render_bucket}")
    return shader_definition, shader_file_name, int(render_bucket)


__all__ = [
    "ShaderDefinition",
    "ShaderLayoutDefinition",
    "ShaderLibrary",
    "ShaderParameterDefinition",
    "YdrShader",
    "coerce_shader_name",
    "load_shader_library",
    "read_shader_library",
    "resolve_shader_reference",
]
