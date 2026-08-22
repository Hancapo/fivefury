from __future__ import annotations

import struct
from pathlib import Path

import numpy
import pytest
import trimesh
from trimesh.visual.material import MultiMaterial, SimpleMaterial
from trimesh.visual.texture import TextureVisuals

from fivefury import (
    BoundSphere,
    BoundType,
    DiagnosticSeverity,
    GameTarget,
    Quaternion,
    Texture,
    TextureFormat,
    Vector2,
    Vector3,
    Ydr,
    YdrBone,
    YdrBoneFlagName,
    YdrBoneFlags,
    YdrBuild,
    YdrGen9Shader,
    YdrJoints,
    YdrLight,
    YdrLightType,
    YdrLod,
    YdrMaterialInput,
    YdrMesh,
    YdrMeshInput,
    YdrModel,
    YdrModelInput,
    YdrRenderMask,
    YdrShader,
    YdrSkeleton,
    YdrSkeletonBinding,
    Ytd,
    calculate_bone_tag,
    calculate_skeleton_unknown_hashes,
    create_ydr,
    read_trimesh_scene,
    read_ydr,
    skeleton_bone_flag_names,
    trimesh_to_ydr,
)
from fivefury.resource import split_rsc7_sections
from fivefury.ydr.gen9 import (
    ShaderGen9ParameterDefinition,
    decode_gen9_vertex_declaration,
)
from fivefury.ydr.resource_headers import GEN9_DRAWABLE_HEADERS
from fivefury.ydr.write_materials import _coerce_gen9_cbuffer_bytes
from tests.helpers import configured_path, reference_root

_TEXTURE_BASE_VFT = 0x40617568

_LEGACY_GEN9_ADAPTATION_CASES = (
    ("alpha.sps", "default.sps", 1),
    ("cutout.sps", "default.sps", 3),
    ("emissive_alpha.sps", "emissive.sps", 1),
    ("emissivenight_alpha.sps", "emissivenight.sps", 1),
    ("emissivestrong_alpha.sps", "emissivestrong.sps", 1),
    ("glass_emissive_alpha.sps", "glass_emissive.sps", 1),
    ("glass_emissivenight_alpha.sps", "glass_emissivenight.sps", 1),
    ("normal_alpha.sps", "normal.sps", 1),
    ("normal_cutout.sps", "normal.sps", 3),
    ("normal_reflect_alpha.sps", "normal_reflect.sps", 1),
    ("normal_spec_alpha.sps", "normal_spec.sps", 1),
    ("normal_spec_reflect_alpha.sps", "normal_spec_reflect.sps", 1),
    ("normal_spec_reflect_emissivenight_alpha.sps", "normal_spec_reflect_emissivenight.sps", 1),
    ("ped_default_cutout.sps", "ped_default.sps", 3),
    ("reflect_alpha.sps", "reflect.sps", 1),
    ("spec_alpha.sps", "spec.sps", 1),
    ("spec_const.sps", "default_spec.sps", 0),
    ("spec_reflect_alpha.sps", "spec_reflect.sps", 1),
)


def test_gen9_cbuffer_accepts_exact_flat_multi_vector_values() -> None:
    parameter = ShaderGen9ParameterDefinition(
        name='bloodzoneadjust',
        kind='CBuffer',
        param_length=96,
    )
    values = tuple(float(index) for index in range(24))

    payload = _coerce_gen9_cbuffer_bytes(values, parameter=parameter)

    assert len(payload) == 96
    assert payload == struct.pack('<24f', *values)

_GEN9_ENVIRONMENT_SHADER_FAMILIES = (
    "spec_reflect.sps",
    "reflect.sps",
    "glass.sps",
    "normal_spec_reflect.sps",
    "normal_reflect.sps",
    "glass_emissivenight.sps",
    "glass_reflect.sps",
    "glass_emissive.sps",
    "reflect_decal.sps",
    "glass_normal_spec_reflect.sps",
    "spec_reflect_decal.sps",
    "normal_spec_reflect_decal.sps",
    "normal_reflect_decal.sps",
)


def _triangle_mesh(material: str = "default") -> YdrMeshInput:
    return YdrMeshInput(
        positions=[
            Vector3(),
            Vector3(1.0, 0.0, 0.0),
            Vector3(0.0, 1.0, 0.0),
        ],
        indices=[0, 1, 2],
        material=material,
        texcoords=[
            [
                Vector2(),
                Vector2(1.0, 0.0),
                Vector2(0.0, 1.0),
            ]
        ],
    )


def _offset_triangle_mesh(offset_x: float, material: str = "default") -> YdrMeshInput:
    return YdrMeshInput(
        positions=[
            Vector3(offset_x, 0.0, 0.0),
            Vector3(1.0 + offset_x, 0.0, 0.0),
            Vector3(offset_x, 1.0, 0.0),
        ],
        indices=[0, 1, 2],
        material=material,
        texcoords=[
            [
                Vector2(),
                Vector2(1.0, 0.0),
                Vector2(0.0, 1.0),
            ]
        ],
    )


def _virtual_to_offset(pointer: int) -> int:
    return int(pointer) - 0x50000000


def _first_model_offsets(resource_bytes: bytes) -> tuple[bytes, int, int]:
    _header, system_data, _graphics_data = split_rsc7_sections(resource_bytes)
    model_list_off = _virtual_to_offset(int.from_bytes(system_data[0xA0:0xA8], "little"))
    model_off = _virtual_to_offset(int.from_bytes(system_data[model_list_off + 0x10 : model_list_off + 0x18], "little"))
    geometry_ptrs_off = _virtual_to_offset(int.from_bytes(system_data[model_off + 0x08 : model_off + 0x10], "little"))
    geometry_off = _virtual_to_offset(int.from_bytes(system_data[geometry_ptrs_off : geometry_ptrs_off + 0x08], "little"))
    return system_data, model_off, geometry_off


def _first_shader_offsets(resource_bytes: bytes) -> tuple[bytes, int, int]:
    _header, system_data, _graphics_data = split_rsc7_sections(resource_bytes)
    shader_group_off = _virtual_to_offset(int.from_bytes(system_data[0x10:0x18], "little"))
    shader_ptrs_off = _virtual_to_offset(int.from_bytes(system_data[shader_group_off + 0x10 : shader_group_off + 0x18], "little"))
    shader_off = _virtual_to_offset(int.from_bytes(system_data[shader_ptrs_off : shader_ptrs_off + 0x08], "little"))
    params_off = _virtual_to_offset(int.from_bytes(system_data[shader_off + 0x00 : shader_off + 0x08], "little"))
    return system_data, shader_off, params_off


def _first_gen9_shader_offsets(resource_bytes: bytes) -> tuple[bytes, int, int, int]:
    _header, system_data, _graphics_data = split_rsc7_sections(resource_bytes)
    shader_group_off = _virtual_to_offset(int.from_bytes(system_data[0x10:0x18], "little"))
    shader_ptrs_off = _virtual_to_offset(int.from_bytes(system_data[shader_group_off + 0x10 : shader_group_off + 0x18], "little"))
    shader_off = _virtual_to_offset(int.from_bytes(system_data[shader_ptrs_off : shader_ptrs_off + 0x08], "little"))
    params_off = _virtual_to_offset(int.from_bytes(system_data[shader_off + 0x08 : shader_off + 0x10], "little"))
    infos_off = _virtual_to_offset(int.from_bytes(system_data[shader_off + 0x20 : shader_off + 0x28], "little"))
    return system_data, shader_off, params_off, infos_off


def _embedded_texture_dictionary_offset(resource_bytes: bytes) -> tuple[bytes, int]:
    _header, system_data, _graphics_data = split_rsc7_sections(resource_bytes)
    shader_group_off = _virtual_to_offset(
        int.from_bytes(system_data[0x10:0x18], "little")
    )
    texture_dictionary_off = _virtual_to_offset(
        int.from_bytes(
            system_data[shader_group_off + 0x08 : shader_group_off + 0x10],
            "little",
        )
    )
    return system_data, texture_dictionary_off


def test_create_ydr_builds_default_shader_resource(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        name="triangle",
    )

    assert isinstance(build, YdrBuild)
    ydr_path = tmp_path / "triangle.ydr"
    build.save(ydr_path)

    ydr = read_ydr(ydr_path)
    assert ydr.materials[0].shader_definition is not None
    assert ydr.materials[0].shader_definition.name == "default"
    assert ydr.materials[0].resolved_shader_file_name == "default.sps"
    assert ydr.materials[0].texture_names == ["test_diffuse"]
    assert ydr.materials[0].get_numeric_parameter("matMaterialColorScale") == pytest.approx((1.0, 0.0, 0.0, 1.0))
    assert ydr.materials[0].get_numeric_parameter("HardAlphaBlend") == pytest.approx(1.0)
    assert ydr.materials[0].get_numeric_parameter("useTessellation") == pytest.approx(0.0)
    assert ydr.materials[0].get_numeric_parameter("wetnessMultiplier") == pytest.approx(1.0)
    assert ydr.materials[0].get_numeric_parameter("globalAnimUV0") == pytest.approx((1.0, 0.0, 0.0))
    assert ydr.materials[0].get_numeric_parameter("globalAnimUV1") == pytest.approx((0.0, 1.0, 0.0))
    assert ydr.meshes[0].normals
    assert not ydr.meshes[0].tangents
    assert ydr.get_model(0).render_mask == int(YdrRenderMask.STATIC_PROP)

    _header, system_data, graphics_data = split_rsc7_sections(ydr_path.read_bytes())
    assert int.from_bytes(system_data[0x00:0x04], "little") == 0x40573178
    assert int.from_bytes(system_data[0x04:0x08], "little") == 1
    assert int.from_bytes(system_data[0x08:0x10], "little") >= 0x50000000
    assert int.from_bytes(system_data[0x10:0x18], "little") != 0
    assert int.from_bytes(system_data[0x50:0x58], "little") != 0
    assert int.from_bytes(system_data[0xA0:0xA8], "little") != 0
    assert int.from_bytes(system_data[0xA8:0xB0], "little") != 0
    assert graphics_data == b""

    model_list_off = int.from_bytes(system_data[0xA0:0xA8], "little") - 0x50000000
    model_off = int.from_bytes(system_data[model_list_off + 0x10 : model_list_off + 0x18], "little") - 0x50000000
    geometry_ptrs_off = int.from_bytes(system_data[model_off + 0x08 : model_off + 0x10], "little") - 0x50000000
    geometry_off = int.from_bytes(system_data[geometry_ptrs_off : geometry_ptrs_off + 0x08], "little") - 0x50000000
    vertex_buffer_off = int.from_bytes(system_data[geometry_off + 0x18 : geometry_off + 0x20], "little") - 0x50000000
    index_buffer_off = int.from_bytes(system_data[geometry_off + 0x38 : geometry_off + 0x40], "little") - 0x50000000

    assert int.from_bytes(system_data[model_off + 0x00 : model_off + 0x04], "little") == 0x40610A98
    assert int.from_bytes(system_data[model_off + 0x2C : model_off + 0x30], "little") == 0x000100E3
    assert int.from_bytes(system_data[model_off + 0x2E : model_off + 0x30], "little") == 1
    assert int.from_bytes(system_data[geometry_off + 0x00 : geometry_off + 0x04], "little") == 0x40618798
    assert int.from_bytes(system_data[vertex_buffer_off + 0x00 : vertex_buffer_off + 0x04], "little") == 0x4061D3F8
    assert int.from_bytes(system_data[index_buffer_off + 0x00 : index_buffer_off + 0x04], "little") == 0x4061D158
    assert system_data[vertex_buffer_off + 0x10 : vertex_buffer_off + 0x18] == system_data[vertex_buffer_off + 0x20 : vertex_buffer_off + 0x28]
    assert int.from_bytes(system_data[vertex_buffer_off + 0x10 : vertex_buffer_off + 0x18], "little") >= 0x50000000
    assert int.from_bytes(system_data[index_buffer_off + 0x10 : index_buffer_off + 0x18], "little") >= 0x50000000
    assert int.from_bytes(system_data[geometry_off + 0x78 : geometry_off + 0x80], "little") >= 0x50000000


