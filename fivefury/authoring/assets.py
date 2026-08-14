from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Generic, TypeVar, cast

from ..gamefile import GameFile
from ..hashing import jenk_hash

AssetT = TypeVar("AssetT")


def canonical_asset_path(value: str | Path) -> str:
    normalized = str(value).strip().replace("\\", "/")
    if not normalized:
        raise ValueError("Asset paths cannot be empty")
    return str(PurePosixPath(normalized)).lower()


def asset_name(value: str | Path) -> str:
    return PurePosixPath(canonical_asset_path(value)).stem


@dataclass(slots=True)
class AssetRef(Generic[AssetT]):
    name: str
    asset_type: type[AssetT] | None = None
    path: str | None = None
    target: AssetT | None = None

    def __post_init__(self) -> None:
        self.name = asset_name(self.name)
        if self.path is not None:
            self.path = canonical_asset_path(self.path)
        if (
            self.target is not None
            and self.asset_type is not None
            and not isinstance(self.target, self.asset_type)
        ):
            raise TypeError(
                f"Expected {self.asset_type.__name__}, got {type(self.target).__name__}"
            )

    @property
    def hash(self) -> int:
        return int(jenk_hash(self.name))

    @property
    def resolved(self) -> bool:
        return self.target is not None

    def bind(self, target: AssetT) -> AssetT:
        if self.asset_type is not None and not isinstance(target, self.asset_type):
            raise TypeError(
                f"Expected {self.asset_type.__name__}, got {type(target).__name__}"
            )
        self.target = target
        return target

    def resolve(self, assets: AssetSet) -> AssetT | None:
        if self.target is not None:
            return self.target
        target = assets.resolve(self)
        if target is not None:
            self.target = target
        return target

    def require(self, assets: AssetSet) -> AssetT:
        target = self.resolve(assets)
        if target is None:
            expected = (
                f" ({self.asset_type.__name__})" if self.asset_type is not None else ""
            )
            raise KeyError(
                f"Unresolved asset reference: {self.path or self.name}{expected}"
            )
        return target


class AssetSet(MutableMapping[str, object]):
    def __init__(self) -> None:
        self._assets: dict[str, object] = {}

    def __getitem__(self, key: str) -> object:
        return self._assets[canonical_asset_path(key)]

    def __setitem__(self, key: str, value: object) -> None:
        path = canonical_asset_path(key)
        current = self._assets.get(path)
        if current is not None and current is not value:
            raise KeyError(f"Asset path is already registered: {path}")
        self._assets[path] = value

    def __delitem__(self, key: str) -> None:
        del self._assets[canonical_asset_path(key)]

    def __iter__(self) -> Iterator[str]:
        return iter(self._assets)

    def __len__(self) -> int:
        return len(self._assets)

    def replace(self, path: str | Path, asset: object) -> object:
        self._assets[canonical_asset_path(path)] = asset
        return asset

    @classmethod
    def from_directory(cls, directory: str | Path) -> AssetSet:
        root = Path(directory)
        if not root.is_dir():
            raise NotADirectoryError(root)
        assets = cls()
        for source in sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(root).as_posix().casefold(),
        ):
            assets.file(source, path=source.relative_to(root))
        return assets

    def file(
        self,
        source: str | Path,
        *,
        path: str | Path | None = None,
    ) -> GameFile:
        game_file = GameFile.from_path(source, path=path)
        self[game_file.path] = game_file
        return game_file

    def of_type(self, asset_type: type[AssetT]) -> tuple[AssetT, ...]:
        return tuple(
            cast(AssetT, target)
            for asset in self._assets.values()
            if isinstance((target := self._target(asset)), asset_type)
        )

    def resolve(self, reference: AssetRef[AssetT]) -> AssetT | None:
        if reference.path is not None:
            candidate = self._assets.get(reference.path)
            if candidate is not None:
                return self._check_type(reference, candidate)

        matches = [
            target
            for path, candidate in self._assets.items()
            if (target := self._target(candidate)) is not None
            if asset_name(path) == reference.name
            and (
                reference.asset_type is None
                or isinstance(target, reference.asset_type)
            )
        ]
        if len(matches) > 1:
            raise KeyError(f"Ambiguous asset reference: {reference.name}")
        return cast(AssetT, matches[0]) if matches else None

    def require(
        self, name: str, asset_type: type[AssetT], *, path: str | None = None
    ) -> AssetT:
        return AssetRef(name=name, path=path, asset_type=asset_type).require(self)

    @staticmethod
    def _check_type(reference: AssetRef[AssetT], candidate: object) -> AssetT:
        candidate = AssetSet._target(candidate)
        if reference.asset_type is not None and not isinstance(
            candidate, reference.asset_type
        ):
            raise TypeError(
                f"Asset {reference.path or reference.name} is {type(candidate).__name__}, "
                f"expected {reference.asset_type.__name__}"
            )
        return cast(AssetT, candidate)

    @staticmethod
    def _target(candidate: object) -> object:
        return candidate.parsed if isinstance(candidate, GameFile) else candidate


__all__ = ["AssetRef", "AssetSet", "asset_name", "canonical_asset_path"]
