from __future__ import annotations

from fivefury import (
    Cdr,
    CdrLod,
    CdrMaterial,
    CdrMaterialParameter,
    CdrMesh,
    CdrModel,
    DrawableAsset,
    DrawableLod,
    DrawableMaterial,
    DrawableMesh,
    DrawableModel,
    DrawableParameter,
    Ydr,
    YdrLod,
    YdrMaterial,
    YdrMaterialParameterRef,
    YdrMesh,
    YdrModel,
    YdrTextureRef,
)
from fivefury.drawable import load_shader_library
from fivefury.hashing import jenk_hash


def test_formats_share_drawable_domain_types() -> None:
    assert YdrLod is DrawableLod
    assert CdrLod is DrawableLod
    assert issubclass(Ydr, DrawableAsset)
    assert issubclass(Cdr, DrawableAsset)
    assert issubclass(YdrModel, DrawableModel)
    assert issubclass(CdrModel, DrawableModel)
    assert issubclass(YdrMesh, DrawableMesh)
    assert issubclass(CdrMesh, DrawableMesh)
    assert issubclass(YdrMaterial, DrawableMaterial)
    assert issubclass(CdrMaterial, DrawableMaterial)
    assert issubclass(YdrMaterialParameterRef, DrawableParameter)
    assert issubclass(CdrMaterialParameter, DrawableParameter)


def test_common_lod_queries_accept_platform_spellings() -> None:
    model = YdrModel(lod=DrawableLod.MEDIUM)
    drawable = Ydr(version=165, lods={DrawableLod.MEDIUM: [model]}, lod_distances={DrawableLod.MEDIUM: 100.0})

    assert drawable.get_lod("med") == [model]
    assert drawable.get_lod("medium") == [model]
    assert drawable.primary_lod is DrawableLod.MEDIUM


def test_common_material_mesh_and_asset_queries() -> None:
    parameter = CdrMaterialParameter(
        name="DiffuseSampler",
        name_hash=jenk_hash("DiffuseSampler"),
        texture_name="shared_diffuse",
    )
    material = CdrMaterial(
        index=0,
        name="shared",
        shader_hash=jenk_hash("default"),
        shader_name="default",
        shader_file_name="default.sps",
        material_hash=jenk_hash("default.sps"),
        render_bucket=0,
        draw_bucket_mask=0,
        parameters=[parameter],
    )
    mesh = CdrMesh(geometry_type=0, material_index=0, material=material, positions=[(0.0, 0.0, 0.0)], indices=[0])
    model = CdrModel(lod=CdrLod.HIGH, index=0, meshes=[mesh])
    drawable = Cdr(version=164, path="shared.cdr", materials=[material], lods={CdrLod.HIGH: [model]})

    assert material.get_parameter("diffusesampler") is parameter
    assert material.primary_texture_name == "shared_diffuse"
    assert mesh.vertex_count == 1
    assert mesh.index_count == 1
    assert model.materials == [material]
    assert drawable.models == [model]
    assert drawable.meshes == [mesh]
    assert drawable.texture_names == ["shared_diffuse"]
    assert drawable.get_material("default") is material


def test_ydr_material_uses_common_texture_queries() -> None:
    texture = YdrTextureRef(name="legacy_diffuse", parameter_name="DiffuseSampler")
    parameter = YdrMaterialParameterRef(
        name="DiffuseSampler",
        name_hash=jenk_hash("DiffuseSampler"),
        type_name="Texture",
        texture=texture,
    )
    material = YdrMaterial(index=0, name="legacy", textures=[texture], parameters=[parameter])

    assert material.texture_names == ["legacy_diffuse"]
    assert material.primary_texture_name == "legacy_diffuse"


def test_shared_shader_catalog_is_format_neutral() -> None:
    library = load_shader_library()

    shader = library.get_shader("normal_spec")
    assert shader is not None
    assert shader.get_parameter("DiffuseSampler") is not None
