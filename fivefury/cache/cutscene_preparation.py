from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ..authoring import Diagnostic, DiagnosticSeverity
from ..gamefile import GameFileType

if TYPE_CHECKING:
    from ..cut.resolution.runtime import CutsceneResolutionCancellation
    from .core import GameFileCache


class CutsceneResolutionIndex(StrEnum):
    ASSET_TEXTURES = "asset_textures"
    TEXTURE_PARENTS = "texture_parents"
    VEHICLE_APPEARANCES = "vehicle_appearances"
    REL_SOUNDS = "rel_sounds"
    PED_INIT = "ped_init"


class CutsceneIndexPreparationStatus(StrEnum):
    READY = "ready"
    LOADED = "loaded"
    REBUILT = "rebuilt"


@dataclass(frozen=True, slots=True)
class CutsceneIndexPreparation:
    index: CutsceneResolutionIndex
    status: CutsceneIndexPreparationStatus
    elapsed_ns: int
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_ns / 1_000_000_000.0


@dataclass(frozen=True, slots=True)
class CutsceneResolutionPreparation:
    indexes: tuple[CutsceneIndexPreparation, ...]
    elapsed_ns: int

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_ns / 1_000_000_000.0

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        return tuple(
            diagnostic
            for index in self.indexes
            for diagnostic in index.diagnostics
        )


@dataclass(frozen=True, slots=True)
class CutsceneResolutionPreparationProgress:
    index: CutsceneResolutionIndex
    completed: int
    total: int
    index_completed: int
    index_total: int
    asset: str | None = None

    @property
    def fraction(self) -> float:
        return self.completed / self.total if self.total else 1.0


CutsceneResolutionPreparationCallback = Callable[
    [CutsceneResolutionPreparationProgress],
    None,
]


def _diagnostics_for_rel(cache: GameFileCache) -> tuple[Diagnostic, ...]:
    return tuple(
        Diagnostic(
            code="cut.preparation.rel.unreadable",
            message=error,
            severity=DiagnosticSeverity.WARNING,
        )
        for error in cache.rel_sound_index_errors
    )


def _prepare_asset_textures(
    cache: GameFileCache,
    cancellation: CutsceneResolutionCancellation | None,
    asset_progress: Callable[[str], None],
) -> tuple[CutsceneIndexPreparationStatus, tuple[Diagnostic, ...]]:
    from .views import _ArchetypeMap

    if cache._archetype_view is None:
        cache._archetype_view = _ArchetypeMap(cache)
    return (
        cache._archetype_view.prepare_texture_index(
            cancellation,
            asset_progress=asset_progress,
        ),
        (),
    )


def _prepare_texture_parents(
    cache: GameFileCache,
    cancellation: CutsceneResolutionCancellation | None,
    asset_progress: Callable[[str], None],
) -> tuple[CutsceneIndexPreparationStatus, tuple[Diagnostic, ...]]:
    from .views import _TextureParentMap

    if cache._texture_parent_view is None:
        cache._texture_parent_view = _TextureParentMap(cache)
    return (
        cache._texture_parent_view.prepare(
            cancellation,
            asset_progress=asset_progress,
        ),
        (),
    )


def _prepare_rel_sounds(
    cache: GameFileCache,
    cancellation: CutsceneResolutionCancellation | None,
    asset_progress: Callable[[str], None] | None = None,
) -> tuple[CutsceneIndexPreparationStatus, tuple[Diagnostic, ...]]:
    from ..cut.resolution.runtime import check_cutscene_resolution_cancelled
    from ..rel import RelFile, RelSoundIndex
    from .rel_sound_index import load_rel_sound_index, save_rel_sound_index

    assets = tuple(cache.iter_assets(GameFileType.REL))
    if (
        cache._rel_sound_index is not None
        and cache._rel_sound_asset_count == len(assets)
    ):
        return CutsceneIndexPreparationStatus.READY, _diagnostics_for_rel(cache)
    cached = load_rel_sound_index(cache.get_index_cache_path())
    if cached is not None:
        cache._rel_sound_index, cache._rel_sound_index_errors = cached
        cache._rel_sound_asset_count = len(assets)
        return CutsceneIndexPreparationStatus.LOADED, _diagnostics_for_rel(cache)
    rels = []
    errors: list[str] = []
    for asset in assets:
        check_cutscene_resolution_cancelled(cancellation)
        if asset_progress is not None:
            asset_progress(asset.path)
        try:
            game_file = cache.load_asset(asset)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{asset.path}: {type(exc).__name__}: {exc}")
            continue
        if game_file is None or not isinstance(game_file.parsed, RelFile):
            errors.append(asset.path)
            continue
        rels.append(game_file.parsed)
    cache._rel_sound_index = RelSoundIndex(rels)
    cache._rel_sound_asset_count = len(assets)
    cache._rel_sound_index_errors = tuple(errors)
    save_rel_sound_index(
        cache.get_index_cache_path(),
        cache._rel_sound_index,
        cache._rel_sound_index_errors,
    )
    return CutsceneIndexPreparationStatus.REBUILT, _diagnostics_for_rel(cache)


