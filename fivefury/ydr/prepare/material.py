from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from ..build_types import (
    MaterialParameterValue,
    TextureInputValue,
    YdrMaterialInput,
    YdrTextureInput,
)
from ..gen9 import ShaderGen9Definition
from ..gen9_shader_enums import YdrGen9Shader
from ..shader_enums import YdrShader
from ..shaders import ShaderDefinition, ShaderLibrary, ShaderParameterDefinition

_TEXTURE_SLOT_ALIASES = {
    "SPECULARSAMPLER": "SpecSampler",
}


@dataclasses.dataclass(slots=True)
class PreparedMaterial:
    index: int
    name: str
    shader_definition: ShaderDefinition
    shader_file_name: str
    render_bucket: int
    textures: dict[str, YdrTextureInput | None]
    parameters: dict[str, MaterialParameterValue]
    gen9_definition: ShaderGen9Definition | None = None


@dataclasses.dataclass(slots=True)
class ShaderParameterEntry:
    definition: ShaderParameterDefinition
    data_type: int
    data_pointer: int = 0
    inline_data: bytes = b""


def coerce_texture_name(value: str | Path) -> str:
    text = str(value).strip().replace("\\", "/")
    candidate = Path(text)
    stem = candidate.stem
    return stem or candidate.name or text


def coerce_texture_input(
    value: str | Path | YdrTextureInput | None,
) -> YdrTextureInput | None:
    if value is None:
        return None
    if isinstance(value, YdrTextureInput):
        return YdrTextureInput(
            name=coerce_texture_name(value.name),
            embedded=bool(value.embedded),
            source=value.source,
        )
    return YdrTextureInput(name=coerce_texture_name(value))


def normalize_material_textures(
    textures: Mapping[str, str | Path | YdrTextureInput | None],
) -> dict[str, YdrTextureInput | None]:
    normalized: dict[str, YdrTextureInput | None] = {}
    for slot, value in textures.items():
        slot_name = str(slot).strip()
        slot_name = _TEXTURE_SLOT_ALIASES.get(slot_name.upper(), slot_name)
        normalized[slot_name] = coerce_texture_input(value)
    return normalized


def normalize_materials(
    materials: Sequence[YdrMaterialInput] | None,
    *,
    shader: str | YdrShader | YdrGen9Shader,
    material_textures: Mapping[str, str | Path | YdrTextureInput | None] | None,
) -> list[YdrMaterialInput]:
    if materials is not None and material_textures is not None:
        raise ValueError("Pass either materials= or material_textures=, not both")
    if materials is not None:
        return [
            YdrMaterialInput(
                name=material.name,
                shader=material.shader,
                layout_shader=material.layout_shader,
                textures=dict(material.textures),
                parameters=dict(material.parameters),
                render_bucket=int(material.render_bucket),
                gen9_definition=material.gen9_definition,
            )
            for material in materials
        ]

    default_textures: dict[str, str | Path | YdrTextureInput | None] = {}
    if material_textures is not None:
        default_textures.update(dict(material_textures))
    return [YdrMaterialInput(name="default", shader=shader, textures=default_textures)]


class MaterialPreparer(Protocol):
    def __call__(
        self,
        materials: Sequence[YdrMaterialInput],
        shader_library: ShaderLibrary,
        *,
        prepared_material_cls: type[PreparedMaterial],
        normalize_material_textures: Callable[
            [Mapping[str, TextureInputValue]], dict[str, YdrTextureInput | None]
        ],
        resolve_shader: Callable[
            [str | YdrShader, int, ShaderLibrary], tuple[ShaderDefinition, str, int]
        ],
    ) -> tuple[list[PreparedMaterial], dict[str, int]]: ...
