from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from pathlib import Path

from ..common import atomic_write_bytes
from ..vector import Aabb3, aabb_expand, aabb_merge
from .enums import YmapContentFlags, YmapFlags, YmapLodLightCategory
from .lights import DistantLodLightsSoa, LodLightsSoa
from .lodlight_generation import GeneratedLodLight, LodLightSourceInstance
from .lodlight_partition import (
    MAX_LOD_LIGHTS_PER_CELL,
    partition_lod_lights_by_category,
)
from .model import Ymap

LOD_LIGHT_VISIBILITY_RADII: dict[YmapLodLightCategory, tuple[float, float]] = {
    YmapLodLightCategory.SMALL: (450.0, 450.0),
    YmapLodLightCategory.MEDIUM: (3000.0, 950.0),
    YmapLodLightCategory.LARGE: (2700.0, 2700.0),
}


@dataclasses.dataclass(slots=True, frozen=True)
class LodLightMapPair:
    distant: Ymap
    lod: Ymap
    category: YmapLodLightCategory
    index: int

    def validate(self) -> list[str]:
        issues = [*self.distant.validate(), *self.lod.validate()]
        distant_lights = self.distant.distant_lod_lights
        lod_lights = self.lod.lod_lights
        if not isinstance(distant_lights, DistantLodLightsSoa):
            issues.append("distant map has no DistantLODLightsSOA")
            return issues
        if not isinstance(lod_lights, LodLightsSoa):
            issues.append("LOD map has no LODLightsSOA")
            return issues
        if len(distant_lights) != len(lod_lights):
            issues.append("paired distant and LOD maps have different light counts")
        if distant_lights.category != self.category:
            issues.append("distant map category does not match the pair category")
        if int(self.lod.parent) != int(self.distant.name):
            issues.append("LOD map does not reference its distant parent")
        return issues

    def require_valid(self) -> LodLightMapPair:
        issues = self.validate()
        if issues:
            raise ValueError("Invalid LOD-light map pair:\n- " + "\n- ".join(issues))
        return self


def build_lod_light_maps(
    lights: Sequence[GeneratedLodLight],
    *,
    name_prefix: str = "",
    script_group_name: str | None = None,
    max_lights_per_cell: int = MAX_LOD_LIGHTS_PER_CELL,
) -> list[LodLightMapPair]:
    source = list(lights)
    _validate_unique_hashes(source)
    if not source:
        return []
    if script_group_name is not None:
        group_name = script_group_name.strip()
        if not group_name:
            raise ValueError("script_group_name must not be empty")
        return [
            _build_pair(
                source,
                category=YmapLodLightCategory.MEDIUM,
                index=0,
                distant_name=f"{group_name}_DistantLights",
                lod_name=f"{group_name}_LODLights",
                manual_stream=True,
            )
        ]

    prefix = f"{name_prefix.strip('_')}_" if name_prefix.strip("_") else ""
    result: list[LodLightMapPair] = []
    cells_by_category = partition_lod_lights_by_category(
        source,
        max_lights_per_cell=max_lights_per_cell,
    )
    for category in YmapLodLightCategory:
        label = category.name.lower()
        for index, cell in enumerate(cells_by_category.get(category, [])):
            result.append(
                _build_pair(
                    cell,
                    category=category,
                    index=index,
                    distant_name=f"{prefix}DistLODLights_{label}{index:03d}",
                    lod_name=f"{prefix}LODLights_{label}{index:03d}",
                )
            )
    return result


def build_lod_light_maps_from_sources(
    sources: Sequence[LodLightSourceInstance],
    *,
    name_prefix: str = "",
    script_group_name: str | None = None,
    max_lights_per_cell: int = MAX_LOD_LIGHTS_PER_CELL,
) -> list[LodLightMapPair]:
    lights = [light for source in sources for light in source.extract()]
    return build_lod_light_maps(
        lights,
        name_prefix=name_prefix,
        script_group_name=script_group_name,
        max_lights_per_cell=max_lights_per_cell,
    )


