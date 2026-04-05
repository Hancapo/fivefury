from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from ..hashing import jenk_hash
from ..ytd import Ytd
from .defs import LOD_ORDER
from .shaders import ShaderDefinition

if TYPE_CHECKING:
    from .builder import YdrBuild, YdrMaterialInput, YdrMeshInput, YdrModelInput, YdrTextureInput
    from .materials import YdrMaterialDescriptor
    from .shaders import ShaderLibrary


NumericParameterValue = float | tuple[float, ...] | tuple[tuple[float, ...], ...]


class YdrLightType(enum.IntEnum):
    POINT = 1
    SPOT = 2
    CAPSULE = 4


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
        from .builder import YdrTextureInput

        return YdrTextureInput(name=self.name)


@dataclasses.dataclass(slots=True)
class YdrMaterialParameterRef:
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

    def to_builder_value(self) -> float | tuple[float, ...] | None:
        if self.is_texture or self.value is None:
            return None
        if isinstance(self.value, tuple) and self.value and isinstance(self.value[0], tuple):
            return None
        if isinstance(self.value, tuple):
            if len(self.value) == 1:
                return float(self.value[0])
            return tuple(float(component) for component in self.value)
        return float(self.value)


@dataclasses.dataclass(slots=True)
class YdrLight:
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    color: tuple[int, int, int] = (255, 255, 255)
    flashiness: int = 0
    intensity: float = 1.0
    flags: int = 0
    bone_id: int = 0
    light_type: YdrLightType = YdrLightType.POINT
    group_id: int = 0
    time_flags: int = 0
    falloff: float = 0.0
    falloff_exponent: float = 0.0
    culling_plane_normal: tuple[float, float, float] = (0.0, 0.0, 0.0)
    culling_plane_offset: float = 0.0
    shadow_blur: int = 0
    volume_intensity: float = 0.0
    volume_size_scale: float = 0.0
    volume_outer_color: tuple[int, int, int] = (0, 0, 0)
    light_hash: int = 0
    volume_outer_intensity: float = 0.0
    corona_size: float = 0.0
    volume_outer_exponent: float = 0.0
    light_fade_distance: int = 0
    shadow_fade_distance: int = 0
    specular_fade_distance: int = 0
    volumetric_fade_distance: int = 0
    shadow_near_clip: float = 0.0
    corona_intensity: float = 0.0
    corona_z_bias: float = 0.0
    direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    tangent: tuple[float, float, float] = (1.0, 0.0, 0.0)
    cone_inner_angle: float = 0.0
    cone_outer_angle: float = 0.0
    extent: tuple[float, float, float] = (0.0, 0.0, 0.0)
    projected_texture_hash: int = 0
    unknown_0h: int = 0
    unknown_4h: int = 0
    unknown_14h: int = 0
    unknown_45h: int = 0
    unknown_46h: int = 0
    unknown_48h: int = 0
    unknown_a4h: int = 0


