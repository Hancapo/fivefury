from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from pathlib import Path

from ...game_target import GameTarget, coerce_game_target
from ...mesh_source import (
    MeshSource,
    iter_mesh_instances,
    load_mesh_scene,
    mesh_source_name,
)
from ...ytd import Ytd
from ...ytyp import Archetype, Ytyp, cutscene_prop_flags
from ...ytyp.archetypes import ArchetypeAssetType
from ...ytyp.lod import infer_archetype_hd_texture_dist, infer_archetype_lod_dist
from ..build_types import YdrBuild, YdrMaterialInput, YdrMeshInput
from ..builder import save_ydr
from ..defs import YdrLod
from ..gen9_shader_enums import YdrGen9Shader
from ..shader_enums import YdrShader
from ..write_geometry import compute_bounds
from .geometry import mesh_to_ydr_input
from .materials import MaterialRegistry, iter_material_parts, visual_colour

_LEGACY_YDR_VERSION = 165
_ENHANCED_YDR_VERSION = 159


@dataclasses.dataclass(slots=True)
class TrimeshScene:
    meshes: list[YdrMeshInput]
    materials: list[YdrMaterialInput]
    name: str = ""
    embedded_textures: Ytd | None = None

    def to_ydr(
        self,
        *,
        lod: YdrLod | str = YdrLod.HIGH,
        version: int | None = None,
        game: GameTarget | None = None,
    ) -> YdrBuild:
        return YdrBuild.from_meshes(
            meshes=self.meshes,
            materials=self.materials,
            name=self.name,
            lod=lod,
            version=_resolve_target_version(version=version, game=game),
            embedded_textures=self.embedded_textures,
        )


def read_trimesh_scene(
    source: MeshSource,
    *,
    name: str | None = None,
    file_type: str | None = None,
    process: bool = False,
    default_shader: str | YdrShader | YdrGen9Shader = YdrShader.DEFAULT,
    shader: str | YdrShader | YdrGen9Shader | None = None,
    default_colour: tuple[float, float, float, float] | None = None,
    material_colours_as_textures: bool = False,
) -> TrimeshScene:
    source_scene = load_mesh_scene(source, file_type=file_type, process=process)
    registry = MaterialRegistry(
        default_shader=default_shader,
        shader=shader,
        colours_as_textures=material_colours_as_textures,
    )
    meshes: list[YdrMeshInput] = []
    for instance in iter_mesh_instances(source_scene):
        for source_material, slot, face_indices in iter_material_parts(instance.mesh):
            material_name = registry.resolve(
                source_material,
                geometry_name=instance.geometry_name,
                slot=slot,
                colour=visual_colour(instance.mesh),
            )
            meshes.append(
                mesh_to_ydr_input(
                    instance.mesh,
                    instance.transform,
                    material_name,
                    default_colour=default_colour,
                    face_indices=face_indices,
                )
            )

    if not meshes:
        raise ValueError(f"Mesh source {mesh_source_name(source)!r} does not contain triangle meshes")
    return TrimeshScene(
        meshes=meshes,
        materials=registry.materials,
        name=(name or mesh_source_name(source)).lower(),
        embedded_textures=registry.embedded_textures,
    )


def _compute_scene_bounds(
    meshes: Sequence[YdrMeshInput],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]:
    return compute_bounds([position for mesh in meshes for position in mesh.positions])


def _lowercase_output_path(value: str | Path) -> Path:
    path = Path(value)
    return path.with_name(path.name.lower())


def _resolve_target_version(*, version: int | None, game: GameTarget | None) -> int:
    if version is not None:
        return int(version)
    if game is None:
        return _LEGACY_YDR_VERSION
    target_game = coerce_game_target(game)
    if target_game is GameTarget.GTA5:
        return _LEGACY_YDR_VERSION
    if target_game is GameTarget.GTA5_ENHANCED:
        return _ENHANCED_YDR_VERSION
    raise ValueError(f"Unsupported Trimesh-to-YDR target game: {game}")


def _save_companion_ytyp(
    scene: TrimeshScene,
    destination: str | Path,
    *,
    cutscene_prop: bool,
) -> Path:
    target = _lowercase_output_path(destination)
    base_name = target.stem.lower()
    ytyp_name = f"{base_name}_meta"
    centre, bb_min, bb_max, radius = _compute_scene_bounds(scene.meshes)
    lod_dist = infer_archetype_lod_dist(bs_radius=radius, bb_min=bb_min, bb_max=bb_max)
    hd_texture_dist = infer_archetype_hd_texture_dist(
        bs_radius=radius,
        lod_dist=lod_dist,
        bb_min=bb_min,
        bb_max=bb_max,
    )
    ytyp = Ytyp(name=ytyp_name)
    ytyp.archetypes.append(
        Archetype(
            name=base_name,
            asset_name=base_name,
            texture_dictionary=f"{base_name}_txd",
            asset_type=ArchetypeAssetType.DRAWABLE,
            flags=int(cutscene_prop_flags(animated=True)) if cutscene_prop else 0,
            lod_dist=lod_dist,
            hd_texture_dist=hd_texture_dist,
            bb_min=bb_min,
            bb_max=bb_max,
            bs_centre=centre,
            bs_radius=radius,
        )
    )
    return ytyp.save(target.with_name(f"{ytyp_name}.ytyp"))


def trimesh_to_ydr(
    source: MeshSource,
    destination: str | Path | None = None,
    *,
    name: str | None = None,
    file_type: str | None = None,
    process: bool = False,
    default_shader: str | YdrShader | YdrGen9Shader = YdrShader.DEFAULT,
    shader: str | YdrShader | YdrGen9Shader | None = None,
    default_colour: tuple[float, float, float, float] | None = None,
    material_colours_as_textures: bool = False,
    generate_ytyp: bool = False,
    cutscene_prop: bool = False,
    version: int | None = None,
    game: GameTarget | None = None,
) -> YdrBuild:
    scene = read_trimesh_scene(
        source,
        name=name,
        file_type=file_type,
        process=process,
        default_shader=default_shader,
        shader=shader,
        default_colour=default_colour,
        material_colours_as_textures=material_colours_as_textures,
    )
    build = scene.to_ydr(version=version, game=game)
    if destination is None:
        if not isinstance(source, (str, Path)):
            raise ValueError("destination is required for in-memory Trimesh sources")
        destination = Path(source).with_suffix(".ydr")
    result = save_ydr(build, _lowercase_output_path(destination))
    if generate_ytyp:
        _save_companion_ytyp(scene, result, cutscene_prop=cutscene_prop)
    return build


__all__ = ["TrimeshScene", "read_trimesh_scene", "trimesh_to_ydr"]
