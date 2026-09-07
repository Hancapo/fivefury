from __future__ import annotations

from collections import ChainMap
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from ...cut.resolution.runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)
from ...game_target import GameTarget
from ...gamefile import GameFileType
from ...metahash import MetaHash
from ..core import GameFileCache
from ..cutscene_preparation import (
    CutsceneResolutionPreparation,
    CutsceneResolutionPreparationCallback,
)
from ..registrations import AssetRegistration
from ..views import AssetRecord
from .queries import OverlayQueries

if TYPE_CHECKING:
    from ...cut.payloads import CutVehicleVariationPayload
    from ...vehiclemeta.appearance import ResolvedVehicleAppearance


class _OverlayAssets(Mapping[str, AssetRecord]):
    def __init__(self, overlay: GameFileOverlay) -> None:
        self.overlay = overlay

    def __iter__(self) -> Iterator[str]:
        return iter(dict.fromkeys(self.overlay.iter_paths()))

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __getitem__(self, path: str) -> AssetRecord:
        asset = self.overlay.find_path(path)
        if asset is None:
            raise KeyError(path)
        return asset


class _TransientCache(GameFileCache):
    def get_index_cache_path(self) -> None:
        return None

    def _index_cache_relative_path(self, root: Path) -> None:
        return None


class GameFileOverlay(OverlayQueries, _TransientCache):
    """Scoped loose/RPF assets with a borrowed installation fallback.

    Remount explicitly after changing export files. Closing the overlay releases
    only its owned loose cache, never the installation or its persistent indexes.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        fallback: GameFileCache | None = None,
        registrations: Sequence[AssetRegistration] = (),
        game: GameTarget | None = None,
        cancellation: CutsceneResolutionCancellation | None = None,
    ) -> None:
        if isinstance(fallback, GameFileOverlay):
            raise TypeError(
                "Use an installation cache, not another overlay, as fallback"
            )
        target = (
            fallback.game
            if fallback is not None and game is None
            else (game or GameTarget.GTA5)
        )
        if fallback is not None and target != fallback.game:
            raise ValueError(
                "Overlay and installation must target the same game edition"
            )
        super().__init__(game=target, use_index_cache=False)
        self._fallback = fallback
        self._loose = None
        self._source_signature = ()
        self._closed = False
        self.assets = _OverlayAssets(self)
        self.remount(root, registrations=registrations, cancellation=cancellation)

    @property
    def sources(self) -> tuple[GameFileCache, ...]:
        return tuple(
            source for source in (self._loose, self._fallback) if source is not None
        )

    def _sync_sources(self) -> None:
        if self._closed:
            raise ValueError("Asset overlay is closed")
        signature = tuple(
            (id(source), source._view_generation, source.asset_count)
            for source in self.sources
        )
        if signature != self._source_signature:
            self._source_signature = signature
            self._invalidate_views()

    def remount(
        self,
        root: str | Path,
        *,
        registrations: Sequence[AssetRegistration] = (),
        cancellation: CutsceneResolutionCancellation | None = None,
    ) -> None:
        if self._closed:
            raise ValueError("Asset overlay is closed")
        check_cutscene_resolution_cancelled(cancellation)
        path = Path(root).resolve()
        if not path.is_dir():
            raise NotADirectoryError(path)
        replacement = _TransientCache(
            path,
            game=self.game,
            use_index_cache=False,
            crypto=None if self._fallback is None else self._fallback.crypto,
        )
        try:
            replacement.scan(load_keys=False, use_index_cache=False)
            if replacement.scan_errors:
                raise ValueError(
                    f"Unable to index overlay archives: {replacement.scan_errors}"
                )
            for registration in registrations:
                check_cutscene_resolution_cancelled(cancellation)
                replacement.register_metadata(registration)
            check_cutscene_resolution_cancelled(cancellation)
        except BaseException:
            replacement.close()
            raise
        previous = self._loose
        self._loose = replacement
        self.root = path
        self._sync_sources()
        if previous is not None:
            previous.close()

    def close(self) -> None:
        if self._loose is not None:
            self._loose.close()
        self._invalidate_views()
        self._closed = True

    def resolve_vehicle_appearance(
        self,
        binding_or_model: Any,
        *,
        variation: CutVehicleVariationPayload | None = None,
    ) -> ResolvedVehicleAppearance:
        self._sync_sources()
        return super().resolve_vehicle_appearance(binding_or_model, variation=variation)

    @property
    def asset_count(self) -> int:
        return sum(source.asset_count for source in self.sources)

    @property
    def kind_counts(self) -> Mapping[GameFileType, int]:
        from collections import Counter

        counts = Counter()
        for source in self.sources:
            counts.update(source.kind_counts)
        return counts

    def prepare_cutscene_resolution(
        self,
        *,
        cancellation: CutsceneResolutionCancellation | None = None,
        progress: CutsceneResolutionPreparationCallback | None = None,
    ) -> CutsceneResolutionPreparation:
        self._sync_sources()
        indexes = []
        elapsed_ns = 0
        for source in self.sources:
            check_cutscene_resolution_cancelled(cancellation)
            prepared = source.prepare_cutscene_resolution(
                cancellation=cancellation, progress=progress
            )
            indexes.extend(prepared.indexes)
            elapsed_ns += prepared.elapsed_ns
        return CutsceneResolutionPreparation(tuple(indexes), elapsed_ns)

    @property
    def archetype_dict(self) -> Mapping[int, Any]:
        self._sync_sources()
        return ChainMap(*(source.archetype_dict for source in self.sources))

    def texture_dictionary_hashes_for_asset(
        self, query: Any
    ) -> tuple[int | MetaHash, ...]:
        asset = self._source_record(query)
        if asset is None:
            return ()
        for source in self.sources:
            matches = source.texture_dictionary_hashes_for_asset(asset)
            if matches:
                return matches
        return ()

    def scan(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise TypeError("Use remount() to replace an overlay's loose assets")

    def register_metadata(self, registration: AssetRegistration) -> NoReturn:
        raise TypeError("Pass registrations to the constructor or remount()")

    def register_archive(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise TypeError("Place archives in the loose root and remount()")
