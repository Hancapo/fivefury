from __future__ import annotations

import dataclasses
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from ...cache.ped_index import load_ped_init_index, save_ped_init_index
from ...gamefile import GameFileType
from ...metahash import MetaHash
from ...yed import (
    PedExpressionSet,
    PedExpressionSetMetadata,
    is_null_expression_reference,
)
from .common import _load_file, _preferred_asset, _source_rank
from .models import (
    CutsceneResolveIssue,
    ResolvedCutBinding,
    ResolvedPedExpressionSet,
)
from .runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache
    from ...gamefile import GameFile


PedInitMatch = tuple[Any, Any, Any]
ExpressionSetMatch = tuple[Any, Any, PedExpressionSet]


def _ped_init_data_by_model(
    cache: GameFileCache,
    issues: list[CutsceneResolveIssue],
    cancellation: CutsceneResolutionCancellation | None,
    required_hashes: set[int],
) -> dict[int, tuple[int, list[PedInitMatch]]]:
    cached_index = getattr(cache, "_ped_init_asset_index", None)
    if cached_index is None:
        try:
            cached_index = load_ped_init_index(cache.get_index_cache_path())
        except (AttributeError, OSError):
            cached_index = None
        if cached_index is not None:
            with suppress(AttributeError):
                cache._ped_init_asset_index = cached_index

    if cached_index is not None:
        asset_ids = {
            asset_id
            for reference_hash in required_hashes
            for asset_id in cached_index.get(reference_hash, ())
        }
        matches: dict[int, tuple[int, list[PedInitMatch]]] = {}
        try:
            assets = [cache._record_from_id(asset_id) for asset_id in asset_ids]
        except (AttributeError, IndexError):
            cached_index = None
        else:
            for asset in sorted(assets, key=_source_rank):
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
                    if (
                        reference_hash not in required_hashes
                        or asset.id not in cached_index.get(reference_hash, ())
                    ):
                        continue
                    existing = matches.get(reference_hash)
                    if existing is None:
                        matches[reference_hash] = (
                            source_tier,
                            [(asset, game_file, item)],
                        )
                    else:
                        existing[1].append((asset, game_file, item))
            return matches

    matches: dict[int, tuple[int, list[PedInitMatch]]] = {}
    asset_ids_by_model: dict[int, tuple[int, list[int]]] = {}
    indexable = True
    for asset in sorted(
        cache.find_assets("peds.ymt", kind=GameFileType.YMT),
        key=_source_rank,
    ):
        check_cutscene_resolution_cancelled(cancellation)
        game_file = _load_file(cache, asset, issues)
        metadata = getattr(getattr(game_file, "parsed", None), "ped_metadata", None)
        if metadata is None:
            continue
        source_tier = _source_rank(asset)[0]
        asset_id = getattr(asset, "id", None)
        if not isinstance(asset_id, int):
            indexable = False
        for item in metadata.init_datas:
            reference_hash = int(getattr(item.name, "uint", 0))
            existing = matches.get(reference_hash)
            if existing is None or source_tier < existing[0]:
                matches[reference_hash] = (
                    source_tier,
                    [(asset, game_file, item)],
                )
                if isinstance(asset_id, int):
                    asset_ids_by_model[reference_hash] = (source_tier, [asset_id])
            elif source_tier == existing[0]:
                existing[1].append((asset, game_file, item))
                if isinstance(asset_id, int):
                    indexed = asset_ids_by_model.setdefault(
                        reference_hash,
                        (source_tier, []),
                    )[1]
                    if asset_id not in indexed:
                        indexed.append(asset_id)
    compact_index = {
        reference_hash: tuple(asset_ids)
        for reference_hash, (_, asset_ids) in asset_ids_by_model.items()
    }
    if indexable:
        try:
            save_ped_init_index(cache.get_index_cache_path(), compact_index)
            cache._ped_init_asset_index = compact_index
        except (AttributeError, OSError):
            pass
    return matches


def _init_record_identity(item: Any) -> tuple[Any, ...]:
    """Identify an init record by its metadata, ignoring the parsed source node."""
    if not dataclasses.is_dataclass(item):
        return (item,)
    return tuple(
        getattr(item, field.name)
        for field in dataclasses.fields(item)
        if field.name != "raw"
    )


