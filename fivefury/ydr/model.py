from __future__ import annotations

import dataclasses
import enum
import math
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Sequence, Union

from ..bounds import Bound
from ..hashing import jenk_hash
from ..ytd import Texture, TextureFormat, Ytd
from ._helpers import find_material, find_parameter
from .defs import LOD_ORDER, YdrLod, YdrSkeletonBinding, coerce_lod, coerce_skeleton_binding
from .shaders import ShaderDefinition

if TYPE_CHECKING:
    from ..bounds import BoundComposite, BoundCompositeFlags, BoundMaterial
    from .build_types import YdrBuild, YdrMaterialInput, YdrMeshInput, YdrModelInput, YdrTextureInput
    from .collision import YdrCollisionStats
    from .materials import YdrMaterialDescriptor
    from .shaders import ShaderLibrary


NumericParameterValue = float | tuple[float, ...] | tuple[tuple[float, ...], ...]
Matrix4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]


@dataclasses.dataclass(slots=True)
class YdrValidationIssue:
    level: str
    code: str
    message: str
    context: str = ""


class YdrLightType(enum.IntEnum):
    POINT = 1
    SPOT = 2
    CAPSULE = 4


class YdrBoneFlags(enum.IntFlag):
    NONE = 0
    ROT_X = 0x1
    ROT_Y = 0x2
    ROT_Z = 0x4
    LIMIT_ROTATION = 0x8
    TRANS_X = 0x10
    TRANS_Y = 0x20
    TRANS_Z = 0x40
    LIMIT_TRANSLATION = 0x80
    SCALE_X = 0x100
    SCALE_Y = 0x200
    SCALE_Z = 0x400
    LIMIT_SCALE = 0x800
    UNKNOWN_0 = 0x1000
    UNKNOWN_1 = 0x2000
    UNKNOWN_2 = 0x4000
    UNKNOWN_3 = 0x8000


def calculate_bone_tag(name: str) -> int:
    hash_value = 0
    for char in str(name):
        code = ord(char)
        if 97 <= code <= 122:
            code -= 32
        hash_value = ((hash_value << 4) + code) & 0xFFFFFFFF
        high = hash_value & 0xF0000000
        if high:
            hash_value ^= high >> 24
        hash_value &= ~high
    return int((hash_value % 0xFE8F) + 0x170)


@dataclasses.dataclass(slots=True)
class YdrBone:
    name: str = ""
    tag: int = 0
    index: int = 0
    parent_index: int = -1
    next_sibling_index: int = -1
    flags: YdrBoneFlags = YdrBoneFlags.NONE
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    transform_unk: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    inverse_bind_transform: Matrix4 | None = None
    unknown_1ch: int = 0
    unknown_2ch: float = 1.0
    unknown_34h: int = 0
    unknown_48h: int = 0


@dataclasses.dataclass(slots=True)
class YdrSkeleton:
    bones: list[YdrBone] = dataclasses.field(default_factory=list)
    parent_indices: list[int] = dataclasses.field(default_factory=list)
    child_indices: list[int] = dataclasses.field(default_factory=list)
    transformations: list[Matrix4] = dataclasses.field(default_factory=list)
    transformations_inverted: list[Matrix4] = dataclasses.field(default_factory=list)
    unknown_1ch: int = 0
    unknown_50h: int = 0
    unknown_54h: int = 0
    unknown_58h: int = 0
    unknown_5ch: int = 1
    unknown_62h: int = 0
    unknown_64h: int = 0
    unknown_68h: int = 0

    @classmethod
    def create(cls) -> "YdrSkeleton":
        return cls()

    @property
    def bone_count(self) -> int:
        return len(self.bones)

    def build(self) -> "YdrSkeleton":
        for index, bone in enumerate(self.bones):
            bone.index = index
            bone.next_sibling_index = -1
        parent_to_children: dict[int, list[YdrBone]] = {}
        for bone in self.bones:
            parent_to_children.setdefault(int(bone.parent_index), []).append(bone)
        for children in parent_to_children.values():
            for current, nxt in zip(children, children[1:]):
                current.next_sibling_index = int(nxt.index)
        self.parent_indices = [int(item.parent_index) for item in self.bones]
        self.child_indices = []
        self.transformations = []
        self.transformations_inverted = []
        return self

    def get_bone_by_index(self, index: int) -> YdrBone | None:
        if 0 <= int(index) < len(self.bones):
            return self.bones[int(index)]
        return None

    def get_bone_by_tag(self, tag: int) -> YdrBone | None:
        for bone in self.bones:
            if int(bone.tag) == int(tag):
                return bone
        return None

    def get_bone_by_name(self, name: str) -> YdrBone | None:
        lowered = str(name).lower()
        for bone in self.bones:
            if bone.name.lower() == lowered:
                return bone
        return None

    def require_bone(self, value: str | int) -> YdrBone:
        bone = self.get_bone_by_name(value) if isinstance(value, str) else self.get_bone_by_index(value)
        if bone is None and isinstance(value, int):
            bone = self.get_bone_by_tag(value)
        if bone is None:
            raise KeyError(f"Unknown YDR bone '{value}'")
        return bone

    def add_bone(
        self,
        name: str,
        *,
        parent: YdrBone | str | int | None = None,
        tag: int | None = None,
        flags: YdrBoneFlags = YdrBoneFlags.NONE,
        rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
        translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
        scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    ) -> YdrBone:
        index = len(self.bones)
        parent_index = -1
        if parent is not None:
            if isinstance(parent, YdrBone):
                parent_bone = parent
            elif isinstance(parent, str):
                parent_bone = self.require_bone(parent)
            else:
                parent_bone = self.require_bone(int(parent))
            parent_index = int(parent_bone.index)
            siblings = [bone for bone in self.bones if int(bone.parent_index) == parent_index]
            if siblings:
                siblings[-1].next_sibling_index = index
        bone = YdrBone(
            name=str(name),
            tag=int(calculate_bone_tag(name) if tag is None else tag),
            index=index,
            parent_index=parent_index,
            next_sibling_index=-1,
            flags=flags,
            rotation=tuple(float(v) for v in rotation),
            translation=tuple(float(v) for v in translation),
            scale=tuple(float(v) for v in scale),
        )
        self.bones.append(bone)
        self.build()
        return bone

    def resolve_bone_ids(self, bone_ids: Sequence[int]) -> list[YdrBone]:
        resolved: list[YdrBone] = []
        for bone_id in bone_ids:
            bone = self.get_bone_by_tag(int(bone_id))
            if bone is None:
                bone = self.get_bone_by_index(int(bone_id))
            if bone is not None:
                resolved.append(bone)
        return resolved