def _prepare_ped_init(
    cache: GameFileCache,
    cancellation: CutsceneResolutionCancellation | None,
    asset_progress: Callable[[str], None] | None = None,
) -> tuple[CutsceneIndexPreparationStatus, tuple[Diagnostic, ...]]:
    from ..cut.resolution.runtime import check_cutscene_resolution_cancelled
    from .ped_index import load_ped_init_index, save_ped_init_index
    from .precedence import asset_source_rank

    if cache._ped_init_asset_index is not None:
        return CutsceneIndexPreparationStatus.READY, ()
    cached = load_ped_init_index(cache.get_index_cache_path())
    if cached is not None:
        cache._ped_init_asset_index = cached
        return CutsceneIndexPreparationStatus.LOADED, ()

    diagnostics: list[Diagnostic] = []
    indexed: dict[int, tuple[int, list[int]]] = {}
    for asset in sorted(
        cache.find_assets("peds.ymt", kind=GameFileType.YMT),
        key=asset_source_rank,
    ):
        check_cutscene_resolution_cancelled(cancellation)
        if asset_progress is not None:
            asset_progress(asset.path)
        try:
            game_file = cache.load_asset(asset)
        except (OSError, ValueError) as exc:
            diagnostics.append(
                Diagnostic(
                    code="cut.preparation.ped.unreadable",
                    message=str(exc),
                    severity=DiagnosticSeverity.WARNING,
                    asset=asset.path,
                )
            )
            continue
        metadata = getattr(getattr(game_file, "parsed", None), "ped_metadata", None)
        if metadata is None:
            continue
        tier = asset_source_rank(asset)[0]
        for item in metadata.init_datas:
            model_hash = int(getattr(item.name, "uint", 0))
            if not model_hash:
                continue
            current = indexed.get(model_hash)
            if current is None or tier < current[0]:
                indexed[model_hash] = (tier, [asset.id])
            elif tier == current[0] and asset.id not in current[1]:
                current[1].append(asset.id)
    values = {
        model_hash: tuple(asset_ids)
        for model_hash, (_tier, asset_ids) in indexed.items()
    }
    save_ped_init_index(cache.get_index_cache_path(), values)
    cache._ped_init_asset_index = values
    return CutsceneIndexPreparationStatus.REBUILT, tuple(diagnostics)


def _prepare_index(
    index: CutsceneResolutionIndex,
    operation: Callable[[], tuple[CutsceneIndexPreparationStatus, tuple[Diagnostic, ...]]],
) -> CutsceneIndexPreparation:
    started_ns = time.perf_counter_ns()
    status, diagnostics = operation()
    return CutsceneIndexPreparation(
        index=index,
        status=status,
        elapsed_ns=time.perf_counter_ns() - started_ns,
        diagnostics=diagnostics,
    )


