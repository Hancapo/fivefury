from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ...gamefile import GameFileType
from ...metahash import MetaHash
from ...ymt import iter_ped_drawables
from ..scene import CutScene
from .common import _load_file, _preferred_asset, _source_rank
from .models import CutsceneResolveIssue, ResolvedCutBinding
from .runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)
from .values import field_hash

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache
    from ...gamefile import GameFile

_MODEL_KINDS_BY_ROLE: dict[str, tuple[GameFileType, ...]] = {
    "ped": (
        GameFileType.YFT,
        GameFileType.YDD,
        GameFileType.YMT,
        GameFileType.YTD,
    ),
    "prop": (GameFileType.YDR, GameFileType.YDD, GameFileType.YFT, GameFileType.YTD),
    "vehicle": (GameFileType.YFT, GameFileType.YTD, GameFileType.YCD),
    "weapon": (GameFileType.YDR, GameFileType.YDD, GameFileType.YFT, GameFileType.YTD),
    "particle_fx": (GameFileType.YPT,),
}


def _resolve_bindings(
    cache: GameFileCache,
    scene: CutScene,
    issues: list[CutsceneResolveIssue],
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> dict[int, ResolvedCutBinding]:
    result: dict[int, ResolvedCutBinding] = {}
    for binding in scene.bindings:
        check_cutscene_resolution_cancelled(cancellation)
        resolved = ResolvedCutBinding(binding=binding)
        result[binding.object_id] = resolved
        kinds = _MODEL_KINDS_BY_ROLE.get(binding.role)
        if kinds is None:
            continue
        reference_hash = field_hash(binding.fields.get("StreamingName"))
        if reference_hash is None and binding.role == "particle_fx":
            reference_hash = field_hash(binding.fields.get("athFxListHash"))
        resolved.reference_hash = reference_hash
        if reference_hash is None:
            issues.append(
                CutsceneResolveIssue(
                    severity="info",
                    code="binding.reference_missing",
                    message=f"{binding.display_name} has no resolvable streamed asset reference",
                    object_id=binding.object_id,
                )
            )
            continue
        for kind in kinds:
            asset = _preferred_asset(cache, reference_hash, kind)
            if asset is None:
                continue
            resolved.assets[kind] = asset
            game_file = _load_file(cache, asset, issues, object_id=binding.object_id)
            if game_file is not None:
                resolved.files[kind] = game_file
        if resolved.model_file is None and binding.role in {
            "ped",
            "prop",
            "vehicle",
            "weapon",
        }:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="binding.model_unresolved",
                    message=f"No drawable or fragment matched 0x{reference_hash:08X}",
                    object_id=binding.object_id,
                )
            )
    return result


