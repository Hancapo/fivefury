from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class YftGeometryStats:
    drawable_count: int = 0
    model_count: int = 0
    mesh_count: int = 0
    vertex_count: int = 0
    index_count: int = 0
    triangle_count: int = 0
    material_count: int = 0
    texture_count: int = 0


__all__ = [
    "YftGeometryStats",
]
