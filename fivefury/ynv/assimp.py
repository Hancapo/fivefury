from __future__ import annotations

from pathlib import Path

from ..game_target import GameTarget
from ..ydr.assimp import AssimpScene, read_assimp_scene
from .authoring import YnvSourcePolygon, build_ynv_cells, get_ynv_file_coords
from .model import Ynv


def _iter_scene_triangles(scene: AssimpScene) -> list[YnvSourcePolygon]:
    triangles: list[YnvSourcePolygon] = []
    for mesh in scene.meshes:
        for index in range(0, len(mesh.indices), 3):
            triangle_indices = mesh.indices[index : index + 3]
            if len(triangle_indices) != 3:
                continue
            triangles.append(
                YnvSourcePolygon(
                    vertices=[
                        mesh.positions[int(vertex_index)]
                        for vertex_index in triangle_indices
                    ],
                    source_key=(id(mesh), index // 3),
                )
            )
    return triangles


def assimp_to_ynvs(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    game: str | GameTarget = GameTarget.GTA5,
    processing: int | None = None,
) -> list[Ynv] | list[Path]:
    scene = read_assimp_scene(source, processing=processing)
    ynvs = [
        ynv
        for ynv, _ in build_ynv_cells(
            _iter_scene_triangles(scene),
            source_path=str(source),
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


def obj_to_nav(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    game: str | GameTarget = GameTarget.GTA5,
    processing: int | None = None,
) -> list[Ynv] | list[Path]:
    return assimp_to_ynvs(source, destination, game=game, processing=processing)


__all__ = ["assimp_to_ynvs", "obj_to_nav"]
