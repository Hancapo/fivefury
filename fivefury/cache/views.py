from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator as AbcIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..common import hash_value
from ..gamefile import GameFileType, guess_game_file_type
from ..metahash import MetaHash
from ..rpf import RpfArchive, RpfFileEntry, _normalize_key
from .kinds import coerce_game_file_kind as _coerce_kind
from .paths import path_name as _path_name, path_stem as _path_stem, split_archive_asset_path as _split_archive_asset_path

if TYPE_CHECKING:
    from .core import GameFileCache

_FLAG_LOOSE = 1
_FLAG_RESOURCE = 2
_FLAG_ENCRYPTED = 4

class AssetRecord:
    __slots__ = ("_cache", "id")

    def __init__(self, cache: GameFileCache, asset_id: int) -> None:
        self._cache = cache
        self.id = int(asset_id)

    def __repr__(self) -> str:
        return (
            "AssetRecord("
            f"id={self.id}, path={self.path!r}, kind={self.kind.name}, size={self.size}, "
            f"stored_size={self.stored_size}, uncompressed_size={self.uncompressed_size})"
        )

    @classmethod
    def from_cache(cls, cache: GameFileCache, asset_id: int) -> AssetRecord:
        return cls(cache, asset_id)

    @property
    def path(self) -> str:
        return self._cache._index.get_path(self.id)

    @property
    def kind(self) -> GameFileType:
        stored = GameFileType(int(self._cache._index.get_kind(self.id)))
        return guess_game_file_type(self.path, stored)

    @property
    def size(self) -> int:
        return int(self._cache._index.get_size(self.id))

    @property
    def stored_size(self) -> int:
        return self.size

    @property
    def uncompressed_size(self) -> int:
        return int(self._cache._index.get_uncompressed_size(self.id))

    @property
    def entry(self) -> Optional[RpfFileEntry]:
        return self._cache._live_entries.get(self.id)

    @property
    def archive(self) -> Optional[RpfArchive]:
        return self._cache._live_archives.get(self.id)

    @property
    def loose_path(self) -> Optional[Path]:
        return self._cache._loose_path_for_id(self.id)

    @property
    def is_resource(self) -> bool:
        return self._cache._flag_is_set(self.id, _FLAG_RESOURCE)

    @property
    def is_encrypted(self) -> bool:
        return self._cache._flag_is_set(self.id, _FLAG_ENCRYPTED)

    @property
    def archive_encryption(self) -> int:
        return int(self._cache._index.get_archive_encryption(self.id))

    @property
    def name_hash(self) -> int:
        return int(self._cache._index.get_name_hash(self.id))

    @property
    def short_hash(self) -> int:
        return int(self._cache._index.get_short_hash(self.id))

    @property
    def short_name_hash(self) -> int:
        return self.short_hash

    @property
    def key(self) -> str:
        return self.path

    @property
    def name(self) -> str:
        return _path_name(self.path)

    @property
    def extension(self) -> str:
        name = self.name
        dot = name.rfind(".")
        return name[dot:].lower() if dot >= 0 else ""

    @property
    def stem(self) -> str:
        return _path_stem(self.path)

    @property
    def is_loose(self) -> bool:
        return self._cache._flag_is_set(self.id, _FLAG_LOOSE)

    @property
    def is_archive_entry(self) -> bool:
        return self.entry is not None and self.archive is not None

    @property
    def source_path(self) -> str:
        loose = self.loose_path
        if loose is not None:
            return str(loose)
        archive = self.archive
        if archive is not None and archive.source_path:
            return archive.source_path
        return self.path

    @property
    def archive_rel(self) -> str | None:
        split = _split_archive_asset_path(self.path)
        return split[0] if split is not None else None

    @property
    def entry_path(self) -> str | None:
        split = _split_archive_asset_path(self.path)
        if split is None or not split[1]:
            return None
        return split[1]