def test_rigid_bone_binding_is_applied_to_drawable_bounds(tmp_path: Path) -> None:
    skeleton = YdrSkeleton()
    root = skeleton.bone("root")
    skeleton.bone("piece", parent=root, translation=Vector3(10.0, 2.0, 3.0))
    build = create_ydr(
        meshes=[_triangle_mesh()],
        skeleton=skeleton,
        skeleton_binding=YdrSkeletonBinding.rigid(bone_index=1),
        name="rigid_piece_bounds",
    )

    ydr_path = tmp_path / "rigid_piece_bounds.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.bounding_box_min.components == pytest.approx((10.0, 2.0, 3.0))
    assert ydr.bounding_box_max.components == pytest.approx((11.0, 3.0, 3.0))
    assert ydr.bounding_center.components == pytest.approx((10.5, 2.5, 3.0))


def test_create_ydr_writes_legacy_texture_base_contract(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        name="texture_base_contract",
    )

    ydr_path = tmp_path / "texture_base_contract.ydr"
    build.save(ydr_path)
    system_data, _shader_off, params_off = _first_shader_offsets(ydr_path.read_bytes())
    texture_base_off = _virtual_to_offset(int.from_bytes(system_data[params_off + 0x08 : params_off + 0x10], "little"))

    assert int.from_bytes(system_data[texture_base_off + 0x00 : texture_base_off + 0x04], "little") == _TEXTURE_BASE_VFT
    assert int.from_bytes(system_data[texture_base_off + 0x04 : texture_base_off + 0x08], "little") == 1
    assert int.from_bytes(system_data[texture_base_off + 0x30 : texture_base_off + 0x32], "little") == 1
    assert int.from_bytes(system_data[texture_base_off + 0x32 : texture_base_off + 0x34], "little") == 2


def test_create_ydr_writes_and_reads_joints(tmp_path: Path) -> None:
    skeleton = YdrSkeleton()
    root_bone = skeleton.bone("root")
    joints = YdrJoints()
    joints.rotation_limit(
        bone_id=root_bone.tag,
        min=Vector3(-1.0, -0.5, -0.25),
        max=Vector3(1.0, 0.5, 0.25),
        unknown_ah=7,
        num_control_points=2,
        joint_dofs=3,
    )
    joints.translation_limit(
        bone_id=root_bone.tag,
        min=Vector3(-0.1, -0.2, -0.3),
        max=Vector3(0.1, 0.2, 0.3),
    )
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        skeleton=skeleton,
        joints=joints,
        name="triangle_joints",
    )

    ydr_path = tmp_path / "triangle_joints.ydr"
    build.save(ydr_path)

    _header, system_data, _graphics_data = split_rsc7_sections(ydr_path.read_bytes())
    assert int.from_bytes(system_data[0x90:0x98], "little") != 0

    ydr = read_ydr(ydr_path)
    assert ydr.has_joints
    assert ydr.joints is not None
    assert len(ydr.joints.rotation_limits) == 1
    assert len(ydr.joints.translation_limits) == 1
    assert ydr.joints.rotation_limits[0].bone_id == root_bone.tag
    assert ydr.joints.rotation_limits[0].unknown_ah == 7
    assert ydr.joints.rotation_limits[0].num_control_points == 2
    assert ydr.joints.rotation_limits[0].joint_dofs == 3
    assert ydr.joints.rotation_limits[0].min.components == pytest.approx((-1.0, -0.5, -0.25))
    assert ydr.joints.rotation_limits[0].max.components == pytest.approx((1.0, 0.5, 0.25))
    assert ydr.joints.translation_limits[0].bone_id == root_bone.tag
    assert ydr.joints.translation_limits[0].min.components == pytest.approx((-0.1, -0.2, -0.3))
    assert ydr.joints.translation_limits[0].max.components == pytest.approx((0.1, 0.2, 0.3))


def test_roundtrip_real_ydr_without_embedded_textures_stays_system_only(tmp_path: Path) -> None:
    source_path = configured_path(
        "FIVEFURY_TEST_YDR_SYSTEM_ONLY",
        reference_root() / "ydr/bigbugboard.ydr",
    )
    if not source_path.exists():
        pytest.skip("real YDR sample not available")

    ydr = read_ydr(source_path)
    output_path = tmp_path / source_path.name
    ydr.save(output_path)

    _header, system_data, graphics_data = split_rsc7_sections(output_path.read_bytes())
    assert graphics_data == b""
    assert int.from_bytes(system_data[0x04:0x08], "little") == 1

    _system_data, _model_off, geometry_off = _first_model_offsets(output_path.read_bytes())
    vertex_buffer_off = _virtual_to_offset(int.from_bytes(system_data[geometry_off + 0x18 : geometry_off + 0x20], "little"))
    index_buffer_off = _virtual_to_offset(int.from_bytes(system_data[geometry_off + 0x38 : geometry_off + 0x40], "little"))
    assert int.from_bytes(system_data[geometry_off + 0x78 : geometry_off + 0x80], "little") >= 0x50000000
    assert int.from_bytes(system_data[vertex_buffer_off + 0x10 : vertex_buffer_off + 0x18], "little") >= 0x50000000
    assert int.from_bytes(system_data[index_buffer_off + 0x10 : index_buffer_off + 0x18], "little") >= 0x50000000


def test_create_ydr_supports_normal_spec_slots(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh(material="main")],
        materials=[
            YdrMaterialInput(
                name="main",
                shader="normal_spec.sps",
                textures={
                    "DiffuseSampler": "wall_a",
                    "BumpSampler": "wall_a_n",
                    "SpecSampler": "wall_a_s",
                },
            )
        ],
        name="triangle_ns",
    )
    ydr_path = tmp_path / "triangle_ns.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    descriptor = ydr.materials[0].material_descriptor
    assert descriptor.shader_name == "normal_spec"
    assert descriptor.get_texture("DiffuseSampler").texture_name == "wall_a"
    assert descriptor.get_texture("BumpSampler").texture_name == "wall_a_n"
    assert descriptor.get_texture("SpecSampler").texture_name == "wall_a_s"
    assert descriptor.get_parameter("specMapIntMask").value == pytest.approx((1.0, 0.0, 0.0))
    assert descriptor.get_parameter("specularIntensityMult").value == pytest.approx(1.0)
    assert descriptor.get_parameter("specularFalloffMult").value == pytest.approx(100.0)
    assert descriptor.get_parameter("specularFresnel").value == pytest.approx(0.75)


def test_create_ydr_roundtrips_array_shader_parameters(tmp_path: Path) -> None:
    expected = (
        (1.0, 2.0, 3.0, 4.0),
        (5.0, 6.0, 7.0, 8.0),
        (9.0, 10.0, 11.0, 12.0),
        (13.0, 14.0, 15.0, 16.0),
        (17.0, 18.0, 19.0, 20.0),
    )
    build = create_ydr(
        meshes=[_triangle_mesh(material="main")],
        materials=[
            YdrMaterialInput(
                name="main",
                shader="cable.sps",
                textures={"textureSamp": "test_diffuse"},
                parameters={"gCableParams": expected},
            )
        ],
        name="cable_array",
    )

    path1 = tmp_path / "cable_array_1.ydr"
    build.save(path1)
    ydr1 = read_ydr(path1)
    value1 = ydr1.materials[0].get_numeric_parameter("gCableParams")

    assert value1 is not None
    assert len(value1) == len(expected)
    for actual, wanted in zip(value1, expected, strict=True):
        assert actual == pytest.approx(wanted)

    path2 = tmp_path / "cable_array_2.ydr"
    ydr1.save(path2)
    ydr2 = read_ydr(path2)
    value2 = ydr2.materials[0].get_numeric_parameter("gCableParams")

    assert value2 is not None
    assert len(value2) == len(expected)
    for actual, wanted in zip(value2, expected, strict=True):
        assert actual == pytest.approx(wanted)


def test_create_ydr_accepts_named_render_mask_presets(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        render_mask=YdrRenderMask.SHELL,
        name="triangle_shell",
    )

    ydr_path = tmp_path / "triangle_shell.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.get_model(0).render_mask == int(YdrRenderMask.SHELL)


def test_ydr_render_mask_exposes_composable_runtime_passes(tmp_path: Path) -> None:
    assert int(YdrRenderMask.DEFAULT) == 0x01
    assert int(YdrRenderMask.SHADOW) == 0x02
    assert int(YdrRenderMask.REFLECTION) == 0x04
    assert int(YdrRenderMask.MIRROR) == 0x08
    assert int(YdrRenderMask.WATER_REFLECTION) == 0x10
    assert int(YdrRenderMask.RESERVED_PASSES) == 0xE0
    assert int(YdrRenderMask.STATIC_PROP) == 227
    assert int(YdrRenderMask.INTERIOR_PROP) == 235
    assert int(YdrRenderMask.SHELL) == 239
    assert int(YdrRenderMask.FULL) == 255

    render_mask = YdrRenderMask.STATIC_PROP | YdrRenderMask.WATER_REFLECTION
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        render_mask=render_mask,
        name="triangle_water_reflection",
    )

    ydr_path = tmp_path / "triangle_water_reflection.ydr"
    build.save(ydr_path)
    restored = YdrRenderMask(read_ydr(ydr_path).get_model(0).render_mask)

    assert restored == render_mask
    assert YdrRenderMask.DEFAULT in restored
    assert YdrRenderMask.WATER_REFLECTION in restored
    assert YdrRenderMask.SHADOW in restored
    assert YdrRenderMask.REFLECTION not in restored


def test_ydr_build_from_meshes_can_add_models_declaratively() -> None:
    build = YdrBuild.from_meshes(
        meshes=[_triangle_mesh(material="main")],
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="declarative_build",
        lod_distance=500.0,
        flags=7,
    )

    added = build.model(
        [_offset_triangle_mesh(2.0, material="main")],
        lod=YdrLod.MEDIUM,
        render_mask=YdrRenderMask.SHELL,
        lod_distance=250.0,
    )

    assert build.model_count == 2
    assert build.get_lod(YdrLod.HIGH)[0].meshes[0].material == "main"
    assert build.get_lod(YdrLod.HIGH)[0].flags == 7
    assert build.get_lod(YdrLod.MEDIUM) == [added]
    assert added.render_mask == YdrRenderMask.SHELL
    assert build.lod_distances[YdrLod.HIGH] == pytest.approx(500.0)
    assert build.lod_distances[YdrLod.MEDIUM] == pytest.approx(250.0)


def test_read_ydr_preserves_numeric_material_parameters(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh(material="main")],
        materials=[
            YdrMaterialInput(
                name="main",
                shader="normal_spec.sps",
                textures={
                    "DiffuseSampler": "wall_a",
                    "BumpSampler": "wall_a_n",
                    "SpecSampler": "wall_a_s",
                },
                parameters={
                    "bumpiness": 1.5,
                    "specMapIntMask": (1.0, 0.25, 0.0),
                },
            )
        ],
        name="triangle_ns_params",
    )
    ydr_path = tmp_path / "triangle_ns_params.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    material = ydr.materials[0]
    assert material.get_numeric_parameter("bumpiness") == pytest.approx(1.5)
    assert material.get_numeric_parameter("specMapIntMask") == pytest.approx((1.0, 0.25, 0.0))
    assert material.material_descriptor.get_parameter("bumpiness").value == pytest.approx(1.5)


