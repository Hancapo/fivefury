from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from pathlib import Path

from .reader import read_yft


@dataclasses.dataclass(frozen=True, slots=True)
class YftCorpusEntry:
    path: Path
    readable: bool
    drawable_count: int = 0
    physics_lod_count: int = 0
    physics_group_count: int = 0
    physics_child_count: int = 0
    has_bounds: bool = False
    error: str = ""


def iter_yft_paths(paths: Iterable[str | Path]) -> tuple[Path, ...]:
    results: list[Path] = []
    for source in paths:
        path = Path(source)
        if path.is_dir():
            results.extend(sorted(path.rglob("*.yft")))
        elif path.suffix.lower() == ".yft":
            results.append(path)
    return tuple(dict.fromkeys(results))


def scan_yft_corpus(
    paths: Iterable[str | Path],
    *,
    limit: int | None = None,
    resolve_physics_entities: bool = False,
) -> tuple[YftCorpusEntry, ...]:
    entries: list[YftCorpusEntry] = []
    for index, path in enumerate(iter_yft_paths(paths)):
        if limit is not None and index >= limit:
            break
        try:
            yft = read_yft(path, resolve_physics_entities=resolve_physics_entities)
        except Exception as exc:
            entries.append(YftCorpusEntry(path=path, readable=False, error=str(exc)))
            continue
        entries.append(
            YftCorpusEntry(
                path=path,
                readable=True,
                drawable_count=yft.drawable_count,
                physics_lod_count=len(yft.physics_lod_details),
                physics_group_count=sum(lod.num_groups for lod in yft.physics_lod_details),
                physics_child_count=sum(lod.num_children for lod in yft.physics_lod_details),
                has_bounds=any(lod.composite_bound is not None for lod in yft.physics_lod_details),
            )
        )
    return tuple(entries)


__all__ = [
    "YftCorpusEntry",
    "iter_yft_paths",
    "scan_yft_corpus",
]
