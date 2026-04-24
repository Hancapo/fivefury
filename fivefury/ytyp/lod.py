from __future__ import annotations

from math import sqrt


DEFAULT_ARCHETYPE_LOD_DIST = 100.0
DEFAULT_ARCHETYPE_HD_TEXTURE_DIST = 50.0
ARCHETYPE_LOD_RADIUS_SCALE = 3.0
ARCHETYPE_HD_TEXTURE_RADIUS_SCALE = 1.5


def _radius_from_bounds(
    bb_min: tuple[float, float, float] | None,
    bb_max: tuple[float, float, float] | None,
) -> float:
    if bb_min is None or bb_max is None:
        return 0.0
    dx = float(bb_max[0]) - float(bb_min[0])
    dy = float(bb_max[1]) - float(bb_min[1])
    dz = float(bb_max[2]) - float(bb_min[2])
    if dx <= 0.0 and dy <= 0.0 and dz <= 0.0:
        return 0.0
    return sqrt(dx * dx + dy * dy + dz * dz) * 0.5


def infer_archetype_radius(
    *,
    bs_radius: float = 0.0,
    bb_min: tuple[float, float, float] | None = None,
    bb_max: tuple[float, float, float] | None = None,
) -> float:
    radius = float(bs_radius or 0.0)
    if radius > 0.0:
        return radius
    return _radius_from_bounds(bb_min, bb_max)


def infer_archetype_lod_dist(
    *,
    bs_radius: float = 0.0,
    bb_min: tuple[float, float, float] | None = None,
    bb_max: tuple[float, float, float] | None = None,
    minimum: float = DEFAULT_ARCHETYPE_LOD_DIST,
) -> float:
    radius = infer_archetype_radius(bs_radius=bs_radius, bb_min=bb_min, bb_max=bb_max)
    return max(float(minimum), radius * ARCHETYPE_LOD_RADIUS_SCALE)


def infer_archetype_hd_texture_dist(
    *,
    bs_radius: float = 0.0,
    lod_dist: float = 0.0,
    bb_min: tuple[float, float, float] | None = None,
    bb_max: tuple[float, float, float] | None = None,
    minimum: float = DEFAULT_ARCHETYPE_HD_TEXTURE_DIST,
) -> float:
    radius = infer_archetype_radius(bs_radius=bs_radius, bb_min=bb_min, bb_max=bb_max)
    inferred = max(float(minimum), radius * ARCHETYPE_HD_TEXTURE_RADIUS_SCALE)
    lod = float(lod_dist or 0.0)
    return min(inferred, lod) if lod > 0.0 else inferred


__all__ = [
    "ARCHETYPE_HD_TEXTURE_RADIUS_SCALE",
    "ARCHETYPE_LOD_RADIUS_SCALE",
    "DEFAULT_ARCHETYPE_HD_TEXTURE_DIST",
    "DEFAULT_ARCHETYPE_LOD_DIST",
    "infer_archetype_hd_texture_dist",
    "infer_archetype_lod_dist",
    "infer_archetype_radius",
]