def test_edit_parsed_ydr_material_and_save_roundtrip(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh(material="main")],
        materials=[
            YdrMaterialInput(
                name="main",
                shader="normal_spec.sps",
                textures={
                    "DiffuseSampler": "wall_a",
                    "BumpSampler": "wall_a_n",
                    "SpecSampler": "wall_a_s",
                },
                parameters={
                    "bumpiness": 1.0,
                    "specularIntensityMult": 1.0,
                },
            )
        ],
        name="editable_triangle",
    )
    source_path = tmp_path / "editable_triangle.ydr"
    build.save(source_path)

    ydr = read_ydr(source_path)
    material = ydr.materials[0]
    material.update(
        shader="spec.sps",
        textures={
            "DiffuseSampler": "wall_b",
            "SpecSampler": "wall_b_s",
            "BumpSampler": None,
        },
        parameters={
            "specularIntensityMult": 2.5,
        },
    )

    edited_path = tmp_path / "editable_triangle_out.ydr"
    ydr.save(edited_path)
    edited = read_ydr(edited_path)

    edited_material = edited.materials[0]
    assert edited_material.shader_definition is not None
    assert edited_material.shader_definition.name == "spec"
    assert edited_material.get_texture("DiffuseSampler").name == "wall_b"
    assert edited_material.get_texture("SpecSampler").name == "wall_b_s"
    assert edited_material.get_texture("BumpSampler") is None
    assert edited_material.get_numeric_parameter("specularIntensityMult") == pytest.approx(2.5)


def test_edit_parsed_ydr_material_declaratively(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh(material="main")],
        materials=[
            YdrMaterialInput(
                name="main",
                shader="normal_spec.sps",
                textures={
                    "DiffuseSampler": "wall_a",
                    "BumpSampler": "wall_a_n",
                    "SpecSampler": "wall_a_s",
                },
                parameters={
                    "bumpiness": 1.0,
                    "specularIntensityMult": 1.0,
                },
            )
        ],
        name="editable_triangle_decl",
    )
    source_path = tmp_path / "editable_triangle_decl.ydr"
    build.save(source_path)

    ydr = read_ydr(source_path)
    ydr.update_material(
        0,
        shader="spec.sps",
        textures={
            "DiffuseSampler": "wall_c",
            "SpecSampler": "wall_c_s",
            "BumpSampler": None,
        },
        parameters={
            "specularIntensityMult": 3.0,
        },
    )

    edited_path = tmp_path / "editable_triangle_decl_out.ydr"
    ydr.save(edited_path)
    edited = read_ydr(edited_path)

    edited_material = edited.materials[0]
    assert edited_material.shader_definition is not None
    assert edited_material.shader_definition.name == "spec"
    assert edited_material.get_texture("DiffuseSampler").name == "wall_c"
    assert edited_material.get_texture("SpecSampler").name == "wall_c_s"
    assert edited_material.get_texture("BumpSampler") is None
    assert edited_material.get_numeric_parameter("specularIntensityMult") == pytest.approx(3.0)


def test_create_ydr_accepts_shader_enum() -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        materials=[
            YdrMaterialInput(
                shader=YdrShader.SPEC,
                textures={
                    "DiffuseSampler": "wall_a",
                    "SpecSampler": "wall_a_s",
                },
            )
        ],
    )

    assert build.materials[0].shader == YdrShader.SPEC


def test_shader_file_name_infers_render_bucket_and_slot_alias(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        materials=[
            YdrMaterialInput(
                shader="normal_spec_cutout.sps",
                textures={
                    "DiffuseSampler": "wall_a",
                    "BumpSampler": "wall_a_n",
                    "SpecularSampler": "wall_a_s",
                },
            )
        ],
        name="bucket_inferred",
    )
    target = tmp_path / "bucket_inferred.ydr"
    build.save(target)

    ydr = read_ydr(target)
    material = ydr.materials[0]
    assert material.render_bucket == 3
    assert material.resolved_shader_file_name == "normal_spec_cutout.sps"
    assert material.get_texture("SpecSampler").name == "wall_a_s"


def test_unknown_shader_file_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown YDR shader 'specular.sps'"):
        create_ydr(
            meshes=[_triangle_mesh()],
            materials=[YdrMaterialInput(shader="specular.sps")],
        ).to_bytes()


def _make_trimesh_scene(
    *,
    diffuse: tuple[int, int, int, int] = (255, 128, 64, 255),
    textures: bool = True,
) -> trimesh.Scene:
    material_kwargs = (
        {
            "map_kd": r"C:\textures\facade_d.dds",
            "map_bump": r"C:\textures\facade_n.dds",
            "map_ks": r"C:\textures\facade_s.dds",
        }
        if textures
        else {}
    )
    material = SimpleMaterial(name="Facade", diffuse=diffuse, **material_kwargs)
    visual = TextureVisuals(
        uv=numpy.array(((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))),
        material=material,
    )
    mesh = trimesh.Trimesh(
        vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        faces=((0, 1, 2),),
        vertex_normals=((0.0, 0.0, 1.0),) * 3,
        visual=visual,
        process=False,
    )
    scene = trimesh.Scene()
    scene.add_geometry(
        mesh,
        node_name="facade_node",
        geom_name="facade_geometry",
        transform=trimesh.transformations.translation_matrix((2.0, 3.0, 4.0)),
    )
    return scene


def test_read_trimesh_scene_converts_native_scene() -> None:
    imported = read_trimesh_scene(_make_trimesh_scene(), name="facade")

    assert imported.name == "facade"
    assert imported.materials[0].name == "Facade"
    assert imported.materials[0].shader == "normal_spec.sps"
    assert imported.materials[0].textures["DiffuseSampler"] == "facade_d"
    assert imported.materials[0].textures["BumpSampler"] == "facade_n"
    assert imported.materials[0].textures["SpecSampler"] == "facade_s"
    assert imported.meshes[0].positions[0].components == pytest.approx((2.0, -4.0, 3.0))
    assert imported.meshes[0].positions[1].components == pytest.approx((3.0, -4.0, 3.0))
    assert imported.meshes[0].texcoords[0][2].components == pytest.approx((0.0, 0.0))


def test_read_trimesh_scene_can_convert_material_colours_to_embedded_textures() -> None:
    pytest.importorskip("PIL")
    pytest.importorskip("texfury")

    imported = read_trimesh_scene(
        _make_trimesh_scene(diffuse=(64, 128, 191, 255), textures=False),
        name="flat_colour",
        material_colours_as_textures=True,
    )

    assert imported.embedded_textures is not None
    assert len(imported.embedded_textures.textures) == 1
    texture = imported.embedded_textures.textures[0]
    assert texture.name == "facade_colour"
    assert texture.width == 4
    assert texture.height == 4
    assert texture.format == TextureFormat.BC1
    assert len(texture.data) == 8
    assert imported.materials[0].textures["DiffuseSampler"] == "facade_colour"


@pytest.mark.parametrize("suffix", ["obj", "ply", "stl"])
def test_read_trimesh_scene_autodetects_native_formats(
    tmp_path: Path,
    suffix: str,
) -> None:
    source_path = tmp_path / f"triangle.{suffix}"
    payload = trimesh.creation.icosphere(subdivisions=1).export(file_type=suffix)
    source_path.write_bytes(payload.encode() if isinstance(payload, str) else payload)

    imported = read_trimesh_scene(source_path)

    assert imported.meshes
    assert imported.name == "triangle"


def test_read_trimesh_scene_rejects_unsupported_suffix(tmp_path: Path) -> None:
    source_path = tmp_path / "shared.fbx"
    source_path.write_bytes(b"fake")

    with pytest.raises(ValueError, match="Trimesh does not support mesh source suffix"):
        read_trimesh_scene(source_path)


def test_read_trimesh_scene_loads_typed_bytes() -> None:
    payload = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"

    imported = read_trimesh_scene(payload, file_type="obj", name="memory_triangle")

    assert imported.name == "memory_triangle"
    assert imported.meshes[0].indices == [0, 1, 2]
    with pytest.raises(ValueError, match="file_type is required"):
        read_trimesh_scene(payload)


def test_read_trimesh_scene_preserves_instances() -> None:
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    scene = trimesh.Scene()
    scene.add_geometry(mesh, node_name="left", geom_name="shared")
    scene.graph.update(
        frame_to="right",
        frame_from=scene.graph.base_frame,
        matrix=trimesh.transformations.translation_matrix((10.0, 0.0, 0.0)),
        geometry="shared",
    )

    imported = read_trimesh_scene(scene, name="instances")

    assert len(imported.meshes) == 2
    minimum_x = sorted(min(position.x for position in mesh.positions) for mesh in imported.meshes)
    assert minimum_x == pytest.approx([-0.5, 9.5])


def test_read_trimesh_scene_splits_face_materials() -> None:
    materials = MultiMaterial(
        [
            SimpleMaterial(name="red", diffuse=(255, 0, 0, 255)),
            SimpleMaterial(name="blue", diffuse=(0, 0, 255, 255)),
        ]
    )
    mesh = trimesh.Trimesh(
        vertices=((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)),
        faces=((0, 1, 2), (1, 3, 2)),
        vertex_normals=((0, 0, 1),) * 4,
        visual=TextureVisuals(
            uv=((0, 0), (1, 0), (0, 1), (1, 1)),
            material=materials,
            face_materials=(0, 1),
        ),
        process=False,
    )

    imported = read_trimesh_scene(mesh, name="materials")

    assert [material.name for material in imported.materials] == ["red", "blue"]
    assert [mesh.material for mesh in imported.meshes] == ["red", "blue"]
    assert all(len(mesh.indices) == 3 for mesh in imported.meshes)
    assert all(mesh.normals for mesh in imported.meshes)


def test_read_trimesh_scene_uses_inverse_transpose_for_normals() -> None:
    normal = (2**-0.5, 2**-0.5, 0.0)
    mesh = trimesh.Trimesh(
        vertices=((0, 0, 0), (1, 0, 0), (0, 0, 1)),
        faces=((0, 1, 2),),
        vertex_normals=(normal,) * 3,
        process=False,
    )
    scene = trimesh.Scene()
    scene.add_geometry(mesh, transform=numpy.diag((2.0, 1.0, 1.0, 1.0)))

    imported = read_trimesh_scene(scene, name="scaled")

    assert imported.meshes[0].normals[0].components == pytest.approx(
        (1.0 / 5**0.5, 0.0, 2.0 / 5**0.5)
    )


def test_trimesh_to_ydr_roundtrip_from_native_scene(tmp_path: Path) -> None:
    ydr_path = tmp_path / "triangle.ydr"

    build = trimesh_to_ydr(_make_trimesh_scene(), ydr_path, name="triangle")
    assert isinstance(build, YdrBuild)
    assert ydr_path.exists()
    ydr = read_ydr(ydr_path)

    assert ydr.materials[0].shader_definition is not None
    assert ydr.materials[0].shader_definition.name == "normal_spec"
    assert ydr.materials[0].texture_names == ["facade_d", "facade_n", "facade_s"]
    assert ydr.meshes[0].indices == [0, 1, 2]


def test_trimesh_to_ydr_fills_missing_uvs_and_normals(tmp_path: Path) -> None:
    target = tmp_path / "box.ydr"

    trimesh_to_ydr(trimesh.creation.box(), target, name="box")
    ydr = read_ydr(target)

    assert ydr.meshes[0].normals
    assert ydr.meshes[0].texcoords[0]
    assert set(ydr.meshes[0].texcoords[0]) == {Vector2()}