def save_lod_light_maps(
    pairs: Sequence[LodLightMapPair],
    directory: str | Path,
    *,
    version: int = 2,
) -> list[Path]:
    output = Path(directory)
    payloads: list[tuple[Path, bytes]] = []
    for pair in pairs:
        pair.require_valid()
        for ymap in (pair.distant, pair.lod):
            name = ymap.name.text
            if not name:
                raise ValueError("generated YMAP name is unresolved")
            payloads.append(
                (output / f"{name}.ymap", ymap.to_bytes(version=version, validate=True))
            )
    output.mkdir(parents=True, exist_ok=True)
    return [atomic_write_bytes(path, data) for path, data in payloads]


def _build_pair(
    source: Sequence[GeneratedLodLight],
    *,
    category: YmapLodLightCategory,
    index: int,
    distant_name: str,
    lod_name: str,
    manual_stream: bool = False,
) -> LodLightMapPair:
    street = sorted(
        (item for item in source if item.is_street_light),
        key=lambda item: int(item.light.hash),
    )
    other = sorted(
        (item for item in source if not item.is_street_light),
        key=lambda item: int(item.light.hash),
    )
    ordered = street + other
    physical_extents = _physical_extents(ordered)
    distant_radius, lod_radius = LOD_LIGHT_VISIBILITY_RADII[category]
    distant_streaming_extents = _streaming_extents(ordered, distant_radius)
    lod_streaming_extents = _streaming_extents(ordered, lod_radius)

    distant_soa = DistantLodLightsSoa(
        num_street_lights=len(street),
        category=category,
    )
    lod_soa = LodLightsSoa()
    for item in ordered:
        distant_soa.append(item.light.position, item.light.rgbi)
        lod_soa.append(item.light)

    manual_flag = YmapFlags.MANUAL_STREAM_ONLY if manual_stream else YmapFlags.NONE
    distant = Ymap(
        name=distant_name,
        flags=YmapFlags.IS_PARENT | manual_flag,
        content_flags=YmapContentFlags.DISTANT_LOD_LIGHTS,
        streaming_extents_min=distant_streaming_extents[0],
        streaming_extents_max=distant_streaming_extents[1],
        entities_extents_min=physical_extents[0],
        entities_extents_max=physical_extents[1],
        distant_lod_lights=distant_soa,
    )
    lod = Ymap(
        name=lod_name,
        parent=distant_name,
        flags=manual_flag,
        content_flags=YmapContentFlags.LOD_LIGHTS,
        streaming_extents_min=lod_streaming_extents[0],
        streaming_extents_max=lod_streaming_extents[1],
        entities_extents_min=physical_extents[0],
        entities_extents_max=physical_extents[1],
        lod_lights=lod_soa,
    )
    return LodLightMapPair(
        distant=distant,
        lod=lod,
        category=category,
        index=index,
    ).require_valid()


def _physical_extents(lights: Sequence[GeneratedLodLight]) -> Aabb3:
    bounds: Aabb3 | None = None
    for item in lights:
        bounds = aabb_merge(bounds, item.physical_bounds)
    if bounds is None:
        raise ValueError("at least one LOD light is required")
    return bounds


def _streaming_extents(
    lights: Sequence[GeneratedLodLight], radius: float
) -> Aabb3:
    bounds: Aabb3 | None = None
    for item in lights:
        position = item.light.position
        bounds = aabb_merge(bounds, aabb_expand((position, position), radius))
    if bounds is None:
        raise ValueError("at least one LOD light is required")
    return bounds


def _validate_unique_hashes(lights: Sequence[GeneratedLodLight]) -> None:
    seen: dict[int, GeneratedLodLight] = {}
    for item in lights:
        light_hash = int(item.light.hash) & 0xFFFFFFFF
        previous = seen.get(light_hash)
        if previous is not None:
            raise ValueError(
                f"LOD light hash collision 0x{light_hash:08X} between "
                f"{previous.source_model_name or '<unknown>'}[{previous.source_light_index}] "
                f"and {item.source_model_name or '<unknown>'}[{item.source_light_index}]"
            )
        seen[light_hash] = item


__all__ = [
    "LOD_LIGHT_VISIBILITY_RADII",
    "LodLightMapPair",
    "build_lod_light_maps",
    "build_lod_light_maps_from_sources",
    "save_lod_light_maps",
]
