from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..vector import Vector2, Vector3
from .glass import YftGlassPane, YftGlassPaneFlag

if TYPE_CHECKING:
    from ..ydr import YdrMesh, YdrMeshInput

BlendIndices = tuple[int, int, int, int]
BlendWeights = tuple[float, float, float, float]

_EPSILON = 1.1920928955078125e-07


def _require_vector(value: object, expected: type[Vector2 | Vector3], label: str):
    if not isinstance(value, expected):
        raise TypeError(f"{label} must be a {expected.__name__}")
    if not value.is_finite:
        raise ValueError(f"{label} must be finite")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class YftGlassOrthonormalTransform:
    x_axis: Vector3 = Vector3(1.0, 0.0, 0.0)
    y_axis: Vector3 = Vector3(0.0, 1.0, 0.0)
    z_axis: Vector3 = Vector3(0.0, 0.0, 1.0)
    translation: Vector3 = Vector3()

    def __post_init__(self) -> None:
        axes = tuple(
            _require_vector(axis, Vector3, label)
            for axis, label in (
                (self.x_axis, "x_axis"),
                (self.y_axis, "y_axis"),
                (self.z_axis, "z_axis"),
            )
        )
        _require_vector(self.translation, Vector3, "translation")
        if any(abs(axis.length - 1.0) > 1.0e-5 for axis in axes):
            raise ValueError("transform axes must have unit length")
        if any(
            abs(axes[first].dot(axes[second])) > 1.0e-5
            for first, second in ((0, 1), (0, 2), (1, 2))
        ):
            raise ValueError("transform axes must be mutually orthogonal")
        if axes[0].cross(axes[1]).dot(axes[2]) < 1.0 - 1.0e-5:
            raise ValueError("transform axes must form a right-handed basis")

    def untransform_vector(self, value: Vector3) -> Vector3:
        return Vector3(
            value.dot(self.x_axis),
            value.dot(self.y_axis),
            value.dot(self.z_axis),
        )

    def untransform_point(self, value: Vector3) -> Vector3:
        return self.untransform_vector(value - self.translation)


