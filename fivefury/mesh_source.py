from __future__ import annotations

import dataclasses
import io
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, TypeAlias

import numpy
import trimesh

MeshSource: TypeAlias = (
    str
    | Path
    | bytes
    | bytearray
    | memoryview
    | BinaryIO
    | trimesh.Scene
    | trimesh.Trimesh
)


@dataclasses.dataclass(frozen=True, slots=True)
class MeshInstance:
    node_name: str
    geometry_name: str
    mesh: trimesh.Trimesh
    transform: numpy.ndarray


def supported_mesh_formats() -> tuple[str, ...]:
    return tuple(sorted(str(value).lower() for value in trimesh.available_formats()))


def _normalize_file_type(value: str) -> str:
    return value.strip().lower().lstrip(".")


def _path_file_type(path: Path) -> str:
    name = path.name.lower()
    matches = [value for value in supported_mesh_formats() if name.endswith(f".{value}")]
    if not matches:
        supported = ", ".join(supported_mesh_formats())
        raise ValueError(
            f"Trimesh does not support mesh source suffix {path.suffix!r}; "
            f"available formats: {supported}"
        )
    return max(matches, key=len)


def load_mesh_scene(
    source: MeshSource,
    *,
    file_type: str | None = None,
    process: bool = False,
) -> trimesh.Scene:
    if isinstance(source, trimesh.Scene):
        return source
    if isinstance(source, trimesh.Trimesh):
        return trimesh.Scene(source)

    resolved_type = _normalize_file_type(file_type) if file_type else None
    file_obj: object = source
    if isinstance(source, (bytes, bytearray, memoryview)):
        if resolved_type is None:
            raise ValueError("file_type is required when loading mesh bytes")
        file_obj = io.BytesIO(bytes(source))
    elif isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(path)
        resolved_type = resolved_type or _path_file_type(path)
        file_obj = path

    if resolved_type is not None and resolved_type not in supported_mesh_formats():
        raise ValueError(f"Trimesh does not support mesh file type {resolved_type!r}")

    try:
        return trimesh.load_scene(
            file_obj,
            file_type=resolved_type,
            process=bool(process),
            maintain_order=not process,
        )
    except NotImplementedError as exc:
        source_type = resolved_type or "unknown"
        raise ValueError(f"Trimesh does not support mesh file type {source_type!r}") from exc


def iter_mesh_instances(scene: trimesh.Scene) -> Iterator[MeshInstance]:
    for node_name in scene.graph.nodes_geometry:
        transform, geometry_name = scene.graph[node_name]
        geometry = scene.geometry.get(geometry_name)
        if not isinstance(geometry, trimesh.Trimesh):
            continue
        matrix = numpy.asarray(transform, dtype=numpy.float64)
        if matrix.shape != (4, 4) or not numpy.isfinite(matrix).all():
            raise ValueError(f"Scene node {node_name!r} has an invalid transform")
        yield MeshInstance(
            node_name=str(node_name),
            geometry_name=str(geometry_name),
            mesh=geometry,
            transform=matrix,
        )


def mesh_source_name(source: MeshSource, *, fallback: str = "mesh") -> str:
    if isinstance(source, (str, Path)):
        return Path(source).stem.lower()
    if isinstance(source, trimesh.Scene):
        name = source.metadata.get("name")
        if name:
            return str(name).strip().lower()
    if isinstance(source, trimesh.Trimesh):
        name = source.metadata.get("name")
        if name:
            return str(name).strip().lower()
    stream_name = getattr(source, "name", None)
    if stream_name:
        return Path(str(stream_name)).stem.lower()
    return fallback


__all__ = [
    "MeshInstance",
    "MeshSource",
    "iter_mesh_instances",
    "load_mesh_scene",
    "mesh_source_name",
    "supported_mesh_formats",
]
