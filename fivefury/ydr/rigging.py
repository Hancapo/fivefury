from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Iterable, Sequence

from .defs import YdrLod, coerce_lod
from .model import Ydr, YdrBone, YdrMesh, YdrModel, YdrSkeleton


Vec3 = tuple[float, float, float]
Vec4 = tuple[float, float, float, float]
Index4 = tuple[int, int, int, int]


class RadialRigFalloff(enum.StrEnum):
    CONSTANT = "constant"
    LINEAR = "linear"
    SMOOTH = "smooth"


@dataclasses.dataclass(frozen=True, slots=True)
class RadialBoneRigRule:
    bone: str | int | YdrBone
    radius: float
    strength: float = 1.0
    center: Vec3 | None = None
    falloff: RadialRigFalloff | str = RadialRigFalloff.SMOOTH
    replace_existing: bool = False

    def __post_init__(self) -> None:
        if float(self.radius) <= 0.0:
            raise ValueError("radius must be greater than zero")
        if float(self.strength) < 0.0:
            raise ValueError("strength cannot be negative")


@dataclasses.dataclass(frozen=True, slots=True)
class RadialRigReport:
    meshes: int = 0
    vertices: int = 0
    bones_added: int = 0

    @property
    def changed(self) -> bool:
        return self.vertices > 0 or self.bones_added > 0


@dataclasses.dataclass(frozen=True, slots=True)
class _ResolvedRule:
    bone_tag: int
    bone_index: int | None
    center: Vec3
    radius: float
    strength: float
    falloff: RadialRigFalloff
    replace_existing: bool


def _bone_center(bone: YdrBone, skeleton: YdrSkeleton | None) -> Vec3:
    if skeleton is not None and 0 <= int(bone.index) < len(skeleton.transformations):
        matrix = skeleton.transformations[int(bone.index)]
        return (float(matrix[3][0]), float(matrix[3][1]), float(matrix[3][2]))
    return tuple(float(value) for value in bone.translation)


def _resolve_rule(rule: RadialBoneRigRule, skeleton: YdrSkeleton | None) -> _ResolvedRule:
    bone = rule.bone
    resolved_bone: YdrBone | None = None
    if isinstance(bone, YdrBone):
        resolved_bone = bone
        bone_tag = int(bone.tag)
    elif isinstance(bone, str):
        if skeleton is None:
            raise ValueError("skeleton= is required when radial rigging by bone name")
        resolved_bone = skeleton.require_bone(bone)
        bone_tag = int(resolved_bone.tag)
    else:
        bone_tag = int(bone)
        if skeleton is not None:
            resolved_bone = skeleton.get_bone_by_tag(bone_tag) or skeleton.get_bone_by_index(bone_tag)
    if rule.center is None and resolved_bone is None:
        raise ValueError("center= is required when radial rigging by numeric bone without a matching skeleton bone")
    center = tuple(float(value) for value in (rule.center if rule.center is not None else _bone_center(resolved_bone, skeleton)))
    return _ResolvedRule(
        bone_tag=bone_tag,
        bone_index=int(resolved_bone.index) if resolved_bone is not None else None,
        center=center,
        radius=float(rule.radius),
        strength=float(rule.strength),
        falloff=RadialRigFalloff(rule.falloff),
        replace_existing=bool(rule.replace_existing),
    )


def _distance(a: Vec3, b: Vec3) -> float:
    return math.sqrt(sum((float(a[index]) - float(b[index])) ** 2 for index in range(3)))


def _falloff_weight(rule: _ResolvedRule, position: Vec3) -> float:
    t = max(0.0, min(1.0, 1.0 - (_distance(position, rule.center) / rule.radius)))
    if t <= 0.0:
        return 0.0
    if rule.falloff is RadialRigFalloff.CONSTANT:
        value = 1.0
    elif rule.falloff is RadialRigFalloff.LINEAR:
        value = t
    else:
        value = t * t * (3.0 - (2.0 * t))
    return max(0.0, min(1.0, value * rule.strength))


def _ensure_tuple4(values: Sequence[float | int], fill: float = 0.0) -> tuple[float, float, float, float]:
    padded = [float(value) for value in values[:4]]
    padded.extend([float(fill)] * (4 - len(padded)))
    return (padded[0], padded[1], padded[2], padded[3])


def _ensure_index4(values: Sequence[int], fill: int = 0) -> Index4:
    padded = [int(value) for value in values[:4]]
    padded.extend([int(fill)] * (4 - len(padded)))
    return (padded[0], padded[1], padded[2], padded[3])


def _normalise_influences(influences: dict[int, float], max_influences: int) -> tuple[Vec4, Index4]:
    ranked = sorted(
        ((int(index), max(0.0, float(weight))) for index, weight in influences.items() if float(weight) > 0.0),
        key=lambda item: item[1],
        reverse=True,
    )[:max_influences]
    total = sum(weight for _, weight in ranked)
    if total <= 0.0:
        ranked = [(0, 1.0)]
        total = 1.0
    weights = [weight / total for _, weight in ranked]
    indices = [index for index, _ in ranked]
    return (_ensure_tuple4(weights), _ensure_index4(indices))


