from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy

from .build_types import YdrBuild, YdrMaterialInput, YdrMeshInput
from .builder import save_ydr
from .defs import YdrLod
from .gen9_shader_enums import YdrGen9Shader
from .shader_enums import YdrShader
from .write_geometry import compute_bounds
from ..game_target import GameTarget, coerce_game_target
from ..texture import Texture
from ..ytd import TextureFormat, Ytd
from ..ytyp import Archetype, Ytyp, cutscene_prop_flags
from ..ytyp.archetypes import ArchetypeAssetType
from ..ytyp.lod import infer_archetype_hd_texture_dist, infer_archetype_lod_dist

_LEGACY_YDR_VERSION = 165
_ENHANCED_YDR_VERSION = 159

_SEMANTIC_NONE = 0
_SEMANTIC_DIFFUSE = 1
_SEMANTIC_SPECULAR = 2
_SEMANTIC_HEIGHT = 5
_SEMANTIC_NORMALS = 6
_SUPPORTED_ASSIMP_SUFFIXES = {".obj", ".fbx", ".x"}


@dataclasses.dataclass(slots=True)
class AssimpMaterial:
    name: str
    diffuse_texture: str | None = None
    normal_texture: str | None = None
    specular_texture: str | None = None
    diffuse_color: tuple[float, float, float, float] | None = None

    def to_ydr_material(self, *, shader: str | YdrShader | YdrGen9Shader) -> YdrMaterialInput:
        textures: dict[str, str] = {}
        if self.diffuse_texture:
            textures["DiffuseSampler"] = self.diffuse_texture
        if self.normal_texture:
            textures["BumpSampler"] = self.normal_texture
        if self.specular_texture:
            textures["SpecSampler"] = self.specular_texture
        return YdrMaterialInput(name=self.name, shader=shader, textures=textures)


@dataclasses.dataclass(slots=True)
class AssimpScene:
    meshes: list[YdrMeshInput]
    materials: list[YdrMaterialInput]
    name: str = ""
    embedded_textures: Ytd | None = None

    def to_ydr(
        self,
        *,
        lod: YdrLod | str = YdrLod.HIGH,
        version: int | None = None,
        game: GameTarget | None = None,
    ) -> YdrBuild:
        return YdrBuild.from_meshes(
            meshes=self.meshes,
            materials=self.materials,
            name=self.name,
            lod=lod,
            version=_resolve_target_version(version=version, game=game),
            embedded_textures=self.embedded_textures,
        )


def _validate_input_format(source: str | Path) -> Path:
    source_path = Path(source)
    suffix = source_path.suffix.lower()
    if suffix not in _SUPPORTED_ASSIMP_SUFFIXES:
        supported = ", ".join(sorted(_SUPPORTED_ASSIMP_SUFFIXES))
        raise ValueError(f"Unsupported Assimp source suffix {source_path.suffix!r}; expected one of {supported}")
    return source_path


def _load_impasse():
    try:
        import impasse
        from impasse.constants import ProcessingStep
    except Exception as exc:  # pragma: no cover - depends on local native assimp installation
        raise RuntimeError(
            "Assimp import requires 'impasse' plus a working native assimp library available on PATH."
        ) from exc
    return impasse, ProcessingStep


def _default_processing_flags(processing_step: Any) -> int:
    return int(
        processing_step.Triangulate
        | processing_step.JoinIdenticalVertices
        | processing_step.GenSmoothNormals
        | processing_step.CalcTangentSpace
    )


def _read_impasse_scene(source: str | Path, processing: int | None = None):
    impasse, processing_step = _load_impasse()
    return impasse.load(
        str(source),
        processing=_default_processing_flags(processing_step) if processing is None else int(processing),
    )


def _safe_list(values: Any) -> list[Any]:
    if values is None:
        return []
    return list(values)


def _as_matrix4(value: Any) -> numpy.ndarray:
    if value is None:
        return numpy.identity(4, dtype=float)
    matrix = numpy.asarray(value, dtype=float)
    if matrix.shape == (4, 4):
        return matrix
    raise ValueError(f"Expected a 4x4 transform matrix, got shape {matrix.shape!r}")


