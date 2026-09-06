from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from ...drawable import DrawableMesh, DrawableModel
from ...vector import Vector2, Vector3, Vector4
from ...ycd.model import YcdUvClipBinding
from ..build_types import YdrMeshInput, YdrModelInput
from ..defs import YdrLod, YdrSkeletonBinding, coerce_lod, coerce_skeleton_binding
from .material import YdrMaterial
from .skeleton import YdrBone, YdrSkeleton


@dataclasses.dataclass(slots=True)
class YdrMesh(DrawableMesh[YdrMaterial]):
    material_index: int = -1
    material: YdrMaterial | None = None
    indices: list[int] = dataclasses.field(default_factory=list)
    positions: list[Vector3] = dataclasses.field(default_factory=list)
    normals: list[Vector3] = dataclasses.field(default_factory=list)
    tangents: list[Vector4] = dataclasses.field(default_factory=list)
    texcoords: list[list[Vector2]] = dataclasses.field(default_factory=list)
    colours0: list[tuple[float, float, float, float]] = dataclasses.field(
        default_factory=list
    )
    colours1: list[tuple[float, float, float, float]] = dataclasses.field(
        default_factory=list
    )
    blend_weights: list[tuple[float, float, float, float]] = dataclasses.field(
        default_factory=list
    )
    blend_indices: list[tuple[int, int, int, int]] = dataclasses.field(
        default_factory=list
    )
    bone_ids: list[int] = dataclasses.field(default_factory=list)
    vertex_stride: int = 0
    declaration_flags: int = 0
    declaration_types: int = 0
    vertex_buffer_flags: int = 0
    render_mask: int = 0
    flags: int = 0

    def resolve_bones(self, skeleton: YdrSkeleton | None) -> list[YdrBone]:
        if skeleton is None:
            return []
        return skeleton.resolve_bone_ids(self.bone_ids)

    def set_bone_ids(
        self,
        bone_ids: Sequence[int | YdrBone | str],
        *,
        skeleton: YdrSkeleton | None = None,
    ) -> YdrMesh:
        resolved: list[int] = []
        for item in bone_ids:
            if isinstance(item, YdrBone):
                resolved.append(int(item.index))
            elif isinstance(item, str):
                if skeleton is None:
                    raise ValueError("skeleton= is required when binding bones by name")
                resolved.append(int(skeleton.require_bone(item).index))
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
    ) -> YdrMesh:
        if bone_ids is not None:
            self.set_bone_ids(bone_ids, skeleton=skeleton)
        if weights is not None:
            self.blend_weights = [
                tuple(float(component) for component in weight) for weight in weights
            ]
        if indices is not None:
            self.blend_indices = [
                tuple(int(component) for component in index) for index in indices
            ]
        return self

    def clear_skin(self) -> YdrMesh:
        self.blend_weights = []
        self.blend_indices = []
        self.bone_ids = []
        return self

    def to_input(self, *, material_name: str | None = None) -> YdrMeshInput:
        return YdrMeshInput(
            positions=list(self.positions),
            indices=list(self.indices),
            material=material_name
            or (
                self.material.name
                if self.material is not None and self.material.name
                else f"material_{self.material_index}"
            ),
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
class YdrModel(DrawableModel[YdrMesh, YdrMaterial]):
    lod: YdrLod
    index: int = 0
    meshes: list[YdrMesh] = dataclasses.field(default_factory=list)
    render_mask: int = 0
    flags: int = 0
    skeleton_binding: YdrSkeletonBinding = dataclasses.field(
        default_factory=YdrSkeletonBinding
    )

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

    def ycd_uv_binding(
        self, material: str | int, *, object_name: str
    ) -> YcdUvClipBinding:
        resolved = self.get_material(material)
        if resolved is None:
            raise KeyError(f"Unknown YDR model material '{material}'")
        return resolved.ycd_uv_binding(object_name=object_name)

    def ycd_uv_bindings(self, *, object_name: str) -> list[YcdUvClipBinding]:
        return [
            material.ycd_uv_binding(object_name=object_name)
            for material in self.materials
        ]

    def set_skin_binding(
        self,
        *,
        bone_index: int = 0,
        has_skin: int = 1,
        unknown_1: int = 0x11,
        unknown_2: int = 0,
    ) -> YdrModel:
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
    ) -> YdrModel:
        if isinstance(bone, YdrBone):
            bone_index = int(bone.index)
        elif isinstance(bone, str):
            if skeleton is None:
                raise ValueError(
                    "skeleton= is required when binding a model by bone name"
                )
            bone_index = int(skeleton.require_bone(bone).index)
        else:
            bone_index = int(bone)
        self.skeleton_binding = YdrSkeletonBinding.rigid(
            bone_index=bone_index,
            unknown_1=unknown_1,
            unknown_2=unknown_2,
        )
        return self

    def clear_skin_binding(self) -> YdrModel:
        self.skeleton_binding = YdrSkeletonBinding()
        return self

    def to_input(self, *, material_name_by_index: dict[int, str]) -> YdrModelInput:
        return YdrModelInput(
            meshes=[
                mesh.to_input(
                    material_name=material_name_by_index.get(
                        mesh.material_index, f"material_{mesh.material_index}"
                    )
                )
                for mesh in self.meshes
            ],
            render_mask=int(self.render_mask),
            flags=int(self.flags),
            skeleton_binding=coerce_skeleton_binding(self.skeleton_binding),
        )
