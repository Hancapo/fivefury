from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..metahash import HashLike, MetaHash
from .enums import ManifestFlags
from .model import ImapDependencies, ItypDependencies, PackFileMetaData
from .resource import Ymf


def create_ymf_for_ymaps(
    ymaps: Iterable[Any] | None = None,
    *,
    cache: Any | None = None,
    ytyps: Iterable[Any] = (),
    dependencies: Mapping[HashLike, Iterable[HashLike]] | None = None,
    interior_ymaps: Iterable[HashLike] = (),
    infer_interior_flags: bool = True,
    include_empty_imaps: bool = False,
    include_ytyp_dependencies: bool = True,
    strict: bool = False,
    name: str = "_manifest",
) -> Ymf:
    """Build a pack manifest for a set of streamed map files.

    The game uses the manifest to connect streamed IMAP/YMAP files to the ITYP/YTYP
    files that define the archetypes used by those maps. A cache lets this resolve
    vanilla or already-scanned custom archetypes automatically.
    """

    manifest = build_ymf_manifest_for_ymaps(
        ymaps,
        cache=cache,
        ytyps=ytyps,
        dependencies=dependencies,
        interior_ymaps=interior_ymaps,
        infer_interior_flags=infer_interior_flags,
        include_empty_imaps=include_empty_imaps,
        include_ytyp_dependencies=include_ytyp_dependencies,
        strict=strict,
    )
    return Ymf.from_manifest(manifest, name=name)


def build_ymf_for_ymaps(*args: Any, **kwargs: Any) -> Ymf:
    return create_ymf_for_ymaps(*args, **kwargs)


def build_ymf_manifest_for_ymaps(
    ymaps: Iterable[Any] | None = None,
    *,
    cache: Any | None = None,
    ytyps: Iterable[Any] = (),
    dependencies: Mapping[HashLike, Iterable[HashLike]] | None = None,
    interior_ymaps: Iterable[HashLike] = (),
    infer_interior_flags: bool = True,
    include_empty_imaps: bool = False,
    include_ytyp_dependencies: bool = True,
    strict: bool = False,
) -> PackFileMetaData:
    archetype_to_ytyp, ytyp_dependency_map = _build_ytyp_dependency_index(cache=cache, ytyps=ytyps)
    explicit_dependencies = _normalize_dependency_map(dependencies)
    interior_hashes = {int(MetaHash.from_value(item)) for item in interior_ymaps}
    missing_archetypes: dict[int, set[int]] = {}
    imap_entries: list[ImapDependencies] = []
    used_ytyps: list[MetaHash] = []
    used_ytyp_hashes: set[int] = set()

    for ymap, name_hint in _iter_ymap_inputs(ymaps, cache=cache):
        ymap_name = _prefer_named_hash(getattr(ymap, "name", 0), name_hint)
        ymap_hash = int(ymap_name)
        dependency_names: list[MetaHash] = []
        seen_dependencies: set[int] = set()

        for dependency in explicit_dependencies.get(ymap_hash, ()):
            _append_unique_hash(dependency_names, seen_dependencies, dependency)

        for archetype_name in _iter_ymap_archetype_names(ymap):
            archetype_hash = int(archetype_name)
            ytyp_name = archetype_to_ytyp.get(archetype_hash)
            if ytyp_name is None:
                missing_archetypes.setdefault(ymap_hash, set()).add(archetype_hash)
                continue
            _append_unique_hash(dependency_names, seen_dependencies, ytyp_name)

        for dependency in dependency_names:
            _append_unique_hash(used_ytyps, used_ytyp_hashes, dependency)

        if dependency_names or include_empty_imaps:
            flags = ManifestFlags.NONE
            if ymap_hash in interior_hashes or (infer_interior_flags and _ymap_has_mlo_instance(ymap)):
                flags |= ManifestFlags.INTERIOR_DATA
            imap_entries.append(ImapDependencies(imap_name=ymap_name, ityp_dependencies=dependency_names, flags=flags))

    if strict and missing_archetypes:
        details = ", ".join(
            f"0x{ymap_hash:08X}: {', '.join(f'0x{item:08X}' for item in sorted(archetypes))}"
            for ymap_hash, archetypes in sorted(missing_archetypes.items())
        )
        raise ValueError(f"Unable to resolve YMF archetype dependencies: {details}")

    ityp_entries = _build_used_ytyp_dependency_entries(used_ytyps, ytyp_dependency_map) if include_ytyp_dependencies else []
    return PackFileMetaData(imap_dependencies_2=imap_entries, ityp_dependencies_2=ityp_entries)