def _resolve_ped_expression_resources(
    cache: GameFileCache,
    resolved_bindings: dict[int, ResolvedCutBinding],
    issues: list[CutsceneResolveIssue],
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> None:
    metadata_matches: dict[
        int,
        tuple[int, list[tuple[AssetRecord, GameFile, Any]]],
    ] = {}
    for asset in sorted(
        cache.find_assets("peds.ymt", kind=GameFileType.YMT),
        key=_source_rank,
    ):
        check_cutscene_resolution_cancelled(cancellation)
        game_file = _load_file(cache, asset, issues)
        metadata = getattr(
            getattr(game_file, "parsed", None), "ped_metadata", None
        )
        if metadata is None:
            continue
        source_tier = _source_rank(asset)[0]
        for item in metadata.init_datas:
            reference_hash = int(getattr(item.name, "uint", 0))
            existing = metadata_matches.get(reference_hash)
            if existing is None or source_tier < existing[0]:
                metadata_matches[reference_hash] = (
                    source_tier,
                    [(asset, game_file, item)],
                )
            elif source_tier == existing[0]:
                existing[1].append((asset, game_file, item))

    for object_id, resolved in resolved_bindings.items():
        check_cutscene_resolution_cancelled(cancellation)
        if resolved.binding.role != "ped":
            continue
        candidates = metadata_matches.get(int(resolved.reference_hash or 0))
        matches = tuple(item for _, _, item in candidates[1]) if candidates else ()
        resolved.ped_init_data_candidates = matches
        if candidates and len(candidates[1]) == 1:
            asset, game_file, item = candidates[1][0]
            resolved.ped_metadata_asset = asset
            resolved.ped_metadata_file = game_file
            resolved.ped_init_data = item
        else:
            resolved.ped_metadata_asset = None
            resolved.ped_metadata_file = None
            resolved.ped_init_data = None
        if resolved.ped_init_data is None:
            issues.append(
                CutsceneResolveIssue(
                    severity="info" if not matches else "warning",
                    code="binding.ymt_init_unresolved",
                    message=(
                        f"{resolved.binding.display_name} matched {len(matches)} ped init records; "
                        "an exact unique YMT init record is required"
                    ),
                    asset_path=(
                        resolved.ped_metadata_asset.path
                        if resolved.ped_metadata_asset is not None
                        else None
                    ),
                    object_id=object_id,
                )
            )
            continue
        expression_hash = int(
            getattr(
                getattr(resolved.ped_init_data, "expression_dictionary_name", None),
                "uint",
                0,
            )
        )
        if expression_hash == 0:
            continue
        asset = _preferred_asset(cache, expression_hash, GameFileType.YED)
        if asset is None:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="binding.yed_unresolved",
                    message=(
                        f"{resolved.binding.display_name} expression dictionary "
                        f"0x{expression_hash:08X} was not found"
                    ),
                    object_id=object_id,
                )
            )
            continue
        game_file = _load_file(cache, asset, issues, object_id=object_id)
        if game_file is not None:
            resolved.assets[GameFileType.YED] = asset
            resolved.files[GameFileType.YED] = game_file


_PED_COMPONENT_PREFIXES: dict[int, str] = {
    0: "head",
    1: "berd",
    2: "hair",
    3: "uppr",
    4: "lowr",
    5: "hand",
    6: "feet",
    7: "teef",
    8: "accs",
    9: "task",
    10: "decl",
    11: "jbib",
}

_PED_PROP_PREFIXES: dict[int, str] = {
    12: "p_head",
    13: "p_eyes",
    14: "p_ears",
    15: "p_mouth",
    16: "p_lhand",
    17: "p_rhand",
    18: "p_lwrist",
    19: "p_rwrist",
    20: "p_lhip",
    21: "p_lfoot",
    22: "p_rfoot",
    23: "ph_lhand",
    24: "ph_rhand",
}

_PED_VARIATION_PREFIXES = {**_PED_COMPONENT_PREFIXES, **_PED_PROP_PREFIXES}


def _ped_component_variations(
    scene: CutScene,
    object_id: int,
    initial: Mapping[int, tuple[int, int]] | None = None,
) -> dict[int, set[tuple[int, int]]]:
    result: dict[int, set[tuple[int, int]]] = {
        component: {(0, 0)} for component in _PED_COMPONENT_PREFIXES
    }
    for component, variation in (initial or {}).items():
        if component not in _PED_VARIATION_PREFIXES:
            continue
        drawable, texture = variation
        if drawable >= 0:
            result.setdefault(component, set()).add((int(drawable), int(texture)))
    for event in scene.timeline:
        if event.event_name != "set_variation":
            continue
        target = event.payload.get("iObjectId", event.target_id)
        if target != object_id:
            continue
        component = event.payload.get("iComponent")
        drawable = event.payload.get("iDrawable")
        texture = event.payload.get("iTexture", 0)
        if component not in _PED_VARIATION_PREFIXES or not isinstance(drawable, int):
            continue
        if drawable >= 0:
            result.setdefault(component, set()).add(
                (drawable, int(texture) if isinstance(texture, int) else 0)
            )
    return result


def _ped_asset_relevance(asset: AssetRecord, model_stem: str) -> tuple[int, int, str]:
    parts = asset.path.replace("\\", "/").lower().split("/")
    if model_stem in parts:
        folder_rank = 0
    elif any(part.startswith(f"{model_stem}_") for part in parts):
        folder_rank = 1
    else:
        folder_rank = 2
    source_rank, path = _source_rank(asset)
    return folder_rank, source_rank, path