def test_trimesh_scene_to_ydr_accepts_enhanced_game() -> None:
    imported = read_trimesh_scene(
        _make_trimesh_scene(),
        name="triangle",
        shader=YdrGen9Shader.DEFAULT,
    )
    build = imported.to_ydr(game=GameTarget.GTA5_ENHANCED)

    assert build.version == 159
    assert build.materials[0].shader == YdrGen9Shader.DEFAULT


def test_trimesh_to_ydr_persists_embedded_colour_textures(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    pytest.importorskip("texfury")
    ydr_path = tmp_path / "flat_colour.ydr"

    build = trimesh_to_ydr(
        _make_trimesh_scene(diffuse=(255, 0, 0, 128), textures=False),
        ydr_path,
        name="flat_colour",
        material_colours_as_textures=True,
    )
    ydr = read_ydr(ydr_path)

    assert build.embedded_textures is not None
    assert len(build.embedded_textures.textures) == 1
    assert ydr.embedded_textures is not None
    assert ydr.embedded_textures.textures[0].name == "facade_colour"
    assert ydr.materials[0].texture_names == ["facade_colour"]


def test_trimesh_to_ydr_writes_enhanced(tmp_path: Path) -> None:
    ydr_path = tmp_path / "enhanced.ydr"

    build = trimesh_to_ydr(
        _make_trimesh_scene(textures=False),
        ydr_path,
        name="enhanced",
        game=GameTarget.GTA5_ENHANCED,
        shader=YdrGen9Shader.DEFAULT,
    )
    ydr = read_ydr(ydr_path)

    assert build.version == 159
    assert ydr.version == 159
    assert ydr.materials[0].resolved_shader_file_name == "default.sps"


def test_writer_auto_splits_meshes_over_vertex_limit(tmp_path: Path) -> None:
    vertex_count = 66000
    positions = [Vector3(float(index), 0.0, 0.0) for index in range(vertex_count)]
    texcoords0 = [Vector2()] * vertex_count
    mesh = YdrMeshInput(
        positions=positions,
        indices=list(range(vertex_count)),
        material="default",
        texcoords=[texcoords0],
    )
    build = create_ydr(
        meshes=[mesh],
        material_textures={"DiffuseSampler": "test_diffuse"},
        name="split_limit_case",
    )

    ydr_path = tmp_path / "split_limit_case.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert len(ydr.meshes) >= 2
    assert all(len(mesh.positions) <= 65535 for mesh in ydr.meshes)
    assert sum(len(mesh.indices) for mesh in ydr.meshes) == vertex_count


def test_build_and_read_multi_model_ydr(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [
            YdrModelInput(meshes=[_offset_triangle_mesh(0.0, material="main")], render_mask=1),
            YdrModelInput(meshes=[_offset_triangle_mesh(2.0, material="main")], render_mask=2),
        ]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="multi_model",
    )

    ydr_path = tmp_path / "multi_model.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.model_count == 2
    assert len(ydr.get_lod(YdrLod.HIGH)) == 2
    assert ydr.get_model(0) is not None
    assert ydr.get_model(1) is not None
    assert ydr.get_model(0).render_mask == 1
    assert ydr.get_model(1).render_mask == 2
    assert ydr.get_model(0).mesh_count == 1
    assert ydr.get_model(1).mesh_count == 1
    assert ydr.get_model(0).material_indices == [0]
    assert ydr.get_model(0).material_count == 1
    assert ydr.get_model(0).materials[0].name == "material_0"
    assert ydr.get_model(0).get_material(0) is ydr.materials[0]


def test_writer_derives_root_lod_bucket_mask_from_used_materials(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={
            YdrLod.HIGH: [
                YdrModelInput(
                    meshes=[
                        _offset_triangle_mesh(0.0, material="opaque"),
                        _offset_triangle_mesh(2.0, material="decal"),
                    ],
                    render_mask=0xFF,
                    flags=0,
                )
            ]
        },
        materials=[
            YdrMaterialInput(
                name="opaque",
                shader="default.sps",
                textures={"DiffuseSampler": "opaque_diffuse"},
            ),
            YdrMaterialInput(
                name="decal",
                shader="decal.sps",
                textures={"DiffuseSampler": "decal_diffuse"},
            ),
        ],
        name="automatic_root_bucket_mask",
    )

    ydr_path = tmp_path / "automatic_root_bucket_mask.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    # High byte: model sub-buckets. Low byte: opaque (bit 0) and decal
    # (bit 2). Per-model flags live in grmModel and are not this summary.
    assert ydr.render_mask_flags[YdrLod.HIGH] == 0xFF05


def test_build_and_read_multi_lod_ydr(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={
            YdrLod.HIGH: [YdrModelInput(meshes=[_offset_triangle_mesh(0.0, material="main")], render_mask=0xFF)],
            YdrLod.MEDIUM: [YdrModelInput(meshes=[_offset_triangle_mesh(3.0, material="main")], render_mask=0xAA)],
        },
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="multi_lod",
        lod_distances={
            YdrLod.HIGH: 150.0,
            YdrLod.MEDIUM: 300.0,
        },
        render_mask_flags={
            YdrLod.HIGH: 0x0000FF05,
            YdrLod.MEDIUM: 0x0000AA01,
        },
    )

    ydr_path = tmp_path / "multi_lod.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)
    _header, system_data, _graphics_data = split_rsc7_sections(ydr_path.read_bytes())

    assert len(ydr.get_lod(YdrLod.HIGH)) == 1
    assert len(ydr.get_lod(YdrLod.MEDIUM)) == 1
    assert ydr.lod_distances[YdrLod.HIGH] == pytest.approx(150.0)
    assert ydr.lod_distances[YdrLod.MEDIUM] == pytest.approx(300.0)
    assert ydr.render_mask_flags[YdrLod.HIGH] == 0x0000FF05
    assert ydr.render_mask_flags[YdrLod.MEDIUM] == 0x0000AA01

    high_ptr = int.from_bytes(system_data[0x50:0x58], "little")
    med_ptr = int.from_bytes(system_data[0x58:0x60], "little")
    low_ptr = int.from_bytes(system_data[0x60:0x68], "little")
    models_ptr = int.from_bytes(system_data[0xA0:0xA8], "little")

    assert high_ptr >= 0x50000000
    assert med_ptr >= 0x50000000
    assert low_ptr == 0
    assert models_ptr == high_ptr
    assert int.from_bytes(system_data[0x80:0x84], "little") == 0x0000FF05
    assert int.from_bytes(system_data[0x84:0x88], "little") == 0x0000AA01


def test_build_and_read_ydr_lights(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        lights=[
            YdrLight(
                position=Vector3(1.0, 2.0, 3.0),
                color=(10, 20, 30),
                intensity=4.5,
                light_type=YdrLightType.SPOT,
                falloff=15.0,
                volume_outer_color=(40, 50, 60),
                light_hash=77,
                direction=Vector3(0.0, 0.0, -1.0),
                tangent=Vector3(1.0, 0.0, 0.0),
                cone_inner_angle=0.25,
                cone_outer_angle=0.5,
                projected_texture_hash=0x12345678,
            )
        ],
        name="with_lights",
    )

    ydr_path = tmp_path / "with_lights.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert len(ydr.lights) == 1
    light = ydr.lights[0]
    assert light.position.components == pytest.approx((1.0, 2.0, 3.0))
    assert light.color == (10, 20, 30)
    assert light.intensity == pytest.approx(4.5)
    assert light.light_type is YdrLightType.SPOT
    assert light.falloff == pytest.approx(15.0)
    assert light.volume_outer_color == (40, 50, 60)
    assert light.light_hash == 77
    assert light.direction.components == pytest.approx((0.0, 0.0, -1.0))
    assert light.tangent.components == pytest.approx((1.0, 0.0, 0.0))
    assert light.cone_inner_angle == pytest.approx(0.25)
    assert light.cone_outer_angle == pytest.approx(0.5)
    assert light.projected_texture_hash == 0x12345678


def test_declarative_ydr_light_helpers_roundtrip(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        name="light_helpers",
    )
    point = build.light(YdrLight.point(
        position=Vector3(1.0, 2.0, 3.0),
        color=(10, 20, 30),
        intensity=4.0,
        falloff=25.0,
    ))
    spot = build.light(YdrLight.spot(
        position=Vector3(4.0, 5.0, 6.0),
        direction=Vector3(0.0, 0.0, -1.0),
        cone_inner_angle=0.2,
        cone_outer_angle=0.6,
    ))
    capsule = build.light(YdrLight.capsule(position=Vector3(7.0, 8.0, 9.0), extent=Vector3(0.0, 0.0, 3.0)))

    assert point.light_type is YdrLightType.POINT
    assert spot.light_type is YdrLightType.SPOT
    assert capsule.light_type is YdrLightType.CAPSULE

    path = tmp_path / "light_helpers.ydr"
    build.save(path)
    ydr = read_ydr(path)

    assert [light.light_type for light in ydr.lights] == [YdrLightType.POINT, YdrLightType.SPOT, YdrLightType.CAPSULE]
    assert ydr.lights[0].position.components == pytest.approx((1.0, 2.0, 3.0))
    assert ydr.lights[0].color == (10, 20, 30)
    assert ydr.lights[0].intensity == pytest.approx(4.0)
    assert ydr.lights[0].falloff == pytest.approx(25.0)
    assert ydr.lights[1].direction.components == pytest.approx((0.0, 0.0, -1.0))
    assert ydr.lights[1].cone_outer_angle == pytest.approx(0.6)
    assert ydr.lights[2].extent.components == pytest.approx((0.0, 0.0, 3.0))

    parsed_spot = ydr.light(YdrLight.spot(position=Vector3(10.0, 0.0, 0.0), cone_outer_angle=1.0))
    assert parsed_spot.light_type is YdrLightType.SPOT
    assert len(ydr.lights) == 4
    ydr.clear_lights()
    assert ydr.lights == []


def test_build_and_read_ydr_embedded_textures(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "embedded_diffuse"},
            )
        ],
        embedded_textures=_tiny_embedded_ytd(),
        name="with_embedded_textures",
    )

    ydr_path = tmp_path / "with_embedded_textures.ydr"
    build.save(ydr_path)
    system_data, texture_dictionary_off = _embedded_texture_dictionary_offset(
        ydr_path.read_bytes()
    )
    ydr = read_ydr(ydr_path)

    assert (
        system_data[texture_dictionary_off + 0x08 : texture_dictionary_off + 0x10]
        == b"\0" * 8
    )
    assert ydr.embedded_textures is not None
    assert ydr.embedded_textures.names() == ["embedded_diffuse"]
    assert ydr.embedded_textures.get("embedded_diffuse").width == 4
    assert ydr.materials[0].get_texture("DiffuseSampler").name == "embedded_diffuse"


def test_build_and_read_ydr_embedded_textures_enhanced(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "embedded_diffuse"},
            )
        ],
        embedded_textures=Ytd(textures=list(_tiny_embedded_ytd().textures), game="gta5_enhanced"),
        version=159,
        name="with_embedded_textures_enhanced",
    )

    ydr_path = tmp_path / "with_embedded_textures_enhanced.ydr"
    build.save(ydr_path)
    system_data, texture_dictionary_off = _embedded_texture_dictionary_offset(
        ydr_path.read_bytes()
    )
    ydr = read_ydr(ydr_path)

    assert (
        system_data[texture_dictionary_off + 0x08 : texture_dictionary_off + 0x10]
        == b"\0" * 8
    )
    assert ydr.embedded_textures is not None
    assert ydr.embedded_textures.game == "gta5_enhanced"


