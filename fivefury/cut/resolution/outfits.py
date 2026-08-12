from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from ...cache.ped_assets import matching_ped_assets
from ...cache.precedence import asset_source_rank, preferred_asset
from ...gamefile import GameFile, GameFileType
from ...metahash import MetaHash
from ...ymt import iter_ped_drawables, iter_ped_props
from .models import (
    CutsceneResolveIssue,
    PedOutfitCatalog,
    PedOutfitOption,
    ResolvedCutBinding,
    ResolvedPedOutfitVariant,
)
from .runtime import (
    CutsceneResolutionCancellation,
    check_cutscene_resolution_cancelled,
)

if TYPE_CHECKING:
    from ...cache import AssetRecord, GameFileCache


def _issue(
    code: str,
    message: str,
    *,
    severity: str = "warning",
    asset_path: str | None = None,
) -> CutsceneResolveIssue:
    return CutsceneResolveIssue(
        severity=severity,
        code=code,
        message=message,
        asset_path=asset_path,
    )


def _query_identity(
    cache: GameFileCache,
    query: ResolvedCutBinding | AssetRecord | GameFile | str | int,
) -> tuple[str, int | None, AssetRecord | None, GameFile | None]:
    if isinstance(query, ResolvedCutBinding):
        model_asset = query.assets.get(GameFileType.YFT)
        variation_asset = query.assets.get(GameFileType.YMT)
        variation_file = query.files.get(GameFileType.YMT)
        name = model_asset.stem if model_asset is not None else ""
        return name.lower(), query.reference_hash, variation_asset, variation_file

    if isinstance(query, GameFile):
        asset = cache.find_path(query.path, kind=query.kind)
        name = PurePosixPath(query.path.replace("\\", "/")).stem.lower()
        model_hash = int(MetaHash(name)) if name else None
        if query.kind is GameFileType.YMT:
            return name, model_hash, asset, query
        variation = preferred_asset(cache, model_hash or 0, GameFileType.YMT)
        return name, model_hash, variation, None

    if not isinstance(query, (str, int)):
        asset = query
        name = asset.stem.lower()
        model_hash = asset.short_hash
        if asset.kind is GameFileType.YMT:
            return name, model_hash, asset, None
        variation = preferred_asset(cache, model_hash, GameFileType.YMT)
        return name, model_hash, variation, None

    if isinstance(query, str):
        name = PurePosixPath(query.replace("\\", "/")).stem.lower()
        model_hash = int(MetaHash(name)) if name else None
    else:
        name = ""
        model_hash = int(query) & 0xFFFFFFFF

    variation = preferred_asset(cache, model_hash or 0, GameFileType.YMT)
    model_asset = preferred_asset(cache, model_hash or 0, GameFileType.YFT)
    if not name:
        source = model_asset or variation
        name = source.stem.lower() if source is not None else ""
    return name, model_hash, variation, None


def _collect_candidates(
    cache: GameFileCache,
    model_name: str,
    kind: GameFileType,
) -> list[AssetRecord]:
    result = cache.find_container_assets(
        model_name,
        kind=kind,
        include_prefixed=True,
    )
    seen = {asset.id for asset in result}
    for asset in cache.find_assets(model_name, kind=kind):
        if asset.id not in seen:
            result.append(asset)
            seen.add(asset.id)
    return result


def _same_name_asset(
    assets: Iterable[AssetRecord],
    model_name: str,
) -> AssetRecord | None:
    candidates = [asset for asset in assets if asset.stem.lower() == model_name]
    return min(candidates, key=asset_source_rank) if candidates else None


def _first_matching_asset(
    assets: Iterable[AssetRecord],
    model_name: str,
    pattern: str,
) -> AssetRecord | None:
    matches = matching_ped_assets(
        assets,
        model_name,
        re.compile(pattern),
    )
    return matches[0] if matches else None


def _texture_assets(
    assets: Iterable[AssetRecord],
    model_name: str,
    prefix: str,
    drawable: int,
    texture_count: int,
    same_name: AssetRecord | None,
) -> tuple[AssetRecord, ...]:
    if same_name is not None:
        return (same_name,)
    result = []
    for texture in range(texture_count):
        letter = chr(ord("a") + texture)
        asset = _first_matching_asset(
            assets,
            model_name,
            rf"^{re.escape(prefix)}_diff_{drawable:03d}_{letter}(?:_|$)",
        )
        if asset is not None:
            result.append(asset)
    return tuple(result)


