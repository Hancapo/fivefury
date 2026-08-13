from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .._native import NativeTextureIndex
from ..common import hash_value
from ..gamefile import GameFileType
from ..ytd import Texture, TextureDescriptor, YtdCatalog, read_ytd_catalog
from .precedence import asset_source_rank

if TYPE_CHECKING:
    from .core import GameFileCache
    from .views import AssetRecord


@dataclass(frozen=True, slots=True)
class TextureCatalogEntry:
    descriptor: TextureDescriptor
    dictionary_path: str
    dictionary_name: str
    dictionary_hash: int

    @property
    def name(self) -> str:
        return self.descriptor.name

    @property
    def name_hash(self) -> int:
        return self.descriptor.name_hash


@dataclass(slots=True)
class TextureCatalog:
    cache: GameFileCache = field(repr=False)
    _generation: int = field(default=-1, init=False, repr=False)
    _dictionaries: dict[str, YtdCatalog] = field(default_factory=dict, init=False, repr=False)
    _dictionary_ids: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _entries: list[TextureCatalogEntry] = field(default_factory=list, init=False, repr=False)
    _index: NativeTextureIndex = field(default_factory=NativeTextureIndex, init=False, repr=False)
    _complete: bool = field(default=False, init=False, repr=False)
    errors: dict[str, str] = field(default_factory=dict, init=False)

    def _ensure_generation(self) -> None:
        generation = self.cache._view_generation
        if self._generation == generation:
            return
        self._dictionaries.clear()
        self._dictionary_ids.clear()
        self._entries.clear()
        self._index.clear()
        self.errors.clear()
        self._complete = False
        self._generation = generation

    def clear(self) -> None:
        self._generation = -1
        self._ensure_generation()

    def _coerce_dictionary_asset(self, query: Any) -> AssetRecord | None:
        return self.cache._coerce_asset(query, kind=GameFileType.YTD)

    def index_dictionary(self, query: Any) -> YtdCatalog | None:
        self._ensure_generation()
        asset = self._coerce_dictionary_asset(query)
        if asset is None:
            return None
        existing = self._dictionaries.get(asset.path)
        if existing is not None:
            return existing
        data = self.cache.read_bytes(asset, logical=False)
        if not data:
            self.errors[asset.path] = "Texture dictionary data is unavailable"
            return None
        try:
            catalog = read_ytd_catalog(data)
        except Exception as exc:
            self.errors[asset.path] = f"{type(exc).__name__}: {exc}"
            return None
        self._dictionaries[asset.path] = catalog
        dictionary_id = len(self._dictionary_ids)
        self._dictionary_ids[asset.path] = dictionary_id
        entries = [
            TextureCatalogEntry(
                descriptor=descriptor,
                dictionary_path=asset.path,
                dictionary_name=asset.stem,
                dictionary_hash=asset.short_hash,
            )
            for descriptor in catalog
        ]
        first_entry_id = self._index.add_many(
            [entry.name_hash for entry in entries],
            dictionary_id,
        )
        if first_entry_id != len(self._entries):
            raise RuntimeError("Native texture index entry order diverged from its catalog")
        self._entries.extend(entries)
        return catalog

    def build(self, dictionaries: Any | None = None) -> TextureCatalog:
        self._ensure_generation()
        if dictionaries is None:
            assets = self.cache.iter_assets(kind=GameFileType.YTD)
        elif isinstance(dictionaries, (str, bytes)) or not hasattr(dictionaries, "__iter__"):
            assets = (dictionaries,)
        else:
            assets = dictionaries
        for asset in assets:
            self.index_dictionary(asset)
        if dictionaries is None:
            self._complete = True
        return self

    def dictionary(self, query: Any) -> YtdCatalog | None:
        return self.index_dictionary(query)

    def iter_entries(self, dictionary: Any | None = None) -> Iterator[TextureCatalogEntry]:
        self._ensure_generation()
        if dictionary is not None:
            asset = self._coerce_dictionary_asset(dictionary)
            if asset is None:
                return
            self.index_dictionary(asset)
            dictionary_id = self._dictionary_ids[asset.path]
            for entry_id in self._index.find_dictionary(dictionary_id):
                yield self._entries[entry_id]
            return
        yield from self._entries

    def find(self, value: str | int, *, dictionary: Any | None = None) -> list[TextureCatalogEntry]:
        self._ensure_generation()
        target_hash = hash_value(value)
        if dictionary is not None:
            return [entry for entry in self.iter_entries(dictionary) if entry.name_hash == target_hash]
        if not self._complete:
            self.build()
        matches = [self._entries[entry_id] for entry_id in self._index.find_texture(target_hash)]
        matches.sort(
            key=lambda entry: asset_source_rank(
                self.cache.get_asset(entry.dictionary_path, kind=GameFileType.YTD)
            )
        )
        return matches

    def load(self, entry: TextureCatalogEntry) -> Texture | None:
        ytd = self.cache._coerce_ytd(entry.dictionary_path)
        return ytd.get_texture(entry.name) if ytd is not None else None


__all__ = ["TextureCatalog", "TextureCatalogEntry"]
