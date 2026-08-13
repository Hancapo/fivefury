from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from ..common import hash_value
from ..gamefile import GameFileType
from ..ytd import Texture, TextureDescriptor
from .textures import TextureCatalogEntry

if TYPE_CHECKING:
    from .core import GameFileCache


class TextureResolutionStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    INVALID_CONTEXT = "invalid_context"


class TextureResolutionSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TextureResolutionIssue:
    severity: TextureResolutionSeverity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class TextureResolutionStep:
    action: str
    outcome: str
    detail: str
    container_path: str = ""
    parent_depth: int = 0


@dataclass(slots=True)
class TextureResolutionCandidate:
    descriptor: TextureDescriptor
    container_path: str
    container_name: str
    origin: str
    parent_depth: int = 0
    texture: Texture | None = None


@dataclass(frozen=True, slots=True)
class TextureResolution:
    requested_name: str
    requested_hash: int
    status: TextureResolutionStatus
    selected: TextureResolutionCandidate | None
    candidates: tuple[TextureResolutionCandidate, ...]
    steps: tuple[TextureResolutionStep, ...]
    issues: tuple[TextureResolutionIssue, ...]

    @property
    def texture(self) -> Texture | None:
        return self.selected.texture if self.selected is not None else None

    @property
    def found(self) -> bool:
        return self.status is TextureResolutionStatus.FOUND


def _descriptor_from_texture(texture: Texture, *, index: int, game: str) -> TextureDescriptor:
    return TextureDescriptor(
        name=texture.name,
        name_hash=hash_value(texture.name),
        width=texture.width,
        height=texture.height,
        format=texture.format,
        mip_count=texture.mip_count,
        usage=texture.usage,
        usage_flags=texture.usage_flags,
        data_size=len(texture.data),
        index=index,
        game=game,
    )


def _candidate_from_catalog(
    entry: TextureCatalogEntry,
    *,
    origin: str,
    parent_depth: int,
) -> TextureResolutionCandidate:
    return TextureResolutionCandidate(
        descriptor=entry.descriptor,
        container_path=entry.dictionary_path,
        container_name=entry.dictionary_name,
        origin=origin,
        parent_depth=parent_depth,
    )


