from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ..extensions import EXTENSION_STRUCT_INFOS, extensions_from_meta, extensions_to_meta
from ..extensions.defs import MetaBackedStruct
from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta import Meta, MetaBuilder, RawStruct, read_meta
from ..meta.defs import meta_name
from ..resource import build_rsc7
from ..ymap.defs import _ensure_base_name
from ..ymap.model import _suggest_resource_path

from .archetypes import BaseArchetypeDef, TimeArchetypeDef
from .defs import YTYP_STRUCT_INFOS, YTYP_ENUM_INFOS
from .mlo import MloArchetypeDef

if TYPE_CHECKING:  # pragma: no cover
    from ..rpf import RpfArchive, RpfFileEntry

_ALL_STRUCT_INFOS = list(YTYP_STRUCT_INFOS) + list(EXTENSION_STRUCT_INFOS)


@dataclasses.dataclass(slots=True)
class YtypDependency(MetaHashFieldsMixin):
    """YTYP dependency reference.

    CMapTypes writes dependencies as a hash array. The wrapper keeps high-level
    construction declarative without leaking raw hashes through the public API.
    """

    _hash_fields = ("name",)

    name: MetaHash | HashLike = 0

    def to_meta(self) -> MetaHash:
        return self.name

    @classmethod
    def from_meta(cls, value: MetaHash | HashLike) -> "YtypDependency":
        return cls(name=value)

    def __int__(self) -> int:
        return int(self.name)

    def __str__(self) -> str:
        return str(self.name)


@dataclasses.dataclass(slots=True)
class CompositeEntityType:
    """Opaque YTYP composite entity type entry.

    The format stores these as META payloads. Fivefury preserves unknown entries
    losslessly while still allowing explicit list/object based construction.
    """

    value: Any = None

    def to_meta(self) -> Any:
        return self.value.to_meta() if hasattr(self.value, "to_meta") else self.value

    @classmethod
    def from_meta(cls, value: Any) -> "CompositeEntityType":
        return cls(value=value)


def _coerce_dependency(item: YtypDependency | MetaHash | HashLike) -> YtypDependency:
    return item if isinstance(item, YtypDependency) else YtypDependency(name=item)


def _coerce_composite_entity_type(item: CompositeEntityType | Any) -> CompositeEntityType:
    return item if isinstance(item, CompositeEntityType) else CompositeEntityType(value=item)


