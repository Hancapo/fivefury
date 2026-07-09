from __future__ import annotations

from ..drawable import ShaderDefinition, ShaderLibrary, ShaderParameterDefinition


def _parameter(name: str, type_name: str) -> ShaderParameterDefinition:
    return ShaderParameterDefinition(name=name, type_name=type_name)


# PS3 material effects present in the retail CDR corpus but absent from the PC
# legacy shader catalog. The names and declarations match the console shader
# sources; this table is intentionally independent from fivefury.ydr.
_PS3_SHADER_DEFINITIONS = (
    ShaderDefinition(
        name="trees_lod2d",
        file_names_by_bucket={3: ("trees_lod2d.sps",)},
        parameters=(
            _parameter("DiffuseSampler", "Texture"),
            _parameter("UseTreeNormals", "float"),
            _parameter("treeLod2Normal", "float3"),
            _parameter("treeLod2Params", "float4"),
            _parameter("RESERVE_VS_CONST_c255", "float4"),
            _parameter("RESERVE_VS_CONST_c254", "float4"),
            _parameter("RESERVE_VS_CONST_c253", "float4"),
        ),
    ),
)

_PS3_SHADER_LIBRARY = ShaderLibrary(_PS3_SHADER_DEFINITIONS)

# These declarations are emitted by PS3 shaders but are not represented in the
# legacy PC preset metadata. They may also occur in otherwise shared effects.
_PS3_PARAMETER_DEFINITIONS = {
    parameter.name_hash: parameter
    for parameter in (
        _parameter("RESERVE_VS_CONST_c255", "float4"),
        _parameter("RESERVE_VS_CONST_c254", "float4"),
        _parameter("RESERVE_VS_CONST_c253", "float4"),
        _parameter("MirrorReflectionSampler", "Texture"),
        _parameter("gCSMShaderVars_deferred", "float4"),
    )
}


def get_cdr_shader_definition(shader_hash: int) -> ShaderDefinition | None:
    return _PS3_SHADER_LIBRARY.get_shader(int(shader_hash))


def get_cdr_parameter_definition(name_hash: int) -> ShaderParameterDefinition | None:
    return _PS3_PARAMETER_DEFINITIONS.get(int(name_hash))


def resolve_cdr_shader_file_name(
    shader_hash: int,
    shader_file_hash: int,
    shader_library: ShaderLibrary,
) -> str | None:
    ps3_definition = get_cdr_shader_definition(shader_hash)
    if ps3_definition is not None and (file_name := ps3_definition.get_file_name(shader_file_hash)) is not None:
        return file_name

    return shader_library.get_file_name(int(shader_file_hash))


__all__ = [
    "get_cdr_parameter_definition",
    "get_cdr_shader_definition",
    "resolve_cdr_shader_file_name",
]
