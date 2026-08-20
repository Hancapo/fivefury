from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ..bounds import Bound
from ..metahash import HashLike
from ..vector import Vector3
from ..ybn import Ybn, read_ybn
from ..ymap import MloInstanceDef, Ymap, YmapContentFlags, YmapFlags, read_ymap
from ..ymap.mlo_validation import mlo_archetypes_by_hash
from ..ytyp import Ytyp, read_ytyp
from ..ytyp.mlo_validation import exit_portal_count
from .model import (
    Gta5CacheBound,
    Gta5CacheFileDate,
    Gta5CacheInteriorProxy,
    Gta5CacheMapData,
    Gta5CacheMode,
    Gta5CacheY,
)


def _as_sequence(value: Any, expected_attribute: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return list(value.values())
    if hasattr(value, expected_attribute):
        return [value]
    return list(value)


def _bound_entries(ybns: Any) -> list[Gta5CacheBound]:
    if ybns is None:
        return []
    entries: list[Gta5CacheBound] = []
    if isinstance(ybns, Mapping):
        for name, value in ybns.items():
            if isinstance(value, Gta5CacheBound):
                entries.append(value)
            elif isinstance(value, Ybn):
                entries.append(Gta5CacheBound.from_ybn(name, value))
            elif isinstance(value, Bound):
                entries.append(Gta5CacheBound.from_bound(name, value))
            else:
                raise TypeError(
                    f"unsupported YBN mapping value: {type(value).__name__}"
                )
        return entries
    if isinstance(ybns, (Ybn, Gta5CacheBound)):
        ybns = (ybns,)
    for value in ybns:
        if isinstance(value, Gta5CacheBound):
            entries.append(value)
            continue
        if not isinstance(value, Ybn):
            raise TypeError(f"unsupported YBN source: {type(value).__name__}")
        if not value.path:
            raise ValueError(
                "unnamed YBN sources require a mapping key or Gta5CacheBound"
            )
        entries.append(Gta5CacheBound.from_ybn(Path(value.path).stem, value))
    return entries


def build_gta5_cache_y(
    ymaps: Ymap | Iterable[Ymap],
    *,
    ytyps: Ytyp | Iterable[Ytyp] | Mapping[Any, Ytyp] | None = None,
    ybns: Mapping[HashLike, Ybn | Bound | Gta5CacheBound]
    | Iterable[Ybn | Gta5CacheBound]
    | None = None,
    file_dates: Iterable[Gta5CacheFileDate] = (),
    mode: Gta5CacheMode = Gta5CacheMode.STANDARD,
) -> Gta5CacheY:
    map_sources = _as_sequence(ymaps, "entities")
    type_sources = _as_sequence(ytyps, "archetypes")
    if not all(isinstance(ymap, Ymap) for ymap in map_sources):
        raise TypeError("ymaps must contain Ymap objects")
    if not all(isinstance(ytyp, Ytyp) for ytyp in type_sources):
        raise TypeError("ytyps must contain Ytyp objects")
    mode = mode if isinstance(mode, Gta5CacheMode) else Gta5CacheMode(mode)

    parent_hashes = {int(ymap.parent) for ymap in map_sources if int(ymap.parent)}
    if map_sources:
        world_physics_min = Vector3.minimum(
            ymap.entities_extents_min for ymap in map_sources
        )
        world_physics_max = Vector3.maximum(
            ymap.entities_extents_max for ymap in map_sources
        )
    else:
        world_physics_min = world_physics_max = Vector3()

    def streaming_bounds(
        ymap: Ymap,
    ) -> tuple[Vector3, Vector3]:
        minimum = ymap.streaming_extents_min
        maximum = ymap.streaming_extents_max
        if ymap.content_flags & YmapContentFlags.DISTANT_LOD_LIGHTS:
            minimum = Vector3.minimum((minimum, world_physics_min))
            maximum = Vector3.maximum((maximum, world_physics_max))
        return minimum, maximum

    map_entries: list[Gta5CacheMapData] = []
    for ymap in map_sources:
        streaming_min, streaming_max = streaming_bounds(ymap)
        map_entries.append(
            Gta5CacheMapData(
                name_hash=ymap.name,
                parent_name_hash=ymap.parent,
                content_flags=int(ymap.content_flags),
                streaming_min=streaming_min,
                streaming_max=streaming_max,
                physics_min=ymap.entities_extents_min,
                physics_max=ymap.entities_extents_max,
                dynamic_streaming=not bool(ymap.flags & YmapFlags.MANUAL_STREAM_ONLY),
                contains_block_info=bool(
                    ymap.content_flags & YmapContentFlags.BLOCKINFO
                ),
                is_parent=bool(ymap.flags & YmapFlags.IS_PARENT)
                or int(ymap.name) in parent_hashes,
            )
        )

    mlo_archetypes = mlo_archetypes_by_hash(type_sources)
    proxies: list[Gta5CacheInteriorProxy] = []
    for ymap in map_sources:
        for entity in ymap.entities:
            if not isinstance(entity, MloInstanceDef):
                continue
            archetype = mlo_archetypes.get(int(entity.archetype_name))
            proxies.append(
                Gta5CacheInteriorProxy(
                    group_id=entity.group_id,
                    floor_id=entity.floor_id,
                    exit_portal_count=exit_portal_count(archetype)
                    if archetype is not None
                    else entity.num_exit_portals,
                    archetype_hash=entity.archetype_name,
                    ymap_hash=ymap.name,
                    position=entity.position,
                    rotation=entity.rotation,
                    bounds_min=ymap.entities_extents_min,
                    bounds_max=ymap.entities_extents_max,
                )
            )

    cache = Gta5CacheY(
        mode=mode,
        file_dates=list(file_dates),
        map_data=map_entries,
        interior_proxies=proxies,
        bounds=_bound_entries(ybns),
    )
    cache.validate().raise_for_errors()
    return cache


def build_gta5_cache_y_from_directory(
    directory: str | Path,
    *,
    file_dates: Iterable[Gta5CacheFileDate] = (),
    mode: Gta5CacheMode = Gta5CacheMode.STANDARD,
    recursive: bool = True,
) -> Gta5CacheY:
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(root)
    glob = root.rglob if recursive else root.glob
    ytyps = [read_ytyp(path.read_bytes()) for path in sorted(glob("*.ytyp"))]
    ymaps = [read_ymap(path.read_bytes()) for path in sorted(glob("*.ymap"))]
    ybns = {path.stem: read_ybn(path, path=path) for path in sorted(glob("*.ybn"))}
    return build_gta5_cache_y(
        ymaps, ytyps=ytyps, ybns=ybns, file_dates=file_dates, mode=mode
    )


__all__ = ["build_gta5_cache_y", "build_gta5_cache_y_from_directory"]