def _vector3(value: Any) -> tuple[float, float, float]:
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return (float(value.x), float(value.y), float(value.z))
    if len(value) >= 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    raise ValueError(f"Expected a 3D vector, got {value!r}")


def _vector4(value: Any) -> tuple[float, float, float, float]:
    if hasattr(value, "r") and hasattr(value, "g") and hasattr(value, "b") and hasattr(value, "a"):
        return (float(value.r), float(value.g), float(value.b), float(value.a))
    if len(value) >= 4:
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    raise ValueError(f"Expected a 4D vector, got {value!r}")


def _convert_position(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (x, -z, y)


def _convert_normal(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (x, -z, y)


def _transform_position(value: Any, matrix: numpy.ndarray) -> tuple[float, float, float]:
    x, y, z = _vector3(value)
    transformed = matrix @ numpy.array((x, y, z, 1.0), dtype=float)
    return _convert_position(float(transformed[0]), float(transformed[1]), float(transformed[2]))


def _transform_direction(value: Any, matrix: numpy.ndarray) -> tuple[float, float, float]:
    x, y, z = _vector3(value)
    transformed = matrix[:3, :3] @ numpy.array((x, y, z), dtype=float)
    length = float(numpy.linalg.norm(transformed))
    if length > 0.0:
        transformed = transformed / length
    return _convert_normal(float(transformed[0]), float(transformed[1]), float(transformed[2]))


def _uv2(value: Any) -> tuple[float, float]:
    if hasattr(value, "x") and hasattr(value, "y"):
        return (float(value.x), 1.0 - float(value.y))
    if len(value) >= 2:
        return (float(value[0]), 1.0 - float(value[1]))
    raise ValueError(f"Expected a 2D vector, got {value!r}")


def _texture_name(value: Any) -> str | None:
    if value is None:
        return None
    raw = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value)
    cleaned = raw.strip().strip('"')
    if not cleaned:
        return None
    path = Path(cleaned)
    return path.stem or path.name


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _colour4(value: Any) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        r, g, b, a = _vector4(value)
    except Exception:
        return None
    return (_clamp_unit(r), _clamp_unit(g), _clamp_unit(b), _clamp_unit(a))


def _byte_from_unit(value: float) -> int:
    return int(round(_clamp_unit(value) * 255.0)) & 0xFF


def _solid_colour_texfury_texture(name: str, colour: tuple[float, float, float, float]) -> Texture:
    try:
        import texfury
        from PIL import Image as PILImage
    except Exception as exc:  # pragma: no cover - depends on optional runtime deps
        raise RuntimeError(
            "material_colours_as_textures requires texfury and Pillow to be installed and importable."
        ) from exc

    rgba = tuple(_byte_from_unit(channel) for channel in colour)
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


def _material_colour_texture_name(material_name: str) -> str:
    base = (material_name or "material").strip().lower().replace(" ", "_")
    return f"{base}_colour"


def _iter_material_properties(material: Any) -> Iterable[tuple[str, int, Any]]:
    properties = getattr(material, "properties", None)
    if properties is not None:
        for prop in properties:
            yield (str(getattr(prop, "key", "")), int(getattr(prop, "semantic", 0)), getattr(prop, "data", None))
        return
    items = getattr(material, "items", None)
    if callable(items):
        for key, value in items():
            if isinstance(key, tuple):
                yield (str(key[0]), int(key[1]), value)
            else:
                yield (str(key), _SEMANTIC_NONE, value)


def _find_material_property(material: Any, key_names: Sequence[str], semantics: Sequence[int]) -> Any | None:
    wanted_keys = {key.lower() for key in key_names}
    wanted_semantics = {int(value) for value in semantics}
    for key, semantic, value in _iter_material_properties(material):
        if key.lower() in wanted_keys and int(semantic) in wanted_semantics:
            return value
    return None


def _material_name(material: Any, index: int) -> str:
    raw = _find_material_property(material, ("?mat.name", "$mat.name"), (_SEMANTIC_NONE,))
    if raw is None:
        return f"material_{index}"
    text = str(raw).strip()
    return text or f"material_{index}"


def _make_unique_name(base_name: str, used: set[str]) -> str:
    candidate = base_name or "material"
    if candidate not in used:
        used.add(candidate)
        return candidate
    suffix = 1
    while True:
        next_candidate = f"{candidate}_{suffix}"
        if next_candidate not in used:
            used.add(next_candidate)
            return next_candidate
        suffix += 1


def _infer_shader(
    material: AssimpMaterial,
    default_shader: str | YdrShader | YdrGen9Shader,
) -> str | YdrShader | YdrGen9Shader:
    has_normal = material.normal_texture is not None
    has_spec = material.specular_texture is not None
    if has_normal and has_spec:
        return "normal_spec.sps"
    if has_normal:
        return "normal.sps"
    if has_spec:
        return "spec.sps"
    return default_shader


def _build_material_inputs(
    scene_materials: Sequence[Any],
    *,
    default_shader: str | YdrShader | YdrGen9Shader,
    shader: str | YdrShader | YdrGen9Shader | None,
    material_colours_as_textures: bool,
) -> tuple[list[YdrMaterialInput], dict[int, str], Ytd | None]:
    if not scene_materials:
        selected_shader = shader if shader is not None else default_shader
        return ([AssimpMaterial(name="default").to_ydr_material(shader=selected_shader)], {0: "default"}, None)
    used_names: set[str] = set()
    used_texture_names: set[str] = set()
    material_inputs: list[YdrMaterialInput] = []
    index_to_name: dict[int, str] = {}
    embedded_textures: Ytd | None = None
    for index, material in enumerate(scene_materials):
        name = _make_unique_name(_material_name(material, index), used_names)
        parsed = AssimpMaterial(
            name=name,
            diffuse_texture=_texture_name(_find_material_property(material, ("$tex.file",), (_SEMANTIC_DIFFUSE,))),
            normal_texture=_texture_name(_find_material_property(material, ("$tex.file",), (_SEMANTIC_NORMALS, _SEMANTIC_HEIGHT))),
            specular_texture=_texture_name(_find_material_property(material, ("$tex.file",), (_SEMANTIC_SPECULAR,))),
            diffuse_color=_colour4(_find_material_property(material, ("$clr.diffuse", "?clr.diffuse"), (_SEMANTIC_NONE,))),
        )
        if material_colours_as_textures and parsed.diffuse_texture is None and parsed.diffuse_color is not None:
            texture_name = _make_unique_name(_material_colour_texture_name(name), used_texture_names)
            parsed.diffuse_texture = texture_name
            if embedded_textures is None:
                embedded_textures = Ytd()
            embedded_textures.add_texture(_solid_colour_texfury_texture(texture_name, parsed.diffuse_color))
        selected_shader = shader if shader is not None else _infer_shader(parsed, default_shader)
        material_inputs.append(parsed.to_ydr_material(shader=selected_shader))
        index_to_name[index] = name
    return material_inputs, index_to_name, embedded_textures


def _resolve_mesh_material_name(scene_materials: Sequence[Any], mesh: Any, material_names: dict[int, str]) -> str:
    mesh_material = getattr(mesh, "material", None)
    if mesh_material is None:
        return material_names.get(0, "default")
    for index, material in enumerate(scene_materials):
        if material == mesh_material:
            return material_names[index]
    return material_names.get(0, "default")


def _mesh_instances(scene: Any) -> list[tuple[Any, numpy.ndarray]]:
    root = getattr(scene, "root_node", None)
    meshes = _safe_list(getattr(scene, "meshes", []))
    if root is None:
        return [(mesh, numpy.identity(4, dtype=float)) for mesh in meshes]
    instances: list[tuple[Any, numpy.ndarray]] = []

    def visit(node: Any, parent_transform: numpy.ndarray) -> None:
        world_transform = parent_transform @ _as_matrix4(getattr(node, "transformation", None))
        for mesh in _safe_list(getattr(node, "meshes", [])):
            instances.append((mesh, world_transform))
        for child in _safe_list(getattr(node, "children", [])):
            visit(child, world_transform)

    visit(root, numpy.identity(4, dtype=float))
    if instances:
        return instances
    return [(mesh, numpy.identity(4, dtype=float)) for mesh in meshes]


def _mesh_to_input(
    mesh: Any,
    transform: numpy.ndarray,
    material_name: str,
    *,
    default_colour: tuple[float, float, float, float] | None = None,
) -> YdrMeshInput | None:
    if _safe_list(getattr(mesh, "bones", [])):
        raise NotImplementedError("Skinned Assimp mesh import is not implemented yet.")
    vertices = _safe_list(getattr(mesh, "vertices", []))
    faces = _safe_list(getattr(mesh, "faces", []))
    if not vertices or not faces:
        return None
    positions = [_transform_position(value, transform) for value in vertices]
    indices: list[int] = []
    for face in faces:
        face_indices = [int(value) for value in face]
        if len(face_indices) < 3:
            continue
        for tri_index in range(1, len(face_indices) - 1):
            indices.extend((face_indices[0], face_indices[tri_index], face_indices[tri_index + 1]))
    if not indices:
        return None
    normals_source = _safe_list(getattr(mesh, "normals", []))
    normals = [_transform_direction(value, transform) for value in normals_source] if len(normals_source) == len(vertices) else None
    tangents_source = _safe_list(getattr(mesh, "tangents", []))
    bitangents_source = _safe_list(getattr(mesh, "bitangents", []))
    tangents = None
    if len(tangents_source) == len(vertices):
        tangents = []
        for index, tangent in enumerate(tangents_source):
            tx, ty, tz = _transform_direction(tangent, transform)
            handedness = 1.0
            if normals is not None and len(bitangents_source) == len(vertices):
                bitangent = numpy.array(_transform_direction(bitangents_source[index], transform), dtype=float)
                tangent_vec = numpy.array((tx, ty, tz), dtype=float)
                normal_vec = numpy.array(normals[index], dtype=float)
                cross = numpy.cross(normal_vec, tangent_vec)
                handedness = -1.0 if float(numpy.dot(cross, bitangent)) < 0.0 else 1.0
            tangents.append((tx, ty, tz, handedness))
    colours = None
    colour_sets = _safe_list(getattr(mesh, "colors", []))
    if colour_sets and colour_sets[0] is not None:
        colours0 = _safe_list(colour_sets[0])
        if len(colours0) == len(vertices):
            colours = [_vector4(value) for value in colours0]
    if colours is None and default_colour is not None:
        colours = [default_colour] * len(vertices)
    texcoords = None
    texcoord_sets = _safe_list(getattr(mesh, "texture_coords", []))
    if texcoord_sets and texcoord_sets[0] is not None:
        uv0 = _safe_list(texcoord_sets[0])
        if len(uv0) == len(vertices):
            texcoords = [[_uv2(value) for value in uv0]]
    return YdrMeshInput(
        positions=positions,
        indices=indices,
        material=material_name,
        normals=normals,
        texcoords=texcoords,
        tangents=tangents,
        colours0=colours,
    )


def _compute_scene_bounds(
    meshes: Sequence[YdrMeshInput],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float]:
    return compute_bounds([position for mesh in meshes for position in mesh.positions])


def _lowercase_output_path(value: str | Path) -> Path:
    path = Path(value)
    return path.with_name(path.name.lower())


def _resolve_target_version(*, version: int | None, game: GameTarget | None) -> int:
    if version is not None:
        return int(version)
    if game is None:
        return _LEGACY_YDR_VERSION
    target_game = coerce_game_target(game)
    if target_game is GameTarget.GTA5:
        return _LEGACY_YDR_VERSION
    if target_game is GameTarget.GTA5_ENHANCED:
        return _ENHANCED_YDR_VERSION
    raise ValueError(f"Unsupported Assimp->YDR target game: {game}")


def save_companion_ytyp(scene: AssimpScene, destination: str | Path, *, cutscene_prop: bool = False) -> Path:
    target = _lowercase_output_path(destination)
    base_name = target.stem.lower()
    ytyp_name = f"{base_name}_meta"
    centre, bb_min, bb_max, radius = _compute_scene_bounds(scene.meshes)
    lod_dist = infer_archetype_lod_dist(bs_radius=radius, bb_min=bb_min, bb_max=bb_max)
    hd_texture_dist = infer_archetype_hd_texture_dist(
        bs_radius=radius,
        lod_dist=lod_dist,
        bb_min=bb_min,
        bb_max=bb_max,
    )
    ytyp = Ytyp(name=ytyp_name)
    ytyp.add_archetype(
        Archetype(
            name=base_name,
            asset_name=base_name,
            texture_dictionary=f"{base_name}_txd",
            asset_type=ArchetypeAssetType.DRAWABLE,
            flags=int(cutscene_prop_flags(animated=True)) if cutscene_prop else 0,
            lod_dist=lod_dist,
            hd_texture_dist=hd_texture_dist,
            bb_min=bb_min,
            bb_max=bb_max,
            bs_centre=centre,
            bs_radius=radius,
        )
    )
    return ytyp.save(target.with_name(f"{ytyp_name}.ytyp"))


def read_assimp_scene(
    source: str | Path,
    *,
    default_shader: str | YdrShader | YdrGen9Shader = "default.sps",
    shader: str | YdrShader | YdrGen9Shader | None = None,
    processing: int | None = None,
    default_colour: tuple[float, float, float, float] | None = None,
    material_colours_as_textures: bool = False,
) -> AssimpScene:
    source_path = _validate_input_format(source)
    scene = _read_impasse_scene(source_path, processing=processing)
    scene_materials = _safe_list(getattr(scene, "materials", []))
    materials, material_names, embedded_textures = _build_material_inputs(
        scene_materials,
        default_shader=default_shader,
        shader=shader,
        material_colours_as_textures=material_colours_as_textures,
    )
    meshes: list[YdrMeshInput] = []
    for mesh, transform in _mesh_instances(scene):
        material_name = _resolve_mesh_material_name(scene_materials, mesh, material_names)
        mesh_input = _mesh_to_input(mesh, transform, material_name, default_colour=default_colour)
        if mesh_input is not None:
            meshes.append(mesh_input)
    if not meshes:
        raise ValueError(f"Assimp source '{source_path}' does not contain any triangle meshes")
    return AssimpScene(meshes=meshes, materials=materials, name=source_path.stem.lower(), embedded_textures=embedded_textures)


def assimp_to_ydr(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    default_shader: str | YdrShader | YdrGen9Shader = "default.sps",
    shader: str | YdrShader | YdrGen9Shader | None = None,
    processing: int | None = None,
    default_colour: tuple[float, float, float, float] | None = None,
    material_colours_as_textures: bool = False,
    generate_ytyp: bool = False,
    cutscene_prop: bool = False,
    version: int | None = None,
    game: GameTarget | None = None,
) -> YdrBuild:
    scene = read_assimp_scene(
        source,
        default_shader=default_shader,
        shader=shader,
        processing=processing,
        default_colour=default_colour,
        material_colours_as_textures=material_colours_as_textures,
    )
    build = scene.to_ydr(version=version, game=game)
    if destination is None:
        destination = Path(source).with_suffix(".ydr")
    result = save_ydr(build, _lowercase_output_path(destination))
    if generate_ytyp:
        save_companion_ytyp(scene, result, cutscene_prop=cutscene_prop)
    return build


__all__ = [
    "AssimpMaterial",
    "AssimpScene",
    "assimp_to_ydr",
    "read_assimp_scene",
    "save_companion_ytyp",
]
