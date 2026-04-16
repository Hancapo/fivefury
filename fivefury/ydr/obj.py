from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Sequence

from .build_types import YdrBuild, YdrMaterialInput, YdrMeshInput
from .write_geometry import compute_bounds
from .builder import save_ydr
from .defs import YdrLod
from ..ytyp import Archetype, Ytyp
from ..ytyp.archetypes import ArchetypeAssetType


@dataclasses.dataclass(slots=True)
class ObjMaterial:
    name: str
    diffuse_texture: str | None = None
    normal_texture: str | None = None
    specular_texture: str | None = None

    def to_ydr_material(self, *, shader: str) -> YdrMaterialInput:
        textures: dict[str, str] = {}
        if self.diffuse_texture:
            textures["DiffuseSampler"] = self.diffuse_texture
        if self.normal_texture:
            textures["BumpSampler"] = self.normal_texture
        if self.specular_texture:
            textures["SpecSampler"] = self.specular_texture
        return YdrMaterialInput(name=self.name, shader=shader, textures=textures)


@dataclasses.dataclass(slots=True)
class ObjScene:
    meshes: list[YdrMeshInput]
    materials: list[YdrMaterialInput]
    name: str = ""

    def to_ydr(self, *, lod: YdrLod | str = YdrLod.HIGH, version: int = 165) -> YdrBuild:
        return YdrBuild.from_meshes(meshes=self.meshes, materials=self.materials, name=self.name, lod=lod, version=version)


@dataclasses.dataclass(slots=True)
class _ObjMeshBuilder:
    material_name: str
    positions: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)
    normals: list[tuple[float, float, float]] | None = dataclasses.field(default_factory=list)
    texcoords0: list[tuple[float, float]] | None = dataclasses.field(default_factory=list)
    indices: list[int] = dataclasses.field(default_factory=list)
    lookup: dict[tuple[int, int | None, int | None], int] = dataclasses.field(default_factory=dict)

    def add_vertex(
        self,
        key: tuple[int, int | None, int | None],
        *,
        position: tuple[float, float, float],
        texcoord: tuple[float, float] | None,
        normal: tuple[float, float, float] | None,
    ) -> int:
        existing = self.lookup.get(key)
        if existing is not None:
            return existing
        index = len(self.positions)
        self.lookup[key] = index
        self.positions.append(position)
        if self.texcoords0 is not None:
            if texcoord is None:
                self.texcoords0 = None
            else:
                self.texcoords0.append(texcoord)
        if self.normals is not None:
            if normal is None:
                self.normals = None
            else:
                self.normals.append(normal)
        return index

    def to_mesh_input(
        self,
        *,
        default_colour: tuple[float, float, float, float] | None = None,
    ) -> YdrMeshInput:
        texcoords = [self.texcoords0] if self.texcoords0 else None
        normals = self.normals if self.normals else None
        colours0 = [default_colour] * len(self.positions) if default_colour is not None else None
        return YdrMeshInput(
            positions=self.positions,
            indices=self.indices,
            material=self.material_name,
            normals=normals,
            texcoords=texcoords,
            colours0=colours0,
        )


def _texture_name_from_map(value: str) -> str:
    return Path(value.strip().strip('"')).stem or Path(value.strip().strip('"')).name