@dataclasses.dataclass(slots=True)
class Ytyp(MetaHashFieldsMixin):
    _hash_fields = ("name",)

    extensions: list[Any] = dataclasses.field(default_factory=list)
    archetypes: list[BaseArchetypeDef | TimeArchetypeDef | MloArchetypeDef | RawStruct | dict[str, Any]] = dataclasses.field(default_factory=list)
    name: MetaHash | HashLike = 0
    dependencies: list[YtypDependency | MetaHash | HashLike] = dataclasses.field(default_factory=list)
    composite_entity_types: list[CompositeEntityType | Any] = dataclasses.field(default_factory=list)
    meta_name: str = ""

    def __post_init__(self) -> None:
        self.name = _ensure_base_name(self.name, ".ytyp")
        self.dependencies = [_coerce_dependency(item) for item in self.dependencies]
        self.composite_entity_types = [_coerce_composite_entity_type(item) for item in self.composite_entity_types]

    @property
    def resource_name(self) -> str:
        return self.meta_name

    @resource_name.setter
    def resource_name(self, value: str) -> None:
        self.meta_name = str(value or "")

    def add(self, item: Any) -> Any:
        if isinstance(item, (BaseArchetypeDef, TimeArchetypeDef, MloArchetypeDef)):
            return self.add_archetype(item)
        if isinstance(item, YtypDependency):
            self.dependencies.append(item)
            return item
        if isinstance(item, CompositeEntityType):
            self.composite_entity_types.append(item)
            return item
        if isinstance(item, MetaBackedStruct):
            return self.add_extension(item)
        raise TypeError(f"Unsupported YTYP component: {type(item).__name__}")

    def add_archetype(self, archetype: BaseArchetypeDef | TimeArchetypeDef | MloArchetypeDef) -> Any:
        self.archetypes.append(archetype)
        return archetype

    def add_dependency(self, dependency: YtypDependency | MetaHash | HashLike) -> YtypDependency:
        return self.dependency(dependency)

    def dependency(self, dependency: YtypDependency | MetaHash | HashLike) -> YtypDependency:
        dependency_ref = _coerce_dependency(dependency)
        self.dependencies.append(dependency_ref)
        return dependency_ref

    def add_extension(self, extension: Any) -> Any:
        self.extensions.append(extension)
        return extension

    def composite_entity_type(self, value: CompositeEntityType | Any) -> CompositeEntityType:
        composite = _coerce_composite_entity_type(value)
        self.composite_entity_types.append(composite)
        return composite

    def archetype(self, name: HashLike, **kwargs: Any) -> BaseArchetypeDef:
        archetype = BaseArchetypeDef(name=name, asset_name=kwargs.pop("asset_name", name), **kwargs)
        self.add_archetype(archetype)
        return archetype

    def create_archetype(self, name: HashLike, **kwargs: Any) -> BaseArchetypeDef:
        return self.archetype(name, **kwargs)

    def time_archetype(self, name: HashLike, **kwargs: Any) -> TimeArchetypeDef:
        archetype = TimeArchetypeDef(name=name, asset_name=kwargs.pop("asset_name", name), **kwargs)
        self.add_archetype(archetype)
        return archetype

    def mlo_archetype(self, name: HashLike, **kwargs: Any) -> MloArchetypeDef:
        archetype = MloArchetypeDef(name=name, asset_name=kwargs.pop("asset_name", name), **kwargs)
        self.add_archetype(archetype)
        return archetype

    def suggested_path(self) -> str:
        return _suggest_resource_path(self.name, self.meta_name, ".ytyp", "unnamed.ytyp")

    def build(self) -> "Ytyp":
        self.name = _ensure_base_name(self.name, ".ytyp")
        deduped: list[Any] = []
        seen: set[int] = set()
        for dependency in self.dependencies:
            dependency_ref = _coerce_dependency(dependency)
            key = int(dependency_ref)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(dependency_ref)
        self.dependencies = deduped
        return self

    def validate(self) -> list[str]:
        issues: list[str] = []
        if not self.archetypes:
            issues.append("YTYP has no archetypes")
        return issues

    def to_meta_root(self) -> dict[str, Any]:
        return {
            "extensions": extensions_to_meta(self.extensions),
            "archetypes": [archetype.to_meta() if hasattr(archetype, "to_meta") else archetype for archetype in self.archetypes],
            "name": self.name,
            "dependencies": [dependency.to_meta() if hasattr(dependency, "to_meta") else dependency for dependency in self.dependencies],
            "compositeEntityTypes": [
                item.to_meta() if hasattr(item, "to_meta") else item for item in self.composite_entity_types
            ],
            "_meta_name_hash": meta_name("CMapTypes"),
        }

    def to_bytes(self, *, version: int = 2) -> bytes:
        self.build()
        builder = MetaBuilder(struct_infos=_ALL_STRUCT_INFOS, enum_infos=YTYP_ENUM_INFOS, name=self.meta_name or "")
        system = builder.build(root_name_hash=meta_name("CMapTypes"), root_value=self.to_meta_root())
        system_flags = builder.page_flags | (((version >> 4) & 0xF) << 28)
        return build_rsc7(system, version=version, system_alignment=0x2000, system_flags=system_flags)

    def save(self, path: str | Path | None = None, *, version: int = 2) -> Path:
        destination = Path(path) if path is not None else Path(self.suggested_path())
        destination.write_bytes(self.to_bytes(version=version))
        return destination

    def save_into_rpf(
        self,
        archive: RpfArchive,
        path: str | Path | None = None,
        *,
        version: int = 2,
    ) -> RpfFileEntry:
        target = path if path is not None else self.suggested_path()
        return archive.add_file(target, self.to_bytes(version=version))

    def to_meta(self) -> Meta:
        return Meta(
            Name=self.meta_name or "",
            root_name_hash=meta_name("CMapTypes"),
            root_value=self.to_meta_root(),
            struct_infos=_ALL_STRUCT_INFOS,
            enum_infos=YTYP_ENUM_INFOS,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "Ytyp":
        parsed = read_meta(data)
        root = parsed.decoded_root
        if not isinstance(root, dict) or root.get("_meta_name") != "CMapTypes":
            raise ValueError("META payload is not a CMapTypes/YTYP")
        archetypes: list[Any] = []
        for item in root.get("archetypes", []) or []:
            if isinstance(item, dict) and item.get("_meta_name") == "CTimeArchetypeDef":
                archetypes.append(TimeArchetypeDef.from_meta(item))
            elif isinstance(item, dict) and item.get("_meta_name") == "CMloArchetypeDef":
                archetypes.append(MloArchetypeDef.from_meta(item))
            elif isinstance(item, dict) and item.get("_meta_name") == "CBaseArchetypeDef":
                archetypes.append(BaseArchetypeDef.from_meta(item))
            else:
                archetypes.append(item)
        return cls(
            extensions=extensions_from_meta(root.get("extensions", []) or []),
            archetypes=archetypes,
            name=root.get("name", 0),
            dependencies=[YtypDependency.from_meta(item) for item in (root.get("dependencies", []) or [])],
            composite_entity_types=[
                CompositeEntityType.from_meta(item) for item in (root.get("compositeEntityTypes", []) or [])
            ],
            meta_name=parsed.name,
        )

    @classmethod
    def from_path(cls, path: str | Path) -> "Ytyp":
        return cls.from_bytes(Path(path).read_bytes())


def read_ytyp(data: bytes) -> Ytyp:
    return Ytyp.from_bytes(data)


def save_ytyp(ytyp: Ytyp, path: str | Path | None = None, *, version: int = 2) -> Path:
    return ytyp.save(path, version=version)