@dataclasses.dataclass(slots=True)
class YdrJointControlPoint:
    max_swing: float = 0.0
    min_twist: float = 0.0
    max_twist: float = 0.0


@dataclasses.dataclass(slots=True)
class YdrJointRotationLimit:
    bone_id: int = 0
    unknown_ah: int = 0
    unknown_0h: int = 0
    unknown_4h: int = 0
    unknown_14h: int = 0
    unknown_18h: int = 0
    unknown_1ch: int = 0
    unknown_20h: int = 0
    unknown_24h: int = 0
    unknown_28h: int = 0
    unknown_30h: int = 0
    unknown_34h: int = 0
    unknown_38h: int = 0
    unknown_3ch: int = 0
    unknown_44h: int = 0
    unknown_48h: int = 0
    unknown_4ch: int = 0
    unknown_bch: int = 0x100
    num_control_points: int = 1
    joint_dofs: int = 3
    unknown_2ch: float = 1.0
    unknown_40h: float = 1.0
    soft_limit_scale: float = 1.0
    min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    twist_limit_min: float = -math.pi
    twist_limit_max: float = math.pi
    unknown_74h: float = math.pi
    unknown_78h: float = -math.pi
    unknown_7ch: float = math.pi
    unknown_80h: float = math.pi
    unknown_84h: float = -math.pi
    unknown_88h: float = math.pi
    unknown_8ch: float = math.pi
    unknown_90h: float = -math.pi
    unknown_94h: float = math.pi
    unknown_98h: float = math.pi
    unknown_9ch: float = -math.pi
    unknown_a0h: float = math.pi
    unknown_a4h: float = math.pi
    unknown_a8h: float = -math.pi
    unknown_ach: float = math.pi
    unknown_b0h: float = math.pi
    unknown_b4h: float = -math.pi
    unknown_b8h: float = math.pi

    def build(self) -> "YdrJointRotationLimit":
        self.min = tuple(float(v) for v in self.min)
        self.max = tuple(float(v) for v in self.max)
        self.num_control_points = int(self.num_control_points)
        self.joint_dofs = int(self.joint_dofs)
        return self


@dataclasses.dataclass(slots=True)
class YdrJointTranslationLimit:
    bone_id: int = 0
    min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    unknown_0h: int = 0
    unknown_4h: int = 0
    unknown_ch: int = 0
    unknown_10h: int = 0
    unknown_14h: int = 0
    unknown_18h: int = 0
    unknown_1ch: int = 0
    unknown_2ch: int = 0
    unknown_3ch: int = 0

    def build(self) -> "YdrJointTranslationLimit":
        self.min = tuple(float(v) for v in self.min)
        self.max = tuple(float(v) for v in self.max)
        return self