@dataclasses.dataclass(frozen=True, slots=True)
class YftGlassPaneMesh:
    positions: Sequence[Vector3]
    indices: Sequence[int]
    uv0: Sequence[Vector2]
    tangents: Sequence[Vector3]
    blend_indices: Sequence[BlendIndices] = ()
    blend_weights: Sequence[BlendWeights] = ()

    @classmethod
    def from_ydr_mesh(cls, mesh: YdrMesh | YdrMeshInput) -> YftGlassPaneMesh:
        if not mesh.texcoords:
            raise ValueError("breakable glass geometry requires UV channel 0")
        if not mesh.tangents:
            raise ValueError("breakable glass geometry requires tangents")
        return cls.declare(
            mesh.positions,
            mesh.indices,
            mesh.texcoords[0],
            tuple(tangent.xyz for tangent in mesh.tangents),
            blend_indices=mesh.blend_indices or (),
            blend_weights=mesh.blend_weights or (),
        )

    @classmethod
    def declare(
        cls,
        positions: Sequence[Vector3],
        indices: Sequence[int],
        uv0: Sequence[Vector2],
        tangents: Sequence[Vector3],
        *,
        blend_indices: Sequence[Sequence[int]] = (),
        blend_weights: Sequence[Sequence[float]] = (),
    ) -> YftGlassPaneMesh:
        return cls(
            positions=tuple(_require_vector(value, Vector3, f"positions[{index}]") for index, value in enumerate(positions)),
            indices=tuple(int(value) for value in indices),
            uv0=tuple(_require_vector(value, Vector2, f"uv0[{index}]") for index, value in enumerate(uv0)),
            tangents=tuple(_require_vector(value, Vector3, f"tangents[{index}]") for index, value in enumerate(tangents)),
            blend_indices=tuple(
                tuple(int(component) for component in value)  # type: ignore[arg-type]
                for value in blend_indices
            ),
            blend_weights=tuple(
                tuple(float(component) for component in value)  # type: ignore[arg-type]
                for value in blend_weights
            ),
        )

    def compute(self, *, bone_index: int | None = None) -> YftGlassPaneGeometry:
        return compute_glass_pane_geometry(self, bone_index=bone_index)

    def build_pane(
        self,
        *,
        bone_index: int | None = None,
        glass_type: int = 0,
        shader_index: int = 0,
        bounds_minimum: Vector3 | None = None,
        bounds_maximum: Vector3 | None = None,
        bounds_transform: YftGlassOrthonormalTransform | None = None,
    ) -> YftGlassPane:
        return build_yft_glass_pane(
            self,
            bone_index=bone_index,
            glass_type=glass_type,
            shader_index=shader_index,
            bounds_minimum=bounds_minimum,
            bounds_maximum=bounds_maximum,
            bounds_transform=bounds_transform,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class YftGlassPaneGeometry:
    position_base: Vector3
    position_width: Vector3
    position_height: Vector3
    uv_min: Vector2
    uv_max: Vector2
    thickness: float
    tangent: Vector3
    bounds_offset_front: float
    bounds_offset_back: float

    def to_pane(
        self,
        *,
        glass_type: int = 0,
        shader_index: int = 0,
    ) -> YftGlassPane:
        return YftGlassPane(
            position_base=self.position_base,
            position_width=self.position_width,
            position_height=self.position_height,
            uv_min=self.uv_min,
            uv_max=self.uv_max,
            thickness=self.thickness,
            flags=YftGlassPaneFlag.TANGENT,
            glass_type=int(glass_type),
            shader_index=int(shader_index),
            bounds_offset_front=self.bounds_offset_front,
            bounds_offset_back=self.bounds_offset_back,
            tangent=self.tangent,
        )


def _major_bone(mesh: YftGlassPaneMesh, vertex_index: int) -> int:
    indices = mesh.blend_indices[vertex_index]
    if not mesh.blend_weights:
        return int(indices[0])
    weights = mesh.blend_weights[vertex_index]
    return int(indices[max(range(4), key=lambda index: float(weights[index]))])


def _selected_vertex_indices(
    mesh: YftGlassPaneMesh, bone_index: int | None
) -> tuple[int, ...]:
    if bone_index is None or not mesh.blend_indices:
        return tuple(range(len(mesh.positions)))
    return tuple(
        index
        for index, bindings in enumerate(mesh.blend_indices)
        if int(bindings[0]) == bone_index
    )


def _validate_mesh(mesh: YftGlassPaneMesh, bone_index: int | None) -> None:
    count = len(mesh.positions)
    if count < 3:
        raise ValueError("glass pane mesh requires at least three vertices")
    if len(mesh.uv0) != count or len(mesh.tangents) != count:
        raise ValueError("positions, uv0, and tangents must have equal lengths")
    if not mesh.indices or len(mesh.indices) % 3:
        raise ValueError("glass pane indices must contain complete triangles")
    if any(index < 0 or index >= count for index in mesh.indices):
        raise ValueError("glass pane triangle references an invalid vertex")
    if mesh.blend_indices:
        if len(mesh.blend_indices) != count:
            raise ValueError("blend_indices must match the vertex count")
        if any(len(value) != 4 for value in mesh.blend_indices):
            raise ValueError("blend_indices entries must contain four components")
    if mesh.blend_weights:
        if len(mesh.blend_weights) != count or not mesh.blend_indices:
            raise ValueError("blend_weights require matching blend_indices")
        if any(len(value) != 4 for value in mesh.blend_weights):
            raise ValueError("blend_weights entries must contain four components")
        if any(
            not math.isfinite(float(component))
            for value in mesh.blend_weights
            for component in value
        ):
            raise ValueError("blend_weights must be finite")
    if bone_index is not None and bone_index < 0:
        raise ValueError("bone_index must be non-negative")


def _largest_valid_triangle(
    mesh: YftGlassPaneMesh, bone_index: int | None
) -> tuple[int, int, int]:
    best: tuple[int, int, int] | None = None
    best_uv_area_squared = -1.0
    filter_bone = bone_index is not None and bool(mesh.blend_indices)
    for start in range(0, len(mesh.indices), 3):
        triangle = tuple(int(value) for value in mesh.indices[start : start + 3])
        if filter_bone and all(
            _major_bone(mesh, vertex_index) != bone_index for vertex_index in triangle
        ):
            continue
        uv0, uv1, uv2 = (mesh.uv0[index] for index in triangle)
        uv10 = uv1 - uv0
        uv20 = uv2 - uv0
        determinant = (uv20.x * uv10.y) - (uv10.x * uv20.y)
        area_squared = determinant * determinant
        if area_squared <= best_uv_area_squared:
            continue
        best = triangle
        best_uv_area_squared = area_squared
    if best is None:
        suffix = f" for bone {bone_index}" if filter_bone else ""
        raise ValueError(f"glass pane mesh has no triangle{suffix}")
    return best


def compute_glass_pane_geometry(
    mesh: YftGlassPaneMesh,
    *,
    bone_index: int | None = None,
) -> YftGlassPaneGeometry:
    _validate_mesh(mesh, bone_index)
    triangle = _largest_valid_triangle(mesh, bone_index)
    p0, p1, p2 = (mesh.positions[index] for index in triangle)
    uv0, uv1, uv2 = (mesh.uv0[index] for index in triangle)

    p10 = p1 - p0
    p20 = p2 - p0
    uv10 = uv1 - uv0
    uv20 = uv2 - uv0
    denominator = (uv20.x * uv10.y) - (uv10.x * uv20.y)
    if abs(denominator) <= _EPSILON:
        raise ValueError("glass pane UV0 coordinates are degenerate")
    alpha = 1.0 / denominator
    width_basis = (p20 * (uv10.y * alpha)) - (p10 * (uv20.y * alpha))
    height_basis = (p10 * (uv20.x * alpha)) - (p20 * (uv10.x * alpha))
    origin = p0 - (width_basis * uv0.x) - (height_basis * uv0.y)

    selected = _selected_vertex_indices(mesh, bone_index)
    if not selected:
        raise ValueError(
            f"glass pane mesh has no vertices bound first to bone {bone_index}"
        )
    uv_min = Vector2(
        min(mesh.uv0[index].x for index in selected),
        min(mesh.uv0[index].y for index in selected),
    )
    uv_max = Vector2(
        max(mesh.uv0[index].x for index in selected),
        max(mesh.uv0[index].y for index in selected),
    )
    position_base = origin + (width_basis * uv_min.x) + (height_basis * uv_min.y)
    position_width = width_basis * (uv_max.x - uv_min.x)
    position_height = height_basis * (uv_max.y - uv_min.y)

    plane_normal = (p0 - p1).cross(p2 - p1).normalized(fallback=Vector3())
    if plane_normal.length <= _EPSILON:
        raise ValueError("glass pane basis triangle is geometrically degenerate")
    depths = [plane_normal.dot(mesh.positions[index]) for index in selected]
    thickness = max(depths) - min(depths)
    tangent_sum = Vector3()
    for index in selected:
        tangent_sum += mesh.tangents[index]
    tangent = tangent_sum.normalized(fallback=Vector3())
    if tangent.length <= _EPSILON:
        raise ValueError("glass pane average tangent is degenerate")
    half_thickness = 0.5 * thickness
    return YftGlassPaneGeometry(
        position_base=position_base,
        position_width=position_width,
        position_height=position_height,
        uv_min=uv_min,
        uv_max=uv_max,
        thickness=thickness,
        tangent=tangent,
        bounds_offset_front=half_thickness,
        bounds_offset_back=half_thickness,
    )


def compute_glass_bounds_offsets(
    geometry: YftGlassPaneGeometry,
    minimum: Vector3,
    maximum: Vector3,
    *,
    transform: YftGlassOrthonormalTransform | None = None,
) -> tuple[float, float]:
    bound_min = _require_vector(minimum, Vector3, "minimum")
    bound_max = _require_vector(maximum, Vector3, "maximum")
    if bound_min.x > bound_max.x or bound_min.y > bound_max.y or bound_min.z > bound_max.z:
        raise ValueError("bound minimum must not exceed maximum")
    pane_normal = geometry.position_height.cross(geometry.position_width).normalized(fallback=Vector3())
    if pane_normal.length <= _EPSILON:
        raise ValueError("glass pane width and height do not define a plane")
    basis = transform or YftGlassOrthonormalTransform()
    bound_normal = basis.untransform_vector(pane_normal)
    bounds_base = basis.untransform_point(geometry.position_base)
    front = Vector3(
        bound_max.x if bound_normal.x >= 0.0 else bound_min.x,
        bound_max.y if bound_normal.y >= 0.0 else bound_min.y,
        bound_max.z if bound_normal.z >= 0.0 else bound_min.z,
    )
    back = Vector3(
        bound_min.x if bound_normal.x >= 0.0 else bound_max.x,
        bound_min.y if bound_normal.y >= 0.0 else bound_max.y,
        bound_min.z if bound_normal.z >= 0.0 else bound_max.z,
    )
    return (
        bound_normal.dot(front - bounds_base),
        bound_normal.dot(bounds_base - back),
    )


def build_yft_glass_pane(
    mesh: YftGlassPaneMesh,
    *,
    bone_index: int | None = None,
    glass_type: int = 0,
    shader_index: int = 0,
    bounds_minimum: Vector3 | None = None,
    bounds_maximum: Vector3 | None = None,
    bounds_transform: YftGlassOrthonormalTransform | None = None,
) -> YftGlassPane:
    geometry = compute_glass_pane_geometry(mesh, bone_index=bone_index)
    if (bounds_minimum is None) != (bounds_maximum is None):
        raise ValueError("bounds_minimum and bounds_maximum must be provided together")
    if bounds_minimum is not None and bounds_maximum is not None:
        front, back = compute_glass_bounds_offsets(
            geometry,
            bounds_minimum,
            bounds_maximum,
            transform=bounds_transform,
        )
        geometry = dataclasses.replace(
            geometry,
            bounds_offset_front=front,
            bounds_offset_back=back,
        )
    return geometry.to_pane(glass_type=glass_type, shader_index=shader_index)


def build_yft_glass_pane_from_mesh(
    mesh: YdrMesh | YdrMeshInput,
    *,
    bone_index: int | None = None,
    glass_type: int = 0,
    shader_index: int | None = None,
    bounds_minimum: Vector3 | None = None,
    bounds_maximum: Vector3 | None = None,
    bounds_transform: YftGlassOrthonormalTransform | None = None,
) -> YftGlassPane:
    resolved_shader_index = (
        int(getattr(mesh, "material_index", -1))
        if shader_index is None
        else int(shader_index)
    )
    if not 0 <= resolved_shader_index <= 0xFF:
        raise ValueError("glass shader index must fit in an unsigned byte")
    return build_yft_glass_pane(
        YftGlassPaneMesh.from_ydr_mesh(mesh),
        bone_index=bone_index,
        glass_type=glass_type,
        shader_index=resolved_shader_index,
        bounds_minimum=bounds_minimum,
        bounds_maximum=bounds_maximum,
        bounds_transform=bounds_transform,
    )


__all__ = [
    "BlendIndices",
    "BlendWeights",
    "Vector2",
    "YftGlassOrthonormalTransform",
    "YftGlassPaneGeometry",
    "YftGlassPaneMesh",
    "build_yft_glass_pane",
    "build_yft_glass_pane_from_mesh",
    "compute_glass_bounds_offsets",
    "compute_glass_pane_geometry",
]