def _matching_ped_assets(
    assets: list[AssetRecord],
    model_stem: str,
    pattern: re.Pattern[str],
) -> list[AssetRecord]:
    matches = []
    for asset in assets:
        parts = asset.path.replace("\\", "/").lower().split("/")
        if not any(
            part == model_stem or part.startswith(f"{model_stem}_") for part in parts
        ):
            continue
        if pattern.match(asset.stem.lower()):
            matches.append(asset)
    return sorted(matches, key=lambda item: _ped_asset_relevance(item, model_stem))


def _resolve_ped_components(
    cache: GameFileCache,
    scene: CutScene,
    resolved_bindings: dict[int, ResolvedCutBinding],
    issues: list[CutsceneResolveIssue],
    initial_ped_variations: Mapping[int, Mapping[int, tuple[int, int]]] | None = None,
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> None:
    search_cache: dict[tuple[str, GameFileType], list[AssetRecord]] = {}
    for object_id, resolved in resolved_bindings.items():
        check_cutscene_resolution_cancelled(cancellation)
        if resolved.binding.role != "ped" or resolved.reference_hash is None:
            continue
        model_asset = resolved.assets.get(GameFileType.YFT)
        if model_asset is None:
            continue
        model_stem = model_asset.stem.lower()
        variations = _ped_component_variations(
            scene, object_id, (initial_ped_variations or {}).get(object_id)
        )
        exact_component_stems: dict[tuple[int, int], str] = {}
        variation_file = resolved.files.get(GameFileType.YMT)
        if variation_file is not None:
            try:
                exact_component_stems = {
                    (int(item.component), int(item.drawable_index)): item.file_stem
                    for item in iter_ped_drawables(variation_file.parsed)
                }
            except (TypeError, ValueError) as exc:
                issues.append(
                    CutsceneResolveIssue(
                        severity="warning",
                        code="binding.ped_variation_invalid",
                        message=f"Could not inspect ped variation metadata: {exc}",
                        asset_path=resolved.assets[GameFileType.YMT].path,
                        object_id=object_id,
                    )
                )
        for kind in (GameFileType.YDD, GameFileType.YTD):
            key = (model_stem, kind)
            if key not in search_cache:
                search_cache[key] = cache.find_container_assets(
                    model_stem,
                    kind=kind,
                    include_prefixed=True,
                )
        ydd_assets = search_cache[(model_stem, GameFileType.YDD)]
        ytd_assets = search_cache[(model_stem, GameFileType.YTD)]
        seen_models: set[str] = set()
        seen_textures: set[str] = set()
        has_component_dictionary = GameFileType.YDD in resolved.files
        for component, requested in variations.items():
            check_cutscene_resolution_cancelled(cancellation)
            prefix = _PED_VARIATION_PREFIXES[component]
            for drawable, texture_index in sorted(requested):
                if component >= 12:
                    model_pattern = re.compile(
                        rf"^{re.escape(prefix)}_{drawable:03d}(?:_\d+)?$"
                    )
                else:
                    exact_stem = exact_component_stems.get((component, drawable))
                    model_pattern = re.compile(
                        rf"^{re.escape(exact_stem)}(?:_\d+)?$"
                        if exact_stem
                        else rf"^{prefix}_{drawable:03d}_[rum](?:_\d+)?$"
                    )
                # A same-name YDD already contains clothing components, but ped
                # props always live in separate streamed-ped-prop dictionaries.
                if component >= 12 or not has_component_dictionary:
                    model_matches = _matching_ped_assets(
                        ydd_assets, model_stem, model_pattern
                    )
                    if model_matches:
                        asset = model_matches[0]
                        if asset.path not in seen_models:
                            seen_models.add(asset.path)
                            game_file = _load_file(
                                cache, asset, issues, object_id=object_id
                            )
                            if game_file is not None:
                                resolved.component_assets.append(asset)
                                resolved.component_files.append(game_file)
                texture_letter = chr(ord("a") + max(0, min(25, texture_index)))
                texture_pattern = re.compile(
                    rf"^{prefix}_diff_{drawable:03d}_{texture_letter}(?:_|$)"
                )
                texture_matches = _matching_ped_assets(
                    ytd_assets, model_stem, texture_pattern
                )
                if texture_matches:
                    asset = texture_matches[0]
                    if asset.path not in seen_textures:
                        seen_textures.add(asset.path)
                        game_file = _load_file(
                            cache, asset, issues, object_id=object_id
                        )
                        if game_file is not None:
                            resolved.component_texture_assets.append(asset)
                            resolved.component_texture_files.append(game_file)
        if not resolved.component_files and not has_component_dictionary:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="binding.ped_components_unresolved",
                    message=f"No component drawables were resolved for {model_stem}",
                    asset_path=model_asset.path,
                    object_id=object_id,
                )
            )