def _convert_obj_position(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (x, -z, y)


def _convert_obj_normal(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (x, -z, y)


def _resolve_obj_index(raw: str, count: int) -> int:
    value = int(raw)
    return value - 1 if value > 0 else count + value


def _parse_mtl(path: Path) -> dict[str, ObjMaterial]:
    materials: dict[str, ObjMaterial] = {}
    current: ObjMaterial | None = None
    if not path.is_file():
        return materials
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        keyword = parts[0].lower()
        value = parts[1].strip() if len(parts) > 1 else ""
        if keyword == "newmtl":
            current = ObjMaterial(name=value or f"material_{len(materials)}")
            materials[current.name] = current
            continue
        if current is None:
            continue
        if keyword == "map_kd":
            current.diffuse_texture = _texture_name_from_map(value)
        elif keyword in {"map_bump", "bump", "norm"}:
            current.normal_texture = _texture_name_from_map(value.split()[-1])
        elif keyword == "map_ks":
            current.specular_texture = _texture_name_from_map(value)
    return materials


def _infer_shader(material: ObjMaterial, default_shader: str) -> str:
    has_normal = material.normal_texture is not None
    has_spec = material.specular_texture is not None
    if has_normal and has_spec:
        return "normal_spec.sps"
    if has_normal:
        return "normal.sps"
    if has_spec:
        return "spec.sps"
    return default_shader


def _compute_scene_bounds(meshes: Sequence[YdrMeshInput]) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]:
    return compute_bounds([p for mesh in meshes for p in mesh.positions])


def _lowercase_output_path(value: str | Path) -> Path:
    path = Path(value)
    return path.with_name(path.name.lower())


def _save_companion_ytyp(scene: ObjScene, destination: str | Path) -> Path:
    target = _lowercase_output_path(destination)
    base_name = target.stem.lower()
    ytyp_name = f"{base_name}_meta"
    centre, bb_min, bb_max, radius = _compute_scene_bounds(scene.meshes)
    ytyp = Ytyp(name=ytyp_name)
    ytyp.add_archetype(
        Archetype(
            name=base_name,
            asset_name=base_name,
            texture_dictionary=f"{base_name}_txd",
            asset_type=ArchetypeAssetType.DRAWABLE,
            bb_min=bb_min,
            bb_max=bb_max,
            bs_centre=centre,
            bs_radius=radius,
        )
    )
    return ytyp.save(target.with_name(f"{ytyp_name}.ytyp"))


def read_obj_scene(
    source: str | Path,
    *,
    default_shader: str = "default.sps",
    shader: str | None = None,
    default_colour: tuple[float, float, float, float] | None = None,
) -> ObjScene:
    obj_path = Path(source)
    vertices: list[tuple[float, float, float]] = []
    texcoords: list[tuple[float, float]] = []
    normals: list[tuple[float, float, float]] = []
    material_libraries: list[Path] = []
    builders: dict[str, _ObjMeshBuilder] = {}
    current_material = "default"

    def get_builder(material_name: str) -> _ObjMeshBuilder:
        if material_name not in builders:
            builders[material_name] = _ObjMeshBuilder(material_name=material_name)
        return builders[material_name]

    for raw_line in obj_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        keyword = parts[0].lower()
        values = parts[1:]
        if keyword == "v" and len(values) >= 3:
            vertices.append(_convert_obj_position(float(values[0]), float(values[1]), float(values[2])))
        elif keyword == "vt" and len(values) >= 2:
            texcoords.append((float(values[0]), 1.0 - float(values[1])))
        elif keyword == "vn" and len(values) >= 3:
            normals.append(_convert_obj_normal(float(values[0]), float(values[1]), float(values[2])))
        elif keyword == "mtllib" and values:
            material_libraries.append(obj_path.parent / " ".join(values))
        elif keyword == "usemtl" and values:
            current_material = " ".join(values)
        elif keyword == "f" and len(values) >= 3:
            builder = get_builder(current_material)
            face_indices: list[int] = []
            for token in values:
                fields = token.split("/")
                vertex_index = _resolve_obj_index(fields[0], len(vertices))
                texcoord_index = _resolve_obj_index(fields[1], len(texcoords)) if len(fields) > 1 and fields[1] else None
                normal_index = _resolve_obj_index(fields[2], len(normals)) if len(fields) > 2 and fields[2] else None
                face_indices.append(
                    builder.add_vertex(
                        (vertex_index, texcoord_index, normal_index),
                        position=vertices[vertex_index],
                        texcoord=texcoords[texcoord_index] if texcoord_index is not None and 0 <= texcoord_index < len(texcoords) else None,
                        normal=normals[normal_index] if normal_index is not None and 0 <= normal_index < len(normals) else None,
                    )
                )
            for tri_index in range(1, len(face_indices) - 1):
                builder.indices.extend((face_indices[0], face_indices[tri_index], face_indices[tri_index + 1]))

    parsed_materials: dict[str, ObjMaterial] = {}
    for mtl_path in material_libraries:
        parsed_materials.update(_parse_mtl(mtl_path))

    material_names = list(dict.fromkeys(builders.keys())) or ["default"]
    ydr_materials: list[YdrMaterialInput] = []
    for material_name in material_names:
        parsed = parsed_materials.get(material_name, ObjMaterial(name=material_name))
        selected_shader = shader if shader is not None else _infer_shader(parsed, default_shader)
        ydr_materials.append(parsed.to_ydr_material(shader=selected_shader))

    meshes = [builder.to_mesh_input(default_colour=default_colour) for builder in builders.values() if builder.indices]
    if not meshes:
        raise ValueError(f"OBJ file '{obj_path}' does not contain any faces")
    return ObjScene(meshes=meshes, materials=ydr_materials, name=obj_path.stem.lower())


def obj_to_ydr(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    default_shader: str = "default.sps",
    shader: str | None = None,
    default_colour: tuple[float, float, float, float] | None = None,
    generate_ytyp: bool = False,
) -> YdrBuild:
    scene = read_obj_scene(source, default_shader=default_shader, shader=shader, default_colour=default_colour)
    build = scene.to_ydr()
    if destination is None:
        destination = Path(source).with_suffix(".ydr")
    result = save_ydr(build, _lowercase_output_path(destination))
    if generate_ytyp:
        _save_companion_ytyp(scene, result)
    return build


__all__ = [
    "ObjMaterial",
    "ObjScene",
    "obj_to_ydr",
    "read_obj_scene",
]
