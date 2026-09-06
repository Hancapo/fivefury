from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .build_types import YdrMeshInput
    from .model import YdrJoints, YdrMesh, YdrSkeleton


def normalize_root_bone_id(
    skeleton: YdrSkeleton | None,
    meshes: Iterable[YdrMesh | YdrMeshInput],
    joints: YdrJoints | None,
) -> None:
    if skeleton is None or not skeleton.bones:
        return
    root = skeleton.bones[0]
    old_tag = int(root.tag)
    if old_tag == 0:
        return

    # In-range palette values are skeleton indices, not tags. Joint limits,
    # unlike mesh palettes, store tags and must follow the root's new tag.
    if old_tag >= len(skeleton.bones):
        for mesh in meshes:
            if mesh.bone_ids is not None:
                mesh.bone_ids = [
                    0 if int(value) == old_tag else int(value)
                    for value in mesh.bone_ids
                ]
    root.tag = 0
    if joints is not None:
        for limit in (*joints.rotation_limits, *joints.translation_limits):
            if int(limit.bone_id) == old_tag:
                limit.bone_id = 0
    skeleton._rebuild_bone_lookups()
