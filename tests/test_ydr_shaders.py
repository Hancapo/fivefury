from __future__ import annotations

from fivefury import (
    YdrGen9Shader,
    YdrShader,
    adapt_shader_to_gen9,
    format_ydr_gen9_shader_info,
    format_ydr_shader_info,
    get_ydr_gen9_shader_info,
    get_ydr_shader_info,
)
from fivefury.hashing import jenk_hash
from fivefury.ydr.gen9 import (
    ShaderParamTypeG9,
    build_runtime_gen9_shader_definition,
    read_gen9_shader_library,
)
from fivefury.ydr.gen9_material_presets import GEN9_MATERIAL_PARAMETERS
from fivefury.ydr.gen9_semantics import GEN9_RESOLVED_PARAMETER_NAMES
from fivefury.ydr.write_materials import _coerce_gen9_cbuffer_bytes

_CANONICAL_CONVERSION_SHADERS = (
    "alpha.sps",
    "cable.sps",
    "cutout.sps",
    "cutout_fence.sps",
    "decal.sps",
    "decal_amb_only.sps",
    "decal_dirt.sps",
    "decal_glue.sps",
    "decal_normal_only.sps",
    "default.sps",
    "emissive.sps",
    "emissive_alpha.sps",
    "emissivenight.sps",
    "emissivenight_alpha.sps",
    "emissivestrong.sps",
    "emissivestrong_alpha.sps",
    "glass.sps",
    "glass_emissive.sps",
    "glass_emissive_alpha.sps",
    "glass_emissivenight.sps",
    "glass_emissivenight_alpha.sps",
    "glass_normal_spec_reflect.sps",
    "glass_reflect.sps",
    "glass_spec.sps",
    "normal.sps",
    "normal_alpha.sps",
    "normal_cubemap_reflect.sps",
    "normal_cutout.sps",
    "normal_decal.sps",
    "normal_reflect.sps",
    "normal_reflect_alpha.sps",
    "normal_reflect_decal.sps",
    "normal_spec.sps",
    "normal_spec_alpha.sps",
    "normal_spec_cubemap_reflect.sps",
    "normal_spec_decal.sps",
    "normal_spec_emissive.sps",
    "normal_spec_reflect.sps",
    "normal_spec_reflect_alpha.sps",
    "normal_spec_reflect_decal.sps",
    "normal_spec_reflect_emissivenight.sps",
    "normal_spec_reflect_emissivenight_alpha.sps",
    "parallax.sps",
    "parallax_specmap.sps",
    "ped_default.sps",
    "ped_default_cutout.sps",
    "ped_default_enveff.sps",
    "radar.sps",
    "reflect.sps",
    "reflect_alpha.sps",
    "reflect_decal.sps",
    "spec.sps",
    "spec_alpha.sps",
    "spec_const.sps",
    "spec_decal.sps",
    "spec_reflect.sps",
    "spec_reflect_alpha.sps",
    "spec_reflect_decal.sps",
    "terrain_cb_4lyr_2tex.sps",
    "terrain_cb_w_4lyr_2tex_blend_pxm_spm.sps",
    "trees.sps",
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


def test_gen9_resolved_semantics_and_glass_sampler_layout() -> None:
    shader = read_gen9_shader_library().require_shader("glass_breakable")

    assert [
        (parameter.semantic_hash, parameter.index, parameter.sampler_value)
        for parameter in shader.sampler_parameters
    ] == [
        (0x184D4D47, 0, 0),
        (0xE44690BB, 1, 5),
        (0xF1FE2B71, 2, 1),
        (0x24C5AB07, 3, 2),
        (0x49C32B64, 4, 4),
    ]
    assert shader.require_parameter("trilinearwrap").semantic_hash == 0xE44690BB
    assert shader.require_parameter("anisotropic4xwrap").semantic_hash == 0x49C32B64


def test_gen9_runtime_layout_preserves_and_resolves_semantic_hashes() -> None:
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
        shader_library=library,
    )

    trilinear = runtime.require_parameter("trilinearwrap")
    anisotropic = runtime.require_parameter("anisotropic4xwrap")
    assert (trilinear.semantic_hash, trilinear.index, trilinear.sampler_value) == (0xE44690BB, 1, 5)
    assert (anisotropic.semantic_hash, anisotropic.index, anisotropic.sampler_value) == (0x49C32B64, 5, 4)
    assert trilinear.pack_info() == bytes.fromhex("BB9046E406000000")
    assert library.require_shader("default").get_parameter(0xBABE4DBA) is None


def test_all_canonical_conversion_shaders_adapt_to_native_gen9() -> None:
    adaptations = [adapt_shader_to_gen9(shader) for shader in _CANONICAL_CONVERSION_SHADERS]

    assert len(adaptations) == 61
    assert all(adaptation.gen9_definition.file_name.endswith(".sps") for adaptation in adaptations)


def test_gen9_environment_texture_names_preserve_legacy_binding() -> None:
    library = read_gen9_shader_library()

    for shader_name in ("glass", "normal_reflect", "normal_spec_reflect", "reflect", "spec_reflect"):
        parameter = library.require_shader(shader_name).require_parameter("EnvironmentSampler")
        assert parameter.name == "EnvironmentTex2D"
        assert parameter.semantic_hash == 0x6572309A

    for shader_name in ("normal_cubemap_reflect", "normal_spec_cubemap_reflect"):
        parameter = library.require_shader(shader_name).require_parameter("EnvironmentSampler")
        assert parameter.name == "EnvironmentTex"
        assert parameter.semantic_hash == 0x757E2A27


def test_gen9_library_exposes_material_preset_parameters() -> None:
    parameter = read_gen9_shader_library().require_shader("glass_emissive").require_parameter("hardalphablend")

    assert parameter.default_value == (1.0, 0.0, 0.0, 0.0)

    info = get_ydr_gen9_shader_info("glass_emissive.sps")
    hard_alpha = next(parameter for parameter in info.cbuffer_parameters if parameter.name == "hardalphablend")
    assert hard_alpha.default_value == (1.0, 0.0, 0.0, 0.0)
    assert "default=(1.0, 0.0, 0.0, 0.0)" in format_ydr_gen9_shader_info(info)


def test_gen9_material_presets_resolve_to_declared_cbuffers() -> None:
    library = read_gen9_shader_library()

    assert len(GEN9_MATERIAL_PARAMETERS) == 112
    assert sum(len(parameters) for parameters in GEN9_MATERIAL_PARAMETERS.values()) == 167

    for shader_name, preset_parameters in GEN9_MATERIAL_PARAMETERS.items():
        shader = library.require_shader(shader_name)
        for semantic_hash, expected in preset_parameters.items():
            parameter = shader.require_parameter(semantic_hash)
            assert parameter.kind_enum is ShaderParamTypeG9.CBUFFER
            assert parameter.default_value == expected
            assert len(
                _coerce_gen9_cbuffer_bytes(expected, parameter=parameter)
            ) == int(parameter.param_length)


def test_gen9_resolved_parameter_names_preserve_serialized_hashes() -> None:
    library = read_gen9_shader_library()

    for semantic_hash, expected_name in GEN9_RESOLVED_PARAMETER_NAMES.items():
        assert int(jenk_hash(expected_name)) == semantic_hash
        parameter = library.get_parameter(semantic_hash)
        assert parameter is not None
        assert parameter.name == expected_name
        assert parameter.semantic_hash == semantic_hash
        assert parameter.pack_info()[:4] == semantic_hash.to_bytes(4, "little")
