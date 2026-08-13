from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import numpy
import trimesh
from trimesh.visual.material import MultiMaterial, PBRMaterial, SimpleMaterial

from ...colors import RGBAUnit, parse_css_rgba_unit
from ...texture import Texture
from ...ytd import TextureFormat, Ytd
from ..build_types import YdrMaterialInput
from ..gen9_shader_enums import YdrGen9Shader
from ..shader_enums import YdrShader


@dataclasses.dataclass(slots=True)
class TrimeshMaterial:
    name: str
    diffuse_texture: str | None = None
    normal_texture: str | None = None
    specular_texture: str | None = None
    diffuse_color: RGBAUnit | None = None

    def to_ydr_material(
        self,
        *,
        shader: str | YdrShader | YdrGen9Shader,
    ) -> YdrMaterialInput:
        textures: dict[str, str] = {}
        if self.diffuse_texture:
            textures["DiffuseSampler"] = self.diffuse_texture
        if self.normal_texture:
            textures["BumpSampler"] = self.normal_texture
        if self.specular_texture:
            textures["SpecSampler"] = self.specular_texture
        return YdrMaterialInput(name=self.name, shader=shader, textures=textures)


def _texture_name(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[-1]
    raw = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value)
    cleaned = raw.strip().strip('"').replace("\\", "/")
    if not cleaned:
        return None
    return Path(cleaned).stem or Path(cleaned).name


def _image_texture_name(image: object) -> str | None:
    info = getattr(image, "info", None)
    if isinstance(info, dict):
        for key in ("file_path", "filename", "name"):
            result = _texture_name(info.get(key))
            if result:
                return result
    for attribute in ("filename", "name"):
        result = _texture_name(getattr(image, attribute, None))
        if result:
            return result
    return None


def _material_texture(material: object, *names: str) -> str | None:
    for name in names:
        result = _image_texture_name(getattr(material, name, None))
        if result:
            return result
    kwargs = getattr(material, "kwargs", None)
    if isinstance(kwargs, dict):
        lowered = {str(key).lower(): value for key, value in kwargs.items()}
        for name in names:
            result = _texture_name(lowered.get(name.lower()))
            if result:
                return result
    return None


