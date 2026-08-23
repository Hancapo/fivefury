from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ..authoring import BuildContext
from ..metahash import HashLike, MetaHash


@dataclass(frozen=True, slots=True)
class YmfArchetypeBinding:
    name: MetaHash
    ytyp: MetaHash
    is_mlo: bool


@dataclass(frozen=True, slots=True)
class YmfYtypBinding:
    name: MetaHash
    dependencies: tuple[MetaHash, ...]


@dataclass(frozen=True, slots=True, init=False)
class YmfDependencyIndex:
    """Immutable archetype and YTYP dependency index shared by YMF builds."""

    _archetypes: Mapping[int, YmfArchetypeBinding]
    _ytyps: Mapping[int, YmfYtypBinding]
    mlo_archetype_hashes: frozenset[int]

    def __init__(
        self,
        archetypes: Iterable[YmfArchetypeBinding],
        ytyps: Iterable[YmfYtypBinding],
    ) -> None:
        archetype_map = {int(item.name): item for item in archetypes}
        ytyp_map = {int(item.name): item for item in ytyps}
        object.__setattr__(self, "_archetypes", MappingProxyType(archetype_map))
        object.__setattr__(self, "_ytyps", MappingProxyType(ytyp_map))
        object.__setattr__(
            self,
            "mlo_archetype_hashes",
            frozenset(
                name_hash
                for name_hash, binding in archetype_map.items()
                if binding.is_mlo
            ),
        )

    @classmethod
    def from_context(cls, context: BuildContext) -> YmfDependencyIndex:
        from ..ytyp import Ytyp

        return cls._from_sources(
            context.assets.of_type(Ytyp),
            cache=context.cache,
        )

    @classmethod
    def _from_sources(
        cls,
        ytyps: Iterable[Any],
        *,
        cache: Any | None = None,
    ) -> YmfDependencyIndex:
        archetypes: dict[int, YmfArchetypeBinding] = {}
        indexed_ytyps: dict[int, YmfYtypBinding] = {}

        for ytyp, name_hint in _iter_ytyp_inputs(ytyps):
            _index_ytyp(ytyp, name_hint, archetypes, indexed_ytyps)

        if cache is not None and hasattr(cache, "iter_assets"):
            from ..gamefile import GameFileType

            for asset in cache.iter_assets(kind=GameFileType.YTYP):
                game_file = (
                    cache.get_file(asset) if hasattr(cache, "get_file") else None
                )
                ytyp = getattr(game_file, "parsed", None)
                if ytyp is not None:
                    _index_ytyp(
                        ytyp,
                        getattr(asset, "stem", None),
                        archetypes,
                        indexed_ytyps,
                    )

        return cls(archetypes.values(), indexed_ytyps.values())

    def archetype(self, value: HashLike) -> YmfArchetypeBinding | None:
        return self._archetypes.get(int(MetaHash.from_value(value)))

    def ytyp(self, value: HashLike) -> YmfYtypBinding | None:
        return self._ytyps.get(int(MetaHash.from_value(value)))


def _index_ytyp(
    ytyp: Any,
    name_hint: str | None,
    archetypes: dict[int, YmfArchetypeBinding],
    ytyps: dict[int, YmfYtypBinding],
) -> None:
    if not hasattr(ytyp, "archetypes"):
        return
    ytyp_name = _prefer_named_hash(getattr(ytyp, "name", 0), name_hint)
    ytyps[int(ytyp_name)] = YmfYtypBinding(
        ytyp_name,
        tuple(
            _dependency_name(item) for item in (getattr(ytyp, "dependencies", []) or [])
        ),
    )
    for archetype in getattr(ytyp, "archetypes", []) or []:
        raw_name = getattr(archetype, "name", None)
        if raw_name in (None, "", 0):
            continue
        name = MetaHash.from_value(raw_name)
        archetypes[int(name)] = YmfArchetypeBinding(
            name,
            ytyp_name,
            hasattr(archetype, "rooms") and hasattr(archetype, "portals"),
        )


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


def _prefer_named_hash(value: Any, name_hint: str | None) -> MetaHash:
    if isinstance(value, MetaHash) and isinstance(value.raw, str) and value.raw:
        return value
    if isinstance(value, str) and value:
        return MetaHash.from_value(value)
    if name_hint:
        return MetaHash.from_value(name_hint)
    return MetaHash.from_value(value or 0)


def _dependency_name(value: Any) -> MetaHash:
    if hasattr(value, "name"):
        return MetaHash.from_value(value.name)
    return MetaHash.from_value(value)


__all__ = [
    "YmfArchetypeBinding",
    "YmfDependencyIndex",
    "YmfYtypBinding",
]