def _catalog_options(
    cache: GameFileCache,
    ymt: Any,
    model_name: str,
    cancellation: CutsceneResolutionCancellation | None,
) -> tuple[dict[int, tuple[PedOutfitOption, ...]], list[CutsceneResolveIssue]]:
    issues: list[CutsceneResolveIssue] = []
    ydd_assets = _collect_candidates(cache, model_name, GameFileType.YDD)
    ytd_assets = _collect_candidates(cache, model_name, GameFileType.YTD)
    same_name_ydd = _same_name_asset(ydd_assets, model_name)
    same_name_ytd = _same_name_asset(ytd_assets, model_name)
    slots: dict[int, list[PedOutfitOption]] = defaultdict(list)

    for drawable in iter_ped_drawables(ymt):
        check_cutscene_resolution_cancelled(cancellation)
        file_stem = drawable.file_stem
        drawable_asset = same_name_ydd or _first_matching_asset(
            ydd_assets,
            model_name,
            rf"^{re.escape(file_stem)}(?:_\d+)?$",
        )
        prefix = file_stem.split("_", 1)[0]
        textures = _texture_assets(
            ytd_assets,
            model_name,
            prefix,
            drawable.drawable_index,
            drawable.texture_count,
            same_name_ytd,
        )
        slots[int(drawable.component)].append(
            PedOutfitOption(
                slot=int(drawable.component),
                drawable=drawable.drawable_index,
                texture_count=drawable.texture_count,
                is_prop=False,
                file_stem=file_stem,
                prop_mask=drawable.prop_mask,
                num_alternatives=drawable.num_alternatives,
                owns_cloth=drawable.owns_cloth,
                drawable_asset=drawable_asset,
                texture_assets=textures,
            )
        )

    for prop in iter_ped_props(ymt):
        check_cutscene_resolution_cancelled(cancellation)
        file_stem = prop.file_stem
        drawable_asset = _first_matching_asset(
            ydd_assets,
            model_name,
            rf"^{re.escape(file_stem)}(?:_\d+)?$",
        )
        prefix = file_stem.rsplit("_", 1)[0]
        textures = _texture_assets(
            ytd_assets,
            model_name,
            prefix,
            prop.drawable_index,
            prop.texture_count,
            None,
        )
        slots[prop.slot].append(
            PedOutfitOption(
                slot=prop.slot,
                drawable=prop.drawable_index,
                texture_count=prop.texture_count,
                is_prop=True,
                file_stem=file_stem,
                drawable_asset=drawable_asset,
                texture_assets=textures,
            )
        )

    for options in slots.values():
        for option in options:
            if option.drawable_asset is None:
                issues.append(
                    _issue(
                        "outfit.drawable_unresolved",
                        f"No drawable asset matched {option.file_stem}",
                    )
                )
            if option.texture_count and not option.texture_assets:
                issues.append(
                    _issue(
                        "outfit.texture_unresolved",
                        f"No texture dictionary matched slot {option.slot} drawable {option.drawable}",
                    )
                )
    return {slot: tuple(options) for slot, options in slots.items()}, issues