def _colour(value: object) -> RGBAUnit | None:
    if value is None:
        return None
    try:
        return parse_css_rgba_unit(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def visual_colour(mesh: trimesh.Trimesh) -> RGBAUnit | None:
    visual = mesh.visual
    if not bool(getattr(visual, "defined", False)):
        return None
    return _colour(getattr(visual, "main_color", None))


def _parse_material(
    material: object | None,
    *,
    name: str,
    fallback_colour: RGBAUnit | None,
) -> TrimeshMaterial:
    if isinstance(material, PBRMaterial):
        return TrimeshMaterial(
            name=name,
            diffuse_texture=_material_texture(material, "baseColorTexture"),
            normal_texture=_material_texture(material, "normalTexture"),
            diffuse_color=_colour(material.baseColorFactor) or fallback_colour,
        )
    if isinstance(material, SimpleMaterial):
        return TrimeshMaterial(
            name=name,
            diffuse_texture=_material_texture(material, "image", "map_kd"),
            normal_texture=_material_texture(
                material,
                "normalTexture",
                "map_bump",
                "bump",
                "map_kn",
                "norm",
            ),
            specular_texture=_material_texture(material, "specularTexture", "map_ks"),
            diffuse_color=_colour(material.diffuse) or fallback_colour,
        )
    return TrimeshMaterial(name=name, diffuse_color=fallback_colour)


def _make_unique_name(base_name: str, used: set[str]) -> str:
    candidate = base_name.strip() or "material"
    if candidate not in used:
        used.add(candidate)
        return candidate
    suffix = 1
    while f"{candidate}_{suffix}" in used:
        suffix += 1
    result = f"{candidate}_{suffix}"
    used.add(result)
    return result


def _material_slots(mesh: trimesh.Trimesh) -> list[object | None]:
    material = getattr(mesh.visual, "material", None)
    if isinstance(material, MultiMaterial):
        return list(material.materials) or [None]
    return [material]


def iter_material_parts(
    mesh: trimesh.Trimesh,
) -> Iterator[tuple[object | None, int, numpy.ndarray | None]]:
    faces = numpy.asarray(mesh.faces)
    if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
        return
    materials = _material_slots(mesh)
    raw_face_materials = getattr(mesh.visual, "face_materials", None)
    face_materials = (
        numpy.asarray(raw_face_materials, dtype=numpy.int64)
        if raw_face_materials is not None
        else numpy.empty(0, dtype=numpy.int64)
    )
    if len(materials) == 1 or face_materials.shape != (len(faces),):
        yield materials[0], 0, None
        return
    for slot in numpy.unique(face_materials):
        slot_index = int(slot)
        if slot_index < 0 or slot_index >= len(materials):
            raise ValueError(
                f"Mesh references material slot {slot_index}, but only {len(materials)} exist"
            )
        face_indices = numpy.flatnonzero(face_materials == slot_index)
        if len(face_indices):
            yield materials[slot_index], slot_index, face_indices


def _infer_shader(
    material: TrimeshMaterial,
    default_shader: str | YdrShader | YdrGen9Shader,
) -> str | YdrShader | YdrGen9Shader:
    if material.normal_texture and material.specular_texture:
        return "normal_spec.sps"
    if material.normal_texture:
        return "normal.sps"
    if material.specular_texture:
        return "spec.sps"
    return default_shader


def _solid_colour_texture(name: str, colour: RGBAUnit) -> Texture:
    try:
        import texfury
        from PIL import Image as PILImage
    except Exception as exc:  # pragma: no cover - optional integration
        raise RuntimeError(
            "material_colours_as_textures requires texfury and Pillow"
        ) from exc

    rgba = tuple(round(component * 255.0) & 0xFF for component in colour)
    image = PILImage.new("RGBA", (4, 4), rgba)
    compressed = texfury.Texture.from_pil(
        image,
        format=texfury.BCFormat.BC1,
        quality=1.0,
        generate_mipmaps=False,
        resize_to_pot=False,
        name=name,
    )
    return Texture.from_raw(
        compressed.data,
        compressed.width,
        compressed.height,
        TextureFormat.BC1,
        compressed.mip_count,
        name=name,
        mip_offsets=getattr(compressed, "_mip_offsets", None),
        mip_sizes=getattr(compressed, "_mip_sizes", None),
    )


@dataclasses.dataclass(slots=True)
class MaterialRegistry:
    default_shader: str | YdrShader | YdrGen9Shader
    shader: str | YdrShader | YdrGen9Shader | None
    colours_as_textures: bool
    materials: list[YdrMaterialInput] = dataclasses.field(default_factory=list, init=False)
    embedded_textures: Ytd | None = dataclasses.field(default=None, init=False)
    _names: dict[tuple[object, ...], str] = dataclasses.field(default_factory=dict, init=False)
    _used_material_names: set[str] = dataclasses.field(default_factory=set, init=False)
    _used_texture_names: set[str] = dataclasses.field(default_factory=set, init=False)

    def resolve(
        self,
        material: object | None,
        *,
        geometry_name: str,
        slot: int,
        colour: RGBAUnit | None,
    ) -> str:
        key = (
            ("material", id(material))
            if material is not None
            else ("visual", geometry_name, slot, colour)
        )
        existing = self._names.get(key)
        if existing is not None:
            return existing

        raw_name = getattr(material, "name", None)
        fallback = f"{geometry_name}_material_{slot}"
        name = _make_unique_name(str(raw_name).strip() if raw_name else fallback, self._used_material_names)
        parsed = _parse_material(material, name=name, fallback_colour=colour)
        if self.colours_as_textures and parsed.diffuse_texture is None and parsed.diffuse_color is not None:
            texture_name = _make_unique_name(
                f"{name.strip().lower().replace(' ', '_')}_colour",
                self._used_texture_names,
            )
            parsed.diffuse_texture = texture_name
            if self.embedded_textures is None:
                self.embedded_textures = Ytd()
            self.embedded_textures.texture(_solid_colour_texture(texture_name, parsed.diffuse_color))

        selected_shader = self.shader if self.shader is not None else _infer_shader(parsed, self.default_shader)
        self.materials.append(parsed.to_ydr_material(shader=selected_shader))
        self._names[key] = name
        return name


__all__ = [
    "MaterialRegistry",
    "TrimeshMaterial",
    "iter_material_parts",
    "visual_colour",
]
