from __future__ import annotations

import dataclasses

from ...drawable import DrawableMaterial, DrawableParameter
from ...drawable.model import NumericParameterValue
from ...hashing import jenk_hash
from ...ycd.model import YcdUvClipBinding
from ..build_types import YdrMaterialInput, YdrTextureInput
from ..gen9 import ShaderGen9Definition
from ..materials import YdrMaterialDescriptor
from ..shaders import ShaderDefinition, ShaderLibrary


@dataclasses.dataclass(slots=True)
class YdrTextureRef:
    name: str
    parameter_hash: int = 0
    parameter_name: str | None = None
    name_hash: int = 0
    uv_index: int | None = None
    parameter_type: str | None = None
    hidden: bool = False

    @property
    def slot_name(self) -> str | None:
        return self.parameter_name

    def to_input(self) -> YdrTextureInput:
        return YdrTextureInput(name=self.name)


@dataclasses.dataclass(slots=True)
class YdrMaterialParameterRef(DrawableParameter):
    name: str
    name_hash: int = 0
    type_name: str | None = None
    subtype: str | None = None
    uv_index: int | None = None
    count: int = 1
    hidden: bool = False
    defaults: dict[str, str] = dataclasses.field(default_factory=dict)
    data_type: int = 0
    texture: YdrTextureRef | None = None
    value: NumericParameterValue | None = None

    @property
    def is_texture(self) -> bool:
        return (self.type_name or "").lower() == "texture"

    @property
    def is_numeric(self) -> bool:
        return not self.is_texture

    @property
    def is_bound(self) -> bool:
        if self.is_texture:
            return self.texture is not None
        return self.value is not None

    @property
    def texture_name(self) -> str | None:
        if self.texture is None:
            return None
        return self.texture.name

    def to_builder_value(self) -> NumericParameterValue | None:
        if self.is_texture or self.value is None:
            return None
        if (
            isinstance(self.value, tuple)
            and self.value
            and isinstance(self.value[0], tuple)
        ):
            return tuple(
                tuple(float(component) for component in row) for row in self.value
            )
        if isinstance(self.value, tuple):
            if len(self.value) == 1:
                return float(self.value[0])
            return tuple(float(component) for component in self.value)
        return float(self.value)


