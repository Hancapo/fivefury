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
) -> CutsceneAssetBundle:
    from ...cache import AssetRecord

    if isinstance(query, AssetRecord):
        source = query
    else:
        candidates = cache.find_assets(query, kind=GameFileType.CUT)
        source = min(candidates, key=_source_rank) if candidates else None
    if source is None or source.kind is not GameFileType.CUT:
        raise FileNotFoundError(f"CUT asset not found: {query}")
    cut_file = cache.load_asset(source)
    if cut_file is None or cut_file.parsed is None:
        raise ValueError(f"Unable to decode CUT asset: {source.path}")
    scene = read_cut_scene(cut_file.parsed)
    issues: list[CutsceneResolveIssue] = []
    ycds, ycd_assets = _resolve_ycds(cache, source, scene, issues)
    bindings = _resolve_bindings(cache, scene, issues)
    normalized_initial_variations = _normalize_initial_ped_variations(
        bindings, initial_ped_variations, issues
    )
    _resolve_ped_components(
        cache, scene, bindings, issues, normalized_initial_variations
    )
    _resolve_binding_texture_chains(cache, bindings, issues)
    subtitle_dictionaries = _resolve_subtitle_dictionaries(
        cache,
        scene,
        issues,
        language=subtitle_language,
    )
    audio_references = _event_references(scene, {"load_audio", "play_audio"})
    audio = _resolve_audio(cache, audio_references, issues)
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
    )
