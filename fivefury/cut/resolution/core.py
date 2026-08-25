from __future__ import annotations

import time
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from ...gamefile import GameFileType
from ..audio_references import (
    cut_audio_container_hints,
    cut_audio_references,
    cut_event_references,
)
from ..scene import read_cut_scene
from .animations import _resolve_ycds
from .audio import _resolve_audio
from .bindings import (
    _normalize_initial_ped_variations,
    _resolve_binding_texture_chains,
    _resolve_bindings,
    _resolve_ped_components,
)
from .common import _source_rank
from .expressions import _resolve_ped_expression_resources
from .models import CutsceneAssetBundle, CutsceneResolveIssue
from .runtime import (
    CutsceneResolutionCancellation,
    CutsceneResolutionSpan,
    CutsceneResolutionTrace,
    check_cutscene_resolution_cancelled,
)
from .subtitles import _resolve_subtitle_dictionaries
from .vehicles import (
    _resolve_vehicle_appearances,
    _resolve_vehicle_high_detail_models,
)

if TYPE_CHECKING:
    from ...cache import GameFileCache


def _run_stage(
    trace: CutsceneResolutionTrace,
    name: str,
    operation: Any,
) -> tuple[Any, list[CutsceneResolveIssue], CutsceneResolutionSpan]:
    issues: list[CutsceneResolveIssue] = []
    started_ns = time.perf_counter_ns()
    value = operation(issues)
    return (
        value,
        issues,
        CutsceneResolutionSpan(
            name=name,
            started_ns=started_ns - trace.started_ns,
            elapsed_ns=time.perf_counter_ns() - started_ns,
        ),
    )