def _build_ytyp_dependency_index(
    *,
    cache: Any | None,
    ytyps: Iterable[Any],
) -> tuple[dict[int, MetaHash], dict[int, tuple[MetaHash, list[MetaHash]]]]:
    archetype_to_ytyp: dict[int, MetaHash] = {}
    ytyp_dependencies: dict[int, tuple[MetaHash, list[MetaHash]]] = {}

    for ytyp, name_hint in _iter_ytyp_inputs(ytyps):
        _index_ytyp(ytyp, name_hint, archetype_to_ytyp, ytyp_dependencies)

    if cache is None or not hasattr(cache, "iter_assets"):
        return archetype_to_ytyp, ytyp_dependencies

    from ..gamefile import GameFileType

    for asset in cache.iter_assets(kind=GameFileType.YTYP):
        game_file = cache.get_file(asset) if hasattr(cache, "get_file") else None
        ytyp = getattr(game_file, "parsed", None)
        if ytyp is None:
            continue
        _index_ytyp(ytyp, getattr(asset, "stem", None), archetype_to_ytyp, ytyp_dependencies)

    return archetype_to_ytyp, ytyp_dependencies


def _index_ytyp(
    ytyp: Any,
    name_hint: str | None,
    archetype_to_ytyp: dict[int, MetaHash],
    ytyp_dependencies: dict[int, tuple[MetaHash, list[MetaHash]]],
) -> None:
    if not hasattr(ytyp, "archetypes"):
        return
    ytyp_name = _prefer_named_hash(getattr(ytyp, "name", 0), name_hint)
    ytyp_hash = int(ytyp_name)
    dependencies = [_dependency_name(item) for item in getattr(ytyp, "dependencies", []) or []]
    ytyp_dependencies[ytyp_hash] = (ytyp_name, dependencies)
    for archetype in getattr(ytyp, "archetypes", []) or []:
        archetype_name = getattr(archetype, "name", None)
        if archetype_name in (None, "", 0):
            continue
        archetype_to_ytyp[int(MetaHash.from_value(archetype_name))] = ytyp_name


def _iter_ytyp_inputs(ytyps: Iterable[Any]) -> Iterable[tuple[Any, str | None]]:
    for source in ytyps:
        if hasattr(source, "archetypes"):
            yield source, None
            continue
        if isinstance(source, (bytes, bytearray, memoryview)):
            from ..ytyp import read_ytyp

            yield read_ytyp(bytes(source)), None
            continue
        from pathlib import Path

        path = Path(str(source))
        if path.is_file():
            from ..ytyp import read_ytyp

            yield read_ytyp(path.read_bytes()), path.stem


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


def _dependency_name(value: Any) -> MetaHash:
    if hasattr(value, "name"):
        return MetaHash.from_value(getattr(value, "name"))
    return MetaHash.from_value(value)


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
    ytyp_dependency_map: dict[int, tuple[MetaHash, list[MetaHash]]],
) -> list[ItypDependencies]:
    entries: list[ItypDependencies] = []
    queued = list(used_ytyps)
    seen_ytyps = {int(item) for item in queued}
    emitted: set[int] = set()
    while queued:
        ytyp_name = queued.pop(0)
        ytyp_hash = int(ytyp_name)
        if ytyp_hash in emitted:
            continue
        emitted.add(ytyp_hash)
        indexed = ytyp_dependency_map.get(ytyp_hash)
        if indexed is None:
            continue
        source_name, dependencies = indexed
        if dependencies:
            entries.append(ItypDependencies(ityp_name=source_name, ityp_dependencies=dependencies))
        for dependency in dependencies:
            dependency_hash = int(dependency)
            if dependency_hash in seen_ytyps:
                continue
            seen_ytyps.add(dependency_hash)
            queued.append(dependency)
    return entries
