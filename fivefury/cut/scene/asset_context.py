from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from ...cache.precedence import asset_source_rank
from ...gamefile import GameFile, GameFileType, guess_game_file_type
from ...metahash import MetaHash

if TYPE_CHECKING:
    from ...authoring import BuildContext


def cut_asset_reference_hash(value: str | int) -> int:
    if isinstance(value, int):
        return int(value) & 0xFFFFFFFF
    text = str(value).strip().replace("\\", "/")
    if text.lower().startswith("0x"):
        try:
            return int(text, 16) & 0xFFFFFFFF
        except ValueError:
            pass
    return MetaHash(PurePosixPath(text).stem.casefold()).uint


@dataclass(frozen=True, slots=True)
class CutContextAsset:
    path: str
    kind: GameFileType
    _value: object | None = None
    _loader: Callable[[], object | None] | None = None
    source_rank: tuple[int, str] = (-1, "")

    @property
    def stem(self) -> str:
        return PurePosixPath(self.path.replace("\\", "/")).stem.casefold()

    @property
    def short_hash(self) -> int:
        return MetaHash(self.stem).uint

    def load(self) -> object | None:
        return self._loader() if self._loader is not None else self._value


class CutAssetContext:
    def __init__(self, context: BuildContext) -> None:
        self.context = context
        self._explicit = tuple(self._explicit_assets())
        self._cache_assets: dict[GameFileType, tuple[CutContextAsset, ...]] = {}

    def _explicit_assets(self) -> Iterator[CutContextAsset]:
        for path, value in self.context.assets.items():
            if isinstance(value, GameFile):
                yield CutContextAsset(
                    path,
                    value.kind,
                    value.parsed,
                    source_rank=(-1, path.casefold()),
                )
            else:
                yield CutContextAsset(
                    path,
                    guess_game_file_type(path),
                    value,
                    source_rank=(-1, path.casefold()),
                )

    @staticmethod
    def _contains_drawable(asset: CutContextAsset, reference: str | int) -> bool:
        if asset.kind is not GameFileType.YDD:
            return False
        value = asset.load()
        finder = getattr(value, "get", None)
        return callable(finder) and finder(reference) is not None

    def _matches(self, asset: CutContextAsset, reference: str | int) -> bool:
        return asset.short_hash == cut_asset_reference_hash(reference) or self._contains_drawable(
            asset, reference
        )

    def find(
        self,
        reference: str | int,
        kinds: tuple[GameFileType, ...],
    ) -> CutContextAsset | None:
        for kind in kinds:
            for asset in self._explicit:
                if asset.kind is kind and self._matches(asset, reference):
                    return asset
        cache = self.context.cache
        if cache is None:
            return None
        reference_hash = cut_asset_reference_hash(reference)
        for kind in kinds:
            matches = cache.find_hash(reference_hash, kind=kind)
            if not matches:
                continue
            record = min(matches, key=asset_source_rank)
            return CutContextAsset(
                record.path,
                kind,
                _loader=lambda record=record: self._load_cache_asset(record),
                source_rank=asset_source_rank(record),
            )
        return None

    def iter_kind(self, kind: GameFileType) -> Iterator[CutContextAsset]:
        explicit_paths: set[str] = set()
        for asset in self._explicit:
            if asset.kind is kind:
                explicit_paths.add(asset.path.casefold())
                yield asset
        for asset in self._cached_kind(kind):
            if asset.path.casefold() not in explicit_paths:
                yield asset

    def _cached_kind(self, kind: GameFileType) -> tuple[CutContextAsset, ...]:
        if kind in self._cache_assets:
            return self._cache_assets[kind]
        cache = self.context.cache
        if cache is None:
            result: tuple[CutContextAsset, ...] = ()
        else:
            result = tuple(
                sorted(
                    (
                        CutContextAsset(
                            record.path,
                            kind,
                            _loader=lambda record=record: self._load_cache_asset(
                                record
                            ),
                            source_rank=asset_source_rank(record),
                        )
                        for record in cache.iter_assets(kind)
                    ),
                    key=lambda asset: asset.source_rank,
                )
            )
        self._cache_assets[kind] = result
        return result

    def _load_cache_asset(self, record: Any) -> object | None:
        game_file = self.context.cache.load_asset(record)
        return game_file.parsed if game_file is not None else None


__all__ = ["CutAssetContext", "CutContextAsset", "cut_asset_reference_hash"]