def _init_records_agree(matches: tuple[Any, ...]) -> bool:
    identity = _init_record_identity(matches[0])
    return all(_init_record_identity(item) == identity for item in matches[1:])


def _select_ped_init_data(
    resolved: ResolvedCutBinding,
    candidates: tuple[int, list[PedInitMatch]] | None,
    issues: list[CutsceneResolveIssue],
    object_id: int,
) -> bool:
    matches = tuple(item for _, _, item in candidates[1]) if candidates else ()
    resolved.ped_init_data_candidates = matches
    # Retail ships whole copies of peds.ymt inside several DLC packs, so a
    # single model routinely matches identical init records at the same source
    # tier.  Records that agree carry no ambiguity to resolve: keep the first
    # by source rank.  Only genuinely conflicting records stay unresolved.
    if matches and _init_records_agree(matches):
        asset, game_file, item = candidates[1][0]
        resolved.ped_metadata_asset = asset
        resolved.ped_metadata_file = game_file
        resolved.ped_init_data = item
        return True

    resolved.ped_metadata_asset = None
    resolved.ped_metadata_file = None
    resolved.ped_init_data = None
    issues.append(
        CutsceneResolveIssue(
            severity="info" if not matches else "warning",
            code="binding.ymt_init_unresolved",
            message=(
                f"{resolved.binding.display_name} matched {len(matches)} "
                "conflicting ped init records; a single consistent YMT init "
                "record is required"
            ),
            object_id=object_id,
        )
    )
    return False


def _expression_sets_by_hash(
    cache: GameFileCache,
    issues: list[CutsceneResolveIssue],
    cancellation: CutsceneResolutionCancellation | None,
) -> tuple[dict[int, ExpressionSetMatch], bool]:
    assets = sorted(
        cache.find_assets(
            "expression_sets.xml",
            kind=GameFileType.EXPRESSION_SETS,
        ),
        key=_source_rank,
    )
    matches: dict[int, ExpressionSetMatch] = {}
    loaded_metadata = False
    for asset in assets:
        check_cutscene_resolution_cancelled(cancellation)
        game_file = _load_file(cache, asset, issues)
        metadata = getattr(game_file, "parsed", None)
        if not isinstance(metadata, PedExpressionSetMetadata):
            continue
        loaded_metadata = True
        for expression_set in metadata.expression_sets:
            matches.setdefault(
                expression_set.name.uint,
                (asset, game_file, expression_set),
            )
    return matches, loaded_metadata


def _attach_yed(
    resolved: ResolvedCutBinding,
    asset: AssetRecord,
    game_file: GameFile,
) -> None:
    resolved.assets[GameFileType.YED] = asset
    resolved.files[GameFileType.YED] = game_file


def _resolve_direct_expression_dictionary(
    cache: GameFileCache,
    resolved: ResolvedCutBinding,
    issues: list[CutsceneResolveIssue],
    object_id: int,
) -> None:
    reference = getattr(resolved.ped_init_data, "expression_dictionary_name", None)
    if is_null_expression_reference(reference):
        return
    expression_hash = MetaHash(reference).uint
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
        return
    game_file = _load_file(cache, asset, issues, object_id=object_id)
    if game_file is not None:
        _attach_yed(resolved, asset, game_file)


def _validate_expression_set_programs(
    resolved_set: ResolvedPedExpressionSet,
) -> None:
    yed = resolved_set.dictionary
    get_expression = getattr(yed, "get_expression", None)
    selected_names: list[str] = []
    program_names: list[str] = []
    program_hashes: list[MetaHash] = []
    missing_names: list[str] = []
    expression_set = resolved_set.expression_set
    for index, expression_hash in enumerate(expression_set.expression_names):
        raw_name = (
            expression_set.raw_expression_names[index]
            if index < len(expression_set.raw_expression_names)
            else ""
        )
        lookup = raw_name or expression_hash
        expression = get_expression(lookup) if callable(get_expression) else None
        display_name = raw_name or f"0x{expression_hash.uint:08X}"
        if expression is None:
            missing_names.append(display_name)
            continue
        selected_names.append(display_name)
        program_names.append(str(expression.name))
        program_hashes.append(MetaHash(expression.name_hash))
    resolved_set.selected_expression_names = tuple(selected_names)
    resolved_set.selected_program_names = tuple(program_names)
    resolved_set.selected_program_hashes = tuple(program_hashes)
    resolved_set.missing_expression_names = tuple(missing_names)


