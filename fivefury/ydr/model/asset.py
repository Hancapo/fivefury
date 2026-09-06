from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from ...authoring.context import BuildContext
from ...authoring.diagnostics import ValidationReport
from ...bounds import Bound, BoundComposite, BoundCompositeFlags, BoundMaterial
from ...drawable import DrawableAsset
from ...drawable.model import NumericParameterValue
from ...vector import Quaternion, Vector3
from ...ycd.model import YcdUvClipBinding
from ...ytd import Texture, TextureFormat, Ytd
from ..build_types import YdrBuild
from ..collision import YdrCollisionStats
from ..defs import LOD_ORDER, YdrLod, coerce_lod
from ..shaders import ShaderLibrary
from ..skeleton_binding import normalize_root_bone_id
from .geometry import YdrMesh, YdrModel
from .joints import YdrJointRotationLimit, YdrJoints, YdrJointTranslationLimit
from .lights import YdrLight
from .material import YdrMaterial, YdrTextureRef
from .skeleton import YDR_BONE_ANIMATABLE_FLAGS, YdrBone, YdrBoneFlags, YdrSkeleton
from .validation import validate_drawable


@dataclasses.dataclass(slots=True)
class Ydr(DrawableAsset[YdrMaterial, YdrModel, YdrMesh]):
    version: int
    path: str = ""
    materials: list[YdrMaterial] = dataclasses.field(default_factory=list)
    lods: dict[YdrLod, list[YdrModel]] = dataclasses.field(default_factory=dict)
    bounding_center: Vector3 = dataclasses.field(default_factory=Vector3)
    bounding_sphere_radius: float = 0.0
    bounding_box_min: Vector3 = dataclasses.field(default_factory=Vector3)
    bounding_box_max: Vector3 = dataclasses.field(default_factory=Vector3)
    skeleton: YdrSkeleton | None = None
    joints: YdrJoints | None = None
    lights: list[YdrLight] = dataclasses.field(default_factory=list)
    embedded_textures: Ytd | None = None
    bound: Bound | None = None
    lod_distances: dict[YdrLod, float] = dataclasses.field(default_factory=dict)
    render_mask_flags: dict[YdrLod, int] = dataclasses.field(default_factory=dict)
    unknown_98: int = 0
    unknown_9c: int = 0
    shader_group_pointer: int = 0

    def __post_init__(self) -> None:
        DrawableAsset.__post_init__(self)
        for name in ("bounding_center", "bounding_box_min", "bounding_box_max"):
            if not isinstance(getattr(self, name), Vector3):
                raise TypeError(f"Ydr.{name} must be a Vector3")
        self.render_mask_flags = {
            coerce_lod(lod): int(flags) for lod, flags in self.render_mask_flags.items()
        }

    def build(self) -> Ydr:
        if self.skeleton is not None:
            self.skeleton.build()
            self.normalize_skeleton_bone_ids()
        if self.joints is not None:
            self.joints.build()
        for material_index, material in enumerate(self.materials):
            material.index = material_index
        for model_index, model in enumerate(self.models):
            model.index = model_index
            for mesh in model.meshes:
                if mesh.material is None and 0 <= mesh.material_index < len(
                    self.materials
                ):
                    mesh.material = self.materials[mesh.material_index]
        return self

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview, *, path: str = "") -> Ydr:
        from ..reader import read_ydr

        return read_ydr(data, path=path)

    def normalize_skeleton_bone_ids(self) -> Ydr:
        normalize_root_bone_id(self.skeleton, self.iter_meshes(), self.joints)
        return self

    def ycd_uv_binding(
        self, material: str | int, *, object_name: str | None = None
    ) -> YcdUvClipBinding:
        resolved = self.get_material(material)
        if resolved is None:
            raise KeyError(f"Unknown YDR material '{material}'")
        return resolved.ycd_uv_binding(object_name=object_name or self.name)

    def ycd_uv_bindings(
        self, *, object_name: str | None = None
    ) -> list[YcdUvClipBinding]:
        binding_object_name = object_name or self.name
        return [
            material.ycd_uv_binding(object_name=binding_object_name)
            for material in self.materials
        ]

    @property
    def has_skeleton(self) -> bool:
        return self.skeleton is not None and self.skeleton.bone_count > 0

    @property
    def has_joints(self) -> bool:
        return self.joints is not None and self.joints.has_limits

    def ensure_skeleton(self) -> YdrSkeleton:
        if self.skeleton is None:
            self.skeleton = YdrSkeleton()
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

    def bone(
        self,
        name: str,
        *,
        parent: YdrBone | str | int | None = None,
        tag: int | None = None,
        flags: YdrBoneFlags = YDR_BONE_ANIMATABLE_FLAGS,
        rotation: Quaternion = Quaternion(),
        translation: Vector3 = Vector3(),
        scale: Vector3 = Vector3(1.0, 1.0, 1.0),
    ) -> YdrBone:
        return self.ensure_skeleton().bone(
            name,
            parent=parent,
            tag=tag,
            flags=flags,
            rotation=rotation,
            translation=translation,
            scale=scale,
        )

    def clear_joints(self) -> Ydr:
        self.joints = None
        return self

    def light(self, light: YdrLight | None = None, **kwargs: Any) -> YdrLight:
        resolved = light or YdrLight(**kwargs)
        if light is not None and kwargs:
            raise TypeError("Pass a YdrLight or its fields, not both")
        self.lights.append(resolved)
        return resolved

    def clear_lights(self) -> Ydr:
        self.lights.clear()
        return self

    def rotation_limit(
        self,
        *,
        bone_id: int,
        min: Vector3 = Vector3(),
        max: Vector3 = Vector3(),
        unknown_ah: int = 0,
        num_control_points: int = 1,
        joint_dofs: int = 3,
    ) -> YdrJointRotationLimit:
        return self.ensure_joints().rotation_limit(
            bone_id=bone_id,
            min=min,
            max=max,
            unknown_ah=unknown_ah,
            num_control_points=num_control_points,
            joint_dofs=joint_dofs,
        )

    def translation_limit(
        self,
        *,
        bone_id: int,
        min: Vector3 = Vector3(),
        max: Vector3 = Vector3(),
    ) -> YdrJointTranslationLimit:
        return self.ensure_joints().translation_limit(
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

    def embedded_texture(
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
                raise ValueError(
                    "name=, data=, width=, height= and format= are required when adding raw embedded texture data"
                )
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
            library.textures = [
                item
                for item in library.textures
                if item.name.lower() != texture.name.lower()
            ]
        library.textures.append(texture)
        return texture

    def remove_embedded_texture(self, name: str) -> bool:
        if self.embedded_textures is None:
            return False
        previous = len(self.embedded_textures.textures)
        self.embedded_textures.textures = [
            item
            for item in self.embedded_textures.textures
            if item.name.lower() != str(name).lower()
        ]
        if not self.embedded_textures.textures:
            self.embedded_textures = None
        return (
            len(self.embedded_textures.textures) != previous
            if self.embedded_textures is not None
            else previous > 0
        )

    def build_bound_from_render_geometry(
        self,
        *,
        lod: YdrLod | str | None = None,
        material: BoundMaterial | None = None,
        composite_flags: BoundCompositeFlags | None = None,
    ) -> BoundComposite:
        from ..collision import build_bound_from_render_geometry

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
        material: BoundMaterial | None = None,
        composite_flags: BoundCompositeFlags | None = None,
    ) -> YdrCollisionStats:
        from ..collision import set_bound_from_render_geometry

        return set_bound_from_render_geometry(
            self,
            lod=lod,
            material=material,
            composite_flags=composite_flags,
        )

    def clear_bound(self) -> Ydr:
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

    def clear_embedded_textures(self) -> Ydr:
        self.embedded_textures = None
        return self

    def validate(
        self,
        *,
        context: BuildContext | None = None,
    ) -> ValidationReport:
        return validate_drawable(self, context=context)

    def to_build(
        self, *, lod: YdrLod | str | None = None, name: str | None = None
    ) -> YdrBuild:
        self.build()
        material_name_by_index = {
            material.index: (material.name or f"material_{material.index}")
            for material in self.materials
        }
        if lod is None:
            selected_lods = {
                lod_name: [
                    model.to_input(material_name_by_index=material_name_by_index)
                    for model in self.lods.get(lod_name, [])
                ]
                for lod_name in LOD_ORDER
                if self.lods.get(lod_name)
            }
        else:
            selected_lod = coerce_lod(lod)
            selected_lods = {
                selected_lod: [
                    model.to_input(material_name_by_index=material_name_by_index)
                    for model in self.lods.get(selected_lod, [])
                ]
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

    def save(
        self,
        destination: str | Path,
        *,
        lod: YdrLod | str | None = None,
        name: str | None = None,
        recalculate_skeleton_hashes: bool = True,
    ) -> Path:
        return self.to_build(lod=lod, name=name).save(
            destination,
            recalculate_skeleton_hashes=recalculate_skeleton_hashes,
        )
