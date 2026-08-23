from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from typing import Any

from ..authoring import BuildContext, asset_name
from ..metahash import HashLike, MetaHash
from ..ymap.mlo_validation import mlo_collisions_by_hash
from .dependencies import YmfDependencyIndex
from .enums import ManifestFlags
from .model import (
    ImapDependencies,
    InteriorBoundsFile,
    ItypDependencies,
    PackFileMetaData,
)
from .resource import Ymf


def build_ymf_for_ymaps(
    ymaps: Iterable[Any] | None = None,
    *,
    context: BuildContext | None = None,
    dependency_index: YmfDependencyIndex | None = None,
    dependencies: Mapping[HashLike, Iterable[HashLike]] | None = None,
    interior_bounds: Mapping[HashLike, Iterable[HashLike]] | None = None,
    interior_ymaps: Iterable[HashLike] = (),
    infer_interior_flags: bool = True,
    infer_interior_bounds: bool = True,
    include_empty_imaps: bool = False,
    include_ytyp_dependencies: bool = True,
    permanent_ytyps: Iterable[HashLike] = (),
    name: str = "_manifest",
) -> Ymf:
    """Build a pack manifest for a set of streamed map files.

    The game uses the manifest to connect streamed IMAP/YMAP files to the ITYP/YTYP
    files that define the archetypes used by those maps. A cache lets this resolve
    vanilla or already-scanned custom archetypes automatically.
    """

    manifest = build_ymf_manifest_for_ymaps(
        ymaps,
        context=context,
        dependency_index=dependency_index,
        dependencies=dependencies,
        interior_bounds=interior_bounds,
        interior_ymaps=interior_ymaps,
        infer_interior_flags=infer_interior_flags,
        infer_interior_bounds=infer_interior_bounds,
        include_empty_imaps=include_empty_imaps,
        include_ytyp_dependencies=include_ytyp_dependencies,
    )
    return Ymf.from_manifest(manifest, name=name, permanent_ytyps=permanent_ytyps)


def build_ymf_manifest_for_ymaps(
    ymaps: Iterable[Any] | None = None,
    *,
    context: BuildContext | None = None,
    dependency_index: YmfDependencyIndex | None = None,
    dependencies: Mapping[HashLike, Iterable[HashLike]] | None = None,
    interior_bounds: Mapping[HashLike, Iterable[HashLike]] | None = None,
    interior_ymaps: Iterable[HashLike] = (),
    infer_interior_flags: bool = True,
    infer_interior_bounds: bool = True,
    include_empty_imaps: bool = False,
    include_ytyp_dependencies: bool = True,
) -> PackFileMetaData:
    context = context or BuildContext(strict=False)
    cache = context.cache
    ybns = _context_ybns(context)
    dependency_index = dependency_index or YmfDependencyIndex.from_context(context)
    explicit_dependencies = _normalize_dependency_map(dependencies)
    interior_hashes = {int(MetaHash.from_value(item)) for item in interior_ymaps}
    missing_archetypes: dict[int, set[int]] = {}
    imap_entries: list[ImapDependencies] = []
    used_ytyps: list[MetaHash] = []
    used_ytyp_hashes: set[int] = set()
    used_mlo_hashes: set[int] = set()

    for ymap, name_hint in _iter_ymap_inputs(ymaps, cache=cache):
        ymap_name = _prefer_named_hash(getattr(ymap, "name", 0), name_hint)
        ymap_hash = int(ymap_name)
        dependency_names: list[MetaHash] = []
        seen_dependencies: set[int] = set()

        for dependency in explicit_dependencies.get(ymap_hash, ()):
            _append_unique_hash(dependency_names, seen_dependencies, dependency)

        for archetype_name in _iter_ymap_archetype_names(ymap):
            archetype_hash = int(archetype_name)
            archetype = dependency_index.archetype(archetype_hash)
            if archetype is not None and archetype.is_mlo:
                used_mlo_hashes.add(archetype_hash)
            if archetype is None:
                missing_archetypes.setdefault(ymap_hash, set()).add(archetype_hash)
                continue
            _append_unique_hash(dependency_names, seen_dependencies, archetype.ytyp)

        for dependency in dependency_names:
            _append_unique_hash(used_ytyps, used_ytyp_hashes, dependency)

        if dependency_names or include_empty_imaps:
            flags = ManifestFlags.NONE
            if ymap_hash in interior_hashes or (infer_interior_flags and _ymap_has_mlo_instance(ymap)):
                flags |= ManifestFlags.INTERIOR_DATA
            imap_entries.append(ImapDependencies(imap_name=ymap_name, ityp_dependencies=dependency_names, flags=flags))

    if context.strict and missing_archetypes:
        details = ", ".join(
            f"0x{ymap_hash:08X}: {', '.join(f'0x{item:08X}' for item in sorted(archetypes))}"
            for ymap_hash, archetypes in sorted(missing_archetypes.items())
        )
        raise ValueError(f"Unable to resolve YMF archetype dependencies: {details}")

    mlo_hashes = used_mlo_hashes | set(dependency_index.mlo_archetype_hashes)
    mlo_ytyps = frozenset(
        int(binding.ytyp)
        for name_hash in mlo_hashes
        if (binding := dependency_index.archetype(name_hash)) is not None
    )
    ityp_entries = (
        _build_used_ytyp_dependency_entries(
            used_ytyps,
            dependency_index,
            mlo_ytyps=mlo_ytyps if infer_interior_flags else frozenset(),
        )
        if include_ytyp_dependencies
        else []
    )
    interior_entries = _build_interior_bounds(
        interior_bounds,
        mlo_hashes=mlo_hashes,
        ybns=ybns if infer_interior_bounds else None,
    )
    return PackFileMetaData(
        imap_dependencies_2=imap_entries,
        ityp_dependencies_2=ityp_entries,
        interiors=interior_entries,
    )