@dataclasses.dataclass(slots=True)
class YdrMaterial(DrawableMaterial[YdrMaterialParameterRef]):
    index: int
    name: str = ""
    shader_name_hash: int = 0
    shader_name: str | None = None
    shader_file_hash: int = 0
    shader_file_name: str | None = None
    render_bucket: int = 0
    textures: list[YdrTextureRef] = dataclasses.field(default_factory=list)
    parameters: list[YdrMaterialParameterRef] = dataclasses.field(default_factory=list)
    shader_definition: ShaderDefinition | None = None
    gen9_definition: ShaderGen9Definition | None = None

    def get_parameter(self, value: str | int) -> YdrMaterialParameterRef | None:
        parameter = DrawableMaterial.get_parameter(self, value)
        if parameter is not None or self.gen9_definition is None:
            return parameter
        definition = self.gen9_definition.get_parameter(value)
        if definition is None:
            return None
        return DrawableMaterial.get_parameter(
            self, definition.legacy_name or definition.name
        )

    @property
    def resolved_shader_file_name(self) -> str | None:
        if self.shader_file_name:
            return self.shader_file_name
        if self.shader_definition is None:
            return None
        return self.shader_definition.pick_file_name(self.render_bucket)

    @property
    def texture_slots(self) -> dict[str, YdrTextureRef]:
        slots: dict[str, YdrTextureRef] = {}
        for texture in self.textures:
            if texture.parameter_name:
                slots[texture.parameter_name] = texture
        return slots

    @property
    def slot_index(self) -> int:
        return int(self.index)

    @property
    def material_descriptor(self) -> YdrMaterialDescriptor:
        from ..materials import build_material_descriptor

        return build_material_descriptor(self)

    def ycd_uv_binding(self, *, object_name: str) -> YcdUvClipBinding:
        return YcdUvClipBinding(
            object_name=str(object_name), slot_index=self.slot_index
        )

    def ycd_uv_clip_name(self, *, object_name: str) -> str:
        return self.ycd_uv_binding(object_name=object_name).clip_name

    def ycd_uv_clip_hash(self, *, object_name: str) -> int:
        return int(self.ycd_uv_binding(object_name=object_name).clip_hash.uint)

    def get_texture(self, value: str | int) -> YdrTextureRef | None:
        parameter = self.get_parameter(value)
        if parameter is None or not parameter.is_texture:
            return None
        return parameter.texture

    def _sync_textures(self) -> None:
        self.textures = [
            parameter.texture
            for parameter in self.parameters
            if parameter.is_texture and parameter.texture is not None
        ]

    def _set_shader(
        self,
        shader: str,
        *,
        render_bucket: int | None = None,
        shader_library: ShaderLibrary | None = None,
        preserve_values: bool = True,
    ) -> None:
        from ..shaders import load_shader_library, resolve_shader_reference

        active_shader_library = (
            shader_library if shader_library is not None else load_shader_library()
        )
        next_render_bucket = int(
            self.render_bucket if render_bucket is None else render_bucket
        )
        shader_definition, shader_file_name, next_render_bucket = (
            resolve_shader_reference(shader, next_render_bucket, active_shader_library)
        )

        previous_parameters = {
            parameter.name.lower(): parameter for parameter in self.parameters
        }
        next_parameters: list[YdrMaterialParameterRef] = []
        for definition in shader_definition.parameters:
            previous = (
                previous_parameters.get(definition.name.lower())
                if preserve_values
                else None
            )
            next_parameters.append(
                YdrMaterialParameterRef(
                    name=definition.name,
                    name_hash=definition.name_hash,
                    type_name=definition.type_name,
                    subtype=definition.subtype,
                    uv_index=definition.uv_index,
                    count=definition.count,
                    hidden=definition.hidden,
                    defaults=dict(definition.defaults),
                    data_type=0 if definition.is_texture else 1,
                    texture=previous.texture
                    if previous is not None and previous.is_texture
                    else None,
                    value=(
                        previous.value
                        if previous is not None
                        and previous.is_numeric
                        and previous.value is not None
                        else definition.default_value
                    ),
                )
            )

        self.shader_definition = shader_definition
        self.gen9_definition = None
        self.shader_name = shader_definition.name
        self.shader_name_hash = int(shader_definition.name_hash)
        self.shader_file_name = shader_file_name
        self.shader_file_hash = int(jenk_hash(shader_file_name))
        self.render_bucket = next_render_bucket
        self.parameters = next_parameters
        self._sync_textures()

    def _set_texture(
        self, slot: str | int, texture: str | YdrTextureRef | None
    ) -> None:
        parameter = self.get_parameter(slot)
        if parameter is None:
            raise KeyError(f"Unknown YDR texture slot '{slot}'")
        if not parameter.is_texture:
            raise TypeError(f"YDR parameter '{parameter.name}' is not a texture slot")
        if texture is None:
            parameter.texture = None
        elif isinstance(texture, YdrTextureRef):
            parameter.texture = texture
        else:
            parameter.texture = YdrTextureRef(
                name=str(texture),
                parameter_hash=parameter.name_hash,
                parameter_name=parameter.name,
                uv_index=parameter.uv_index,
                parameter_type=parameter.type_name,
                hidden=parameter.hidden,
            )
        self._sync_textures()

    def _set_parameter(
        self,
        name: str | int,
        value: float | tuple[float, ...] | tuple[tuple[float, ...], ...] | None,
    ) -> None:
        parameter = self.get_parameter(name)
        if parameter is None:
            raise KeyError(f"Unknown YDR parameter '{name}'")
        if parameter.is_texture:
            raise TypeError(f"YDR parameter '{parameter.name}' is a texture slot")
        parameter.value = value

    def _remove_parameter(self, name: str | int) -> None:
        parameter = self.get_parameter(name)
        if parameter is None:
            raise KeyError(f"Unknown YDR parameter '{name}'")
        if parameter.is_texture:
            parameter.texture = None
            self._sync_textures()
            return
        parameter.value = None

    def update(
        self,
        *,
        shader: str | None = None,
        render_bucket: int | None = None,
        textures: dict[str, str | YdrTextureRef | None] | None = None,
        parameters: dict[str, NumericParameterValue | None] | None = None,
        preserve_values: bool = True,
        shader_library: ShaderLibrary | None = None,
    ) -> YdrMaterial:
        if shader is not None or render_bucket is not None:
            self._set_shader(
                shader
                or self.resolved_shader_file_name
                or self.shader_name
                or "default.sps",
                render_bucket=render_bucket,
                shader_library=shader_library,
                preserve_values=preserve_values,
            )
        for slot, texture in (textures or {}).items():
            if texture is None and self.get_parameter(slot) is None:
                continue
            self._set_texture(slot, texture)
        for name, value in (parameters or {}).items():
            self._set_parameter(name, value)
        return self

    def to_input(self) -> YdrMaterialInput:
        material_name = self.name or f"material_{self.index}"
        textures = {
            parameter.name: (
                parameter.texture.to_input() if parameter.texture is not None else None
            )
            for parameter in self.parameters
            if parameter.is_texture
        }
        numeric_parameters: dict[str, NumericParameterValue] = {}
        for parameter in self.parameters:
            value = parameter.to_builder_value()
            if value is None:
                continue
            numeric_parameters[parameter.name] = value
        shader = self.resolved_shader_file_name or self.shader_name or "default.sps"
        return YdrMaterialInput(
            name=material_name,
            shader=shader,
            layout_shader=self.shader_definition.name
            if self.shader_definition is not None
            else None,
            textures=textures,
            parameters=numeric_parameters,
            render_bucket=int(self.render_bucket),
            gen9_definition=self.gen9_definition,
        )
