from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ..metahash import HashLike, MetaHash

from .archetypes import BaseArchetypeDef, TimeArchetypeDef
from .mlo import MloArchetypeDef
from .model import Ytyp


def time_flags(start: int, end: int, *, invert: bool = False) -> int:
    """Build a 24-bit ``time_flags`` mask from an hour range.

    Hours use a 24h clock (0-23).  The range wraps around midnight::

        time_flags(13, 18)   # visible 13:00-17:59
        time_flags(22, 6)    # visible 22:00-05:59 (overnight)
        time_flags(0, 24)    # visible all day (0xFFFFFF)

    Set *invert* to ``True`` to get the opposite window::

        time_flags(13, 18, invert=True)  # hidden 13:00-17:59

    Returns an ``int`` ready for :attr:`TimeArchetypeDef.time_flags`.
    """
    if start < 0 or end < 0 or start > 24 or end > 24:
        raise ValueError("Hours must be between 0 and 24")
    start_h = start % 24
    end_h = end % 24
    if start == end or (start_h == 0 and end == 24):
        mask = 0xFFFFFF
    elif start_h < end_h:
        mask = sum(1 << h for h in range(start_h, end_h))
    else:
        mask = sum(1 << h for h in range(start_h, 24)) | sum(1 << h for h in range(0, end_h))
    if invert:
        mask = 0xFFFFFF & ~mask
    return mask


def _coerce_ytyp_source(source: Ytyp | bytes | str | Path) -> Ytyp:
    if isinstance(source, Ytyp):
        return source
    if isinstance(source, bytes):
        return Ytyp.from_bytes(source)
    return Ytyp.from_path(source)


def _expand_ytyp_sources(
    source: Ytyp | bytes | str | Path,
    *,
    recursive: bool,
) -> list[Ytyp | bytes | str | Path]:
    if isinstance(source, (Ytyp, bytes)):
        return [source]
    path = Path(source)
    if path.is_dir():
        ytyp_paths = sorted(
            candidate
            for candidate in (path.rglob("*.ytyp") if recursive else path.glob("*.ytyp"))
            if candidate.is_file()
        )
        if not ytyp_paths:
            raise ValueError(f"No .ytyp files found in: {path}")
        return ytyp_paths
    return [path]


def merge_ytyps(
    *sources: Ytyp | bytes | str | Path,
    destination: str | Path | None = None,
    name: HashLike | None = None,
    recursive: bool = False,
    version: int = 2,
) -> Ytyp | Path:
    if len(sources) == 1 and isinstance(sources[0], (list, tuple, set)):
        sources = tuple(sources[0])
    if not sources:
        raise ValueError("merge_ytyps requires at least one YTYP source")

    expanded_sources: list[Ytyp | bytes | str | Path] = []
    for source in sources:
        expanded_sources.extend(_expand_ytyp_sources(source, recursive=recursive))

    ytyps = [_coerce_ytyp_source(source) for source in expanded_sources]
    merged_name = str(name or ytyps[0].name or "merged_meta").strip().lower()
    merged = Ytyp(name=merged_name)

    dependency_keys: set[int] = set()
    archetypes_by_name: dict[int, Any] = {}
    anonymous_index = -1

    for ytyp in ytyps:
        merged.extensions.extend(copy.deepcopy(ytyp.extensions))
        merged.composite_entity_types.extend(copy.deepcopy(ytyp.composite_entity_types))
        for dependency in ytyp.dependencies:
            dependency_key = int(MetaHash(dependency))
            if dependency_key in dependency_keys:
                continue
            dependency_keys.add(dependency_key)
            merged.dependencies.append(copy.deepcopy(dependency))
        for archetype in ytyp.archetypes:
            name_key = int(MetaHash(getattr(archetype, "name", 0)))
            if name_key == 0:
                name_key = anonymous_index
                anonymous_index -= 1
            archetypes_by_name[name_key] = copy.deepcopy(archetype)

    merged.archetypes = list(archetypes_by_name.values())

    if destination is None:
        return merged
    return merged.save(destination, version=version)


def ytyp_from_ydr_folder(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    name: HashLike | None = None,
    recursive: bool = False,
    texture_suffix: str = "_txd",
    version: int = 2,
) -> Ytyp | Path:
    folder = Path(source)
    if not folder.is_dir():
        raise ValueError(f"YDR folder does not exist: {folder}")

    from ..ydr import read_ydr

    ydr_paths = sorted(
        path
        for path in (folder.rglob("*") if recursive else folder.iterdir())
        if path.is_file() and path.suffix.lower() == ".ydr"
    )
    if not ydr_paths:
        raise ValueError(f"No .ydr files found in: {folder}")

    ytyp_name = str(name or f"{folder.name}_meta").strip().lower()
    ytyp = Ytyp(name=ytyp_name)

    for ydr_path in ydr_paths:
        model_name = ydr_path.stem.lower()
        ydr = read_ydr(ydr_path, path=ydr_path)
        ytyp.add_archetype(
            BaseArchetypeDef(
                name=model_name,
                asset_name=model_name,
                texture_dictionary=f"{model_name}{texture_suffix}",
                asset_type=2,
                bb_min=ydr.bounding_box_min,
                bb_max=ydr.bounding_box_max,
                bs_centre=ydr.bounding_center,
                bs_radius=ydr.bounding_sphere_radius,
            )
        )

    if destination is None:
        return ytyp
    return ytyp.save(destination, version=version)