def resolve_ped_outfit_catalog(
    cache: GameFileCache,
    query: ResolvedCutBinding | AssetRecord | GameFile | str | int,
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> PedOutfitCatalog:
    check_cutscene_resolution_cancelled(cancellation)
    model_name, model_hash, variation_asset, variation_file = _query_identity(
        cache, query
    )
    cache_key = (
        cache._view_generation,
        model_hash or 0,
        variation_asset.id if variation_asset is not None else -1,
    )
    cached = cache._ped_outfit_catalog_cache.get(cache_key)
    if cached is not None:
        return cached

    issues: list[CutsceneResolveIssue] = []
    if variation_file is None and variation_asset is not None:
        check_cutscene_resolution_cancelled(cancellation)
        variation_file = cache.load_asset(variation_asset)
    if variation_file is None:
        issues.append(
            _issue(
                "outfit.variation_unresolved",
                f"No ped variation YMT matched {model_name or f'0x{model_hash or 0:08X}'}",
            )
        )
        return PedOutfitCatalog(
            model_name=model_name,
            model_hash=model_hash,
            variation_asset=variation_asset,
            slots=MappingProxyType({}),
            issues=tuple(issues),
        )

    try:
        slots, option_issues = _catalog_options(
            cache,
            variation_file.parsed,
            model_name,
            cancellation,
        )
        issues.extend(option_issues)
    except (AttributeError, TypeError, ValueError, IndexError) as exc:
        slots = {}
        issues.append(
            _issue(
                "outfit.variation_invalid",
                f"Could not inspect ped variation metadata: {exc}",
                asset_path=variation_asset.path if variation_asset is not None else None,
            )
        )

    catalog = PedOutfitCatalog(
        model_name=model_name,
        model_hash=model_hash,
        variation_asset=variation_asset,
        slots=MappingProxyType(slots),
        issues=tuple(issues),
    )
    cache._ped_outfit_catalog_cache[cache_key] = catalog
    return catalog


def _invalid_variant(
    slot: int,
    drawable: int,
    code: str,
    message: str,
) -> ResolvedPedOutfitVariant:
    option = PedOutfitOption(
        slot=slot,
        drawable=drawable,
        texture_count=0,
        is_prop=slot >= 12,
        file_stem=None,
    )
    return ResolvedPedOutfitVariant(
        option=option,
        issues=(_issue(code, message, severity="error"),),
    )


def _load_selected_file(
    cache: GameFileCache,
    asset: AssetRecord,
    issues: list[CutsceneResolveIssue],
) -> GameFile | None:
    try:
        return cache.load_asset(asset)
    except Exception as exc:  # noqa: BLE001 - asset failures are diagnostics
        issues.append(
            _issue(
                "outfit.asset_load_failed",
                f"Unable to load {asset.path}: {type(exc).__name__}: {exc}",
                asset_path=asset.path,
            )
        )
        return None


def resolve_ped_outfit_variant(
    cache: GameFileCache,
    catalog: PedOutfitCatalog,
    slot: int,
    drawable: int,
    texture: int = 0,
    *,
    cancellation: CutsceneResolutionCancellation | None = None,
) -> ResolvedPedOutfitVariant:
    check_cutscene_resolution_cancelled(cancellation)
    slot_value = int(slot)
    drawable_value = int(drawable)
    texture_value = int(texture)
    options = catalog.slots.get(slot_value)
    if options is None:
        return _invalid_variant(
            slot_value,
            drawable_value,
            "outfit.slot_invalid",
            f"Ped outfit slot {slot_value} is not present",
        )
    option = next(
        (item for item in options if item.drawable == drawable_value),
        None,
    )
    if option is None:
        return _invalid_variant(
            slot_value,
            drawable_value,
            "outfit.drawable_invalid",
            f"Drawable {drawable_value} is not valid for slot {slot_value}",
        )
    if texture_value < 0 or texture_value >= option.texture_count:
        return ResolvedPedOutfitVariant(
            option=option,
            issues=(
                _issue(
                    "outfit.texture_invalid",
                    f"Texture {texture_value} is not valid for slot {slot_value} drawable {drawable_value}",
                    severity="error",
                ),
            ),
        )

    issues: list[CutsceneResolveIssue] = []
    drawable_files = []
    if option.drawable_asset is not None:
        check_cutscene_resolution_cancelled(cancellation)
        loaded = _load_selected_file(cache, option.drawable_asset, issues)
        if loaded is not None:
            drawable_files.append(loaded)
    else:
        issues.append(
            _issue(
                "outfit.drawable_unresolved",
                f"No drawable asset matched {option.file_stem}",
            )
        )

    texture_letter = chr(ord("a") + texture_value)
    if option.is_prop:
        prefix = option.file_stem.rsplit("_", 1)[0] if option.file_stem else ""
    else:
        prefix = option.file_stem.split("_", 1)[0] if option.file_stem else ""
    selected = next(
        (
            asset
            for asset in option.texture_assets
            if re.match(
                rf"^{re.escape(prefix)}_diff_{drawable_value:03d}_{texture_letter}(?:_|$)",
                asset.stem.lower(),
            )
        ),
        None,
    )
    if selected is None and len(option.texture_assets) == 1:
        selected = option.texture_assets[0]

    texture_files = []
    if selected is not None:
        for asset, _depth in cache.iter_texture_dictionary_chain(selected):
            check_cutscene_resolution_cancelled(cancellation)
            loaded = _load_selected_file(cache, asset, issues)
            if loaded is not None:
                texture_files.append(loaded)
    elif option.texture_count:
        issues.append(
            _issue(
                "outfit.texture_unresolved",
                f"No texture dictionary matched slot {slot_value} drawable {drawable_value} texture {texture_value}",
            )
        )

    return ResolvedPedOutfitVariant(
        option=option,
        drawable_files=tuple(drawable_files),
        texture_files=tuple(texture_files),
        issues=tuple(issues),
    )


__all__ = ["resolve_ped_outfit_catalog", "resolve_ped_outfit_variant"]