def test_build_and_read_ydr_gen9_writes_native_shader_and_buffer_layouts(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "embedded_diffuse"},
                parameters={"matMaterialColorScale": (0.25, 0.5, 0.75, 1.0)},
            )
        ],
        version=159,
        name="gen9_native_layout",
    )

    ydr_path = tmp_path / "gen9_native_layout.ydr"
    build.save(ydr_path)
    raw = ydr_path.read_bytes()
    header, system_data, _graphics_data = split_rsc7_sections(raw)
    shader_data, shader_off, params_off, infos_off = _first_gen9_shader_offsets(raw)
    model_data, _model_off, geometry_off = _first_model_offsets(raw)
    vertex_buffer_off = _virtual_to_offset(int.from_bytes(model_data[geometry_off + 0x18 : geometry_off + 0x20], "little"))
    index_buffer_off = _virtual_to_offset(int.from_bytes(model_data[geometry_off + 0x38 : geometry_off + 0x40], "little"))
    declaration_off = _virtual_to_offset(int.from_bytes(model_data[vertex_buffer_off + 0x38 : vertex_buffer_off + 0x40], "little"))

    assert header.version == 159
    assert int.from_bytes(system_data[0:4], "little") == GEN9_DRAWABLE_HEADERS.drawable
    assert int.from_bytes(shader_data[shader_off + 0x04 : shader_off + 0x08], "little") == 0x6D657461
    assert int.from_bytes(shader_data[shader_off + 0x08 : shader_off + 0x10], "little") >= 0x50000000
    assert int.from_bytes(shader_data[shader_off + 0x10 : shader_off + 0x18], "little") >= 0x50000000
    assert int.from_bytes(shader_data[shader_off + 0x20 : shader_off + 0x28], "little") >= 0x50000000
    assert shader_data[infos_off + 0x00] == 2
    assert shader_data[infos_off + 0x01] == 2
    assert shader_data[infos_off + 0x07] == 12
    assert int.from_bytes(model_data[vertex_buffer_off + 0x08 : vertex_buffer_off + 0x0C], "little") == 3
    assert int.from_bytes(model_data[vertex_buffer_off + 0x10 : vertex_buffer_off + 0x14], "little") in {0x00580409, 0x00586409}
    assert int.from_bytes(model_data[vertex_buffer_off + 0x30 : vertex_buffer_off + 0x38], "little") >= 0x50000000
    assert int.from_bytes(model_data[index_buffer_off + 0x10 : index_buffer_off + 0x14], "little") == 0x0058020A
    assert int.from_bytes(model_data[index_buffer_off + 0x30 : index_buffer_off + 0x38], "little") >= 0x50000000

    declaration_data = model_data[declaration_off : declaration_off + 320]
    declaration_flags, declaration_types, declaration_stride, declaration_count = decode_gen9_vertex_declaration(declaration_data)
    assert declaration_stride == int.from_bytes(model_data[vertex_buffer_off + 0x0C : vertex_buffer_off + 0x0E], "little")
    # Shipped Gen9 drawables leave the declaration's packed vertex count at zero; the real count
    # lives on the vertex buffer at +0x08.
    assert declaration_count == 0
    assert int.from_bytes(model_data[vertex_buffer_off + 0x08 : vertex_buffer_off + 0x0C], "little") == 3
    assert declaration_flags != 0
    assert declaration_types != 0
    assert params_off < len(system_data)

    ydr = read_ydr(ydr_path)
    assert ydr.version == 159
    assert ydr.materials[0].shader_definition is not None
    assert ydr.materials[0].shader_definition.name == "default"
    assert ydr.materials[0].resolved_shader_file_name == "default.sps"
    assert ydr.materials[0].texture_names == ["embedded_diffuse"]
    assert ydr.materials[0].get_numeric_parameter("matMaterialColorScale") == pytest.approx((0.25, 0.5, 0.75, 1.0))
    assert len(ydr.meshes[0].positions) == 3


def test_build_ydr_gen9_texture_reference_matches_shipped_layout(tmp_path: Path) -> None:
    """Gen9 shader texture references must match the layout used by shipped drawables.

    The values here were taken from the drawables shipped with GTA V Enhanced: every shader
    parameter texture reference stores its usage count at 0x26 and its name pointer at 0x28,
    keeps depth and mip level at 1, and leaves the shader resource view pointer at 0x30 null.
    Writing the usage count over the view pointer leaves a bogus non-null pointer that the
    runtime then follows.
    """
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "layout_diffuse"},
            )
        ],
        version=159,
        name="gen9_texture_layout",
    )

    ydr_path = tmp_path / "gen9_texture_layout.ydr"
    build.save(ydr_path)
    system_data, shader_off, _params_off, _infos_off = _first_gen9_shader_offsets(ydr_path.read_bytes())

    texture_refs_off = _virtual_to_offset(int.from_bytes(system_data[shader_off + 0x10 : shader_off + 0x18], "little"))
    texture_off = _virtual_to_offset(int.from_bytes(system_data[texture_refs_off : texture_refs_off + 8], "little"))

    assert int.from_bytes(system_data[texture_off + 0x04 : texture_off + 0x08], "little") == 1
    assert int.from_bytes(system_data[texture_off + 0x10 : texture_off + 0x14], "little") == 0x00260000
    assert int.from_bytes(system_data[texture_off + 0x1C : texture_off + 0x1E], "little") == 1  # depth
    assert system_data[texture_off + 0x1E] == 1  # dimension: 2D
    assert system_data[texture_off + 0x20] == 255  # tile mode: auto
    assert system_data[texture_off + 0x22] == 1  # mip levels
    assert int.from_bytes(system_data[texture_off + 0x26 : texture_off + 0x28], "little") == 1  # usage count
    assert int.from_bytes(system_data[texture_off + 0x30 : texture_off + 0x38], "little") == 0  # no SRV
    assert int.from_bytes(system_data[texture_off + 0x38 : texture_off + 0x40], "little") == 0  # no pixel data

    name_off = _virtual_to_offset(int.from_bytes(system_data[texture_off + 0x28 : texture_off + 0x30], "little"))
    assert system_data[name_off : name_off + len(b"layout_diffuse")] == b"layout_diffuse"

    shader_group_off = _virtual_to_offset(int.from_bytes(system_data[0x10:0x18], "little"))
    assert int.from_bytes(system_data[shader_group_off + 0x30 : shader_group_off + 0x34], "little") == 0


def test_build_and_read_ydr_gen9_accepts_native_texture_slot_names(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseTex": "native_diffuse"},
                parameters={"MaterialColorScale": (0.1, 0.2, 0.3, 1.0)},
            )
        ],
        version=159,
        name="gen9_native_slots",
    )

    ydr_path = tmp_path / "gen9_native_slots.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.materials[0].texture_names == ["native_diffuse"]
    assert ydr.materials[0].get_numeric_parameter("matMaterialColorScale") == pytest.approx((0.1, 0.2, 0.3, 1.0))


def test_read_ydr_gen9_keeps_sampler_state_distinct_from_texture_resource(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "bound_diffuse"},
            )
        ],
        version=159,
        name="gen9_sampler_kind",
    )

    ydr_path = tmp_path / "gen9_sampler_kind.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)
    material = ydr.materials[0]

    texture_resource = next(parameter for parameter in material.parameters if parameter.name == "DiffuseSampler")
    sampler_state = next(parameter for parameter in material.parameters if parameter.name == "diffusesampler")

    assert texture_resource.is_texture
    assert texture_resource.texture is not None
    assert texture_resource.texture.name == "bound_diffuse"
    assert not sampler_state.is_texture
    assert sampler_state.value is not None
    assert not any(
        issue.code == "unbound_texture_slot" and "'diffusesampler'" in issue.message
        for issue in ydr.validate()
    )


def test_validate_ydr_gen9_treats_null_texture_resource_as_informational(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[YdrMaterialInput(name="main", shader="default.sps")],
        version=159,
        name="gen9_optional_texture",
    )

    ydr_path = tmp_path / "gen9_optional_texture.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    issue = next(issue for issue in ydr.validate() if issue.code == "unbound_texture_slot")
    assert issue.severity is DiagnosticSeverity.INFO
    assert "DiffuseSampler" in issue.message


def test_build_and_read_ydr_gen9_accepts_shader_enum(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader=YdrGen9Shader.DEFAULT,
                textures={"DiffuseTex": "enum_diffuse"},
                parameters={"MaterialColorScale": (0.6, 0.4, 0.2, 1.0)},
            )
        ],
        version=159,
        name="gen9_shader_enum",
    )

    ydr_path = tmp_path / "gen9_shader_enum.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.materials[0].resolved_shader_file_name == YdrGen9Shader.DEFAULT.value
    assert ydr.materials[0].texture_names == ["enum_diffuse"]
    assert ydr.materials[0].get_numeric_parameter("matMaterialColorScale") == pytest.approx((0.6, 0.4, 0.2, 1.0))


@pytest.mark.parametrize(("legacy_shader", "gen9_shader", "render_bucket"), _LEGACY_GEN9_ADAPTATION_CASES)
def test_build_and_read_ydr_gen9_adapts_legacy_shader_variants(
    tmp_path: Path,
    legacy_shader: str,
    gen9_shader: str,
    render_bucket: int,
) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader=legacy_shader,
                textures={"DiffuseSampler": "adapted_diffuse"},
            )
        ],
        version=159,
        name="gen9_legacy_adaptation",
    )

    ydr_path = tmp_path / f"{legacy_shader}.ydr"
    build.save(ydr_path)
    material = read_ydr(ydr_path).materials[0]

    assert material.resolved_shader_file_name == gen9_shader
    assert material.render_bucket == render_bucket
    if render_bucket in {1, 3} and material.get_parameter("HardAlphaBlend") is not None:
        assert material.get_numeric_parameter("HardAlphaBlend") == pytest.approx(1.0)


@pytest.mark.parametrize("shader", _GEN9_ENVIRONMENT_SHADER_FAMILIES)
def test_build_and_read_ydr_gen9_preserves_environment_sampler_binding(tmp_path: Path, shader: str) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader=shader,
                textures={
                    "DiffuseSampler": "reflect_diffuse",
                    "EnvironmentSampler": "reflect_environment",
                },
            )
        ],
        version=159,
        name="gen9_environment_binding",
    )

    ydr_path = tmp_path / f"{shader}.ydr"
    build.save(ydr_path)
    material = read_ydr(ydr_path).materials[0]

    assert material.get_texture("EnvironmentSampler").name == "reflect_environment"
    assert material.get_texture("EnvironmentTex2D").name == "reflect_environment"


@pytest.mark.parametrize(("value", "expected"), ((None, 1.0), (0.0, 0.0)))
def test_build_and_read_ydr_gen9_applies_defaults_before_material_values(
    tmp_path: Path,
    value: float | None,
    expected: float,
) -> None:
    parameters = {} if value is None else {"hardalphablend": value}
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="glass.sps",
                textures={"DiffuseSampler": "glass_diffuse"},
                parameters=parameters,
            )
        ],
        version=159,
        name="gen9_material_defaults",
    )

    ydr_path = tmp_path / f"gen9_material_defaults_{expected}.ydr"
    build.save(ydr_path)
    material = read_ydr(ydr_path).materials[0]

    assert material.get_numeric_parameter("hardalphablend") == pytest.approx(expected)


