from __future__ import annotations

from fivefury import (
    YdrGen9Shader,
    YdrShader,
    format_ydr_gen9_shader_info,
    format_ydr_shader_info,
    get_ydr_gen9_shader_info,
    get_ydr_shader_info,
)
from fivefury.ydr.gen9 import (
    ShaderParamTypeG9,
    build_runtime_gen9_shader_definition,
    read_gen9_shader_library,
)


def test_get_ydr_shader_info_for_shader_file_enum() -> None:
    info = get_ydr_shader_info(YdrShader.SPEC)

    assert info.requested_shader == "spec.sps"
    assert info.shader_name == "spec"
    assert info.resolved_file_name == "spec.sps"
    assert info.resolved_render_bucket == 0
    assert info.file_names_by_bucket[0] == ("spec.sps", "gta_spec.sps")
    assert [parameter.name for parameter in info.texture_parameters] == ["DiffuseSampler", "SpecSampler"]


def test_format_ydr_shader_info_lists_bucket_and_parameters() -> None:
    formatted = format_ydr_shader_info(YdrShader.NORMAL_SPEC_CUTOUT)

    assert "Shader: normal_spec" in formatted
    assert "Resolved File: normal_spec_cutout.sps" in formatted
    assert "Resolved Render Bucket: 3" in formatted
    assert "[3] normal_spec_cutout.sps, normal_spec_screendooralpha.sps" in formatted
    assert "DiffuseSampler (Texture, uv=0)" in formatted
    assert "SpecSampler (Texture, uv=0)" in formatted


def test_get_ydr_gen9_shader_info_for_shader_file_enum() -> None:
    info = get_ydr_gen9_shader_info(YdrGen9Shader.SPEC)

    assert info.requested_shader == "spec.sps"
    assert info.shader_name == "spec"
    assert info.resolved_file_name == "spec.sps"
    assert info.buffer_sizes == (32, 48)
    assert [parameter.name for parameter in info.texture_parameters] == ["DiffuseTex", "depthbuffertex", "SpecularTex"]


def test_format_ydr_gen9_shader_info_lists_buffers_and_parameters() -> None:
    formatted = format_ydr_gen9_shader_info(YdrGen9Shader.NORMAL_SPEC)

    assert "Gen9 Shader: normal_spec" in formatted
    assert "Resolved File: normal_spec.sps" in formatted
    assert "Buffer Sizes:" in formatted
    assert "DiffuseTex (Texture, legacy=DiffuseSampler, index=0)" in formatted
    assert "SpecularTex (Texture, legacy=SpecSampler, index=3)" in formatted


def test_gen9_literal_parameter_hashes_and_glass_sampler_layout() -> None:
    shader = read_gen9_shader_library().require_shader("glass_breakable")

    assert [
        (parameter.name_hash, parameter.index, parameter.sampler_value)
        for parameter in shader.sampler_parameters
    ] == [
        (0x184D4D47, 0, 0),
        (0xE44690BB, 1, 5),
        (0xF1FE2B71, 2, 1),
        (0x24C5AB07, 3, 2),
        (0x49C32B64, 4, 4),
    ]
    assert shader.require_parameter("specsampler").name_hash == 0xE44690BB
    assert shader.require_parameter("bumpsampler").name_hash == 0x49C32B64


def test_gen9_runtime_layout_preserves_native_hashes_and_resolves_aliases() -> None:
    library = read_gen9_shader_library()
    base = library.require_shader("normal_spec")
    runtime = build_runtime_gen9_shader_definition(
        base,
        (
            (0xE44690BB, int(ShaderParamTypeG9.SAMPLER), 1, 0, 0),
            (0x49C32B64, int(ShaderParamTypeG9.SAMPLER), 5, 0, 0),
        ),
        buffer_sizes=(48,),
        sampler_values=bytes((1, 5, 6, 2, 3, 4)),
    )

    specular = runtime.require_parameter("specsampler")
    bump = runtime.require_parameter("bumpsampler")
    assert (specular.name_hash, specular.index, specular.sampler_value) == (0xE44690BB, 1, 5)
    assert (bump.name_hash, bump.index, bump.sampler_value) == (0x49C32B64, 5, 4)
    assert specular.pack_info() == bytes.fromhex("BB9046E406000000")
    assert library.require_shader("default").require_parameter(
        0xBABE4DBA
    ).name == "diffusesampler"
    assert library.require_shader("normal_spec_tnt").require_parameter(
        0xE44690BB
    ).name == "specsampler"
