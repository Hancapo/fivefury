from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ...gamefile import GameFileType
from ..scene import read_cut_scene
from .animations import _resolve_ycds
from .audio import _event_references, _resolve_audio
from .bindings import (
    _normalize_initial_ped_variations,
    _resolve_binding_texture_chains,
    _resolve_bindings,
    _resolve_ped_components,
)
from .common import _source_rank
from .models import CutsceneAssetBundle, CutsceneResolveIssue
from .runtime import (
    CutsceneResolutionCancellation,
    CutsceneResolutionTrace,
    check_cutscene_resolution_cancelled,
)
from .subtitles import _resolve_subtitle_dictionaries

if TYPE_CHECKING:
    from ...cache import GameFileCache


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
    try:
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
        normalized_initial_variations = _normalize_initial_ped_variations(
            bindings, initial_ped_variations, issues
        )
        with active_trace.span("ped_components"):
            _resolve_ped_components(
                cache,
                scene,
                bindings,
                issues,
                normalized_initial_variations,
                cancellation=cancellation,
            )
        with active_trace.span("textures"):
            _resolve_binding_texture_chains(
                cache, bindings, issues, cancellation=cancellation
            )
        with active_trace.span("subtitles"):
            subtitle_dictionaries = _resolve_subtitle_dictionaries(
                cache,
                scene,
                issues,
                language=subtitle_language,
                cancellation=cancellation,
            )
        with active_trace.span("audio"):
            audio_references = _event_references(
                scene, {"load_audio", "play_audio"}
            )
            audio = _resolve_audio(
                cache, audio_references, issues, cancellation=cancellation
            )
        return CutsceneAssetBundle(
            source=source,
            cut_file=cut_file,
            scene=scene,
            ycd_by_section=ycds,
            ycd_assets_by_section=ycd_assets,
            bindings=bindings,
            audio_references=audio_references,
            audio=audio,
            subtitle_references=_event_references(
                scene, {"load_subtitles", "show_subtitle"}
            ),
            subtitle_dictionaries=subtitle_dictionaries,
            subtitle_language=subtitle_language,
            initial_ped_variations=normalized_initial_variations,
            issues=issues,
            trace=active_trace,
        )
    finally:
        active_trace.finish()