def test_build_and_read_ydr_embedded_bound(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        bound=BoundSphere(
            bound_type=BoundType.SPHERE,
            box_min=Vector3(-1.0, -1.0, -1.0),
            box_max=Vector3(1.0, 1.0, 1.0),
            box_center=Vector3(),
            sphere_center=Vector3(),
            sphere_radius=1.25,
            margin=0.25,
        ),
        name="with_bound",
    )

    ydr_path = tmp_path / "with_bound.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert isinstance(ydr.bound, BoundSphere)
    assert ydr.bound.sphere_radius == pytest.approx(1.25)
    assert ydr.bound.margin == pytest.approx(0.25)


def _skinned_triangle_mesh(material: str = "default") -> YdrMeshInput:
    return YdrMeshInput(
        positions=[
            Vector3(),
            Vector3(1.0, 0.0, 0.0),
            Vector3(0.0, 1.0, 0.0),
        ],
        indices=[0, 1, 2],
        material=material,
        texcoords=[
            [
                Vector2(),
                Vector2(1.0, 0.0),
                Vector2(0.0, 1.0),
            ]
        ],
        blend_weights=[
            (1.0, 0.0, 0.0, 0.0),
            (0.5, 0.5, 0.0, 0.0),
            (1.0, 0.0, 0.0, 0.0),
        ],
        blend_indices=[
            (0, 0, 0, 0),
            (0, 1, 0, 0),
            (1, 0, 0, 0),
        ],
        bone_ids=[0, 1],
    )


def _simple_skeleton() -> YdrSkeleton:
    skeleton = YdrSkeleton()
    root = skeleton.bone(
        "root",
        tag=0,
        flags=YdrBoneFlags.ROT_X | YdrBoneFlags.ROT_Y | YdrBoneFlags.ROT_Z,
    )
    skeleton.bone(
        "child",
        parent=root,
        tag=1,
        flags=YdrBoneFlags.ROT_X | YdrBoneFlags.ROT_Y | YdrBoneFlags.ROT_Z,
        translation=Vector3(0.0, 0.25, 0.0),
    )
    return skeleton.build()


def test_gen9_writer_preserves_explicit_vertex_buffer_flags_on_skinned_mesh(
    tmp_path: Path,
) -> None:
    mesh = _skinned_triangle_mesh()
    mesh.vertex_buffer_flags = 0x00580409
    build = create_ydr(
        meshes=[mesh],
        skeleton=_simple_skeleton(),
        name="explicit_gen9_buffer_flags",
        version=159,
    )

    output = tmp_path / "explicit_gen9_buffer_flags.ydr"
    build.save(output)
    parsed = read_ydr(output)

    assert parsed.meshes[0].blend_weights
    assert parsed.meshes[0].blend_indices
    assert parsed.meshes[0].vertex_buffer_flags == 0x00580409


def test_gen9_writer_derives_skinned_vertex_buffer_flags_when_zero(
    tmp_path: Path,
) -> None:
    build = create_ydr(
        meshes=[_skinned_triangle_mesh()],
        skeleton=_simple_skeleton(),
        name="derived_gen9_buffer_flags",
        version=159,
    )

    output = tmp_path / "derived_gen9_buffer_flags.ydr"
    build.save(output)

    assert read_ydr(output).meshes[0].vertex_buffer_flags == 0x00586409


@pytest.mark.parametrize("flags", (-1, 0x1_0000_0000))
def test_gen9_writer_rejects_vertex_buffer_flags_outside_uint32(flags: int) -> None:
    mesh = _skinned_triangle_mesh()
    mesh.vertex_buffer_flags = flags
    build = create_ydr(
        meshes=[mesh],
        skeleton=_simple_skeleton(),
        name="invalid_gen9_buffer_flags",
        version=159,
    )

    with pytest.raises(ValueError, match="unsigned 32-bit"):
        build.to_bytes()


def _hashable_skeleton() -> YdrSkeleton:
    skeleton = YdrSkeleton()
    root = skeleton.bone(
        "root",
        tag=0,
        flags=YdrBoneFlags.ROT_X | YdrBoneFlags.TRANS_Y | YdrBoneFlags.HAS_CHILD,
        translation=Vector3(1.0, 2.0, 3.0),
        rotation=Quaternion(0.0, 0.0, 0.0, 1.0),
        scale=Vector3(1.0, 1.0, 1.0),
    )
    mid = skeleton.bone(
        "mid",
        parent=root,
        tag=11,
        flags=YdrBoneFlags.ROT_Y | YdrBoneFlags.TRANS_Z | YdrBoneFlags.SCALE_X,
        translation=Vector3(0.0, 0.25, 0.5),
        rotation=Quaternion(0.1, 0.2, 0.3, 0.9),
        scale=Vector3(1.0, 2.0, 1.0),
    )
    skeleton.bone(
        "leaf",
        parent=mid,
        tag=12,
        flags=YdrBoneFlags.ROT_Z | YdrBoneFlags.LIMIT_ROTATION,
        translation=Vector3(-1.0, 0.0, 1.0),
        rotation=Quaternion(0.4, 0.0, 0.0, 0.8),
        scale=Vector3(0.5, 0.5, 0.5),
    )
    return skeleton.build()


def _tiny_embedded_ytd() -> Ytd:
    return Ytd(
        textures=[
            Texture.from_raw(
                bytes([255, 0, 0, 255] * 16),
                width=4,
                height=4,
                format=TextureFormat.A8R8G8B8,
                mip_count=1,
                name="embedded_diffuse",
            )
        ],
        game="gta5",
    )


def test_declarative_skeleton_helpers() -> None:
    skeleton = YdrSkeleton()
    root = skeleton.bone("root")
    child = skeleton.bone(
        "child",
        parent="root",
        translation=Vector3(0.0, 1.0, 0.0),
    )
    skeleton.build()

    assert root.flags == (
        YdrBoneFlags.ROT_X
        | YdrBoneFlags.ROT_Y
        | YdrBoneFlags.ROT_Z
        | YdrBoneFlags.TRANS_X
        | YdrBoneFlags.TRANS_Y
        | YdrBoneFlags.TRANS_Z
        | YdrBoneFlags.HAS_CHILD
    )
    assert root.index == 0
    assert child.index == 1
    assert child.parent_index == 0
    assert skeleton.parent_indices == [-1, 0]
    assert root.next_sibling_index == -1
    assert child.tag == calculate_bone_tag("child")
    assert skeleton.require_bone("child") is child
    assert skeleton.require_bone(child.tag) is child

    ydr = Ydr(version=165)
    bone = ydr.bone("weapon_root")
    assert ydr.has_skeleton is True
    assert bone.name == "weapon_root"
    assert ydr.get_bone_by_name("weapon_root") is bone


def test_skeleton_unknown_hash_helper_is_explicit_and_enum_backed() -> None:
    skeleton = _hashable_skeleton()
    hashes = calculate_skeleton_unknown_hashes(skeleton)

    assert hashes == calculate_skeleton_unknown_hashes(skeleton)
    assert all(value != 0 for value in hashes)
    assert skeleton_bone_flag_names(skeleton.bones[0].flags) == (
        YdrBoneFlagName.ROT_X,
        YdrBoneFlagName.TRANS_Y,
        YdrBoneFlagName.HAS_CHILD,
    )
    assert (skeleton.unknown_50h, skeleton.unknown_54h, skeleton.unknown_58h) == (0, 0, 0)

    skeleton.build()
    assert (skeleton.unknown_50h, skeleton.unknown_54h, skeleton.unknown_58h) == (0, 0, 0)

    assert skeleton.calculate_unknown_hashes() == hashes
    assert skeleton.recalculate_unknown_hashes() is skeleton
    assert (skeleton.unknown_50h, skeleton.unknown_54h, skeleton.unknown_58h) == hashes


def test_skinned_mesh_builds_and_reads(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=YdrSkeletonBinding.skinned(),
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="skinned_tri",
        skeleton=_simple_skeleton(),
    )

    ydr_path = tmp_path / "skinned_tri.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    mesh = ydr.meshes[0]
    assert len(mesh.blend_weights) == 3
    assert len(mesh.blend_indices) == 3
    assert mesh.bone_ids == [0, 1]

    assert mesh.blend_weights[0] == pytest.approx((1.0, 0.0, 0.0, 0.0), abs=1 / 255)
    assert mesh.blend_weights[1] == pytest.approx((0.5, 0.5, 0.0, 0.0), abs=1 / 255)
    assert mesh.blend_indices[0] == (0, 0, 0, 0)
    assert mesh.blend_indices[1] == (0, 1, 0, 0)
    assert mesh.blend_indices[2] == (1, 0, 0, 0)

    model = ydr.get_model(0)
    assert model is not None
    assert model.has_skin is True
    assert model.flags == 1
    assert model.skeleton_binding == YdrSkeletonBinding.skinned(unknown_1=2)
    assert ydr.has_skeleton is True
    assert ydr.skeleton is not None
    assert ydr.skeleton.bone_count == 2
    assert ydr.get_bone_by_name("root") is not None
    assert ydr.get_bone_by_tag(1) is not None
    assert [bone.name for bone in mesh.resolve_bones(ydr.skeleton)] == ["root", "child"]


def test_gen9_skinned_mesh_uses_declared_component_offsets(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={
            YdrLod.HIGH: [
                YdrModelInput(
                    meshes=[_skinned_triangle_mesh(material="main")],
                    skeleton_binding=YdrSkeletonBinding.skinned(),
                )
            ]
        },
        materials=[YdrMaterialInput(name="main", shader="default.sps")],
        version=159,
        name="gen9_skinned_tri",
        skeleton=_simple_skeleton(),
    )

    path = tmp_path / "gen9_skinned_tri.ydr"
    build.save(path)
    mesh = read_ydr(path).meshes[0]

    assert mesh.blend_indices == [
        (0, 0, 0, 0),
        (0, 1, 0, 0),
        (1, 0, 0, 0),
    ]
    assert mesh.blend_weights[1] == pytest.approx(
        (0.5, 0.5, 0.0, 0.0),
        abs=1 / 255,
    )


def test_skinned_default_layout_uses_canonical_default_vertex_data_type(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=YdrSkeletonBinding.skinned(),
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="skinned_default_decl",
        skeleton=_simple_skeleton(),
    )

    ydr_path = tmp_path / "skinned_default_decl.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)
    mesh = ydr.meshes[0]

    assert mesh.declaration_flags == 95
    assert mesh.declaration_types == 0x7755555555996996
    assert mesh.vertex_stride == 44


def test_skinned_models_auto_enable_model_skin_flag(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=YdrSkeletonBinding.skinned(),
            flags=0,
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="skinned_auto_flags",
        skeleton=_simple_skeleton(),
    )

    ydr_path = tmp_path / "skinned_auto_flags.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.get_model(0).flags == 1


def test_skinned_models_preserve_other_model_flags_when_auto_enabling_skin(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=YdrSkeletonBinding.skinned(),
            flags=0x24,
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="skinned_auto_flags_preserve",
        skeleton=_simple_skeleton(),
    )

    ydr_path = tmp_path / "skinned_auto_flags_preserve.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.get_model(0).flags == 0x25


def test_explicit_skinned_ubyte4_blend_indices_are_canonicalized(tmp_path: Path) -> None:
    mesh = _skinned_triangle_mesh(material="main")
    mesh.declaration_flags = 95
    mesh.declaration_types = 8598872888530528406

    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[mesh],
            skeleton_binding=YdrSkeletonBinding.skinned(),
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="skinned_decl_fixup",
        skeleton=_simple_skeleton(),
    )

    ydr_path = tmp_path / "skinned_decl_fixup.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)
    rebuilt_mesh = ydr.meshes[0]

    assert rebuilt_mesh.declaration_flags == 95
    assert rebuilt_mesh.declaration_types == 0x7755555555996996
    assert rebuilt_mesh.blend_indices == [(0, 0, 0, 0), (0, 1, 0, 0), (1, 0, 0, 0)]


