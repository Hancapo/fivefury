from __future__ import annotations

import dataclasses
import enum

from ..drawable import (
    DRAWABLE_LOD_ORDER,
    DrawableAsset,
    DrawableLod,
    DrawableMaterial,
    DrawableMesh,
    DrawableModel,
    DrawableParameter,
)

Matrix4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]


CdrLod = DrawableLod
CDR_LOD_ORDER = DRAWABLE_LOD_ORDER


class CdrGeometryType(enum.IntEnum):
    QUICK_BUFFER = 0
    EDGE = 1


class CdrIndexFlavor(enum.IntEnum):
    TRIANGLE_LIST_CW = 0
    TRIANGLE_LIST_CCW = 1
    COMPRESSED_TRIANGLE_LIST_CW = 2
    COMPRESSED_TRIANGLE_LIST_CCW = 3


class CdrSkinningFlavor(enum.IntEnum):
    NONE = 0
    NO_SCALING = 1
    UNIFORM_SCALING = 2
    NON_UNIFORM_SCALING = 3
    SINGLE_BONE_NO_SCALING = 4
    SINGLE_BONE_UNIFORM_SCALING = 5
    SINGLE_BONE_NON_UNIFORM_SCALING = 6


class CdrVertexSemantic(enum.IntEnum):
    POSITION = 0
    WEIGHT = 1
    BINDING = 2
    NORMAL = 3
    DIFFUSE = 4
    SPECULAR = 5
    TEXCOORD0 = 6
    TEXCOORD1 = 7
    TEXCOORD2 = 8
    TEXCOORD3 = 9
    TEXCOORD4 = 10
    TEXCOORD5 = 11
    TEXCOORD6 = 12
    TEXCOORD7 = 13
    TANGENT0 = 14
    TANGENT1 = 15
    BINORMAL0 = 16
    BINORMAL1 = 17


@dataclasses.dataclass(slots=True)
class CdrVertexFormat:
    channels: int
    stride: int
    flags: int
    dynamic_order: bool
    channel_count: int
    channel_types: int

    def has(self, semantic: CdrVertexSemantic | int) -> bool:
        return bool(self.channels & (1 << int(semantic)))

    def type_of(self, semantic: CdrVertexSemantic | int) -> int:
        return int((self.channel_types >> (int(semantic) * 4)) & 0xF)


@dataclasses.dataclass(slots=True)
class CdrMaterialParameter(DrawableParameter):
    name: str
    name_hash: int
    register: int = 0
    sampler_state: int = 0
    value: float | tuple[float, ...] | tuple[tuple[float, ...], ...] | None = None
    texture_name: str | None = None

    @property
    def is_texture(self) -> bool:
        return self.texture_name is not None


@dataclasses.dataclass(slots=True)
class CdrMaterial(DrawableMaterial[CdrMaterialParameter]):
    index: int
    name: str
    shader_hash: int
    shader_name: str | None
    shader_file_name: str | None
    material_hash: int
    render_bucket: int
    draw_bucket_mask: int
    parameters: list[CdrMaterialParameter] = dataclasses.field(default_factory=list)

@dataclasses.dataclass(slots=True)
class CdrBone:
    name: str
    index: int
    bone_id: int
    parent_index: int
    next_sibling_index: int
    mirror_index: int
    flags: int
    rotation: tuple[float, float, float, float]
    translation: tuple[float, float, float]
    scale: tuple[float, float, float]
    inverse_bind_transform: Matrix4 | None = None
    default_transform: Matrix4 | None = None


@dataclasses.dataclass(slots=True)
class CdrSkeleton:
    bones: list[CdrBone] = dataclasses.field(default_factory=list)
    parent_indices: list[int] = dataclasses.field(default_factory=list)
    child_parent_indices: list[int] = dataclasses.field(default_factory=list)
    signature: int = 0
    signature_non_chiral: int = 0
    signature_comprehensive: int = 0

    def get_bone_by_index(self, index: int) -> CdrBone | None:
        return self.bones[index] if 0 <= index < len(self.bones) else None

    def get_bone_by_id(self, bone_id: int) -> CdrBone | None:
        return next((bone for bone in self.bones if bone.bone_id == int(bone_id)), None)

    def get_bone_by_name(self, name: str) -> CdrBone | None:
        lowered = str(name).lower()
        return next((bone for bone in self.bones if bone.name.lower() == lowered), None)


@dataclasses.dataclass(slots=True)
class CdrJointControlPoint:
    max_swing: float
    min_twist: float
    max_twist: float


@dataclasses.dataclass(slots=True)
class CdrJointRotationLimit:
    bone_id: int
    control_point_count: int
    degrees_of_freedom: int
    zero_rotation: tuple[float, float, float, float]
    zero_rotation_euler: tuple[float, float, float]
    twist_axis: tuple[float, float, float]
    min_twist: float
    max_twist: float
    soft_limit_scale: float
    control_points: list[CdrJointControlPoint] = dataclasses.field(default_factory=list)
    use_twist_limits: bool = False
    use_euler_angles: bool = False
    use_per_control_twist_limits: bool = False


