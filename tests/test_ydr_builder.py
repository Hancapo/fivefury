from __future__ import annotations

from pathlib import Path

import pytest

from fivefury import (
    YdrBuild,
    YdrLight,
    YdrLightType,
    YdrMaterialInput,
    YdrMeshInput,
    YdrModelInput,
    create_ydr,
    obj_to_ydr,
    read_obj_scene,
    read_ydr,
)
from fivefury.resource import split_rsc7_sections


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
    assert ydr.meshes[0].normals
    assert not ydr.meshes[0].tangents

    _header, system_data, _graphics_data = split_rsc7_sections(ydr_path.read_bytes())
    assert int.from_bytes(system_data[0x00:0x04], "little") == 0x40570C38
    assert int.from_bytes(system_data[0x04:0x08], "little") == 1
    assert int.from_bytes(system_data[0x08:0x10], "little") != 0
    assert int.from_bytes(system_data[0x10:0x18], "little") != 0
    assert int.from_bytes(system_data[0x50:0x58], "little") != 0
    assert int.from_bytes(system_data[0xA0:0xA8], "little") != 0
    assert int.from_bytes(system_data[0xA8:0xB0], "little") != 0

    model_list_off = int.from_bytes(system_data[0xA0:0xA8], "little") - 0x50000000
    model_off = int.from_bytes(system_data[model_list_off + 0x10 : model_list_off + 0x18], "little") - 0x50000000
    geometry_ptrs_off = int.from_bytes(system_data[model_off + 0x08 : model_off + 0x10], "little") - 0x50000000
    geometry_off = int.from_bytes(system_data[geometry_ptrs_off : geometry_ptrs_off + 0x08], "little") - 0x50000000
    vertex_buffer_off = int.from_bytes(system_data[geometry_off + 0x18 : geometry_off + 0x20], "little") - 0x50000000
    index_buffer_off = int.from_bytes(system_data[geometry_off + 0x38 : geometry_off + 0x40], "little") - 0x50000000

    assert int.from_bytes(system_data[model_off + 0x00 : model_off + 0x04], "little") == 0x40610A78
    assert int.from_bytes(system_data[geometry_off + 0x00 : geometry_off + 0x04], "little") == 0x40618868
    assert int.from_bytes(system_data[vertex_buffer_off + 0x00 : vertex_buffer_off + 0x04], "little") == 0x4061D3E8
    assert int.from_bytes(system_data[index_buffer_off + 0x00 : index_buffer_off + 0x04], "little") == 0x406131D8
    assert system_data[vertex_buffer_off + 0x10 : vertex_buffer_off + 0x18] == system_data[vertex_buffer_off + 0x20 : vertex_buffer_off + 0x28]


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
        models=[
            YdrModelInput(meshes=[_offset_triangle_mesh(0.0, material="main")], render_mask=1),
            YdrModelInput(meshes=[_offset_triangle_mesh(2.0, material="main")], render_mask=2),
        ],
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
    assert len(ydr.get_lod("high")) == 2
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


def test_build_and_read_ydr_lights(tmp_path: Path) -> None:
    build = YdrBuild(
        models=[YdrModelInput(meshes=[_triangle_mesh(material="main")])],
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


def test_skinned_mesh_builds_and_reads(tmp_path: Path) -> None:
    build = YdrBuild(
        models=[YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=0x0000FF00,
        )],
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="skinned_tri",
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
    assert model.skeleton_binding == 0x0000FF00


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
        models=[YdrModelInput(
            meshes=[_skinned_triangle_mesh(material="main")],
            skeleton_binding=0x0000FF00,
        )],
        materials=[
            YdrMaterialInput(
                name="main",
                shader="default.sps",
                textures={"DiffuseSampler": "test_diffuse"},
            )
        ],
        name="roundtrip_skin",
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