def _resolve_expression_set(
    cache: GameFileCache,
    resolved: ResolvedCutBinding,
    set_reference: Any,
    set_matches: dict[int, ExpressionSetMatch],
    metadata_available: bool,
    issues: list[CutsceneResolveIssue],
    object_id: int,
) -> None:
    set_hash = MetaHash(set_reference).uint
    match = set_matches.get(set_hash)
    if match is None:
        issues.append(
            CutsceneResolveIssue(
                severity="warning",
                code=(
                    "binding.expression_set_unresolved"
                    if metadata_available
                    else "binding.expression_set_metadata_unresolved"
                ),
                message=(
                    f"{resolved.binding.display_name} expression set "
                    f"0x{set_hash:08X} was not found"
                ),
                object_id=object_id,
            )
        )
        return

    source_asset, source_file, expression_set = match
    resolved_set = ResolvedPedExpressionSet(
        expression_set=expression_set,
        source_asset=source_asset,
        source_file=source_file,
    )
    resolved.resolved_expression_set = resolved_set
    dictionary_hash = expression_set.dictionary_name.uint
    asset = _preferred_asset(cache, dictionary_hash, GameFileType.YED)
    if asset is None:
        issues.append(
            CutsceneResolveIssue(
                severity="warning",
                code="binding.expression_set_yed_unresolved",
                message=(
                    f"{resolved.binding.display_name} expression-set dictionary "
                    f"0x{dictionary_hash:08X} was not found"
                ),
                asset_path=source_asset.path,
                object_id=object_id,
            )
        )
        return
    game_file = _load_file(cache, asset, issues, object_id=object_id)
    if game_file is None:
        return
    resolved_set.yed_asset = asset
    resolved_set.yed_file = game_file
    _attach_yed(resolved, asset, game_file)
    _validate_expression_set_programs(resolved_set)
    if resolved_set.missing_expression_names:
        issues.append(
            CutsceneResolveIssue(
                severity="warning",
                code="binding.expression_set_program_unresolved",
                message=(
                    f"{resolved.binding.display_name} expression-set programs were "
                    "not found: " + ", ".join(resolved_set.missing_expression_names)
                ),
                asset_path=asset.path,
                object_id=object_id,
            )
        )


def _resolve_ped_expression_resources(
    cache: GameFileCache,
    resolved_bindings: dict[int, ResolvedCutBinding],
    issues: list[CutsceneResolveIssue],
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> None:
    ped_bindings = tuple(
        (object_id, resolved)
        for object_id, resolved in resolved_bindings.items()
        if resolved.binding.role == "ped"
    )
    if not ped_bindings:
        return
    metadata_matches = _ped_init_data_by_model(
        cache,
        issues,
        cancellation,
        {int(resolved.reference_hash or 0) for _, resolved in ped_bindings},
    )
    expression_sets: dict[int, ExpressionSetMatch] | None = None
    expression_set_metadata_available = False

    for object_id, resolved in ped_bindings:
        check_cutscene_resolution_cancelled(cancellation)
        if not _select_ped_init_data(
            resolved,
            metadata_matches.get(int(resolved.reference_hash or 0)),
            issues,
            object_id,
        ):
            continue

        set_reference = getattr(resolved.ped_init_data, "expression_set_name", None)
        if is_null_expression_reference(set_reference):
            _resolve_direct_expression_dictionary(cache, resolved, issues, object_id)
            continue
        if expression_sets is None:
            expression_sets, expression_set_metadata_available = (
                _expression_sets_by_hash(cache, issues, cancellation)
            )
        _resolve_expression_set(
            cache,
            resolved,
            set_reference,
            expression_sets,
            expression_set_metadata_available,
            issues,
            object_id,
        )


__all__ = ["_resolve_ped_expression_resources"]
