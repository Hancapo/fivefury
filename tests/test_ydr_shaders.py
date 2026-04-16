from __future__ import annotations

from fivefury import YdrShader, format_ydr_shader_info, get_ydr_shader_info


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