def _index_work(cache: GameFileCache) -> dict[CutsceneResolutionIndex, int]:
    return {
        CutsceneResolutionIndex.ASSET_TEXTURES: sum(
            1 for _ in cache.iter_assets(GameFileType.YTYP)
        ),
        CutsceneResolutionIndex.TEXTURE_PARENTS: cache.texture_graph.source_count,
        CutsceneResolutionIndex.VEHICLE_APPEARANCES: sum(
            1
            for kind in (GameFileType.CAR_VARIATIONS, GameFileType.CAR_COLS)
            for _ in cache.iter_assets(kind)
        ),
        CutsceneResolutionIndex.REL_SOUNDS: sum(
            1 for _ in cache.iter_assets(GameFileType.REL)
        ),
        CutsceneResolutionIndex.PED_INIT: len(
            cache.find_assets("peds.ymt", kind=GameFileType.YMT)
        ),
    }


def prepare_cutscene_resolution(
    cache: GameFileCache,
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
    progress: CutsceneResolutionPreparationCallback | None = None,
) -> CutsceneResolutionPreparation:
    from ..cut.resolution.runtime import check_cutscene_resolution_cancelled
    from .vehicle_appearance import prepare_vehicle_appearance_index

    with cache._cutscene_preparation_condition:
        while cache._cutscene_preparation_active:
            cache._cutscene_preparation_condition.wait(timeout=0.05)
            check_cutscene_resolution_cancelled(cancellation)
        cached = cache._cutscene_preparation_result
        if (
            cached is not None
            and cache._cutscene_preparation_generation == cache._view_generation
        ):
            return cached
        cache._cutscene_preparation_active = True

    started_ns = time.perf_counter_ns()
    indexes: list[CutsceneIndexPreparation] = []
    operations = (
        (
            CutsceneResolutionIndex.ASSET_TEXTURES,
            lambda notify: _prepare_asset_textures(cache, cancellation, notify),
        ),
        (
            CutsceneResolutionIndex.TEXTURE_PARENTS,
            lambda notify: _prepare_texture_parents(cache, cancellation, notify),
        ),
        (
            CutsceneResolutionIndex.VEHICLE_APPEARANCES,
            lambda notify: prepare_vehicle_appearance_index(
                cache,
                cancellation=cancellation,
                asset_progress=notify,
            ),
        ),
        (
            CutsceneResolutionIndex.REL_SOUNDS,
            lambda notify: _prepare_rel_sounds(cache, cancellation, notify),
        ),
        (
            CutsceneResolutionIndex.PED_INIT,
            lambda notify: _prepare_ped_init(cache, cancellation, notify),
        ),
    )
    try:
        work = _index_work(cache)
        total = sum(max(1, value) for value in work.values())
        completed = 0
        for index, operation in operations:
            check_cutscene_resolution_cancelled(cancellation)
            index_total = max(1, work[index])
            index_completed = 0

            def asset_progress(
                asset: str,
                *,
                active_index: CutsceneResolutionIndex = index,
                base_completed: int = completed,
                active_total: int = index_total,
            ) -> None:
                nonlocal index_completed
                index_completed += 1
                if progress is not None:
                    progress(
                        CutsceneResolutionPreparationProgress(
                            index=active_index,
                            completed=base_completed + index_completed,
                            total=total,
                            index_completed=index_completed,
                            index_total=active_total,
                            asset=asset,
                        )
                    )

            indexes.append(
                _prepare_index(
                    index,
                    lambda operation=operation: operation(asset_progress),
                )
            )
            if index_completed < index_total and progress is not None:
                progress(
                    CutsceneResolutionPreparationProgress(
                        index=index,
                        completed=completed + index_total,
                        total=total,
                        index_completed=index_total,
                        index_total=index_total,
                    )
                )
            completed += index_total
        result = CutsceneResolutionPreparation(
            indexes=tuple(indexes),
            elapsed_ns=time.perf_counter_ns() - started_ns,
        )
        with cache._cutscene_preparation_condition:
            cache._cutscene_preparation_result = result
            cache._cutscene_preparation_generation = cache._view_generation
        return result
    finally:
        with cache._cutscene_preparation_condition:
            cache._cutscene_preparation_active = False
            cache._cutscene_preparation_condition.notify_all()


__all__ = [
    "CutsceneIndexPreparation",
    "CutsceneIndexPreparationStatus",
    "CutsceneResolutionIndex",
    "CutsceneResolutionPreparation",
    "CutsceneResolutionPreparationCallback",
    "CutsceneResolutionPreparationProgress",
    "prepare_cutscene_resolution",
]
