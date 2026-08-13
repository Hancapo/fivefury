from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from ..common import hash_value
from ..gamefile import GameFileType
from ..gtxd import Gtxd, read_gtxd
from ..ymt import Ymt
from .precedence import asset_source_rank, preferred_asset

if TYPE_CHECKING:
    from .core import GameFileCache
    from .views import AssetRecord


class TextureGraphIssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TextureGraphEdge:
    child: str
    parent: str
    child_hash: int
    parent_hash: int
    source_path: str
    source_rank: tuple[int, str]


@dataclass(frozen=True, slots=True)
class TextureGraphIssue:
    severity: TextureGraphIssueSeverity
    code: str
    message: str
    child_hash: int = 0
    parent_hash: int = 0
    source_paths: tuple[str, ...] = ()


@dataclass(slots=True)
class TextureDictionaryGraph:
    cache: GameFileCache = field(repr=False)
    _generation: int = field(default=-1, init=False, repr=False)
    _edges_by_child: dict[int, list[TextureGraphEdge]] = field(default_factory=dict, init=False, repr=False)
    _selected: dict[int, TextureGraphEdge] = field(default_factory=dict, init=False, repr=False)
    _issues: list[TextureGraphIssue] = field(default_factory=list, init=False, repr=False)

    def clear(self) -> None:
        self._generation = -1
        self._edges_by_child.clear()
        self._selected.clear()
        self._issues.clear()

    def _candidate_assets(self) -> Iterator[AssetRecord]:
        seen: set[str] = set()
        candidates = [*self.cache.iter_assets(kind=GameFileType.GTXD)]
        candidates.extend(self.cache.find_assets("vehicles.meta"))
        candidates.extend(self.cache.find_assets("peds.meta"))
        candidates.extend(
            asset
            for asset in self.cache.iter_assets(kind=GameFileType.YMT)
            if asset.stem.lower() == "gtxd" or asset.stem.lower().endswith("_gtxd")
        )
        for asset in sorted(candidates, key=asset_source_rank):
            if asset.path in seen:
                continue
            seen.add(asset.path)
            yield asset

    @staticmethod
    def _relationships(parsed: Any) -> tuple[Any, ...]:
        if isinstance(parsed, Gtxd):
            return tuple(parsed.relationships)
        if isinstance(parsed, Ymt) and parsed.gtxd is not None:
            return tuple(parsed.gtxd.relationships)
        relationships = getattr(parsed, "txd_relationships", None)
        if relationships is not None:
            return tuple(relationships)
        content = getattr(parsed, "content", None)
        if content is not None and content is not parsed:
            return TextureDictionaryGraph._relationships(content)
        return ()

    def _load_asset_edges(self, asset: AssetRecord) -> None:
        game_file = self.cache.get_file(asset)
        relationships = self._relationships(game_file.parsed) if game_file is not None else ()
        if not relationships:
            data = self.cache.read_bytes(asset, logical=True)
            if data:
                try:
                    relationships = tuple(read_gtxd(data).relationships)
                except Exception:
                    relationships = ()
        if not relationships:
            self._issues.append(
                TextureGraphIssue(
                    TextureGraphIssueSeverity.WARNING,
                    "unreadable_source",
                    f"Texture relationship source '{asset.path}' could not be read",
                    source_paths=(asset.path,),
                )
            )
            return
        rank = asset_source_rank(asset)
        for relationship in relationships:
            child = str(getattr(relationship, "child", "")).strip().lower()
            parent = str(getattr(relationship, "parent", "")).strip().lower()
            if not child or not parent:
                continue
            edge = TextureGraphEdge(
                child=child,
                parent=parent,
                child_hash=hash_value(child),
                parent_hash=hash_value(parent),
                source_path=asset.path,
                source_rank=rank,
            )
            self._edges_by_child.setdefault(edge.child_hash, []).append(edge)

    def _build_issues(self) -> None:
        for child_hash, edges in self._edges_by_child.items():
            parents = {edge.parent_hash for edge in edges}
            if len(parents) > 1:
                selected = self._selected[child_hash]
                self._issues.append(
                    TextureGraphIssue(
                        TextureGraphIssueSeverity.WARNING,
                        "conflicting_parents",
                        f"Texture dictionary '{selected.child}' has conflicting parents; "
                        f"'{selected.parent}' wins by source precedence",
                        child_hash=child_hash,
                        parent_hash=selected.parent_hash,
                        source_paths=tuple(dict.fromkeys(edge.source_path for edge in edges)),
                    )
                )
        for edge in self._selected.values():
            if preferred_asset(self.cache, edge.parent_hash, GameFileType.YTD) is None:
                self._issues.append(
                    TextureGraphIssue(
                        TextureGraphIssueSeverity.WARNING,
                        "missing_parent_dictionary",
                        f"Parent texture dictionary '{edge.parent}' is not indexed",
                        child_hash=edge.child_hash,
                        parent_hash=edge.parent_hash,
                        source_paths=(edge.source_path,),
                    )
                )
        visited: set[int] = set()
        for start in self._selected:
            if start in visited:
                continue
            positions: dict[int, int] = {}
            path: list[int] = []
            current = start
            while current in self._selected and current not in visited:
                if current in positions:
                    cycle = path[positions[current] :]
                    names = [self._selected[value].child for value in cycle]
                    edge = self._selected[current]
                    self._issues.append(
                        TextureGraphIssue(
                            TextureGraphIssueSeverity.ERROR,
                            "parent_cycle",
                            f"Texture dictionary parent cycle: {' -> '.join([*names, names[0]])}",
                            child_hash=current,
                            parent_hash=edge.parent_hash,
                            source_paths=tuple(self._selected[value].source_path for value in cycle),
                        )
                    )
                    break
                positions[current] = len(path)
                path.append(current)
                current = self._selected[current].parent_hash
            visited.update(path)

    def _ensure_graph(self) -> None:
        if self._generation == self.cache._view_generation:
            return
        self._edges_by_child.clear()
        self._selected.clear()
        self._issues.clear()
        for asset in self._candidate_assets():
            self._load_asset_edges(asset)
        for child_hash, edges in self._edges_by_child.items():
            edges.sort(key=lambda edge: (edge.source_rank, edge.parent_hash))
            self._selected[child_hash] = edges[0]
        self._build_issues()
        self._generation = self.cache._view_generation

    def __len__(self) -> int:
        self._ensure_graph()
        return len(self._selected)

    @property
    def issues(self) -> tuple[TextureGraphIssue, ...]:
        self._ensure_graph()
        return tuple(self._issues)

    def edges_from(self, child: str | int) -> tuple[TextureGraphEdge, ...]:
        self._ensure_graph()
        return tuple(self._edges_by_child.get(hash_value(child), ()))

    def selected_edge(self, child: str | int) -> TextureGraphEdge | None:
        self._ensure_graph()
        return self._selected.get(hash_value(child))

    def parent_hash(self, child: str | int) -> int | None:
        edge = self.selected_edge(child)
        return edge.parent_hash if edge is not None else None

    def parent_map(self) -> dict[int, int]:
        self._ensure_graph()
        return {child_hash: edge.parent_hash for child_hash, edge in self._selected.items()}

    def iter_chain(self, child: str | int, *, max_depth: int = 64) -> Iterator[TextureGraphEdge]:
        self._ensure_graph()
        current = hash_value(child)
        seen: set[int] = set()
        for _ in range(max(0, int(max_depth))):
            if current in seen:
                return
            seen.add(current)
            edge = self._selected.get(current)
            if edge is None:
                return
            yield edge
            current = edge.parent_hash

    def descendants(self, parent: str | int) -> tuple[int, ...]:
        self._ensure_graph()
        target = hash_value(parent)
        descendants: set[int] = set()
        pending = [target]
        while pending:
            current = pending.pop()
            for child_hash, edge in self._selected.items():
                if (
                    edge.parent_hash != current
                    or child_hash == target
                    or child_hash in descendants
                ):
                    continue
                descendants.add(child_hash)
                pending.append(child_hash)
        return tuple(sorted(descendants))


__all__ = [
    "TextureDictionaryGraph",
    "TextureGraphEdge",
    "TextureGraphIssue",
    "TextureGraphIssueSeverity",
]