@dataclasses.dataclass(slots=True)
class YdrJoints:
    rotation_limits: list[YdrJointRotationLimit] = dataclasses.field(default_factory=list)
    translation_limits: list[YdrJointTranslationLimit] = dataclasses.field(default_factory=list)
    vft: int = 0x40617800
    unknown_4h: int = 1
    unknown_8h: int = 0
    unknown_20h: int = 0
    unknown_28h: int = 0
    unknown_34h: int = 0
    unknown_36h: int = 1
    unknown_38h: int = 0

    @property
    def has_limits(self) -> bool:
        return bool(self.rotation_limits or self.translation_limits)

    def build(self) -> "YdrJoints":
        self.vft = int(self.vft)
        self.unknown_4h = int(self.unknown_4h)
        self.unknown_8h = int(self.unknown_8h)
        self.unknown_20h = int(self.unknown_20h)
        self.unknown_28h = int(self.unknown_28h)
        self.unknown_34h = int(self.unknown_34h)
        self.unknown_36h = int(self.unknown_36h)
        self.unknown_38h = int(self.unknown_38h)
        for limit in self.rotation_limits:
            limit.build()
        for limit in self.translation_limits:
            limit.build()
        return self

    def add_rotation_limit(
        self,
        *,
        bone_id: int,
        min: tuple[float, float, float] = (0.0, 0.0, 0.0),
        max: tuple[float, float, float] = (0.0, 0.0, 0.0),
        unknown_ah: int = 0,
        num_control_points: int = 1,
        joint_dofs: int = 3,
    ) -> YdrJointRotationLimit:
        limit = YdrJointRotationLimit(
            bone_id=int(bone_id),
            min=tuple(float(v) for v in min),
            max=tuple(float(v) for v in max),
            unknown_ah=int(unknown_ah) & 0xFFFF,
            num_control_points=int(num_control_points),
            joint_dofs=int(joint_dofs),
        )
        self.rotation_limits.append(limit)
        return limit

    def add_translation_limit(
        self,
        *,
        bone_id: int,
        min: tuple[float, float, float] = (0.0, 0.0, 0.0),
        max: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> YdrJointTranslationLimit:
        limit = YdrJointTranslationLimit(
            bone_id=int(bone_id),
            min=tuple(float(v) for v in min),
            max=tuple(float(v) for v in max),
        )
        self.translation_limits.append(limit)
        return limit


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

    def to_builder_value(self) -> NumericParameterValue | None:
        if self.is_texture or self.value is None:
            return None
        if isinstance(self.value, tuple) and self.value and isinstance(self.value[0], tuple):
            return tuple(tuple(float(component) for component in row) for row in self.value)
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

    @classmethod
    def point(
        cls,
        *,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: tuple[int, int, int] = (255, 255, 255),
        intensity: float = 1.0,
        falloff: float = 0.0,
        flags: int = 0,
        bone_id: int = 0,
        group_id: int = 0,
        time_flags: int = 0,
        **overrides: object,
    ) -> "YdrLight":
        return cls(
            position=tuple(float(v) for v in position),
            color=tuple(int(v) for v in color),
            intensity=float(intensity),
            falloff=float(falloff),
            flags=int(flags),
            bone_id=int(bone_id),
            light_type=YdrLightType.POINT,
            group_id=int(group_id),
            time_flags=int(time_flags),
            **overrides,
        )

    @classmethod
    def spot(
        cls,
        *,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        direction: tuple[float, float, float] = (0.0, 0.0, -1.0),
        color: tuple[int, int, int] = (255, 255, 255),
        intensity: float = 1.0,
        falloff: float = 0.0,
        cone_inner_angle: float = 0.0,
        cone_outer_angle: float = 0.0,
        flags: int = 0,
        bone_id: int = 0,
        group_id: int = 0,
        time_flags: int = 0,
        **overrides: object,
    ) -> "YdrLight":
        return cls(
            position=tuple(float(v) for v in position),
            direction=tuple(float(v) for v in direction),
            color=tuple(int(v) for v in color),
            intensity=float(intensity),
            falloff=float(falloff),
            cone_inner_angle=float(cone_inner_angle),
            cone_outer_angle=float(cone_outer_angle),
            flags=int(flags),
            bone_id=int(bone_id),
            light_type=YdrLightType.SPOT,
            group_id=int(group_id),
            time_flags=int(time_flags),
            **overrides,
        )

    @classmethod
    def capsule(
        cls,
        *,
        position: tuple[float, float, float] = (0.0, 0.0, 0.0),
        extent: tuple[float, float, float] = (0.0, 0.0, 0.0),
        color: tuple[int, int, int] = (255, 255, 255),
        intensity: float = 1.0,
        falloff: float = 0.0,
        flags: int = 0,
        bone_id: int = 0,
        group_id: int = 0,
        time_flags: int = 0,
        **overrides: object,
    ) -> "YdrLight":
        return cls(
            position=tuple(float(v) for v in position),
            extent=tuple(float(v) for v in extent),
            color=tuple(int(v) for v in color),
            intensity=float(intensity),
            falloff=float(falloff),
            flags=int(flags),
            bone_id=int(bone_id),
            light_type=YdrLightType.CAPSULE,
            group_id=int(group_id),
            time_flags=int(time_flags),
            **overrides,
        )


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
    def slot_index(self) -> int:
        return int(self.index)

    @property
    def material_descriptor(self) -> YdrMaterialDescriptor:
        from .materials import build_material_descriptor

        return build_material_descriptor(self)

    def ycd_uv_binding(self, *, object_name: str) -> "YcdUvClipBinding":
        from ..ycd import YcdUvClipBinding

        return YcdUvClipBinding(object_name=str(object_name), slot_index=self.slot_index)

    def ycd_uv_clip_name(self, *, object_name: str) -> str:
        return self.ycd_uv_binding(object_name=object_name).clip_name

    def ycd_uv_clip_hash(self, *, object_name: str) -> int:
        return int(self.ycd_uv_binding(object_name=object_name).clip_hash.uint)

    def get_parameter(self, value: str | int) -> YdrMaterialParameterRef | None:
        return find_parameter(self.parameters, value)

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
                    value=(
                        previous.value
                        if previous is not None and previous.is_numeric and previous.value is not None
                        else definition.default_value
                    ),
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
        from .build_types import YdrMaterialInput

        material_name = self.name or f"material_{self.index}"
        textures = {
            parameter.name: parameter.texture.to_input()
            for parameter in self.parameters
            if parameter.is_texture and parameter.texture is not None
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
    vertex_buffer_flags: int = 0
    render_mask: int = 0
    flags: int = 0

    @property
    def texture_names(self) -> list[str]:
        return self.material.texture_names if self.material is not None else []

    def resolve_bones(self, skeleton: YdrSkeleton | None) -> list[YdrBone]:
        if skeleton is None:
            return []
        return skeleton.resolve_bone_ids(self.bone_ids)

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    @property
    def is_skinned(self) -> bool:
        return bool(self.blend_weights or self.blend_indices or self.bone_ids)

    def set_bone_ids(self, bone_ids: Sequence[int | YdrBone | str], *, skeleton: YdrSkeleton | None = None) -> "YdrMesh":
        resolved: list[int] = []
        for item in bone_ids:
            if isinstance(item, YdrBone):
                resolved.append(int(item.tag))
            elif isinstance(item, str):
                if skeleton is None:
                    raise ValueError("skeleton= is required when binding bones by name")
                resolved.append(int(skeleton.require_bone(item).tag))
            else:
                resolved.append(int(item))
        self.bone_ids = resolved
        return self

    def set_skin(
        self,
        *,
        bone_ids: Sequence[int | YdrBone | str] | None = None,
        weights: Sequence[tuple[float, float, float, float]] | None = None,
        indices: Sequence[tuple[int, int, int, int]] | None = None,
        skeleton: YdrSkeleton | None = None,
    ) -> "YdrMesh":
        if bone_ids is not None:
            self.set_bone_ids(bone_ids, skeleton=skeleton)
        if weights is not None:
            self.blend_weights = [tuple(float(component) for component in weight) for weight in weights]
        if indices is not None:
            self.blend_indices = [tuple(int(component) for component in index) for index in indices]
        return self

    def clear_skin(self) -> "YdrMesh":
        self.blend_weights = []
        self.blend_indices = []
        self.bone_ids = []
        return self

    def to_input(self, *, material_name: str | None = None) -> YdrMeshInput:
        from .build_types import YdrMeshInput

        return YdrMeshInput(
            positions=list(self.positions),
            indices=list(self.indices),
            material=material_name or (self.material.name if self.material is not None and self.material.name else f"material_{self.material_index}"),
            normals=list(self.normals),
            texcoords=[list(channel) for channel in self.texcoords],
            tangents=list(self.tangents),
            colours0=list(self.colours0),
            colours1=list(self.colours1),
            blend_weights=list(self.blend_weights) or None,
            blend_indices=list(self.blend_indices) or None,
            bone_ids=list(self.bone_ids) or None,
            vertex_buffer_flags=int(self.vertex_buffer_flags),
            declaration_flags=int(self.declaration_flags),
            declaration_types=int(self.declaration_types),
        )


@dataclasses.dataclass(slots=True)
class YdrModel:
    lod: YdrLod
    index: int = 0
    meshes: list[YdrMesh] = dataclasses.field(default_factory=list)
    render_mask: int = 0
    flags: int = 0
    skeleton_binding: YdrSkeletonBinding = dataclasses.field(default_factory=YdrSkeletonBinding)

    def __post_init__(self) -> None:
        self.lod = coerce_lod(self.lod)
        self.skeleton_binding = coerce_skeleton_binding(self.skeleton_binding)

    @property
    def has_skin(self) -> bool:
        return self.skeleton_binding.is_skinned

    @property
    def bone_index(self) -> int:
        return int(self.skeleton_binding.bone_index)

    @property
    def skeleton_binding_value(self) -> int:
        return int(self.skeleton_binding)

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

    @property
    def slot_indices(self) -> list[int]:
        return self.material_indices

    def iter_materials(self) -> Iterator[YdrMaterial]:
        yield from self.materials

    def get_material(self, value: str | int) -> YdrMaterial | None:
        return find_material(self.materials, value)

    def ycd_uv_binding(self, material: str | int, *, object_name: str) -> "YcdUvClipBinding":
        resolved = self.get_material(material)
        if resolved is None:
            raise KeyError(f"Unknown YDR model material '{material}'")
        return resolved.ycd_uv_binding(object_name=object_name)

    def ycd_uv_bindings(self, *, object_name: str) -> list["YcdUvClipBinding"]:
        return [material.ycd_uv_binding(object_name=object_name) for material in self.materials]

    def set_skin_binding(
        self,
        *,
        bone_index: int = 0,
        has_skin: int = 1,
        unknown_1: int = 0x11,
        unknown_2: int = 0,
    ) -> "YdrModel":
        self.skeleton_binding = YdrSkeletonBinding(
            unknown_1=int(unknown_1) & 0xFF,
            has_skin=int(has_skin) & 0xFF,
            unknown_2=int(unknown_2) & 0xFF,
            bone_index=int(bone_index) & 0xFF,
        )
        return self

    def bind_to_bone(
        self,
        bone: YdrBone | str | int,
        *,
        skeleton: YdrSkeleton | None = None,
        unknown_1: int = 0,
        unknown_2: int = 0,
    ) -> "YdrModel":
        if isinstance(bone, YdrBone):
            bone_index = int(bone.index)
        elif isinstance(bone, str):
            if skeleton is None:
                raise ValueError("skeleton= is required when binding a model by bone name")
            bone_index = int(skeleton.require_bone(bone).index)
        else:
            bone_index = int(bone)
        self.skeleton_binding = YdrSkeletonBinding.rigid(
            bone_index=bone_index,
            unknown_1=unknown_1,
            unknown_2=unknown_2,
        )
        return self

    def clear_skin_binding(self) -> "YdrModel":
        self.skeleton_binding = YdrSkeletonBinding()
        return self

    def to_input(self, *, material_name_by_index: dict[int, str]) -> YdrModelInput:
        from .build_types import YdrModelInput

        return YdrModelInput(
            meshes=[
                mesh.to_input(material_name=material_name_by_index.get(mesh.material_index, f"material_{mesh.material_index}"))
                for mesh in self.meshes
            ],
            render_mask=int(self.render_mask),
            flags=int(self.flags),
            skeleton_binding=coerce_skeleton_binding(self.skeleton_binding),
        )


@dataclasses.dataclass(slots=True)
class Ydr:
    version: int
    path: str = ""
    materials: list[YdrMaterial] = dataclasses.field(default_factory=list)
    lods: dict[YdrLod, list[YdrModel]] = dataclasses.field(default_factory=dict)
    bounding_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounding_sphere_radius: float = 0.0
    bounding_box_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounding_box_max: tuple[float, float, float] = (0.0, 0.0, 0.0)
    skeleton: YdrSkeleton | None = None
    joints: YdrJoints | None = None
    lights: list[YdrLight] = dataclasses.field(default_factory=list)
    embedded_textures: Ytd | None = None
    bound: Bound | None = None
    lod_distances: dict[YdrLod, float] = dataclasses.field(default_factory=dict)
    render_mask_flags: dict[YdrLod, int] = dataclasses.field(default_factory=dict)
    unknown_98: int = 0
    unknown_9c: int = 0

    def __post_init__(self) -> None:
        self.lods = {coerce_lod(lod): list(models) for lod, models in self.lods.items()}
        self.lod_distances = {coerce_lod(lod): float(distance) for lod, distance in self.lod_distances.items()}
        self.render_mask_flags = {coerce_lod(lod): int(flags) for lod, flags in self.render_mask_flags.items()}

    def build(self) -> "Ydr":
        if self.skeleton is not None:
            self.skeleton.build()
        if self.joints is not None:
            self.joints.build()
        for material_index, material in enumerate(self.materials):
            material.index = material_index
        for model_index, model in enumerate(self.models):
            model.index = model_index
            for mesh in model.meshes:
                if mesh.material is None and 0 <= mesh.material_index < len(self.materials):
                    mesh.material = self.materials[mesh.material_index]
        return self

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, *, path: str = "") -> "Ydr":
        from . import read_ydr

        return read_ydr(data, path=path)

    def get_lod(self, name: YdrLod | str) -> list[YdrModel]:
        return self.lods.get(coerce_lod(name), [])

    def iter_models(self, lod: YdrLod | str | None = None) -> Iterator[YdrModel]:
        if lod is not None:
            yield from self.get_lod(lod)
            return
        for name in LOD_ORDER:
            yield from self.lods.get(name, [])

    def iter_meshes(self, lod: YdrLod | str | None = None) -> Iterator[YdrMesh]:
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

    def get_model(self, index: int, *, lod: YdrLod | str | None = None) -> YdrModel | None:
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
        return find_material(self.materials, value)

    @property
    def slot_indices(self) -> list[int]:
        return [int(material.index) for material in self.materials]

    def ycd_uv_binding(self, material: str | int, *, object_name: str | None = None) -> "YcdUvClipBinding":
        resolved = self.get_material(material)
        if resolved is None:
            raise KeyError(f"Unknown YDR material '{material}'")
        return resolved.ycd_uv_binding(object_name=object_name or self.name)

    def ycd_uv_bindings(self, *, object_name: str | None = None) -> list["YcdUvClipBinding"]:
        binding_object_name = object_name or self.name
        return [material.ycd_uv_binding(object_name=binding_object_name) for material in self.materials]

    @property
    def has_skeleton(self) -> bool:
        return self.skeleton is not None and self.skeleton.bone_count > 0

    @property
    def has_joints(self) -> bool:
        return self.joints is not None and self.joints.has_limits

    def ensure_skeleton(self) -> YdrSkeleton:
        if self.skeleton is None:
            self.skeleton = YdrSkeleton.create()
        return self.skeleton

    def ensure_joints(self) -> YdrJoints:
        if self.joints is None:
            self.joints = YdrJoints()
        return self.joints

    def get_bone_by_index(self, index: int) -> YdrBone | None:
        if self.skeleton is None:
            return None
        return self.skeleton.get_bone_by_index(index)

    def get_bone_by_tag(self, tag: int) -> YdrBone | None:
        if self.skeleton is None:
            return None
        return self.skeleton.get_bone_by_tag(tag)

    def get_bone_by_name(self, name: str) -> YdrBone | None:
        if self.skeleton is None:
            return None
        return self.skeleton.get_bone_by_name(name)

    def add_bone(
        self,
        name: str,
        *,
        parent: YdrBone | str | int | None = None,
        tag: int | None = None,
        flags: YdrBoneFlags = YdrBoneFlags.NONE,
        rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
        translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
        scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    ) -> YdrBone:
        return self.ensure_skeleton().add_bone(
            name,
            parent=parent,
            tag=tag,
            flags=flags,
            rotation=rotation,
            translation=translation,
            scale=scale,
        )

    def set_joints(self, joints: YdrJoints) -> YdrJoints:
        self.joints = joints
        return joints

    def clear_joints(self) -> "Ydr":
        self.joints = None
        return self

    def add_light(
        self,
        light: YdrLight,
    ) -> YdrLight:
        self.lights.append(light)
        return light

    def clear_lights(self) -> "Ydr":
        self.lights.clear()
        return self

    def add_rotation_limit(
        self,
        *,
        bone_id: int,
        min: tuple[float, float, float] = (0.0, 0.0, 0.0),
        max: tuple[float, float, float] = (0.0, 0.0, 0.0),
        unknown_ah: int = 0,
        num_control_points: int = 1,
        joint_dofs: int = 3,
    ) -> YdrJointRotationLimit:
        return self.ensure_joints().add_rotation_limit(
            bone_id=bone_id,
            min=min,
            max=max,
            unknown_ah=unknown_ah,
            num_control_points=num_control_points,
            joint_dofs=joint_dofs,
        )

    def add_translation_limit(
        self,
        *,
        bone_id: int,
        min: tuple[float, float, float] = (0.0, 0.0, 0.0),
        max: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> YdrJointTranslationLimit:
        return self.ensure_joints().add_translation_limit(
            bone_id=bone_id,
            min=min,
            max=max,
        )

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

    def ensure_embedded_textures(self, *, game: str | None = None) -> Ytd:
        if self.embedded_textures is None:
            self.embedded_textures = Ytd(game=game or "gta5")
        elif game:
            self.embedded_textures.game = str(game)
        return self.embedded_textures

    def get_embedded_texture(self, name: str) -> Texture | None:
        if self.embedded_textures is None:
            return None
        try:
            return self.embedded_textures.get(name)
        except KeyError:
            return None

    def add_embedded_texture(
        self,
        texture: Texture | None = None,
        *,
        name: str | None = None,
        data: bytes | None = None,
        width: int | None = None,
        height: int | None = None,
        format: TextureFormat | None = None,
        mip_count: int = 1,
        replace: bool = True,
        game: str | None = None,
    ) -> Texture:
        if texture is None:
            if None in (name, data, width, height, format):
                raise ValueError("name=, data=, width=, height= and format= are required when adding raw embedded texture data")
            texture = Texture.from_raw(
                bytes(data),
                width=int(width),
                height=int(height),
                format=TextureFormat(format),
                mip_count=mip_count,
                name=str(name),
            )
        library = self.ensure_embedded_textures(game=game)
        existing = self.get_embedded_texture(texture.name)
        if existing is not None:
            if not replace:
                raise ValueError(f"Embedded texture '{texture.name}' already exists")
            library.textures = [item for item in library.textures if item.name.lower() != texture.name.lower()]
        library.textures.append(texture)
        return texture

    def remove_embedded_texture(self, name: str) -> bool:
        if self.embedded_textures is None:
            return False
        previous = len(self.embedded_textures.textures)
        self.embedded_textures.textures = [item for item in self.embedded_textures.textures if item.name.lower() != str(name).lower()]
        if not self.embedded_textures.textures:
            self.embedded_textures = None
        return len(self.embedded_textures.textures) != previous if self.embedded_textures is not None else previous > 0

    def set_bound(self, bound: Bound) -> Bound:
        self.bound = bound
        return bound

    def build_bound_from_render_geometry(
        self,
        *,
        lod: YdrLod | str | None = None,
        material: "BoundMaterial | None" = None,
        composite_flags: "BoundCompositeFlags | None" = None,
    ) -> "BoundComposite":
        from .collision import build_bound_from_render_geometry

        return build_bound_from_render_geometry(
            self,
            lod=lod,
            material=material,
            composite_flags=composite_flags,
        )

    def ensure_bound_from_render_geometry(
        self,
        *,
        lod: YdrLod | str | None = None,
        material: "BoundMaterial | None" = None,
        composite_flags: "BoundCompositeFlags | None" = None,
    ) -> "YdrCollisionStats":
        from .collision import set_bound_from_render_geometry

        return set_bound_from_render_geometry(
            self,
            lod=lod,
            material=material,
            composite_flags=composite_flags,
        )

    def clear_bound(self) -> "Ydr":
        self.bound = None
        return self

    def set_model_skin(
        self,
        model: int,
        *,
        bone_index: int = 0,
        has_skin: int = 1,
        unknown_1: int = 0x11,
        unknown_2: int = 0,
    ) -> YdrModel:
        target = self.get_model(model)
        if target is None:
            raise KeyError(f"Unknown YDR model index {model}")
        return target.set_skin_binding(
            bone_index=bone_index,
            has_skin=has_skin,
            unknown_1=unknown_1,
            unknown_2=unknown_2,
        )

    def bind_model_to_bone(
        self,
        model: int,
        bone: YdrBone | str | int,
        *,
        skeleton: YdrSkeleton | None = None,
        unknown_1: int = 0,
        unknown_2: int = 0,
    ) -> YdrModel:
        target = self.get_model(model)
        if target is None:
            raise KeyError(f"Unknown YDR model index {model}")
        active_skeleton = skeleton if skeleton is not None else self.skeleton
        return target.bind_to_bone(
            bone,
            skeleton=active_skeleton,
            unknown_1=unknown_1,
            unknown_2=unknown_2,
        )

    def clear_embedded_textures(self) -> "Ydr":
        self.embedded_textures = None
        return self

    def validate(self) -> list[YdrValidationIssue]:
        issues: list[YdrValidationIssue] = []
        if not self.models:
            issues.append(YdrValidationIssue("error", "missing_models", "YDR has no drawable models"))
        if not self.materials:
            issues.append(YdrValidationIssue("error", "missing_materials", "YDR has no materials"))

        embedded_names = {
            texture.name.lower()
            for texture in (self.embedded_textures.textures if self.embedded_textures is not None else [])
        }
        for material in self.materials:
            if material.shader_definition is None:
                issues.append(
                    YdrValidationIssue("error", "missing_shader_definition", f"Material '{material.name or material.index}' has no resolved shader", context=f"material:{material.index}")
                )
            if not material.resolved_shader_file_name:
                issues.append(
                    YdrValidationIssue("error", "missing_shader_file", f"Material '{material.name or material.index}' has no shader file name", context=f"material:{material.index}")
                )
            for parameter in material.parameters:
                if parameter.is_texture and parameter.texture is None:
                    issues.append(
                        YdrValidationIssue("warning", "unbound_texture_slot", f"Material '{material.name or material.index}' leaves texture slot '{parameter.name}' empty", context=f"material:{material.index}")
                    )
                if parameter.is_texture and parameter.texture is not None and embedded_names and parameter.texture.name.lower() not in embedded_names:
                    issues.append(
                        YdrValidationIssue("info", "external_texture_reference", f"Texture '{parameter.texture.name}' is not present in embedded textures", context=f"material:{material.index}:{parameter.name}")
                    )

        for model in self.models:
            if model.has_skin and not self.has_skeleton:
                issues.append(
                    YdrValidationIssue("error", "missing_skeleton", f"Model {model.index} is skinned but the drawable has no skeleton", context=f"model:{model.index}")
                )
            if self.skeleton is not None and model.bone_index >= self.skeleton.bone_count:
                issues.append(
                    YdrValidationIssue(
                        "error",
                        "invalid_model_bone_binding",
                        f"Model {model.index} references bone index {model.bone_index} outside skeleton range",
                        context=f"model:{model.index}",
                    )
                )
            if int(model.skeleton_binding.has_skin) not in (0, 1):
                issues.append(
                    YdrValidationIssue(
                        "error",
                        "invalid_has_skin_flag",
                        f"Model {model.index} uses unsupported HasSkin value {model.skeleton_binding.has_skin}",
                        context=f"model:{model.index}",
                    )
                )
            if int(model.skeleton_binding.unknown_2) != 0:
                issues.append(
                    YdrValidationIssue(
                        "warning",
                        "unexpected_skeleton_binding_unknown_2",
                        f"Model {model.index} uses non-zero SkeletonBindUnk2 value {model.skeleton_binding.unknown_2}",
                        context=f"model:{model.index}",
                    )
                )
            for mesh_index, mesh in enumerate(model.meshes):
                context = f"model:{model.index}:mesh:{mesh_index}"
                if mesh.material_index < 0 or mesh.material_index >= len(self.materials):
                    issues.append(
                        YdrValidationIssue("error", "invalid_material_index", f"Mesh references invalid material index {mesh.material_index}", context=context)
                    )
                for texture in mesh.material.textures if mesh.material is not None else []:
                    if texture.uv_index is not None and texture.uv_index >= len(mesh.texcoords):
                        issues.append(
                            YdrValidationIssue("error", "missing_uv_channel", f"Mesh is missing UV{texture.uv_index} required by texture slot '{texture.parameter_name or texture.name}'", context=context)
                        )
                if mesh.blend_weights and len(mesh.blend_weights) != mesh.vertex_count:
                    issues.append(
                        YdrValidationIssue("error", "weights_size_mismatch", "Blend weights count does not match vertex count", context=context)
                    )
                if mesh.blend_indices and len(mesh.blend_indices) != mesh.vertex_count:
                    issues.append(
                        YdrValidationIssue("error", "indices_size_mismatch", "Blend indices count does not match vertex count", context=context)
                    )
                if mesh.is_skinned and not mesh.bone_ids:
                    issues.append(
                        YdrValidationIssue("error", "missing_bone_palette", "Skinned mesh has no bone id palette", context=context)
                    )
                if mesh.is_skinned and not model.has_skin:
                    issues.append(
                        YdrValidationIssue("error", "missing_model_skin_flag", "Skinned mesh belongs to a model with HasSkin disabled", context=context)
                    )
                if mesh.bone_ids and self.skeleton is not None:
                    for bone_id in mesh.bone_ids:
                        if self.skeleton.get_bone_by_tag(int(bone_id)) is None and self.skeleton.get_bone_by_index(int(bone_id)) is None:
                            issues.append(
                                YdrValidationIssue("error", "unknown_bone_id", f"Mesh references unknown bone id {bone_id}", context=context)
                            )
        if self.joints is not None and self.joints.has_limits:
            if not self.has_skeleton:
                issues.append(
                    YdrValidationIssue("error", "missing_skeleton_for_joints", "YDR has joint limits but no skeleton", context="joints")
                )
            for index, limit in enumerate(self.joints.rotation_limits):
                if self.skeleton is not None and self.skeleton.get_bone_by_tag(int(limit.bone_id)) is None and self.skeleton.get_bone_by_index(int(limit.bone_id)) is None:
                    issues.append(
                        YdrValidationIssue("error", "unknown_joint_rotation_bone", f"Rotation limit references unknown bone id {limit.bone_id}", context=f"joints:rotation:{index}")
                    )
            for index, limit in enumerate(self.joints.translation_limits):
                if self.skeleton is not None and self.skeleton.get_bone_by_tag(int(limit.bone_id)) is None and self.skeleton.get_bone_by_index(int(limit.bone_id)) is None:
                    issues.append(
                        YdrValidationIssue("error", "unknown_joint_translation_bone", f"Translation limit references unknown bone id {limit.bone_id}", context=f"joints:translation:{index}")
                    )
        return issues

    def to_build(self, *, lod: YdrLod | str | None = None, name: str | None = None) -> YdrBuild:
        from .build_types import YdrBuild

        self.build()
        material_name_by_index = {
            material.index: (material.name or f"material_{material.index}")
            for material in self.materials
        }
        if lod is None:
            selected_lods = {
                lod_name: [model.to_input(material_name_by_index=material_name_by_index) for model in self.lods.get(lod_name, [])]
                for lod_name in LOD_ORDER
                if self.lods.get(lod_name)
            }
        else:
            selected_lod = coerce_lod(lod)
            selected_lods = {
                selected_lod: [model.to_input(material_name_by_index=material_name_by_index) for model in self.lods.get(selected_lod, [])]
            }
        materials = [material.to_input() for material in self.materials]
        return YdrBuild(
            lods=selected_lods,
            materials=materials,
            name=name or self.name,
            version=int(self.version),
            skeleton=self.skeleton,
            joints=self.joints,
            lights=list(self.lights),
            embedded_textures=self.embedded_textures,
            bound=self.bound,
            lod_distances=dict(self.lod_distances),
            render_mask_flags=dict(self.render_mask_flags),
            unknown_98=int(self.unknown_98),
            unknown_9c=int(self.unknown_9c),
        )

    def save(self, destination: str | Path, *, lod: YdrLod | str | None = None, name: str | None = None) -> Path:
        return self.to_build(lod=lod, name=name).save(destination)


Color4 = tuple[float, float, float, float]
_Paintable = Union["YdrMesh", "YdrMeshInput", "YdrModel"]


def _vertex_count(mesh: _Paintable) -> int:
    return len(mesh.positions)


def _set_colours(
    mesh: _Paintable,
    channel: int,
    colours: list[Color4],
) -> None:
    if channel == 0:
        if isinstance(mesh, YdrMesh):
            mesh.colours0 = colours
        else:
            object.__setattr__(mesh, "colours0", colours)
    else:
        if isinstance(mesh, YdrMesh):
            mesh.colours1 = colours
        else:
            object.__setattr__(mesh, "colours1", colours)


def _get_colours(mesh: _Paintable, channel: int) -> list[Color4]:
    source = mesh.colours0 if channel == 0 else mesh.colours1
    if source is None:
        return [(0.0, 0.0, 0.0, 1.0)] * _vertex_count(mesh)
    return [tuple(c) for c in source]


class ColorChannel(enum.IntEnum):
    R = 0
    G = 1
    B = 2
    A = 3
    RG = 10
    RGB = 11
    RGBA = 12
    GA = 13
    BA = 14
    RGA = 15
    GBA = 16
    RBA = 17


_CHANNEL_INDICES: dict[ColorChannel, tuple[int, ...]] = {
    ColorChannel.R: (0,),
    ColorChannel.G: (1,),
    ColorChannel.B: (2,),
    ColorChannel.A: (3,),
    ColorChannel.RG: (0, 1),
    ColorChannel.RGB: (0, 1, 2),
    ColorChannel.RGBA: (0, 1, 2, 3),
    ColorChannel.GA: (1, 3),
    ColorChannel.BA: (2, 3),
    ColorChannel.RGA: (0, 1, 3),
    ColorChannel.GBA: (1, 2, 3),
    ColorChannel.RBA: (0, 2, 3),
}


def _apply_color(
    existing: Color4,
    values: tuple[float, ...],
    components: ColorChannel | None,
) -> Color4:
    if components is None:
        return (*values[:3], values[3] if len(values) > 3 else 1.0)
    result = list(existing)
    for i, target in enumerate(_CHANNEL_INDICES[components]):
        if i < len(values):
            result[target] = values[i]
    return (result[0], result[1], result[2], result[3])


def _iter_meshes(target: _Paintable) -> Iterator[YdrMesh | YdrMeshInput]:
    if isinstance(target, YdrModel):
        yield from target.meshes
    else:
        yield target


def paint_mesh(
    target: _Paintable,
    color: float | tuple[float, ...],
    *,
    channel: int = 0,
    components: ColorChannel | None = None,
) -> None:
    """Fill all vertices with a uniform colour.

    *target* — a :class:`YdrMesh`, :class:`YdrMeshInput`, or
    :class:`YdrModel` (paints every mesh in the model).

    *color* — RGBA tuple, RGB tuple, or a single float for single-component
    painting.  Values are 0-1.

    *channel* — selects ``colours0`` (0, default) or ``colours1`` (1).

    *components* — a :class:`ColorChannel` selecting which RGBA channels to
    overwrite (e.g. ``ColorChannel.R``, ``ColorChannel.GA``).  ``None``
    (default) overwrites all four channels.
    """
    for mesh in _iter_meshes(target):
        values = (float(color),) if isinstance(color, (int, float)) else tuple(color)
        if components is None:
            rgba = _apply_color((0.0, 0.0, 0.0, 1.0), values, None)
            _set_colours(mesh, channel, [rgba] * _vertex_count(mesh))
        else:
            colours = _get_colours(mesh, channel)
            colours = [_apply_color(c, values, components) for c in colours]
            _set_colours(mesh, channel, colours)


def paint_vertices(
    target: _Paintable,
    vertex_indices: Sequence[int],
    color: float | tuple[float, ...],
    *,
    channel: int = 0,
    components: ColorChannel | None = None,
) -> None:
    """Paint specific vertices by index.

    *target* — a :class:`YdrMesh`, :class:`YdrMeshInput`, or
    :class:`YdrModel` (applies to every mesh in the model).

    *color* — RGBA tuple, RGB tuple, or a single float for single-component
    painting.

    *components* — a :class:`ColorChannel` selecting which channels to write.
    ``None`` overwrites all four.  Unmentioned channels and unlisted vertices
    keep their current colour.  If the mesh has no colours yet, unpainted
    vertices default to ``(0, 0, 0, 1)``.
    """
    for mesh in _iter_meshes(target):
        values = (float(color),) if isinstance(color, (int, float)) else tuple(color)
        colours = _get_colours(mesh, channel)
        for idx in vertex_indices:
            if idx < len(colours):
                colours[idx] = _apply_color(colours[idx], values, components)
        _set_colours(mesh, channel, colours)


__all__ = [
    "Color4",
    "ColorChannel",
    "Ydr",
    "YdrBone",
    "YdrBoneFlags",
    "YdrJointControlPoint",
    "YdrJointRotationLimit",
    "YdrJointTranslationLimit",
    "YdrJoints",
    "YdrLight",
    "YdrLightType",
    "YdrMaterial",
    "YdrMaterialParameterRef",
    "YdrMesh",
    "YdrModel",
    "YdrSkeleton",
    "YdrTextureRef",
    "YdrValidationIssue",
    "calculate_bone_tag",
    "paint_mesh",
    "paint_vertices",
]
