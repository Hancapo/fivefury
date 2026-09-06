from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Sequence
from typing import Any, cast

from ....matrix import Matrix4
from ....vector import Quaternion, Vector3
from .bone import YdrBone, calculate_bone_tag
from .flags import YDR_BONE_ANIMATABLE_FLAGS, YdrBoneFlags
from .lookups import _BoneList, _BoneLookups


@dataclasses.dataclass(slots=True)
class YdrSkeleton:
    """Skeleton-owned bone list, with shared mutable bone objects.

    Assigning bones copies the input collection. Edit skeleton.bones itself to
    change membership or order; edits to shared bones affect every owner.
    """

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

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "bones" and value is not getattr(self, "bones", None):
            value = _BoneList(value)
        object.__setattr__(self, name, value)

    @property
    def bone_count(self) -> int:
        return len(self.bones)

    def build(self) -> YdrSkeleton:
        for index, bone in enumerate(self.bones):
            bone.index = index
            bone.next_sibling_index = -1
            bone.flags = YdrBoneFlags(int(bone.flags) & ~int(YdrBoneFlags.HAS_CHILD))
        parent_to_children: dict[int, list[YdrBone]] = {}
        for bone in self.bones:
            parent_to_children.setdefault(int(bone.parent_index), []).append(bone)
        for parent_index, children in parent_to_children.items():
            if parent_index >= 0 and children:
                parent_bone = self.bones[parent_index]
                parent_bone.flags = YdrBoneFlags(
                    int(parent_bone.flags) | int(YdrBoneFlags.HAS_CHILD)
                )
            for current, nxt in itertools.pairwise(children):
                current.next_sibling_index = int(nxt.index)
        self.parent_indices = [int(item.parent_index) for item in self.bones]
        self.child_indices = []
        self.transformations = []
        self.transformations_inverted = []
        self._rebuild_bone_lookups()
        return self

    def _rebuild_bone_lookups(self) -> None:
        lookups = cast(_BoneList, self.bones).lookups
        lookups.dirty = True
        lookups.clear()
        for index, bone in enumerate(self.bones):
            lookups.record(index, bone)
        lookups.dirty = False

    def _ensure_bone_lookups(self) -> _BoneLookups:
        lookups = cast(_BoneList, self.bones).lookups
        if lookups.dirty:
            self._rebuild_bone_lookups()
        return lookups

    def get_bone_by_index(self, index: int) -> YdrBone | None:
        if 0 <= int(index) < len(self.bones):
            return self.bones[int(index)]
        return None

    def get_bone_by_tag(self, tag: int) -> YdrBone | None:
        return self._ensure_bone_lookups().by_tag.get(int(tag))

    def get_bone_by_name(self, name: str) -> YdrBone | None:
        return self._ensure_bone_lookups().by_name.get(str(name).lower())

    def require_bone(self, value: str | int) -> YdrBone:
        bone = (
            self.get_bone_by_name(value)
            if isinstance(value, str)
            else self.get_bone_by_index(value)
        )
        if bone is None and isinstance(value, int):
            bone = self.get_bone_by_tag(value)
        if bone is None:
            raise KeyError(f"Unknown YDR bone '{value}'")
        return bone

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
        if not isinstance(rotation, Quaternion):
            raise TypeError("rotation must be a Quaternion")
        if not isinstance(translation, Vector3):
            raise TypeError("translation must be a Vector3")
        if not isinstance(scale, Vector3):
            raise TypeError("scale must be a Vector3")
        lookups = self._ensure_bone_lookups()
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
            previous_sibling = lookups.last_child_by_parent.get(parent_index)
            if previous_sibling is not None:
                self.bones[previous_sibling].next_sibling_index = index
            parent_bone.flags = YdrBoneFlags(
                int(parent_bone.flags) | int(YdrBoneFlags.HAS_CHILD)
            )
        bone = YdrBone(
            name=str(name),
            tag=int(calculate_bone_tag(name) if tag is None else tag),
            index=index,
            parent_index=parent_index,
            next_sibling_index=-1,
            flags=flags,
            rotation=rotation,
            translation=translation,
            scale=scale,
        )
        self.bones.append(bone)
        self.parent_indices.append(parent_index)
        self.child_indices.clear()
        self.transformations.clear()
        self.transformations_inverted.clear()
        return bone

    def resolve_bone_ids(self, bone_ids: Sequence[int]) -> list[YdrBone]:
        resolved: list[YdrBone] = []
        for bone_id in bone_ids:
            bone = self.get_bone_by_index(int(bone_id))
            if bone is None:
                bone = self.get_bone_by_tag(int(bone_id))
            if bone is not None:
                resolved.append(bone)
        return resolved

    def calculate_unknown_hashes(self) -> tuple[int, int, int]:
        from .signatures import calculate_skeleton_unknown_hashes

        return calculate_skeleton_unknown_hashes(self)

    def recalculate_unknown_hashes(self) -> YdrSkeleton:
        from .signatures import calculate_skeleton_unknown_hashes

        self.unknown_50h, self.unknown_54h, self.unknown_58h = (
            calculate_skeleton_unknown_hashes(self)
        )
        return self
