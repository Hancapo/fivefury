from __future__ import annotations

from collections.abc import Mapping

from .model import Bound, BoundType

GEN9_BOUND_FILE_VFTS: Mapping[BoundType, int] = {
    BoundType.SPHERE: 0x406B2328,
    BoundType.CAPSULE: 0x406B1868,
    BoundType.BOX: 0x406B1F48,
    BoundType.DISC: 0x406B24E8,
    BoundType.CYLINDER: 0x406B2400,
    BoundType.GEOMETRY: 0x406B2020,
    BoundType.GEOMETRY_BVH: 0x406B2130,
    BoundType.COMPOSITE: 0x406B1940,
}


def gen9_bound_file_vft(bound: Bound) -> int:
    try:
        return GEN9_BOUND_FILE_VFTS[bound.bound_type]
    except KeyError as exc:
        raise ValueError(
            f"Gen9 does not define a runtime header for {bound.bound_type.name}"
        ) from exc


__all__ = ["GEN9_BOUND_FILE_VFTS", "gen9_bound_file_vft"]