@dataclasses.dataclass(slots=True)
class CdrJointVectorLimit:
    bone_id: int
    min: tuple[float, float, float]
    max: tuple[float, float, float]


@dataclasses.dataclass(slots=True)
class CdrJoints:
    name: str = ""
    rotation_limits: list[CdrJointRotationLimit] = dataclasses.field(default_factory=list)
    translation_limits: list[CdrJointVectorLimit] = dataclasses.field(default_factory=list)
    scale_limits: list[CdrJointVectorLimit] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(slots=True)
class CdrEdgeStreamAttribute:
    offset: int
    format: int
    component_count: int
    semantic_id: int
    size: int
    vertex_program_slot: int
    fixed_block_offset: int
    fixed_bits: tuple[int, ...] = ()


@dataclasses.dataclass(slots=True)
class CdrEdgeStream:
    stride: int
    attributes: list[CdrEdgeStreamAttribute] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(slots=True)
class CdrEdgeSegment:
    vertex_count: int
    index_count: int
    index_flavor: CdrIndexFlavor
    skinning_flavor: CdrSkinningFlavor
    input_format_id: int
    secondary_input_format_id: int
    output_format_id: int
    indices: list[int] = dataclasses.field(default_factory=list)
    attributes: dict[int, list[tuple[float, ...]]] = dataclasses.field(default_factory=dict)
    blend_weights: list[tuple[float, float, float, float]] = dataclasses.field(default_factory=list)
    blend_indices: list[tuple[int, int, int, int]] = dataclasses.field(default_factory=list)
    matrix_group_offsets: tuple[int, int] = (0, 0)
    matrix_group_counts: tuple[int, int] = (0, 0)
    input_stream: CdrEdgeStream | None = None
    secondary_input_stream: CdrEdgeStream | None = None
    rsx_stream: CdrEdgeStream | None = None
    skin_indices_and_weights: bytes = dataclasses.field(default=b"", repr=False)
    raw_indices: bytes = dataclasses.field(default=b"", repr=False)
    raw_vertices: bytes = dataclasses.field(default=b"", repr=False)
    raw_secondary_vertices: bytes = dataclasses.field(default=b"", repr=False)
    raw_rsx_vertices: bytes = dataclasses.field(default=b"", repr=False)


@dataclasses.dataclass(slots=True)
class CdrMesh(DrawableMesh[CdrMaterial]):
    geometry_type: CdrGeometryType
    material_index: int = -1
    material: CdrMaterial | None = None
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
    vertex_format: CdrVertexFormat | None = None
    edge_segments: list[CdrEdgeSegment] = dataclasses.field(default_factory=list)

@dataclasses.dataclass(slots=True)
class CdrModel(DrawableModel[CdrMesh, CdrMaterial]):
    lod: CdrLod
    index: int
    meshes: list[CdrMesh] = dataclasses.field(default_factory=list)
    matrix_count: int = 0
    flags: int = 0
    model_type: int = 0
    matrix_index: int = 0
    render_mask: int = 0
    skin_flags: int = 0
    bounding_box_min: tuple[float, float, float] | None = None
    bounding_box_max: tuple[float, float, float] | None = None


@dataclasses.dataclass(slots=True)
class Cdr(DrawableAsset[CdrMaterial, CdrModel, CdrMesh]):
    version: int
    path: str = ""
    materials: list[CdrMaterial] = dataclasses.field(default_factory=list)
    lods: dict[CdrLod, list[CdrModel]] = dataclasses.field(default_factory=dict)
    bounding_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounding_sphere_radius: float = 0.0
    bounding_box_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounding_box_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    lod_distances: dict[CdrLod, float] = dataclasses.field(default_factory=dict)
    render_bucket_masks: dict[CdrLod, int] = dataclasses.field(default_factory=dict)
    texture_dictionary_pointer: int = 0
    skeleton_pointer: int = 0
    skeleton: CdrSkeleton | None = None
    joint_data_pointer: int = 0
    joints: CdrJoints | None = None
    page_map_pointer: int = 0
    debug_name: str = ""
    system_data: bytes = dataclasses.field(default=b"", repr=False)
    graphics_data: bytes = dataclasses.field(default=b"", repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.render_bucket_masks = {
            DrawableLod(lod): int(mask)
            for lod, mask in self.render_bucket_masks.items()
        }

    @property
    def platform(self) -> str:
        return "ps3"

__all__ = [
    "CDR_LOD_ORDER",
    "Cdr",
    "CdrBone",
    "CdrEdgeSegment",
    "CdrEdgeStream",
    "CdrEdgeStreamAttribute",
    "CdrGeometryType",
    "CdrIndexFlavor",
    "CdrJointControlPoint",
    "CdrJointRotationLimit",
    "CdrJointVectorLimit",
    "CdrJoints",
    "CdrLod",
    "CdrMaterial",
    "CdrMaterialParameter",
    "CdrMesh",
    "CdrModel",
    "CdrSkinningFlavor",
    "CdrSkeleton",
    "CdrVertexFormat",
    "CdrVertexSemantic",
]