def resolve_texture(
    cache: GameFileCache,
    value: str | int,
    *,
    asset: Any | None = None,
    dictionary: Any | None = None,
    include_parents: bool = True,
    allow_global: bool = False,
    materialize: bool = True,
) -> TextureResolution:
    if asset is not None and dictionary is not None:
        raise ValueError("asset and dictionary are mutually exclusive texture contexts")
    requested_hash = hash_value(value)
    requested_name = str(value) if not isinstance(value, int) else f"0x{requested_hash:08X}"
    candidates: list[TextureResolutionCandidate] = []
    steps: list[TextureResolutionStep] = []
    issues: list[TextureResolutionIssue] = []
    seen: set[tuple[str, int]] = set()

    direct_asset = None
    if asset is not None:
        direct_asset = cache._coerce_asset(asset)
        if (
            direct_asset is None
            and cache._coerce_ymap(asset) is None
            and not hasattr(asset, "texture_dictionary")
        ):
            issues.append(
                TextureResolutionIssue(
                    TextureResolutionSeverity.ERROR,
                    "context_not_found",
                    f"Texture context {asset!r} is not indexed or readable",
                )
            )
            return TextureResolution(
                requested_name,
                requested_hash,
                TextureResolutionStatus.INVALID_CONTEXT,
                None,
                (),
                (),
                tuple(issues),
            )
        try:
            embedded_references = tuple(cache._iter_embedded_texture_refs(asset))
        except (OSError, ValueError):
            embedded_references = ()
            issues.append(
                TextureResolutionIssue(
                    TextureResolutionSeverity.INFO,
                    "embedded_dictionary_unreadable",
                    "The primary resource does not expose a readable embedded texture dictionary",
                )
            )
        for index, reference in enumerate(embedded_references):
            if hash_value(reference.texture.name) != requested_hash:
                continue
            key = (reference.container_path or reference.container_name, requested_hash)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                TextureResolutionCandidate(
                    descriptor=_descriptor_from_texture(
                        reference.texture,
                        index=index,
                        game="embedded",
                    ),
                    container_path=reference.container_path,
                    container_name=reference.container_name,
                    origin="embedded",
                    texture=reference.texture,
                )
            )
        steps.append(
            TextureResolutionStep(
                "embedded",
                "found" if candidates else "not_found",
                "Searched texture dictionaries embedded in the primary resource",
            )
        )

    context = dictionary if dictionary is not None else (direct_asset or asset)

    dictionary_assets = (
        list(cache.iter_texture_dictionary_chain(context, include_parents=include_parents))
        if context is not None
        else []
    )
    for dictionary_asset, parent_depth in dictionary_assets:
        catalog = cache.texture_catalog.dictionary(dictionary_asset)
        descriptor = catalog.find(requested_hash) if catalog is not None else None
        steps.append(
            TextureResolutionStep(
                "dictionary",
                "found" if descriptor is not None else "not_found",
                f"Searched texture dictionary '{dictionary_asset.stem}'",
                container_path=dictionary_asset.path,
                parent_depth=parent_depth,
            )
        )
        if descriptor is None:
            continue
        key = (dictionary_asset.path, requested_hash)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            _candidate_from_catalog(
                TextureCatalogEntry(
                    descriptor,
                    dictionary_asset.path,
                    dictionary_asset.stem,
                    dictionary_asset.short_hash,
                ),
                origin="ytd" if parent_depth == 0 else "gtxd_parent",
                parent_depth=parent_depth,
            )
        )

    if asset is not None:
        primary = cache._coerce_asset(asset)
        same_name = (
            cache.get_asset(primary.stem, kind=GameFileType.YTD)
            if primary is not None and primary.kind is not GameFileType.YTD
            else None
        )
        if same_name is not None and all(
            item[0].path != same_name.path for item in dictionary_assets
        ):
            catalog = cache.texture_catalog.dictionary(same_name)
            descriptor = catalog.find(requested_hash) if catalog is not None else None
            steps.append(
                TextureResolutionStep(
                    "same_name_fallback",
                    "found" if descriptor is not None else "not_found",
                    f"Searched same-name texture dictionary '{same_name.stem}'",
                    container_path=same_name.path,
                )
            )
            if descriptor is not None and (same_name.path, requested_hash) not in seen:
                seen.add((same_name.path, requested_hash))
                candidates.append(
                    _candidate_from_catalog(
                        TextureCatalogEntry(
                            descriptor,
                            same_name.path,
                            same_name.stem,
                            same_name.short_hash,
                        ),
                        origin="same_name_fallback",
                        parent_depth=0,
                    )
                )

    if allow_global and not candidates:
        global_matches = cache.texture_catalog.find(requested_hash)
        for entry in global_matches:
            key = (entry.dictionary_path, requested_hash)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                _candidate_from_catalog(entry, origin="global", parent_depth=0)
            )
        steps.append(
            TextureResolutionStep(
                "global",
                "found" if global_matches else "not_found",
                "Searched the global texture catalog by hash",
            )
        )
        if global_matches:
            issues.append(
                TextureResolutionIssue(
                    TextureResolutionSeverity.WARNING,
                    "global_fallback",
                    "Texture resolution required a global search outside the asset dependency chain",
                )
            )

    selected = candidates[0] if candidates else None
    if selected is not None and materialize and selected.texture is None:
        ytd = cache._coerce_ytd(selected.container_path)
        selected.texture = (
            ytd.get_texture(selected.descriptor.name) if ytd is not None else None
        )
        if selected.texture is None:
            issues.append(
                TextureResolutionIssue(
                    TextureResolutionSeverity.ERROR,
                    "materialization_failed",
                    f"Texture metadata was indexed but '{selected.container_path}' could not be loaded",
                )
            )
    if len(candidates) > 1:
        issues.append(
            TextureResolutionIssue(
                TextureResolutionSeverity.INFO,
                "shadowed_candidates",
                f"{len(candidates) - 1} lower-priority texture candidate(s) were shadowed",
            )
        )
    if selected is None:
        issues.append(
            TextureResolutionIssue(
                TextureResolutionSeverity.WARNING,
                "texture_not_found",
                f"Texture '{requested_name}' was not found in the permitted search scope",
            )
        )
    return TextureResolution(
        requested_name=requested_name,
        requested_hash=requested_hash,
        status=(
            TextureResolutionStatus.FOUND
            if selected is not None
            else TextureResolutionStatus.NOT_FOUND
        ),
        selected=selected,
        candidates=tuple(candidates),
        steps=tuple(steps),
        issues=tuple(issues),
    )


__all__ = [
    "TextureResolution",
    "TextureResolutionCandidate",
    "TextureResolutionIssue",
    "TextureResolutionSeverity",
    "TextureResolutionStatus",
    "TextureResolutionStep",
    "resolve_texture",
]
