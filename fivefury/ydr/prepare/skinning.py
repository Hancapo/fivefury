from __future__ import annotations

from ..model.skeleton import YdrSkeleton


def _resolve_palette_bone_index(raw_bone_id: int, skeleton: YdrSkeleton) -> int:
    bone_id = int(raw_bone_id)
    bone_count = len(skeleton.bones)
    if 0 <= bone_id < bone_count:
        return bone_id
    bone = skeleton.get_bone_by_tag(bone_id)
    if bone is None:
        raise ValueError(f"Mesh skin references unknown skeleton bone id/tag {bone_id}")
    return int(bone.index)


def normalize_skin_channels(
    blend_weights: list[tuple[float, float, float, float]],
    blend_indices: list[tuple[int, int, int, int]],
    bone_ids: list[int],
    skeleton: YdrSkeleton | None,
) -> tuple[list[tuple[int, int, int, int]], list[int]]:
    if blend_weights:
        if not blend_indices:
            raise ValueError("Mesh has blend_weights but no blend_indices")
        if skeleton is not None and skeleton.bones:
            bone_count = len(skeleton.bones)
            if bone_count > 255:
                raise ValueError(
                    "Skinned YDR models currently support at most 255 bones per skeleton"
                )
            source_palette = list(bone_ids) if bone_ids else list(range(bone_count))
            resolved_palette = [
                _resolve_palette_bone_index(bone_id, skeleton)
                for bone_id in source_palette
            ]
            remapped_indices: list[tuple[int, int, int, int]] = []
            for vertex_indices, vertex_weights in zip(
                blend_indices, blend_weights, strict=True
            ):
                remapped: list[int] = []
                for palette_index, weight in zip(
                    vertex_indices, vertex_weights, strict=True
                ):
                    index = int(palette_index)
                    if float(weight) <= 0.0:
                        remapped.append(0)
                        continue
                    if index < 0 or index >= len(resolved_palette):
                        raise ValueError(
                            f"Vertex blend index {index} is outside the mesh bone palette"
                        )
                    remapped.append(int(resolved_palette[index]))
                remapped_indices.append(
                    (remapped[0], remapped[1], remapped[2], remapped[3])
                )
            blend_indices = remapped_indices
            bone_ids = list(range(bone_count))

    return blend_indices, bone_ids