def _resolve_binding_texture_chains(
    cache: GameFileCache,
    resolved_bindings: dict[int, ResolvedCutBinding],
    issues: list[CutsceneResolveIssue],
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> None:
    for object_id, resolved in resolved_bindings.items():
        check_cutscene_resolution_cancelled(cancellation)
        texture_root = resolved.assets.get(GameFileType.YTD)
        if texture_root is None:
            continue
        try:
            chain = cache.list_texture_dictionaries(
                texture_root,
                include_parents=True,
            )
        except Exception as exc:  # noqa: BLE001 - metadata failures become diagnostics
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="binding.texture_chain_failed",
                    message=(
                        f"Unable to resolve the texture dictionary chain for "
                        f"{texture_root.stem}: {type(exc).__name__}: {exc}"
                    ),
                    asset_path=texture_root.path,
                    object_id=object_id,
                )
            )
            continue
        seen_paths: set[str] = set()
        for candidate in chain:
            asset = _preferred_asset(cache, candidate.short_hash, GameFileType.YTD)
            asset = asset or candidate
            if asset.path in seen_paths:
                continue
            seen_paths.add(asset.path)
            game_file = _load_file(cache, asset, issues, object_id=object_id)
            if game_file is None:
                continue
            resolved.texture_assets.append(asset)
            resolved.texture_files.append(game_file)


def _normalize_initial_ped_variations(
    bindings: Mapping[int, ResolvedCutBinding],
    values: Mapping[str | int, Mapping[int, tuple[int, int]]] | None,
    issues: list[CutsceneResolveIssue],
) -> dict[int, dict[int, tuple[int, int]]]:
    """Match external runtime ped snapshots to CUT actors.

    RAGE scripts can register a cutscene actor with the complete variation state
    of an existing ped. That state is deliberately external to the CUT, so a
    standalone resolver must receive it from the caller when fidelity requires
    the script-selected outfit.
    """
    if not values:
        return {}
    result: dict[int, dict[int, tuple[int, int]]] = {}
    for actor, variations in values.items():
        object_ids: list[int] = []
        if isinstance(actor, int) and actor in bindings:
            object_ids = [actor]
        else:
            actor_hash = (
                int(actor) & 0xFFFFFFFF
                if isinstance(actor, int)
                else MetaHash(str(actor)).uint
            )
            for object_id, resolved in bindings.items():
                binding = resolved.binding
                if binding.role != "ped":
                    continue
                hashes = {resolved.reference_hash}
                for field_name in ("cHandle", "cName", "StreamingName"):
                    hashes.add(field_hash(binding.fields.get(field_name)))
                if actor_hash in hashes:
                    object_ids.append(object_id)
        if not object_ids:
            issues.append(
                CutsceneResolveIssue(
                    severity="warning",
                    code="binding.initial_variation_actor_unresolved",
                    message=f"Initial ped variation actor {actor!r} is absent from the CUT",
                )
            )
            continue
        normalized: dict[int, tuple[int, int]] = {}
        for component_value, variation in variations.items():
            component = int(component_value)
            if component not in _PED_VARIATION_PREFIXES or len(variation) != 2:
                issues.append(
                    CutsceneResolveIssue(
                        severity="warning",
                        code="binding.initial_variation_invalid",
                        message=(
                            f"Ignored invalid initial variation for actor {actor!r}, "
                            f"component {component}"
                        ),
                    )
                )
                continue
            normalized[component] = (int(variation[0]), int(variation[1]))
        for object_id in object_ids:
            result.setdefault(object_id, {}).update(normalized)
            issues.append(
                CutsceneResolveIssue(
                    severity="info",
                    code="binding.initial_variation_applied",
                    message=(
                        f"Applied {len(normalized)} caller-supplied initial ped "
                        "variations"
                    ),
                    object_id=object_id,
                )
            )
    return result
