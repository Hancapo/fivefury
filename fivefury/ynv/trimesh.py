from __future__ import annotations

from pathlib import Path

import numpy

from ..game_target import GameTarget
from ..matrix import gta_source_transform, transform_position_array
from ..mesh_source import (
    MeshSource,
    iter_mesh_instances,
    load_mesh_scene,
    mesh_source_name,
    mesh_triangles,
    mesh_vertices,
)
from .authoring import YnvSourcePolygon, build_ynv_cells, get_ynv_file_coords
from .model import Ynv


def _scene_polygons(
    source: MeshSource, *, file_type: str | None, process: bool
) -> list[YnvSourcePolygon]:
    scene = load_mesh_scene(source, file_type=file_type, process=process)
    polygons: list[YnvSourcePolygon] = []
    for instance in iter_mesh_instances(scene):
        mesh = instance.mesh
        try:
            vertices = mesh_vertices(mesh)
            faces = mesh_triangles(mesh)
        except ValueError as exc:
            raise ValueError(f"Mesh {instance.geometry_name!r}: {exc}") from exc
        transform = gta_source_transform(instance.transform)
        positions = transform_position_array(vertices, transform)
        if numpy.linalg.det(transform[:3, :3]) < 0.0:
            faces = faces[:, ::-1]
        for face_index, face_positions in enumerate(positions[faces].tolist()):
            polygons.append(
                YnvSourcePolygon(
                    vertices=face_positions,
                    source_key=(instance.node_name, instance.geometry_name, face_index),
                )
            )
    if not polygons:
        raise ValueError(
            f"Mesh source {mesh_source_name(source)!r} does not contain triangles"
        )
    return polygons


def trimesh_to_ynvs(
    source: MeshSource,
    destination: str | Path | None = None,
    *,
    game: str | GameTarget = GameTarget.GTA5,
    file_type: str | None = None,
    process: bool = False,
) -> list[Ynv] | list[Path]:
    ynvs = [
        ynv
        for ynv, _ in build_ynv_cells(
            _scene_polygons(source, file_type=file_type, process=process),
            source_path=str(source)
            if isinstance(source, (str, Path))
            else mesh_source_name(source),
            game=game,
        )
    ]
    if destination is None:
        return ynvs

    output_dir = Path(destination)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    for ynv in ynvs:
        file_x, file_y = get_ynv_file_coords(
            ynv.area_id % 100,
            ynv.area_id // 100,
        )
        path = output_dir / f"navmesh[{file_x}][{file_y}].ynv"
        ynv.save(path)
        saved_paths.append(path)
    return saved_paths


__all__ = ["trimesh_to_ynvs"]