def test_skinned_layout_selected() -> None:
    from fivefury.ydr.shaders import load_shader_library

    lib = load_shader_library()
    shader = lib.resolve_shader(shader_name="default")
    assert shader is not None

    from fivefury.ydr.builder import _select_layout

    layout = _select_layout(shader, used_uv_indices={0}, skinned=True)
    semantics = {s.lower() for s in layout.semantics}
    assert "blendweights" in semantics
    assert "blendindices" in semantics

    static_layout = _select_layout(shader, used_uv_indices={0}, skinned=False)
    static_semantics = {s.lower() for s in static_layout.semantics}
    assert "blendweights" not in static_semantics


def test_static_mesh_unaffected_by_skinned_support(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        name="static_tri",
    )

    ydr_path = tmp_path / "static_tri.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    mesh = ydr.meshes[0]
    assert mesh.blend_weights == []
    assert mesh.blend_indices == []
    assert mesh.bone_ids == []


def test_skinned_mesh_roundtrip_via_to_build(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=YdrSkeletonBinding.skinned(),
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="roundtrip_skin",
        skeleton=_simple_skeleton(),
    )

    ydr_path = tmp_path / "roundtrip1.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    rebuild = ydr.to_build()
    ydr_path2 = tmp_path / "roundtrip2.ydr"
    rebuild.save(ydr_path2)
    ydr2 = read_ydr(ydr_path2)

    assert len(ydr2.meshes[0].blend_weights) == 3
    assert ydr2.meshes[0].bone_ids == [0, 1]
    assert ydr2.get_model(0).has_skin is True
    assert ydr2.skeleton is not None
    assert [bone.name for bone in ydr2.skeleton.bones] == ["root", "child"]


def test_to_build_preserves_explicit_null_texture_parameters(tmp_path: Path) -> None:
    mesh = _triangle_mesh(material="main")
    mesh.texcoords = [list(mesh.texcoords[0]), list(mesh.texcoords[0])]
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[mesh])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="ped.sps",
                textures={
                    "DiffuseSampler": "ped_diffuse",
                    "TextureSamplerDiffPal": None,
                    "VolumeSampler": None,
                },
            )
        ],
        name="null_texture_parameters",
    )

    path1 = tmp_path / "null_texture_parameters_1.ydr"
    build.save(path1)
    ydr1 = read_ydr(path1)
    material1 = ydr1.materials[0]

    null_slots1 = {
        parameter.name
        for parameter in material1.parameters
        if parameter.is_texture and parameter.texture is None
    }
    assert {"TextureSamplerDiffPal", "VolumeSampler"} <= null_slots1
    assert material1.to_input().textures["TextureSamplerDiffPal"] is None
    assert material1.to_input().textures["VolumeSampler"] is None

    path2 = tmp_path / "null_texture_parameters_2.ydr"
    ydr1.to_build().save(path2)
    ydr2 = read_ydr(path2)
    null_slots2 = {
        parameter.name
        for parameter in ydr2.materials[0].parameters
        if parameter.is_texture and parameter.texture is None
    }
    assert {"TextureSamplerDiffPal", "VolumeSampler"} <= null_slots2


def test_skinned_model_writes_formal_skeleton_binding_bytes(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=YdrSkeletonBinding.skinned(unknown_1=0x11),
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="skinned_bytes",
        skeleton=_simple_skeleton(),
    )

    ydr_path = tmp_path / "skinned_bytes.ydr"
    build.save(ydr_path)
    system_data, model_off, _geometry_off = _first_model_offsets(ydr_path.read_bytes())

    assert int.from_bytes(system_data[model_off + 0x28 : model_off + 0x2C], "little") == 0x00000102
    assert system_data[model_off + 0x28 : model_off + 0x2C] == bytes((0x02, 0x01, 0x00, 0x00))


def test_rigid_model_bone_binding_roundtrip(tmp_path: Path) -> None:
    skeleton = _simple_skeleton()
    build = YdrBuild(
        lods={YdrLod.HIGH: [
            YdrModelInput(
                meshes=[_triangle_mesh(material="main")],
                skeleton_binding=YdrSkeletonBinding.rigid(bone_index=0),
            ),
            YdrModelInput(
                meshes=[_triangle_mesh(material="main")],
                skeleton_binding=YdrSkeletonBinding.rigid(bone_index=1),
            ),
        ]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="rigid_bone_binding",
        skeleton=skeleton,
    )

    ydr_path = tmp_path / "rigid_bone_binding.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.model_count == 2
    assert ydr.models[0].has_skin is False
    assert ydr.models[0].bone_index == 0
    assert ydr.models[0].skeleton_binding == YdrSkeletonBinding.rigid(bone_index=0)
    assert ydr.models[1].has_skin is False
    assert ydr.models[1].bone_index == 1
    assert ydr.models[1].skeleton_binding == YdrSkeletonBinding.rigid(bone_index=1)
    assert ydr.validate().valid


def test_bind_model_to_bone_helper_roundtrip(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh(material="main")],
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="bind_model_to_bone",
    )
    ydr_path = tmp_path / "bind_model_to_bone.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    root = ydr.bone("root", tag=0)
    child = ydr.bone("child", parent=root, tag=1)
    ydr.ensure_skeleton().build()
    ydr.bind_model_to_bone(0, child)

    out_path = tmp_path / "bind_model_to_bone_out.ydr"
    ydr.save(out_path)
    rebuilt = read_ydr(out_path)

    assert rebuilt.get_model(0).has_skin is False
    assert rebuilt.get_model(0).bone_index == 1
    assert rebuilt.get_model(0).skeleton_binding == YdrSkeletonBinding.rigid(bone_index=1)


def test_drawable_model_writes_outer_bounds_data_for_multi_geometry(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[
                _offset_triangle_mesh(0.0, material="main"),
                _offset_triangle_mesh(10.0, material="main"),
            ],
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="multi_geom_bounds",
    )

    ydr_path = tmp_path / "multi_geom_bounds.ydr"
    build.save(ydr_path)
    system_data, model_off, _geometry_off = _first_model_offsets(ydr_path.read_bytes())
    bounds_off = _virtual_to_offset(int.from_bytes(system_data[model_off + 0x18 : model_off + 0x20], "little"))

    assert int.from_bytes(system_data[model_off + 0x10 : model_off + 0x12], "little") == 2
    assert int.from_bytes(system_data[model_off + 0x12 : model_off + 0x14], "little") == 2
    assert int.from_bytes(system_data[model_off + 0x2E : model_off + 0x30], "little") == 2
    assert int.from_bytes(system_data[model_off + 0x04 : model_off + 0x08], "little") == 1

    import struct

    outer_bounds = struct.unpack_from("<8f", system_data, bounds_off)
    first_bounds = struct.unpack_from("<8f", system_data, bounds_off + 32)
    second_bounds = struct.unpack_from("<8f", system_data, bounds_off + 64)
    assert outer_bounds[:3] == pytest.approx((0.0, 0.0, 0.0))
    assert outer_bounds[4:7] == pytest.approx((11.0, 1.0, 0.0))
    assert first_bounds[:3] == pytest.approx((0.0, 0.0, 0.0))
    assert first_bounds[4:7] == pytest.approx((1.0, 1.0, 0.0))
    assert second_bounds[:3] == pytest.approx((10.0, 0.0, 0.0))
    assert second_bounds[4:7] == pytest.approx((11.0, 1.0, 0.0))


def test_geometry_bone_ids_tail_embedding_rules(tmp_path: Path) -> None:
    many_bones_mesh = _skinned_triangle_mesh(material="main")
    many_bones_mesh.bone_ids = [0, 1, 2, 3, 4]
    many_bones_mesh.blend_indices = [
        (0, 1, 2, 3),
        (0, 1, 2, 4),
        (1, 2, 3, 4),
    ]
    skeleton = YdrSkeleton()
    root = skeleton.bone("root", tag=0)
    for index in range(1, 5):
        skeleton.bone(f"bone_{index}", parent=root, tag=index)
    skeleton.build()
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[
                _triangle_mesh(material="main"),
                _skinned_triangle_mesh(material="main"),
                many_bones_mesh,
            ],
            skeleton_binding=YdrSkeletonBinding.skinned(),
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="bone_ids_tail",
        skeleton=skeleton,
    )

    ydr_path = tmp_path / "bone_ids_tail.ydr"
    build.save(ydr_path)
    _header, system_data, _graphics_data = split_rsc7_sections(ydr_path.read_bytes())
    model_list_off = _virtual_to_offset(int.from_bytes(system_data[0xA0:0xA8], "little"))
    model_off = _virtual_to_offset(int.from_bytes(system_data[model_list_off + 0x10 : model_list_off + 0x18], "little"))
    geometry_ptrs_off = _virtual_to_offset(int.from_bytes(system_data[model_off + 0x08 : model_off + 0x10], "little"))
    geometry_offsets = [
        _virtual_to_offset(int.from_bytes(system_data[geometry_ptrs_off + (index * 8) : geometry_ptrs_off + (index * 8) + 8], "little"))
        for index in range(3)
    ]

    assert int.from_bytes(system_data[geometry_offsets[0] + 0x68 : geometry_offsets[0] + 0x70], "little") == 0
    assert int.from_bytes(system_data[geometry_offsets[0] + 0x72 : geometry_offsets[0] + 0x74], "little") == 0

    normalized_palette_ptr = int.from_bytes(system_data[geometry_offsets[1] + 0x68 : geometry_offsets[1] + 0x70], "little")
    assert _virtual_to_offset(normalized_palette_ptr) == geometry_offsets[1] + 0xA0
    assert int.from_bytes(system_data[geometry_offsets[1] + 0x72 : geometry_offsets[1] + 0x74], "little") == 5
    assert system_data[geometry_offsets[1] + 0x98 : geometry_offsets[1] + 0xA0] == b"\x00" * 8
    assert system_data[geometry_offsets[1] + 0xA0 : geometry_offsets[1] + 0xAA] == b"\x00\x00\x01\x00\x02\x00\x03\x00\x04\x00"

    five_bone_ptr = int.from_bytes(system_data[geometry_offsets[2] + 0x68 : geometry_offsets[2] + 0x70], "little")
    assert _virtual_to_offset(five_bone_ptr) == geometry_offsets[2] + 0xA0
    assert int.from_bytes(system_data[geometry_offsets[2] + 0x72 : geometry_offsets[2] + 0x74], "little") == 5
    assert system_data[geometry_offsets[2] + 0x98 : geometry_offsets[2] + 0xA0] == b"\x00" * 8
    assert system_data[geometry_offsets[2] + 0xA0 : geometry_offsets[2] + 0xAA] == b"\x00\x00\x01\x00\x02\x00\x03\x00\x04\x00"


def test_geometry_fixed_fields_match_expected_defaults(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        name="geom_defaults",
    )
    ydr_path = tmp_path / "geom_defaults.ydr"
    build.save(ydr_path)
    system_data, _model_off, geometry_off = _first_model_offsets(ydr_path.read_bytes())

    assert int.from_bytes(system_data[geometry_off + 0x04 : geometry_off + 0x08], "little") == 1
    assert int.from_bytes(system_data[geometry_off + 0x08 : geometry_off + 0x10], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x10 : geometry_off + 0x18], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x20 : geometry_off + 0x28], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x28 : geometry_off + 0x30], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x30 : geometry_off + 0x38], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x40 : geometry_off + 0x48], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x48 : geometry_off + 0x50], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x50 : geometry_off + 0x58], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x62 : geometry_off + 0x64], "little") == 3
    assert int.from_bytes(system_data[geometry_off + 0x64 : geometry_off + 0x68], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x74 : geometry_off + 0x78], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x80 : geometry_off + 0x88], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x88 : geometry_off + 0x90], "little") == 0
    assert int.from_bytes(system_data[geometry_off + 0x90 : geometry_off + 0x98], "little") == 0


