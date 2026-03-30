from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import YdrMaterial, YdrTextureRef


@dataclasses.dataclass(slots=True, frozen=True)
class YdrMaterialLayout:
    type_name: str
    semantics: tuple[str, ...]

    def has_semantic(self, name: str) -> bool:
        return str(name) in self.semantics


@dataclasses.dataclass(slots=True)
class YdrMaterialParameter:
    name: str
    name_hash: int = 0
    type_name: str | None = None
    subtype: str | None = None
    uv_index: int | None = None
    count: int = 1
    hidden: bool = False
    defaults: dict[str, str] = dataclasses.field(default_factory=dict)
    texture: YdrTextureRef | None = None

    @property
    def is_texture(self) -> bool:
        return (self.type_name or "").lower() == "texture"

    @property
    def is_bound(self) -> bool:
        return self.texture is not None

    @property
    def texture_name(self) -> str | None:
        if self.texture is None:
            return None
        return self.texture.name

    @property
    def texture_name_hash(self) -> int:
        if self.texture is None:
            return 0
        return int(self.texture.name_hash)


@dataclasses.dataclass(slots=True)
class YdrMaterialDescriptor:
    material_index: int
    shader_name: str | None = None
    shader_name_hash: int = 0
    shader_file_name: str | None = None
    shader_file_hash: int = 0
    render_bucket: int = 0
    parameters: tuple[YdrMaterialParameter, ...] = ()
    layouts: tuple[YdrMaterialLayout, ...] = ()

    @property
    def texture_slots(self) -> tuple[YdrMaterialParameter, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.is_texture)

    @property
    def bound_textures(self) -> tuple[YdrMaterialParameter, ...]:
        return tuple(parameter for parameter in self.texture_slots if parameter.is_bound)

    @property
    def texture_names(self) -> list[str]:
        return [parameter.texture_name for parameter in self.bound_textures if parameter.texture_name]

    @property
    def expected_semantics(self) -> tuple[str, ...]:
        seen: set[str] = set()
        ordered: list[str] = []
        for layout in self.layouts:
            for semantic in layout.semantics:
                if semantic in seen:
                    continue
                seen.add(semantic)
                ordered.append(semantic)
        return tuple(ordered)

    def get_parameter(self, value: str | int) -> YdrMaterialParameter | None:
        if isinstance(value, str):
            lowered = value.lower()
            for parameter in self.parameters:
                if parameter.name.lower() == lowered:
                    return parameter
            return None
        hash_value = int(value)
        for parameter in self.parameters:
            if parameter.name_hash == hash_value:
                return parameter
        return None

    def get_texture(self, value: str | int) -> YdrMaterialParameter | None:
        parameter = self.get_parameter(value)
        if parameter is None or not parameter.is_texture:
            return None
        return parameter


def build_material_descriptor(material: YdrMaterial) -> YdrMaterialDescriptor:
    from .model import YdrTextureRef

    parameters: list[YdrMaterialParameter] = []
    used_textures: set[int] = set()

    shader_definition = material.shader_definition
    if shader_definition is not None:
        for definition in shader_definition.parameters:
            texture = material.get_texture(definition.name_hash) or material.get_texture(definition.name)
            if texture is not None:
                used_textures.add(id(texture))
            parameters.append(
                YdrMaterialParameter(
                    name=definition.name,
                    name_hash=definition.name_hash,
                    type_name=definition.type_name,
                    subtype=definition.subtype,
                    uv_index=definition.uv_index,
                    count=definition.count,
                    hidden=definition.hidden,
                    defaults=dict(definition.defaults),
                    texture=texture,
                )
            )

    for texture in material.textures:
        if id(texture) in used_textures:
            continue
        fallback_name = texture.parameter_name or (f"hash_{texture.parameter_hash:08X}" if texture.parameter_hash else texture.name)
        parameters.append(
            YdrMaterialParameter(
                name=fallback_name,
                name_hash=int(texture.parameter_hash),
                type_name=texture.parameter_type or "Texture",
                uv_index=texture.uv_index,
                hidden=texture.hidden,
                texture=texture,
            )
        )

    layouts: tuple[YdrMaterialLayout, ...] = ()
    if shader_definition is not None:
        layouts = tuple(
            YdrMaterialLayout(type_name=layout.type_name, semantics=layout.semantics)
            for layout in shader_definition.layouts
        )

    return YdrMaterialDescriptor(
        material_index=int(material.index),
        shader_name=material.shader_name,
        shader_name_hash=int(material.shader_name_hash),
        shader_file_name=material.resolved_shader_file_name,
        shader_file_hash=int(material.shader_file_hash),
        render_bucket=int(material.render_bucket),
        parameters=tuple(parameters),
        layouts=layouts,
    )


__all__ = [
    "YdrMaterialDescriptor",
    "YdrMaterialLayout",
    "YdrMaterialParameter",
    "build_material_descriptor",
]