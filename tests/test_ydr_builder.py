from __future__ import annotations

from pathlib import Path

from fivefury import (
    YdrBuild,
    YdrMaterialInput,
    YdrMeshInput,
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
    result = obj_to_ydr(obj_path, ydr_path)
    assert result == ydr_path
    ydr = read_ydr(ydr_path)

    assert ydr.materials[0].shader_definition is not None
    assert ydr.materials[0].shader_definition.name == "normal_spec"
    assert ydr.materials[0].texture_names == ["triangle_diffuse", "triangle_normal", "triangle_spec"]
    assert ydr.meshes[0].indices == [0, 1, 2]
