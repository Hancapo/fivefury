from __future__ import annotations

from pathlib import Path

from .assimp import AssimpScene, assimp_to_ydr, read_assimp_scene
from .build_types import YdrBuild
from .gen9_shader_enums import YdrGen9Shader
from .shader_enums import YdrShader
from ..game_target import GameTarget


def read_fbx_scene(
    source: str | Path,
    *,
    default_shader: str | YdrShader | YdrGen9Shader = "default.sps",
    shader: str | YdrShader | YdrGen9Shader | None = None,
    processing: int | None = None,
) -> AssimpScene:
    return read_assimp_scene(
        source,
        default_shader=default_shader,
        shader=shader,
        processing=processing,
    )


def fbx_to_ydr(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    default_shader: str | YdrShader | YdrGen9Shader = "default.sps",
    shader: str | YdrShader | YdrGen9Shader | None = None,
    processing: int | None = None,
    generate_ytyp: bool = False,
    version: int | None = None,
    game: GameTarget | None = None,
) -> YdrBuild:
    return assimp_to_ydr(
        source,
        destination,
        default_shader=default_shader,
        shader=shader,
        processing=processing,
        generate_ytyp=generate_ytyp,
        version=version,
        game=game,
    )


__all__ = [
    "fbx_to_ydr",
    "read_fbx_scene",
]