def resolve_cutscene_assets(
    cache: GameFileCache,
    query: Any,
    *,
    subtitle_language: str = "american",
    initial_ped_variations: Mapping[str | int, Mapping[int, tuple[int, int]]]
    | None = None,
    cancellation: CutsceneResolutionCancellation | None = None,
    trace: CutsceneResolutionTrace | None = None,
) -> CutsceneAssetBundle:
    from ...cache import AssetRecord

    active_trace = trace or CutsceneResolutionTrace()
    executor: ThreadPoolExecutor | None = None
    try:
        with active_trace.span("preparation"):
            cache.prepare_cutscene_resolution(cancellation=cancellation)
        with active_trace.span("source"):
            check_cutscene_resolution_cancelled(cancellation)
            if isinstance(query, AssetRecord):
                source = query
            else:
                candidates = cache.find_assets(query, kind=GameFileType.CUT)
                source = min(candidates, key=_source_rank) if candidates else None
            if source is None or source.kind is not GameFileType.CUT:
                raise FileNotFoundError(f"CUT asset not found: {query}")
            active_trace.source = source.path
        with active_trace.span("cut"):
            check_cutscene_resolution_cancelled(cancellation)
            cut_file = cache.load_asset(source)
            if cut_file is None or cut_file.parsed is None:
                raise ValueError(f"Unable to decode CUT asset: {source.path}")
            scene = read_cut_scene(cut_file.parsed)
        issues: list[CutsceneResolveIssue] = []
        with active_trace.span("animations"):
            ycds, ycd_assets = _resolve_ycds(
                cache, source, scene, issues, cancellation=cancellation
            )
        with active_trace.span("bindings"):
            bindings = _resolve_bindings(
                cache, scene, issues, cancellation=cancellation
            )
        with active_trace.span("vehicle_models"):
            _resolve_vehicle_high_detail_models(
                cache,
                bindings,
                issues,
                cancellation=cancellation,
            )
        audio_references = cut_audio_references(scene)
        audio_hints = cut_audio_container_hints(scene, audio_references)

        stages: dict[
            str,
            tuple[Any, list[CutsceneResolveIssue], CutsceneResolutionSpan],
        ] = {}

        def vehicle_appearances(stage_issues: list[CutsceneResolveIssue]) -> None:
            _resolve_vehicle_appearances(
                cache,
                scene,
                bindings,
                stage_issues,
                cancellation=cancellation,
            )

        def facial_resources(stage_issues: list[CutsceneResolveIssue]) -> None:
            _resolve_ped_expression_resources(
                cache,
                bindings,
                stage_issues,
                cancellation=cancellation,
            )

        def subtitles(stage_issues: list[CutsceneResolveIssue]) -> Any:
            return _resolve_subtitle_dictionaries(
                cache,
                scene,
                stage_issues,
                language=subtitle_language,
                cancellation=cancellation,
            )

        def audio_stage(stage_issues: list[CutsceneResolveIssue]) -> Any:
            return _resolve_audio(
                cache,
                audio_references,
                stage_issues,
                container_hints=audio_hints,
                cancellation=cancellation,
            )

        futures: dict[
            str,
            Future[tuple[Any, list[CutsceneResolveIssue], CutsceneResolutionSpan]],
        ] = {}
        if cache.concurrent_asset_reads:
            executor = ThreadPoolExecutor(max_workers=4)
            for name, operation in (
                ("vehicle_appearances", vehicle_appearances),
                ("facial_resources", facial_resources),
                ("subtitles", subtitles),
                ("audio", audio_stage),
            ):
                futures[name] = executor.submit(
                    _run_stage,
                    active_trace,
                    name,
                    operation,
                )
            stages["vehicle_appearances"] = futures["vehicle_appearances"].result()
            stages["facial_resources"] = futures["facial_resources"].result()
        else:
            stages["vehicle_appearances"] = _run_stage(
                active_trace,
                "vehicle_appearances",
                vehicle_appearances,
            )
            stages["facial_resources"] = _run_stage(
                active_trace,
                "facial_resources",
                facial_resources,
            )
        issues.extend(stages["vehicle_appearances"][1])
        issues.extend(stages["facial_resources"][1])
        normalized_initial_variations = _normalize_initial_ped_variations(
            bindings, initial_ped_variations, issues
        )

        def ped_components(stage_issues: list[CutsceneResolveIssue]) -> None:
            _resolve_ped_components(
                cache,
                scene,
                bindings,
                stage_issues,
                normalized_initial_variations,
                cancellation=cancellation,
            )

        def textures(stage_issues: list[CutsceneResolveIssue]) -> None:
            _resolve_binding_texture_chains(
                cache,
                bindings,
                stage_issues,
                cancellation=cancellation,
            )

        stages["ped_components"] = _run_stage(
            active_trace,
            "ped_components",
            ped_components,
        )
        issues.extend(stages["ped_components"][1])
        stages["textures"] = _run_stage(
            active_trace,
            "textures",
            textures,
        )
        issues.extend(stages["textures"][1])
        if executor is not None:
            stages["subtitles"] = futures["subtitles"].result()
            stages["audio"] = futures["audio"].result()
        else:
            stages["subtitles"] = _run_stage(
                active_trace,
                "subtitles",
                subtitles,
            )
            stages["audio"] = _run_stage(
                active_trace,
                "audio",
                audio_stage,
            )
        issues.extend(stages["subtitles"][1])
        issues.extend(stages["audio"][1])
        for name in (
            "vehicle_appearances",
            "facial_resources",
            "ped_components",
            "textures",
            "subtitles",
            "audio",
        ):
            active_trace.spans.append(stages[name][2])
        subtitle_dictionaries = stages["subtitles"][0]
        audio = stages["audio"][0]
        return CutsceneAssetBundle(
            source=source,
            cut_file=cut_file,
            scene=scene,
            ycd_by_section=ycds,
            ycd_assets_by_section=ycd_assets,
            bindings=bindings,
            audio_references=audio_references,
            audio=audio,
            subtitle_references=cut_event_references(
                scene, {"load_subtitles", "show_subtitle"}
            ),
            subtitle_dictionaries=subtitle_dictionaries,
            subtitle_language=subtitle_language,
            initial_ped_variations=normalized_initial_variations,
            issues=issues,
            trace=active_trace,
        )
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
        active_trace.finish()