def _context_ybns(context: BuildContext) -> dict[str, Any]:
    from ..ybn import Ybn

    return {
        asset_name(path): asset
        for path, asset in context.assets.items()
        if isinstance(asset, Ybn)
    }


def _build_interior_bounds(
    explicit: Mapping[HashLike, Iterable[HashLike]] | None,
    *,
    mlo_hashes: set[int],
    ybns: Any,
) -> list[InteriorBoundsFile]:
    entries: dict[int, InteriorBoundsFile] = {}
    for name, bounds in (explicit or {}).items():
        interior_name = MetaHash.from_value(name)
        bound_names = [MetaHash.from_value(bound) for bound in bounds]
        _validate_interior_bounds(interior_name, bound_names)
        entries[int(interior_name)] = InteriorBoundsFile(interior_name, bound_names)

    for archetype_hash in mlo_hashes & set(mlo_collisions_by_hash(ybns)):
        if archetype_hash in entries:
            continue
        name = MetaHash.from_value(archetype_hash)
        entries[archetype_hash] = InteriorBoundsFile(name, [name])
    return list(entries.values())


def _validate_interior_bounds(name: MetaHash, bounds: list[MetaHash]) -> None:
    if len(bounds) not in (1, 2):
        raise ValueError(f"MLO interior {name} must reference one or two YBN bounds")
    if int(name) not in {int(bound) for bound in bounds}:
        raise ValueError(f"MLO interior {name} must include a YBN with the same name")


def _iter_ymap_inputs(ymaps: Iterable[Any] | None, *, cache: Any | None) -> Iterable[tuple[Any, str | None]]:
    if ymaps is None:
        if cache is None or not hasattr(cache, "iter_assets"):
            return
        from ..gamefile import GameFileType

        ymaps = cache.iter_assets(kind=GameFileType.YMAP)

    for source in ymaps:
        if hasattr(source, "entities"):
            yield source, None
            continue
        if cache is not None and hasattr(cache, "get_file"):
            game_file = cache.get_file(source)
            parsed = getattr(game_file, "parsed", None)
            if parsed is not None and hasattr(parsed, "entities"):
                yield parsed, getattr(source, "stem", None)
                continue
        if isinstance(source, (bytes, bytearray, memoryview)):
            from ..ymap import read_ymap

            yield read_ymap(bytes(source)), None
            continue
        from pathlib import Path

        path = Path(str(source))
        if path.is_file():
            from ..ymap import read_ymap

            yield read_ymap(path.read_bytes()), path.stem


def _prefer_named_hash(value: Any, name_hint: str | None) -> MetaHash:
    if isinstance(value, MetaHash) and isinstance(value.raw, str) and value.raw:
        return value
    if isinstance(value, str) and value:
        return MetaHash.from_value(value)
    if name_hint:
        return MetaHash.from_value(name_hint)
    return MetaHash.from_value(value or 0)


def _append_unique_hash(output: list[MetaHash], seen: set[int], value: Any) -> None:
    hashed = MetaHash.from_value(value)
    key = int(hashed)
    if key == 0 or key in seen:
        return
    seen.add(key)
    output.append(hashed)


def _iter_ymap_archetype_names(ymap: Any) -> Iterable[MetaHash]:
    seen: set[int] = set()
    for entity in getattr(ymap, "entities", []) or []:
        archetype_name = getattr(entity, "archetype_name", None)
        if archetype_name in (None, "", 0):
            continue
        hashed = MetaHash.from_value(archetype_name)
        key = int(hashed)
        if key == 0 or key in seen:
            continue
        seen.add(key)
        yield hashed


def _ymap_has_mlo_instance(ymap: Any) -> bool:
    for entity in getattr(ymap, "entities", []) or []:
        if entity.__class__.__name__ == "MloInstanceDef":
            return True
    return False


def _normalize_dependency_map(dependencies: Mapping[HashLike, Iterable[HashLike]] | None) -> dict[int, list[MetaHash]]:
    if not dependencies:
        return {}
    result: dict[int, list[MetaHash]] = {}
    for key, values in dependencies.items():
        result[int(MetaHash.from_value(key))] = [MetaHash.from_value(value) for value in values]
    return result


def _build_used_ytyp_dependency_entries(
    used_ytyps: list[MetaHash],
    dependency_index: YmfDependencyIndex,
    *,
    mlo_ytyps: frozenset[int] = frozenset(),
) -> list[ItypDependencies]:
    entries: list[ItypDependencies] = []
    queued = deque(used_ytyps)
    seen_ytyps = {int(item) for item in queued}
    emitted: set[int] = set()
    while queued:
        ytyp_name = queued.popleft()
        ytyp_hash = int(ytyp_name)
        if ytyp_hash in emitted:
            continue
        emitted.add(ytyp_hash)
        indexed = dependency_index.ytyp(ytyp_hash)
        if indexed is None:
            continue
        source_name = indexed.name
        dependencies = indexed.dependencies
        flags = ManifestFlags.INTERIOR_DATA if ytyp_hash in mlo_ytyps else ManifestFlags(0)
        if dependencies or flags:
            entries.append(
                ItypDependencies(
                    ityp_name=source_name,
                    ityp_dependencies=dependencies,
                    flags=flags,
                )
            )
        for dependency in dependencies:
            dependency_hash = int(dependency)
            if dependency_hash in seen_ytyps:
                continue
            seen_ytyps.add(dependency_hash)
            queued.append(dependency)
    return entries
