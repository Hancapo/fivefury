from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...asset_source import AssetSourceTier
from ...gamefile import GameFile, GameFileType
from ...metahash import MetaHash
from ...rpf import RpfEntry
from ..precedence import asset_source_rank
from ..views import AssetRecord

if TYPE_CHECKING:
    from ..core import GameFileCache

_Kind = GameFileType | str | int | None
_Query = str | Path | int | MetaHash


class OverlayQueries:
    """Route indexed queries without copying or merging source indexes."""

    def _wrap(self, source: GameFileCache, record: AssetRecord) -> AssetRecord:
        offset = 0
        for layer, cache in enumerate(self.sources):
            if cache is source:
                result = AssetRecord(cache, record.id + offset)
                result._storage_id = record.id
                result.source_priority = layer * 4 + asset_source_rank(record)[0]
                result._source_tier = (
                    AssetSourceTier.OVERLAY if layer == 0 else record.source_tier
                )
                return result
            offset += cache.asset_count
        raise ValueError("Asset does not belong to the active overlay")

    def _record_from_id(self, asset_id: int) -> AssetRecord:
        self._sync_sources()
        remaining = asset_id
        for source in self.sources:
            if 0 <= remaining < source.asset_count:
                return self._wrap(source, source._record_from_id(remaining))
            remaining -= source.asset_count
        raise IndexError(asset_id)

    def _query_layers(
        self, method: str, *args: Any, limit: int | None = None, **kwargs: Any
    ) -> list[AssetRecord]:
        self._sync_sources()
        records = [
            self._wrap(source, record)
            for source in self.sources
            for record in getattr(source, method)(*args, **kwargs)
        ]
        records.sort(key=asset_source_rank)
        return records if limit is None else records[:limit]

    def iter_assets(self, kind: _Kind = None) -> Iterator[AssetRecord]:
        return iter(self._query_layers("iter_assets", kind))

    def iter_paths(self, kind: _Kind = None) -> Iterator[str]:
        return (asset.path for asset in self.iter_assets(kind))

    def find_path(self, path: str | Path, *, kind: _Kind = None) -> AssetRecord | None:
        self._sync_sources()
        for source in self.sources:
            record = source.find_path(path, kind=kind)
            if record is not None:
                return self._wrap(source, record)
        return None

    def find_hash(
        self,
        value: int | MetaHash | str,
        *,
        kind: _Kind = None,
        limit: int | None = None,
    ) -> list[AssetRecord]:
        return self._query_layers("find_hash", value, kind=kind, limit=limit)

    def find_hashes(
        self, values: Sequence[int | MetaHash], *, kind: _Kind = None
    ) -> dict[int, list[AssetRecord]]:
        self._sync_sources()
        hashes = tuple(dict.fromkeys(int(value) for value in values))
        result = {value: [] for value in hashes}
        for source in self.sources:
            for value, records in source.find_hashes(hashes, kind=kind).items():
                result[value].extend(self._wrap(source, record) for record in records)
        for records in result.values():
            records.sort(key=asset_source_rank)
        return result

    def find_name(
        self,
        name: str | Path,
        *,
        kind: _Kind = None,
        exact: bool = True,
        limit: int | None = None,
    ) -> list[AssetRecord]:
        return self._query_layers(
            "find_name", name, kind=kind, exact=exact, limit=limit
        )

    def find_assets(
        self,
        query: _Query,
        *,
        kind: _Kind = None,
        exact: bool = True,
        limit: int | None = None,
    ) -> list[AssetRecord]:
        return self._query_layers(
            "find_assets", query, kind=kind, exact=exact, limit=limit
        )

    def find_container_assets(
        self, container: str, *, kind: _Kind = None, include_prefixed: bool = False
    ) -> list[AssetRecord]:
        return self._query_layers(
            "find_container_assets",
            container,
            kind=kind,
            include_prefixed=include_prefixed,
        )

    def find_stem_prefix(
        self, prefix: str, *, kind: GameFileType | str | int
    ) -> list[AssetRecord]:
        return self._query_layers("find_stem_prefix", prefix, kind=kind)

    def _source_record(self, query: _Query | AssetRecord) -> AssetRecord | None:
        self._sync_sources()
        asset = query if isinstance(query, AssetRecord) else self.get_asset(query)
        if asset is None:
            return None
        if not any(asset._cache is source for source in self.sources):
            raise ValueError("Asset belongs to a closed or different overlay mount")
        return asset._cache._record_from_id(asset._storage_id)

    def get_file(self, query: _Query | AssetRecord) -> GameFile | None:
        asset = self._source_record(query)
        return None if asset is None else asset._cache.get_file(asset)

    def read_bytes(
        self, query: _Query | AssetRecord, *, logical: bool = True
    ) -> bytes | None:
        asset = self._source_record(query)
        return (
            None if asset is None else asset._cache.read_bytes(asset, logical=logical)
        )

    def get_entry(self, query: _Query | AssetRecord) -> RpfEntry | None:
        asset = self._source_record(query)
        return None if asset is None else asset._cache.get_entry(asset)

    def _get_entry_for_asset(self, asset: AssetRecord) -> RpfEntry | None:
        return self.get_entry(asset)

    def get_kind_dict(
        self, kind: GameFileType | str | int
    ) -> Mapping[int, AssetRecord]:
        return {
            record.short_hash: record
            for record in reversed(self._query_layers("iter_assets", kind))
        }
