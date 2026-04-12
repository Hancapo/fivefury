from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import (
    BoundSphere,
    BoundType,
    Texture,
    TextureFormat,
    Ydr,
    YdrBone,
    YdrBoneFlags,
    YdrBuild,
    YdrJoints,
    YdrLight,
    YdrLightType,
    YdrLod,
    YdrRenderMask,
    YdrSkeletonBinding,
    YdrMaterialInput,
    YdrMeshInput,
    YdrModelInput,
    YdrSkeleton,
    Ytd,
    calculate_bone_tag,
    create_ydr,
    obj_to_ydr,
    read_obj_scene,
    read_ydr,
)
from fivefury.resource import split_rsc7_sections

_TEXTURE_BASE_VFT = 0x40617568


def _triangle_mesh(material: str = "default") -> YdrMeshInput:
    return YdrMeshInput(
        positions=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
        indices=[0, 1, 2],
        material=material,
        texcoords=[
            [
                (0.0, 0.0),
                (1.0, 0.0),
                (0.0, 1.0),
            ]
        ],
    )


def _offset_triangle_mesh(offset_x: float, material: str = "default") -> YdrMeshInput:
    return YdrMeshInput(
        positions=[
            (0.0 + offset_x, 0.0, 0.0),
            (1.0 + offset_x, 0.0, 0.0),
            (0.0 + offset_x, 1.0, 0.0),
        ],
        indices=[0, 1, 2],
        material=material,
        texcoords=[
            [
                (0.0, 0.0),
                (1.0, 0.0),
                (0.0, 1.0),
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


def test_create_ydr_builds_default_shader_resource(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        texture="test_diffuse",
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


def test_create_ydr_writes_legacy_texture_base_contract(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        texture="test_diffuse",
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
    skeleton = YdrSkeleton.create()
    root_bone = skeleton.add_bone("root")
    joints = YdrJoints()
    joints.add_rotation_limit(
        bone_id=root_bone.tag,
        min=(-1.0, -0.5, -0.25),
        max=(1.0, 0.5, 0.25),
        unknown_ah=7,
        num_control_points=2,
        joint_dofs=3,
    )
    joints.add_translation_limit(
        bone_id=root_bone.tag,
        min=(-0.1, -0.2, -0.3),
        max=(0.1, 0.2, 0.3),
    )
    build = create_ydr(
        meshes=[_triangle_mesh()],
        texture="test_diffuse",
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
    assert ydr.joints.rotation_limits[0].min == pytest.approx((-1.0, -0.5, -0.25))
    assert ydr.joints.rotation_limits[0].max == pytest.approx((1.0, 0.5, 0.25))
    assert ydr.joints.translation_limits[0].bone_id == root_bone.tag
    assert ydr.joints.translation_limits[0].min == pytest.approx((-0.1, -0.2, -0.3))
    assert ydr.joints.translation_limits[0].max == pytest.approx((0.1, 0.2, 0.3))


def test_roundtrip_real_ydr_without_embedded_textures_stays_system_only(tmp_path: Path) -> None:
    source_path = Path(
        r"C:\txData\FiveMBasicServerCFXDefault_F95623.base\resources\anderius\stream\funplace2\bigbugboard.ydr"
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
        texture="test_diffuse",
        render_mask=YdrRenderMask.SHELL,
        name="triangle_shell",
    )

    ydr_path = tmp_path / "triangle_shell.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.get_model(0).render_mask == int(YdrRenderMask.SHELL)


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


def test_obj_to_ydr_roundtrip_with_mtl(tmp_path: Path) -> None:
    obj_path = tmp_path / "triangle.obj"
    mtl_path = tmp_path / "triangle.mtl"
    obj_path.write_text(
        "\n".join(
            [
                "mtllib triangle.mtl",
                "v 0.0 0.0 0.0",
                "v 1.0 0.0 0.0",
                "v 0.0 1.0 0.0",
                "vt 0.0 0.0",
                "vt 1.0 0.0",
                "vt 0.0 1.0",
                "usemtl triangle_mat",
                "f 1/1 2/2 3/3",
            ]
        ),
        encoding="utf-8",
    )
    mtl_path.write_text(
        "\n".join(
            [
                "newmtl triangle_mat",
                "map_Kd triangle_diffuse.dds",
                "map_Bump triangle_normal.dds",
                "map_Ks triangle_spec.dds",
            ]
        ),
        encoding="utf-8",
    )

    scene = read_obj_scene(obj_path)
    assert scene.materials[0].shader == "normal_spec.sps"
    assert scene.materials[0].textures["DiffuseSampler"] == "triangle_diffuse"
    assert scene.materials[0].textures["BumpSampler"] == "triangle_normal"
    assert scene.materials[0].textures["SpecSampler"] == "triangle_spec"

    ydr_path = tmp_path / "triangle_obj.ydr"
    build = obj_to_ydr(obj_path, ydr_path)
    assert isinstance(build, YdrBuild)
    assert ydr_path.exists()
    ydr = read_ydr(ydr_path)

    assert ydr.materials[0].shader_definition is not None
    assert ydr.materials[0].shader_definition.name == "normal_spec"
    assert ydr.materials[0].texture_names == ["triangle_diffuse", "triangle_normal", "triangle_spec"]
    assert ydr.meshes[0].indices == [0, 1, 2]


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
                position=(1.0, 2.0, 3.0),
                color=(10, 20, 30),
                intensity=4.5,
                light_type=YdrLightType.SPOT,
                falloff=15.0,
                volume_outer_color=(40, 50, 60),
                light_hash=77,
                direction=(0.0, 0.0, -1.0),
                tangent=(1.0, 0.0, 0.0),
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
    assert light.position == pytest.approx((1.0, 2.0, 3.0))
    assert light.color == (10, 20, 30)
    assert light.intensity == pytest.approx(4.5)
    assert light.light_type is YdrLightType.SPOT
    assert light.falloff == pytest.approx(15.0)
    assert light.volume_outer_color == (40, 50, 60)
    assert light.light_hash == 77
    assert light.direction == pytest.approx((0.0, 0.0, -1.0))
    assert light.tangent == pytest.approx((1.0, 0.0, 0.0))
    assert light.cone_inner_angle == pytest.approx(0.25)
    assert light.cone_outer_angle == pytest.approx(0.5)
    assert light.projected_texture_hash == 0x12345678


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
    ydr = read_ydr(ydr_path)

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
    ydr = read_ydr(ydr_path)

    assert ydr.embedded_textures is not None
    assert ydr.embedded_textures.game == "gta5_enhanced"
    assert ydr.embedded_textures.names() == ["embedded_diffuse"]


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
            box_min=(-1.0, -1.0, -1.0),
            box_max=(1.0, 1.0, 1.0),
            box_center=(0.0, 0.0, 0.0),
            sphere_center=(0.0, 0.0, 0.0),
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
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
        indices=[0, 1, 2],
        material=material,
        texcoords=[
            [
                (0.0, 0.0),
                (1.0, 0.0),
                (0.0, 1.0),
            ]
        ],
        blend_weights=[
            (1.0, 0.0, 0.0, 0.0),
            (0.5, 0.5, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
        ],
        blend_indices=[
            (0, 0, 0, 0),
            (0, 1, 0, 0),
            (1, 0, 0, 0),
        ],
        bone_ids=[0, 1],
    )


def _simple_skeleton() -> YdrSkeleton:
    skeleton = YdrSkeleton.create()
    root = skeleton.add_bone(
        "root",
        tag=0,
        flags=YdrBoneFlags.ROT_X | YdrBoneFlags.ROT_Y | YdrBoneFlags.ROT_Z,
    )
    skeleton.add_bone(
        "child",
        parent=root,
        tag=1,
        flags=YdrBoneFlags.ROT_X | YdrBoneFlags.ROT_Y | YdrBoneFlags.ROT_Z,
        translation=(0.0, 0.25, 0.0),
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
    skeleton = YdrSkeleton.create()
    root = skeleton.add_bone("root")
    child = skeleton.add_bone("child", parent="root", translation=(0.0, 1.0, 0.0))
    skeleton.build()

    assert root.index == 0
    assert child.index == 1
    assert child.parent_index == 0
    assert skeleton.parent_indices == [-1, 0]
    assert root.next_sibling_index == -1
    assert child.tag == calculate_bone_tag("child")
    assert skeleton.require_bone("child") is child
    assert skeleton.require_bone(child.tag) is child

    ydr = Ydr(version=165)
    bone = ydr.add_bone("weapon_root")
    assert ydr.has_skeleton is True
    assert bone.name == "weapon_root"
    assert ydr.get_bone_by_name("weapon_root") is bone


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
    assert model.skeleton_binding == YdrSkeletonBinding.skinned()
    assert ydr.has_skeleton is True
    assert ydr.skeleton is not None
    assert ydr.skeleton.bone_count == 2
    assert ydr.get_bone_by_name("root") is not None
    assert ydr.get_bone_by_tag(1) is not None
    assert [bone.name for bone in mesh.resolve_bones(ydr.skeleton)] == ["root", "child"]


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
        texture="test_diffuse",
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

    assert int.from_bytes(system_data[model_off + 0x28 : model_off + 0x2C], "little") == 0x00000111
    assert system_data[model_off + 0x28 : model_off + 0x2C] == bytes((0x11, 0x01, 0x00, 0x00))


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
        skeleton=_simple_skeleton(),
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

    two_bone_ptr = int.from_bytes(system_data[geometry_offsets[1] + 0x68 : geometry_offsets[1] + 0x70], "little")
    assert _virtual_to_offset(two_bone_ptr) == geometry_offsets[1] + 0x98
    assert int.from_bytes(system_data[geometry_offsets[1] + 0x72 : geometry_offsets[1] + 0x74], "little") == 2
    assert system_data[geometry_offsets[1] + 0x98 : geometry_offsets[1] + 0x9C] == b"\x00\x00\x01\x00"

    five_bone_ptr = int.from_bytes(system_data[geometry_offsets[2] + 0x68 : geometry_offsets[2] + 0x70], "little")
    assert _virtual_to_offset(five_bone_ptr) == geometry_offsets[2] + 0xA0
    assert int.from_bytes(system_data[geometry_offsets[2] + 0x72 : geometry_offsets[2] + 0x74], "little") == 5
    assert system_data[geometry_offsets[2] + 0x98 : geometry_offsets[2] + 0xA0] == b"\x00" * 8
    assert system_data[geometry_offsets[2] + 0xA0 : geometry_offsets[2] + 0xAA] == b"\x00\x00\x01\x00\x02\x00\x03\x00\x04\x00"


def test_geometry_fixed_fields_match_expected_defaults(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        texture="test_diffuse",
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
            box_min=(-0.5, -0.5, -0.5),
            box_max=(0.5, 0.5, 0.5),
            box_center=(0.0, 0.0, 0.0),
            sphere_center=(0.0, 0.0, 0.0),
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
        texture="test_diffuse",
        name="helper_case",
    )
    path = tmp_path / "helper_case.ydr"
    build.save(path)
    ydr = read_ydr(path)

    added = ydr.add_embedded_texture(
        name="helper_embedded",
        data=bytes([0, 255, 0, 255] * 16),
        width=4,
        height=4,
        format=TextureFormat.A8R8G8B8,
    )
    assert added.name == "helper_embedded"
    assert ydr.get_embedded_texture("helper_embedded") is not None

    ydr.add_embedded_texture(
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

    ydr.set_bound(
        BoundSphere(
            bound_type=BoundType.SPHERE,
            box_min=(-1.0, -1.0, -1.0),
            box_max=(1.0, 1.0, 1.0),
            box_center=(0.0, 0.0, 0.0),
            sphere_center=(0.0, 0.0, 0.0),
            sphere_radius=1.0,
            margin=0.0,
        )
    )
    assert isinstance(ydr.bound, BoundSphere)
    ydr.clear_bound()
    assert ydr.bound is None


def test_declarative_skin_helpers_and_validation(tmp_path: Path) -> None:
    build = create_ydr(
        meshes=[_triangle_mesh()],
        texture="test_diffuse",
        name="skin_helpers",
    )
    path = tmp_path / "skin_helpers.ydr"
    build.save(path)
    ydr = read_ydr(path)

    root = ydr.add_bone("root", tag=0)
    child = ydr.add_bone("child", parent=root, tag=1)
    ydr.ensure_skeleton().build()
    model = ydr.set_model_skin(0)
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
    assert ydr.validate() == []

    mesh.set_skin(indices=[(0, 0, 0, 0)])
    issues = ydr.validate()
    assert any(issue.code == "indices_size_mismatch" for issue in issues)


def test_skeleton_roundtrip_preserves_bone_metadata(tmp_path: Path) -> None:
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
        skeleton=_simple_skeleton(),
    )

    ydr_path = tmp_path / "skeleton_meta.ydr"
    build.save(ydr_path)
    ydr = read_ydr(ydr_path)

    assert ydr.skeleton is not None
    assert ydr.skeleton.parent_indices == [-1, 0]
    assert ydr.skeleton.bones[0].flags == (YdrBoneFlags.ROT_X | YdrBoneFlags.ROT_Y | YdrBoneFlags.ROT_Z)
    assert ydr.skeleton.bones[1].parent_index == 0
    assert ydr.skeleton.bones[1].translation == pytest.approx((0.0, 0.25, 0.0))


def test_joints_roundtrip_preserves_limits(tmp_path: Path) -> None:
    skeleton = _simple_skeleton()
    joints = YdrJoints()
    joints.add_rotation_limit(
        bone_id=0,
        min=(-0.1, -0.2, -0.3),
        max=(0.1, 0.2, 0.3),
        unknown_ah=7,
        num_control_points=2,
        joint_dofs=3,
    )
    joints.add_translation_limit(
        bone_id=1,
        min=(-1.0, -2.0, -3.0),
        max=(1.0, 2.0, 3.0),
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
    assert ydr.joints.rotation_limits[0].min == pytest.approx((-0.1, -0.2, -0.3))
    assert ydr.joints.rotation_limits[0].max == pytest.approx((0.1, 0.2, 0.3))
    assert ydr.joints.translation_limits[0].bone_id == 1
    assert ydr.joints.translation_limits[0].min == pytest.approx((-1.0, -2.0, -3.0))
    assert ydr.joints.translation_limits[0].max == pytest.approx((1.0, 2.0, 3.0))


def test_joints_validation_detects_unknown_bones() -> None:
    ydr = Ydr(version=165)
    ydr.joints = YdrJoints()
    ydr.joints.add_rotation_limit(bone_id=77)
    ydr.joints.add_translation_limit(bone_id=88)

    issues = ydr.validate()

    assert any(issue.code == "missing_skeleton_for_joints" for issue in issues)