class _AssetRecordList(Sequence[AssetRecord]):
    __slots__ = ("_cache",)

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache

    def __len__(self) -> int:
        return self._cache.asset_count

    def __getitem__(self, index: int | slice) -> AssetRecord | list[AssetRecord]:
        if isinstance(index, slice):
            return [self._cache._record_from_id(i) for i in range(*index.indices(len(self)))]
        return self._cache._record_from_id(index)

    def __iter__(self) -> AbcIterator[AssetRecord]:
        for asset_id in range(len(self)):
            yield self._cache._record_from_id(asset_id)


class _AssetRecordMap(Mapping[str, AssetRecord]):
    __slots__ = ("_cache",)

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache

    def __len__(self) -> int:
        return self._cache.asset_count

    def __iter__(self) -> AbcIterator[str]:
        yield from self._cache.iter_paths()

    def __getitem__(self, key: str) -> AssetRecord:
        asset_id = self._cache._index.find_path_id(_normalize_key(key))
        if asset_id is None:
            raise KeyError(key)
        return self._cache._record_from_id(asset_id)

    def get(self, key: str | Path, default: AssetRecord | None = None) -> AssetRecord | None:
        asset_id = self._cache._index.find_path_id(_normalize_key(key))
        if asset_id is None:
            return default
        return self._cache._record_from_id(asset_id)


class _KindHashRecordMap(Mapping[int, AssetRecord]):
    __slots__ = ("_cache", "_kind", "_generation", "_hash_to_id")

    def __init__(self, cache: GameFileCache, kind: GameFileType) -> None:
        self._cache = cache
        self._kind = kind
        self._generation = -1
        self._hash_to_id: dict[int, int] = {}

    def _ensure_index(self) -> None:
        if self._generation == self._cache._view_generation:
            return
        self._hash_to_id = self._cache._index.kind_short_hash_map(int(self._kind))
        self._generation = self._cache._view_generation

    def __len__(self) -> int:
        self._ensure_index()
        return len(self._hash_to_id)

    def __iter__(self) -> AbcIterator[int]:
        self._ensure_index()
        yield from self._hash_to_id

    def __getitem__(self, key: int) -> AssetRecord:
        self._ensure_index()
        try:
            asset_id = self._hash_to_id[int(key)]
        except KeyError as exc:
            raise KeyError(key) from exc
        return self._cache._record_from_id(asset_id)

    def get(self, key: int, default: AssetRecord | None = None) -> AssetRecord | None:
        self._ensure_index()
        asset_id = self._hash_to_id.get(int(key))
        if asset_id is None:
            return default
        return self._cache._record_from_id(asset_id)


class _ArchetypeMap(Mapping[int, Any]):
    __slots__ = ("_cache", "_generation", "_hash_to_archetype")

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache
        self._generation = -1
        self._hash_to_archetype: dict[int, Any] = {}

    def _ensure_index(self) -> None:
        if self._generation == self._cache._view_generation:
            return
        hash_to_archetype: dict[int, Any] = {}
        for asset in self._cache.iter_assets(kind=GameFileType.YTYP):
            game_file = self._cache.get_file(asset)
            if game_file is None:
                continue
            parsed = game_file.parsed
            archetypes = getattr(parsed, "archetypes", None)
            if not isinstance(archetypes, list):
                continue
            for archetype in archetypes:
                name = getattr(archetype, "name", None)
                if name in (None, "", 0):
                    continue
                try:
                    name_hash = int(name)
                except Exception:
                    continue
                if name_hash == 0:
                    continue
                hash_to_archetype[name_hash] = archetype
        self._hash_to_archetype = hash_to_archetype
        self._generation = self._cache._view_generation

    def __len__(self) -> int:
        self._ensure_index()
        return len(self._hash_to_archetype)

    def __iter__(self) -> AbcIterator[int]:
        self._ensure_index()
        yield from self._hash_to_archetype

    def __getitem__(self, key: int) -> Any:
        self._ensure_index()
        try:
            return self._hash_to_archetype[int(key)]
        except KeyError as exc:
            raise KeyError(key) from exc

    def get(self, key: int | str | MetaHash, default: Any = None) -> Any:
        self._ensure_index()
        try:
            return self._hash_to_archetype[hash_value(key)]
        except KeyError:
            return default