def _mesh_palette_index(mesh: YdrMesh, rule: _ResolvedRule) -> tuple[int, bool]:
    for index, existing in enumerate(mesh.bone_ids):
        if int(existing) == int(rule.bone_tag):
            return (index, False)
    if rule.bone_index is not None:
        for index, existing in enumerate(mesh.bone_ids):
            if int(existing) == int(rule.bone_index):
                return (index, False)
    mesh.bone_ids.append(int(rule.bone_tag))
    return (len(mesh.bone_ids) - 1, True)


def _default_skin(mesh: YdrMesh) -> tuple[list[Vec4], list[Index4]]:
    vertex_count = len(mesh.positions)
    weights = list(mesh.blend_weights) if mesh.blend_weights else [(1.0, 0.0, 0.0, 0.0)] * vertex_count
    indices = list(mesh.blend_indices) if mesh.blend_indices else [(0, 0, 0, 0)] * vertex_count
    if len(weights) != vertex_count:
        raise ValueError("blend_weights length must match positions length before radial rigging")
    if len(indices) != vertex_count:
        raise ValueError("blend_indices length must match positions length before radial rigging")
    if not mesh.bone_ids:
        mesh.bone_ids.append(0)
    return (weights, indices)


def rig_mesh_to_bones_radially(
    mesh: YdrMesh,
    rules: Sequence[RadialBoneRigRule],
    *,
    skeleton: YdrSkeleton | None = None,
    max_influences: int = 4,
    min_weight: float = 0.0001,
) -> RadialRigReport:
    """Blend vertices into target bones by radial proximity.

    Existing skinning is preserved by default: affected vertices donate a portion
    of their current total weight to the radial bone, then all influences are
    collapsed back to GTA's four-weight vertex layout.
    """

    if max_influences < 1 or max_influences > 4:
        raise ValueError("max_influences must be between 1 and 4")
    if not mesh.positions or not rules:
        return RadialRigReport()
    resolved_rules = [_resolve_rule(rule, skeleton) for rule in rules]
    weights, indices = _default_skin(mesh)
    vertices_changed = 0
    bones_added = 0
    for rule in resolved_rules:
        palette_index, added = _mesh_palette_index(mesh, rule)
        bones_added += int(added)
        for vertex_index, position in enumerate(mesh.positions):
            amount = _falloff_weight(rule, position)
            if amount <= min_weight:
                continue
            current = {
                int(index): float(weight)
                for index, weight in zip(indices[vertex_index], weights[vertex_index], strict=True)
                if float(weight) > 0.0
            }
            if rule.replace_existing:
                current = {palette_index: amount}
            else:
                scale = max(0.0, 1.0 - amount)
                current = {index: weight * scale for index, weight in current.items()}
                current[palette_index] = current.get(palette_index, 0.0) + amount
            weights[vertex_index], indices[vertex_index] = _normalise_influences(current, max_influences)
            vertices_changed += 1
    if vertices_changed:
        mesh.blend_weights = weights
        mesh.blend_indices = indices
    return RadialRigReport(meshes=int(vertices_changed > 0), vertices=vertices_changed, bones_added=bones_added)


def _iter_models(ydr: Ydr, lod: YdrLod | str | None = None) -> Iterable[YdrModel]:
    if lod is None:
        yield from ydr.models
        return
    yield from ydr.lods.get(coerce_lod(lod), [])


def rig_ydr_to_bones_radially(
    ydr: Ydr,
    rules: Sequence[RadialBoneRigRule],
    *,
    skeleton: YdrSkeleton | None = None,
    lod: YdrLod | str | None = None,
    model: int | None = None,
    max_influences: int = 4,
    min_weight: float = 0.0001,
) -> RadialRigReport:
    active_skeleton = skeleton if skeleton is not None else ydr.skeleton
    total_meshes = 0
    total_vertices = 0
    total_bones_added = 0
    for candidate in _iter_models(ydr, lod=lod):
        if model is not None and int(candidate.index) != int(model):
            continue
        model_vertices = 0
        for mesh in candidate.meshes:
            report = rig_mesh_to_bones_radially(
                mesh,
                rules,
                skeleton=active_skeleton,
                max_influences=max_influences,
                min_weight=min_weight,
            )
            total_meshes += report.meshes
            total_vertices += report.vertices
            total_bones_added += report.bones_added
            model_vertices += report.vertices
        if model_vertices and not candidate.has_skin:
            candidate.set_skin_binding()
    return RadialRigReport(meshes=total_meshes, vertices=total_vertices, bones_added=total_bones_added)


__all__ = [
    "RadialBoneRigRule",
    "RadialRigFalloff",
    "RadialRigReport",
    "rig_mesh_to_bones_radially",
    "rig_ydr_to_bones_radially",
]