@dataclasses.dataclass(slots=True)
class YdrMaterial:
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

    @property
    def texture_names(self) -> list[str]:
        return [texture.name for texture in self.textures if texture.name]

    @property
    def primary_texture_name(self) -> str | None:
        names = self.texture_names
        return names[0] if names else None

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
    def material_descriptor(self) -> YdrMaterialDescriptor:
        from .materials import build_material_descriptor

        return build_material_descriptor(self)

    def get_parameter(self, value: str | int) -> YdrMaterialParameterRef | None:
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

    def get_texture(self, value: str | int) -> YdrTextureRef | None:
        parameter = self.get_parameter(value)
        if parameter is None or not parameter.is_texture:
            return None
        return parameter.texture

    def get_numeric_parameter(self, value: str | int) -> NumericParameterValue | None:
        parameter = self.get_parameter(value)
        if parameter is None or not parameter.is_numeric:
            return None
        return parameter.value

    def _sync_textures(self) -> None:
        self.textures = [parameter.texture for parameter in self.parameters if parameter.is_texture and parameter.texture is not None]

    def _set_shader(
        self,
        shader: str,
        *,
        render_bucket: int | None = None,
        shader_library: ShaderLibrary | None = None,
        preserve_values: bool = True,
    ) -> None:
        from .shaders import load_shader_library

        active_shader_library = shader_library if shader_library is not None else load_shader_library()
        shader_definition = active_shader_library.resolve_shader(shader_name=shader, shader_file_name=shader)
        if shader_definition is None:
            raise ValueError(f"Unknown YDR shader '{shader}'")

        next_render_bucket = int(self.render_bucket if render_bucket is None else render_bucket)
        shader_file_name = shader_definition.pick_file_name(next_render_bucket)
        if shader_file_name is None:
            raise ValueError(f"Shader '{shader_definition.name}' has no file for render bucket {next_render_bucket}")

        previous_parameters = {parameter.name.lower(): parameter for parameter in self.parameters}
        next_parameters: list[YdrMaterialParameterRef] = []
        for definition in shader_definition.parameters:
            previous = previous_parameters.get(definition.name.lower()) if preserve_values else None
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
                    texture=previous.texture if previous is not None and previous.is_texture else None,
                    value=previous.value if previous is not None and previous.is_numeric else None,
                )
            )

        self.shader_definition = shader_definition
        self.shader_name = shader_definition.name
        self.shader_name_hash = int(shader_definition.name_hash)
        self.shader_file_name = shader_file_name
        self.shader_file_hash = int(jenk_hash(shader_file_name))
        self.render_bucket = next_render_bucket
        self.parameters = next_parameters
        self._sync_textures()

    def _set_texture(self, slot: str | int, texture: str | YdrTextureRef | None) -> None:
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

    def _set_parameter(self, name: str | int, value: float | tuple[float, ...] | tuple[tuple[float, ...], ...] | None) -> None:
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
    ) -> "YdrMaterial":
        if shader is not None or render_bucket is not None:
            self._set_shader(
                shader or self.resolved_shader_file_name or self.shader_name or "default.sps",
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
        from .builder import YdrMaterialInput

        material_name = self.name or f"material_{self.index}"
        textures = {
            parameter.name: parameter.texture.to_input()
            for parameter in self.parameters
            if parameter.is_texture and parameter.texture is not None
        }
        numeric_parameters: dict[str, float | tuple[float, ...] | int | str] = {}
        for parameter in self.parameters:
            value = parameter.to_builder_value()
            if value is None:
                continue
            numeric_parameters[parameter.name] = value
        shader = self.resolved_shader_file_name or self.shader_name or "default.sps"
        return YdrMaterialInput(
            name=material_name,
            shader=shader,
            textures=textures,
            parameters=numeric_parameters,
            render_bucket=int(self.render_bucket),
        )


@dataclasses.dataclass(slots=True)
class YdrMesh:
    material_index: int = -1
    material: YdrMaterial | None = None
    indices: list[int] = dataclasses.field(default_factory=list)
    positions: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    normals: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    tangents: list[tuple[float, float, float, float]] = dataclasses.field(default_factory=list)
    texcoords: list[list[tuple[float, float]]] = dataclasses.field(default_factory=list)
    colours0: list[tuple[float, float, float, float]] = dataclasses.field(default_factory=list)
    colours1: list[tuple[float, float, float, float]] = dataclasses.field(default_factory=list)
    blend_weights: list[tuple[float, float, float, float]] = dataclasses.field(default_factory=list)
    blend_indices: list[tuple[int, int, int, int]] = dataclasses.field(default_factory=list)
    bone_ids: list[int] = dataclasses.field(default_factory=list)
    vertex_stride: int = 0
    declaration_flags: int = 0
    declaration_types: int = 0
    render_mask: int = 0
    flags: int = 0

    @property
    def texture_names(self) -> list[str]:
        return self.material.texture_names if self.material is not None else []

    def to_input(self, *, material_name: str | None = None) -> YdrMeshInput:
        from .builder import YdrMeshInput

        return YdrMeshInput(
            positions=list(self.positions),
            indices=list(self.indices),
            material=material_name or (self.material.name if self.material is not None and self.material.name else f"material_{self.material_index}"),
            normals=list(self.normals),
            texcoords=[list(channel) for channel in self.texcoords],
            tangents=list(self.tangents),
            colours0=list(self.colours0),
            colours1=list(self.colours1),
        )


@dataclasses.dataclass(slots=True)
class YdrModel:
    lod: str
    index: int = 0
    meshes: list[YdrMesh] = dataclasses.field(default_factory=list)
    render_mask: int = 0
    flags: int = 0
    skeleton_binding: int = 0

    @property
    def has_skin(self) -> bool:
        return bool((self.skeleton_binding >> 8) & 0xFF)

    @property
    def bone_index(self) -> int:
        return (self.skeleton_binding >> 24) & 0xFF

    @property
    def mesh_count(self) -> int:
        return len(self.meshes)

    @property
    def material_indices(self) -> list[int]:
        indices: list[int] = []
        seen: set[int] = set()
        for mesh in self.meshes:
            if mesh.material_index < 0 or mesh.material_index in seen:
                continue
            seen.add(mesh.material_index)
            indices.append(mesh.material_index)
        return indices

    @property
    def materials(self) -> list[YdrMaterial]:
        materials: list[YdrMaterial] = []
        seen: set[int] = set()
        for mesh in self.meshes:
            material = mesh.material
            if material is None or material.index in seen:
                continue
            seen.add(material.index)
            materials.append(material)
        return materials

    @property
    def material_count(self) -> int:
        return len(self.materials)

    def iter_materials(self) -> Iterator[YdrMaterial]:
        yield from self.materials

    def get_material(self, value: str | int) -> YdrMaterial | None:
        if isinstance(value, str):
            lowered = value.lower()
            for material in self.materials:
                if material.name.lower() == lowered:
                    return material
                if (material.shader_name or "").lower() == lowered:
                    return material
            return None
        index = int(value)
        for material in self.materials:
            if material.index == index:
                return material
        return None

    def to_input(self, *, material_name_by_index: dict[int, str]) -> YdrModelInput:
        from .builder import YdrModelInput

        return YdrModelInput(
            meshes=[
                mesh.to_input(material_name=material_name_by_index.get(mesh.material_index, f"material_{mesh.material_index}"))
                for mesh in self.meshes
            ],
            render_mask=int(self.render_mask),
            flags=int(self.flags),
            skeleton_binding=int(self.skeleton_binding),
        )


@dataclasses.dataclass(slots=True)
class Ydr:
    version: int
    path: str = ""
    materials: list[YdrMaterial] = dataclasses.field(default_factory=list)
    lods: dict[str, list[YdrModel]] = dataclasses.field(default_factory=dict)
    bounding_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounding_sphere_radius: float = 0.0
    bounding_box_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounding_box_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    lights: list[YdrLight] = dataclasses.field(default_factory=list)
    embedded_textures: Ytd | None = None

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, *, path: str = "") -> "Ydr":
        from . import read_ydr

        return read_ydr(data, path=path)

    def get_lod(self, name: str) -> list[YdrModel]:
        return self.lods.get(str(name).lower(), [])

    def iter_models(self, lod: str | None = None) -> Iterator[YdrModel]:
        if lod is not None:
            yield from self.get_lod(lod)
            return
        for name in LOD_ORDER:
            yield from self.lods.get(name, [])

    def iter_meshes(self, lod: str | None = None) -> Iterator[YdrMesh]:
        for model in self.iter_models(lod=lod):
            yield from model.meshes

    @property
    def models(self) -> list[YdrModel]:
        models: list[YdrModel] = []
        for lod in LOD_ORDER:
            models.extend(self.lods.get(lod, []))
        return models

    @property
    def model_count(self) -> int:
        return len(self.models)

    def get_model(self, index: int, *, lod: str | None = None) -> YdrModel | None:
        models = list(self.iter_models(lod=lod))
        if 0 <= int(index) < len(models):
            return models[int(index)]
        return None

    @property
    def meshes(self) -> list[YdrMesh]:
        for lod in LOD_ORDER:
            models = self.lods.get(lod)
            if models:
                meshes: list[YdrMesh] = []
                for model in models:
                    meshes.extend(model.meshes)
                return meshes
        return []

    @property
    def texture_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for material in self.materials:
            for name in material.texture_names:
                lowered = name.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                names.append(name)
        return names

    @property
    def name(self) -> str:
        if self.path:
            return Path(self.path).stem
        return "drawable"

    def get_material(self, value: str | int) -> YdrMaterial | None:
        if isinstance(value, str):
            lowered = value.lower()
            for material in self.materials:
                if material.name.lower() == lowered:
                    return material
                if (material.shader_name or "").lower() == lowered:
                    return material
            return None
        index = int(value)
        for material in self.materials:
            if material.index == index:
                return material
        return None

    def require_material(self, value: str | int) -> YdrMaterial:
        material = self.get_material(value)
        if material is None:
            raise KeyError(f"Unknown YDR material '{value}'")
        return material

    def update_material(
        self,
        material: str | int,
        *,
        shader: str | None = None,
        render_bucket: int | None = None,
        textures: dict[str, str | YdrTextureRef | None] | None = None,
        parameters: dict[str, NumericParameterValue | None] | None = None,
        preserve_values: bool | None = None,
        shader_library: ShaderLibrary | None = None,
    ) -> YdrMaterial:
        target = self.require_material(material)
        return target.update(
            shader=shader,
            render_bucket=render_bucket,
            textures=textures,
            parameters=parameters,
            preserve_values=preserve_values,
            shader_library=shader_library,
        )

    def to_build(self, *, lod: str | None = None, name: str | None = None) -> YdrBuild:
        from .builder import YdrBuild

        if lod is None:
            selected_lod = next((lod_name for lod_name in LOD_ORDER if any(self.lods.get(lod_name, []))), "high")
        else:
            selected_lod = lod.lower()
        material_name_by_index = {
            material.index: (material.name or f"material_{material.index}")
            for material in self.materials
        }
        selected_models = list(self.iter_models(lod=selected_lod))
        materials = [material.to_input() for material in self.materials]
        return YdrBuild(
            models=[model.to_input(material_name_by_index=material_name_by_index) for model in selected_models],
            materials=materials,
            name=name or self.name,
            lod=selected_lod,
            version=int(self.version),
            lights=list(self.lights),
        )

    def save(self, destination: str | Path, *, lod: str | None = None, name: str | None = None) -> Path:
        return self.to_build(lod=lod, name=name).save(destination)


__all__ = [
    "Ydr",
    "YdrLight",
    "YdrLightType",
    "YdrMaterial",
    "YdrMaterialParameterRef",
    "YdrMesh",
    "YdrModel",
    "YdrTextureRef",
]