def test_to_build_preserves_embedded_assets(tmp_path: Path) -> None:
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(meshes=[_triangle_mesh(material="main")])]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "embedded_diffuse"},
            )
        ],
        embedded_textures=_tiny_embedded_ytd(),
        bound=BoundSphere(
            bound_type=BoundType.SPHERE,
            box_min=Vector3(-0.5, -0.5, -0.5),
            box_max=Vector3(0.5, 0.5, 0.5),
            box_center=Vector3(),
            sphere_center=Vector3(),
            sphere_radius=0.75,
            margin=0.1,
        ),
        name="embedded_assets_roundtrip",
    )

    path1 = tmp_path / "embedded_assets_roundtrip_1.ydr"
    build.save(path1)
    ydr = read_ydr(path1)

    rebuilt = ydr.to_build()
    path2 = tmp_path / "embedded_assets_roundtrip_2.ydr"
    rebuilt.save(path2)
    ydr2 = read_ydr(path2)

    assert ydr2.embedded_textures is not None
    assert ydr2.embedded_textures.names() == ["embedded_diffuse"]
    assert isinstance(ydr2.bound, BoundSphere)
    assert ydr2.bound.sphere_radius == pytest.approx(0.75)


def test_declarative_embedded_texture_and_bound_helpers(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        name="helper_case",
    )
    path = tmp_path / "helper_case.ydr"
    build.save(path)
    ydr = read_ydr(path)

    added = ydr.embedded_texture(
        name="helper_embedded",
        data=bytes([0, 255, 0, 255] * 16),
        width=4,
        height=4,
        format=TextureFormat.A8R8G8B8,
    )
    assert added.name == "helper_embedded"
    assert ydr.get_embedded_texture("helper_embedded") is not None

    ydr.embedded_texture(
        Texture.from_raw(
            bytes([0, 0, 255, 255] * 16),
            width=4,
            height=4,
            format=TextureFormat.A8R8G8B8,
            mip_count=1,
            name="helper_embedded",
        ),
        replace=True,
    )
    assert ydr.get_embedded_texture("helper_embedded").data[:4] == bytes([0, 0, 255, 255])
    assert ydr.remove_embedded_texture("helper_embedded") is True
    assert ydr.get_embedded_texture("helper_embedded") is None

    ydr.bound = BoundSphere(
        bound_type=BoundType.SPHERE,
        box_min=Vector3(-1.0, -1.0, -1.0),
        box_max=Vector3(1.0, 1.0, 1.0),
        box_center=Vector3(),
        sphere_center=Vector3(),
        sphere_radius=1.0,
        margin=0.0,
    )
    assert isinstance(ydr.bound, BoundSphere)
    ydr.clear_bound()
    assert ydr.bound is None


def test_declarative_skin_helpers_and_validation(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        material_textures={"DiffuseSampler": "test_diffuse"},
        name="skin_helpers",
    )
    path = tmp_path / "skin_helpers.ydr"
    build.save(path)
    ydr = read_ydr(path)

    root = ydr.bone("root", tag=0)
    child = ydr.bone("child", parent=root, tag=1)
    ydr.ensure_skeleton().build()
    ydr.set_model_skin(0)
    mesh = ydr.meshes[0]
    mesh.set_skin(
        bone_ids=[root, child],
        weights=[
            (1.0, 0.0, 0.0, 0.0),
            (0.5, 0.5, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
        ],
        indices=[
            (0, 0, 0, 0),
            (0, 1, 0, 0),
            (1, 0, 0, 0),
        ],
    )
    assert mesh.is_skinned is True
    assert mesh.bone_ids == [root.tag, child.tag]
    assert ydr.validate().valid

    mesh.set_skin(indices=[(0, 0, 0, 0)])
    issues = ydr.validate()
    assert any(issue.code == "indices_size_mismatch" for issue in issues)


def test_skeleton_roundtrip_preserves_bone_metadata(tmp_path: Path) -> None:
    skeleton = _simple_skeleton().recalculate_unknown_hashes()
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=YdrSkeletonBinding.skinned(),
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="skeleton_meta",
        skeleton=skeleton,
    )

    ydr_path = tmp_path / "skeleton_meta.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.skeleton is not None
    assert ydr.skeleton.parent_indices == [-1, 0]
    assert ydr.skeleton.bones[0].flags == (
        YdrBoneFlags.ROT_X
        | YdrBoneFlags.ROT_Y
        | YdrBoneFlags.ROT_Z
        | YdrBoneFlags.HAS_CHILD
    )
    assert ydr.skeleton.bones[1].parent_index == 0
    assert ydr.skeleton.bones[1].translation.components == pytest.approx((0.0, 0.25, 0.0))
    assert (ydr.skeleton.unknown_50h, ydr.skeleton.unknown_54h, ydr.skeleton.unknown_58h) == skeleton.calculate_unknown_hashes()


def test_ydr_writer_normalizes_root_bone_id(tmp_path: Path) -> None:
    skeleton = YdrSkeleton()
    root = skeleton.bone("root", tag=0xB692)
    child = skeleton.bone("child", parent=root, tag=0x1A7F)
    skeleton.build()
    joints = YdrJoints()
    joints.rotation_limit(bone_id=root.tag)
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=YdrSkeletonBinding.skinned(),
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="root_id_normalized",
        skeleton=skeleton,
        joints=joints,
    )
    build.lods[YdrLod.HIGH][0].meshes[0].bone_ids = [root.tag, child.tag]

    ydr_path = tmp_path / "root_id_normalized.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.skeleton is not None
    assert ydr.skeleton.bones[0].tag == 0
    assert ydr.meshes[0].bone_ids == [0, 1]
    assert ydr.joints is not None
    assert ydr.joints.rotation_limits[0].bone_id == 0


def test_ydr_writer_recalculates_skeleton_unknown_hashes_by_default(tmp_path: Path) -> None:
    skeleton = _hashable_skeleton()
    expected_hashes = skeleton.calculate_unknown_hashes()
    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=YdrSkeletonBinding.skinned(),
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="skeleton_hash_writer",
        skeleton=skeleton,
    )

    recalculated_path = tmp_path / "skeleton_hash_recalculated.ydr"
    build.save(recalculated_path)
    recalculated = read_ydr(recalculated_path)
    assert recalculated.skeleton is not None
    assert (
        recalculated.skeleton.unknown_50h,
        recalculated.skeleton.unknown_54h,
        recalculated.skeleton.unknown_58h,
    ) == expected_hashes

    preserved_path = tmp_path / "skeleton_hash_preserved.ydr"
    build.save(preserved_path, recalculate_skeleton_hashes=False)
    preserved = read_ydr(preserved_path)
    assert preserved.skeleton is not None
    assert (preserved.skeleton.unknown_50h, preserved.skeleton.unknown_54h, preserved.skeleton.unknown_58h) == (0, 0, 0)
    assert (skeleton.unknown_50h, skeleton.unknown_54h, skeleton.unknown_58h) == (0, 0, 0)


def test_joints_roundtrip_preserves_limits(tmp_path: Path) -> None:
    skeleton = _simple_skeleton()
    joints = YdrJoints()
    joints.rotation_limit(
        bone_id=0,
        min=Vector3(-0.1, -0.2, -0.3),
        max=Vector3(0.1, 0.2, 0.3),
        unknown_ah=7,
        num_control_points=2,
        joint_dofs=3,
    )
    joints.translation_limit(
        bone_id=1,
        min=Vector3(-1.0, -2.0, -3.0),
        max=Vector3(1.0, 2.0, 3.0),
    )

    build = YdrBuild(
        lods={YdrLod.HIGH: [YdrModelInput(
            meshes=[_triangle_mesh(material="main")],
        )]},
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="joints_roundtrip",
        skeleton=skeleton,
        joints=joints,
    )

    ydr_path = tmp_path / "joints_roundtrip.ydr"
    build.save(ydr_path)
    system_data, _model_off, _geometry_off = _first_model_offsets(ydr_path.read_bytes())
    joints_ptr = int.from_bytes(system_data[0x90:0x98], "little")
    assert joints_ptr >= 0x50000000

    ydr = read_ydr(ydr_path)

    assert ydr.joints is not None
    assert len(ydr.joints.rotation_limits) == 1
    assert len(ydr.joints.translation_limits) == 1
    assert ydr.joints.rotation_limits[0].bone_id == 0
    assert ydr.joints.rotation_limits[0].unknown_ah == 7
    assert ydr.joints.rotation_limits[0].num_control_points == 2
    assert ydr.joints.rotation_limits[0].joint_dofs == 3
    assert ydr.joints.rotation_limits[0].min.components == pytest.approx((-0.1, -0.2, -0.3))
    assert ydr.joints.rotation_limits[0].max.components == pytest.approx((0.1, 0.2, 0.3))
    assert ydr.joints.translation_limits[0].bone_id == 1
    assert ydr.joints.translation_limits[0].min.components == pytest.approx((-1.0, -2.0, -3.0))
    assert ydr.joints.translation_limits[0].max.components == pytest.approx((1.0, 2.0, 3.0))


def test_joints_validation_detects_unknown_bones() -> None:
    ydr = Ydr(version=165)
    ydr.joints = YdrJoints()
    ydr.joints.rotation_limit(bone_id=77)
    ydr.joints.translation_limit(bone_id=88)

    issues = ydr.validate()

    assert any(issue.code == "missing_skeleton_for_joints" for issue in issues)


def test_skeleton_incremental_and_batch_bone_building() -> None:
    skeleton = YdrSkeleton()
    root = skeleton.bone("root", tag=0)
    child = skeleton.bone("child", parent=root, tag=10)

    assert skeleton.get_bone_by_tag(10) is child
    assert skeleton.get_bone_by_name("CHILD") is child
    assert root.flags & YdrBoneFlags.HAS_CHILD
    assert skeleton.parent_indices == [-1, 0]

    skeleton.bones.extend(
        (
            YdrBone(name="batch_a", tag=20, parent_index=0),
            YdrBone(name="batch_b", tag=30, parent_index=0),
        )
    )
    skeleton.build()

    assert [bone.index for bone in skeleton.bones] == [0, 1, 2, 3]
    assert skeleton.get_bone_by_tag(30).name == "batch_b"
    assert skeleton.bones[2].next_sibling_index == 3


def test_ydr_meshes_include_every_lod_and_primary_meshes_are_explicit() -> None:
    high_mesh = YdrMesh(positions=[Vector3()])
    low_mesh = YdrMesh(positions=[Vector3(10.0, 0.0, 0.0)])
    ydr = Ydr(
        version=165,
        lods={
            YdrLod.HIGH: [YdrModel(YdrLod.HIGH, meshes=[high_mesh])],
            YdrLod.LOW: [YdrModel(YdrLod.LOW, meshes=[low_mesh])],
        },
    )

    assert ydr.meshes == [high_mesh, low_mesh]
    assert ydr.primary_lod is YdrLod.HIGH
    assert ydr.primary_meshes == [high_mesh]
    assert ydr.get_lod_meshes(YdrLod.LOW) == [low_mesh]


@pytest.mark.parametrize(
    ("count", "capacity"),
    [(0, 11), (10, 11), (11, 29), (28, 29), (29, 59), (65167, 65521)],
)
def test_at_hash_bucket_capacity_boundaries(count: int, capacity: int) -> None:
    from fivefury.buckets import at_hash_bucket_capacity

    assert at_hash_bucket_capacity(count) == capacity