class _TextureParentMap(Mapping[int, int]):
    __slots__ = ("_cache", "_generation", "_hash_to_parent")

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache
        self._generation = -1
        self._hash_to_parent: dict[int, int] = {}

    def _add_relation(self, child: str, parent: str, mapping: dict[int, int]) -> None:
        child_name = str(child).strip().lower()
        parent_name = str(parent).strip().lower()
        if not child_name or not parent_name:
            return
        mapping[hash_value(child_name)] = hash_value(parent_name)

    def _load_xml_relations(self, xml_text: str, mapping: dict[int, int]) -> None:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return
        for item in root.findall(".//txdRelationships/Item") + root.findall(".//txdRelationships/item"):
            parent = item.findtext("parent", default="").strip()
            child = item.findtext("child", default="").strip()
            self._add_relation(child, parent, mapping)

    def _ensure_index(self) -> None:
        if self._generation == self._cache._view_generation:
            return
        hash_to_parent: dict[int, int] = {}
        for asset in self._cache.iter_assets():
            if asset.name.lower() not in {"gtxd.meta", "vehicles.meta", "peds.meta", "peds.ymt"}:
                continue
            data = self._cache.read_bytes(asset, logical=True)
            if not data:
                continue
            text = data.decode("utf-8", errors="ignore")
            if "<" not in text:
                continue
            self._load_xml_relations(text, hash_to_parent)
        self._hash_to_parent = hash_to_parent
        self._generation = self._cache._view_generation

    def __len__(self) -> int:
        self._ensure_index()
        return len(self._hash_to_parent)

    def __iter__(self) -> AbcIterator[int]:
        self._ensure_index()
        yield from self._hash_to_parent

    def __getitem__(self, key: int) -> int:
        self._ensure_index()
        try:
            return self._hash_to_parent[int(key)]
        except KeyError as exc:
            raise KeyError(key) from exc

    def get(self, key: int | str | MetaHash, default: int | None = None) -> int | None:
        self._ensure_index()
        return self._hash_to_parent.get(hash_value(key), default)


class _KindCountsView(Mapping[GameFileType, int]):
    __slots__ = ("_cache", "_generation", "_counts")

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache
        self._generation = -1
        self._counts: dict[GameFileType, int] = {}

    def _ensure_index(self) -> None:
        if self._generation == self._cache._view_generation:
            return
        self._counts = {GameFileType(kind): count for kind, count in self._cache._index.kind_counts().items()}
        self._generation = self._cache._view_generation

    def __len__(self) -> int:
        self._ensure_index()
        return len(self._counts)

    def __iter__(self) -> AbcIterator[GameFileType]:
        self._ensure_index()
        yield from self._counts

    def __getitem__(self, key: GameFileType | str | int) -> int:
        self._ensure_index()
        kind = _coerce_kind(key)
        if kind is None:
            raise KeyError(key)
        try:
            return self._counts[kind]
        except KeyError as exc:
            raise KeyError(key) from exc

    def get(self, key: GameFileType | str | int, default: int | None = None) -> int | None:
        self._ensure_index()
        kind = _coerce_kind(key)
        if kind is None:
            return default
        return self._counts.get(kind, default)


@dataclass(slots=True)
class ScanStats:
    elapsed_seconds: float = 0.0
    used_index_cache: bool = False
    saved_index_cache: bool = False
    source_count: int = 0
    rpf_count: int = 0
    loose_count: int = 0
    asset_count: int = 0
    archive_workers: int = 0


__all__ = [
    "AssetRecord",
    "ScanStats",
    "_ArchetypeMap",
    "_AssetRecordList",
    "_AssetRecordMap",
    "_KindCountsView",
    "_KindHashRecordMap",
    "_TextureParentMap",
]
