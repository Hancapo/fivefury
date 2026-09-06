from __future__ import annotations

from collections.abc import Sequence

from ...matrix import matrix4, transform_positions
from ...vector import Aabb3, Vector3, sphere_radius_from_points
from ..model.skeleton import YdrSkeleton
from ..transforms import skeleton_absolute_transforms
from .build import PreparedModel


def compute_bounds(
    positions: Sequence[Vector3],
) -> tuple[Vector3, Vector3, Vector3, float]:
    if not positions:
        zero = Vector3()
        return zero, zero, zero, 0.0
    bounds = Aabb3.from_points(positions)
    centre = bounds.center
    radius = sphere_radius_from_points(centre, positions)
    return centre, bounds.minimum, bounds.maximum, radius


def compute_model_collection_bounds(
    models: Sequence[PreparedModel],
    *,
    skeleton: YdrSkeleton | None = None,
) -> tuple[Vector3, Vector3, Vector3, float]:
    absolute_transforms = skeleton_absolute_transforms(skeleton)
    position_groups = []
    for model in models:
        transform = None
        binding = model.skeleton_binding
        if (
            absolute_transforms
            and not binding.is_skinned
            and 0 <= int(binding.bone_index) < len(absolute_transforms)
        ):
            transform = absolute_transforms[int(binding.bone_index)]
        for mesh in model.meshes:
            if not mesh.positions:
                continue
            position_groups.append(
                mesh.positions
                if transform is None
                # Serialized RAGE matrices act on row vectors; shared math uses columns.
                else transform_positions(mesh.positions, matrix4(transform).T)
            )
    if not position_groups:
        return compute_bounds(())
    mesh_bounds = [Aabb3.from_points(positions) for positions in position_groups]
    bounds = mesh_bounds[0]
    for mesh_bounds_value in mesh_bounds[1:]:
        bounds = bounds.merged(mesh_bounds_value)
    bb_min = bounds.minimum
    bb_max = bounds.maximum
    centre = bounds.center
    radius = max(
        sphere_radius_from_points(centre, positions) for positions in position_groups
    )
    return centre, bb_min, bb_max, radius
