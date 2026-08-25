from __future__ import annotations

from collections.abc import Iterator as AbcIterator
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..common import hash_value
from ..gamefile import GameFileType
from ..metahash import MetaHash
from ..rpf import RpfArchive, RpfFileEntry
from ..rpf.utils import _normalize_key
from .archetype_index import (
    load_asset_texture_index,
    load_texture_parent_index,
    save_asset_texture_index,
    save_texture_parent_index,
)
from .kinds import coerce_game_file_kind as _coerce_kind
from .paths import path_name as _path_name
from .paths import path_stem as _path_stem
from .paths import split_archive_asset_path as _split_archive_asset_path

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
        return GameFileType(int(self._cache._index.get_kind(self.id)))

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
    def entry(self) -> RpfFileEntry | None:
        return self._cache._live_entries.get(self.id)

    @property
    def archive(self) -> RpfArchive | None:
        return self._cache._live_archives.get(self.id)

    @property
    def loose_path(self) -> Path | None:
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
    __slots__ = ("_cache", "_generation", "_hash_to_id", "_kind")

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
    __slots__ = (
        "_asset_hash_to_archetypes",
        "_asset_hash_to_textures",
        "_cache",
        "_generation",
        "_hash_to_archetype",
        "_texture_generation",
    )

    def __init__(self, cache: GameFileCache) -> None:
        self._cache = cache
        self._generation = -1
        self._hash_to_archetype: dict[int, Any] = {}
        self._asset_hash_to_archetypes: dict[int, tuple[Any, ...]] = {}
        self._asset_hash_to_textures: Mapping[int, tuple[int, ...]] = {}
        self._texture_generation = -1

    @staticmethod
    def _hash_field(value: Any) -> int:
        try:
            return int(value or 0) & 0xFFFFFFFF
        except (TypeError, ValueError, OverflowError):
            return 0

    def _build_relationship_indexes(self) -> None:
        archetypes: dict[int, list[Any]] = {}
        textures: dict[int, set[int]] = {}
        for archetype in self._hash_to_archetype.values():
            texture_hash = self._hash_field(
                getattr(archetype, "texture_dictionary", None)
            )
            keys = {
                self._hash_field(getattr(archetype, "name", None)),
                self._hash_field(getattr(archetype, "asset_name", None)),
            }
            keys.discard(0)
            for key in keys:
                archetypes.setdefault(key, []).append(archetype)
                if texture_hash:
                    textures.setdefault(key, set()).add(texture_hash)
        self._asset_hash_to_archetypes = {
            key: tuple(values) for key, values in archetypes.items()
        }
        self._asset_hash_to_textures = {
            key: tuple(sorted(values)) for key, values in textures.items()
        }
        self._texture_generation = self._cache._view_generation

    def _load_texture_index(self) -> bool:
        values = load_asset_texture_index(self._cache.get_index_cache_path())
        if values is None:
            return False
        self._asset_hash_to_textures = values
        self._texture_generation = self._cache._view_generation
        return True

    def _save_texture_index(self) -> None:
        try:
            save_asset_texture_index(
                self._cache.get_index_cache_path(),
                self._asset_hash_to_textures,
            )
        except OSError:
            pass

    def _ensure_index(
        self,
        cancellation: Any | None = None,
        asset_progress: Any | None = None,
    ) -> None:
        if self._generation == self._cache._view_generation:
            return
        from ..cut.resolution.runtime import check_cutscene_resolution_cancelled

        hash_to_archetype: dict[int, Any] = {}
        for asset in self._cache.iter_assets(kind=GameFileType.YTYP):
            check_cutscene_resolution_cancelled(cancellation)
            if asset_progress is not None:
                asset_progress(asset.path)
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
                except (TypeError, ValueError, OverflowError):
                    continue
                if name_hash == 0:
                    continue
                hash_to_archetype[name_hash] = archetype
        self._hash_to_archetype = hash_to_archetype
        self._generation = self._cache._view_generation
        self._build_relationship_indexes()
        self._save_texture_index()

    def _build_texture_index(
        self,
        cancellation: Any | None = None,
        asset_progress: Any | None = None,
    ) -> None:
        from .archetype_relationships import build_asset_texture_relationships

        self._asset_hash_to_textures = build_asset_texture_relationships(
            self._cache,
            cancellation=cancellation,
            progress=asset_progress,
        )
        self._texture_generation = self._cache._view_generation
        self._save_texture_index()

    def _ensure_texture_index(self, cancellation: Any | None = None) -> None:
        if self._texture_generation == self._cache._view_generation:
            return
        if self._load_texture_index():
            return
        self._build_texture_index(cancellation)

    def prepare_texture_index(
        self,
        cancellation: Any | None = None,
        *,
        asset_progress: Any | None = None,
    ) -> Any:
        from .cutscene_preparation import CutsceneIndexPreparationStatus

        if self._texture_generation == self._cache._view_generation:
            return CutsceneIndexPreparationStatus.READY
        if self._load_texture_index():
            return CutsceneIndexPreparationStatus.LOADED
        self._build_texture_index(cancellation, asset_progress)
        return CutsceneIndexPreparationStatus.REBUILT

    def for_asset_hashes(self, values: set[int]) -> tuple[Any, ...]:
        self._ensure_index()
        result: list[Any] = []
        seen: set[int] = set()
        for value in values:
            for archetype in self._asset_hash_to_archetypes.get(int(value), ()):
                identity = id(archetype)
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(archetype)
        return tuple(result)

    def texture_dictionaries_for_asset_hashes(
        self,
        values: set[int],
    ) -> tuple[int, ...]:
        self._ensure_texture_index()
        return tuple(
            dict.fromkeys(
                texture_hash
                for value in values
                for texture_hash in self._asset_hash_to_textures.get(int(value), ())
            )
        )

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

    def _ensure_index(self) -> None:
        if self._generation == self._cache._view_generation:
            return
        cached = load_texture_parent_index(self._cache.get_index_cache_path())
        if cached is not None:
            self._hash_to_parent = cached
            self._generation = self._cache._view_generation
            return
        self._hash_to_parent = self._cache.texture_graph.parent_map()
        try:
            save_texture_parent_index(
                self._cache.get_index_cache_path(),
                self._hash_to_parent,
            )
        except OSError:
            pass
        self._generation = self._cache._view_generation

    def prepare(
        self,
        cancellation: Any | None = None,
        *,
        asset_progress: Any | None = None,
    ) -> Any:
        from .cutscene_preparation import CutsceneIndexPreparationStatus

        if self._generation == self._cache._view_generation:
            return CutsceneIndexPreparationStatus.READY
        cached = load_texture_parent_index(self._cache.get_index_cache_path())
        if cached is not None:
            self._hash_to_parent = cached
            self._generation = self._cache._view_generation
            return CutsceneIndexPreparationStatus.LOADED
        self._hash_to_parent = self._cache.texture_graph.parent_map(
            cancellation=cancellation,
            asset_progress=asset_progress,
        )
        try:
            save_texture_parent_index(
                self._cache.get_index_cache_path(),
                self._hash_to_parent,
            )
        except OSError:
            pass
        self._generation = self._cache._view_generation
        return CutsceneIndexPreparationStatus.REBUILT

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
    __slots__ = ("_cache", "_counts", "_generation")

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
