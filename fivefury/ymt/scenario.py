from __future__ import annotations

import dataclasses
from typing import Any

from ..metahash import MetaHash
from ..pso import PsoHashedString, PsoNode


@dataclasses.dataclass(slots=True, frozen=True)
class YmtAabb:
    minimum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    maximum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    minimum_w: float = 0.0
    maximum_w: float = 0.0

    @classmethod
    def from_value(cls, value: Any) -> "YmtAabb":
        if isinstance(value, PsoNode):
            return cls.from_mapping(value.fields or {})
        if isinstance(value, dict):
            return cls.from_mapping(value)
        return cls()

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "YmtAabb":
        minimum = _vec4(_field(value, "min", "hash_FE2F0903"), default=(0.0, 0.0, 0.0, 0.0))
        maximum = _vec4(_field(value, "max", "hash_606EDCC4"), default=(0.0, 0.0, 0.0, 0.0))
        return cls(
            minimum=minimum[:3],
            maximum=maximum[:3],
            minimum_w=minimum[3],
            maximum_w=maximum[3],
        )

    @property
    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        return self.minimum, self.maximum


@dataclasses.dataclass(slots=True, frozen=True)
class YmtScenarioPointRegionDef:
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    aabb: YmtAabb = dataclasses.field(default_factory=YmtAabb)

    @classmethod
    def from_value(cls, value: Any) -> "YmtScenarioPointRegionDef":
        fields = _fields(value)
        return cls(
            name=MetaHash(_hash_value(_field(fields, "Name", "hash_ACE6443E"))),
            aabb=YmtAabb.from_value(_field(fields, "AABB", "hash_63585F57")),
        )


@dataclasses.dataclass(slots=True, frozen=True)
class YmtScenarioPointGroup:
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    enabled_by_default: bool = False

    @classmethod
    def from_value(cls, value: Any) -> "YmtScenarioPointGroup":
        fields = _fields(value)
        return cls(
            name=MetaHash(_hash_value(_field(fields, "Name", "hash_ACE6443E"))),
            enabled_by_default=bool(_field(fields, "EnabledByDefault", "hash_E9BCEFDB", default=False)),
        )


@dataclasses.dataclass(slots=True, frozen=True)
class YmtScenarioPointManifest:
    version_number: int = 0
    region_defs: list[YmtScenarioPointRegionDef] = dataclasses.field(default_factory=list)
    groups: list[YmtScenarioPointGroup] = dataclasses.field(default_factory=list)
    interior_names: list[MetaHash] = dataclasses.field(default_factory=list)
    raw: PsoNode | None = None

    @classmethod
    def from_pso_node(cls, node: PsoNode) -> "YmtScenarioPointManifest":
        fields = node.fields or {}
        return cls(
            version_number=int(_field(fields, "VersionNumber", "hash_4D0627BB", default=0) or 0),
            region_defs=[YmtScenarioPointRegionDef.from_value(item) for item in _list(_field(fields, "RegionDefs", "hash_DD4D392B"))],
            groups=[YmtScenarioPointGroup.from_value(item) for item in _list(_field(fields, "Groups", "hash_9511BA80"))],
            interior_names=[MetaHash(_hash_value(item)) for item in _list(_field(fields, "InteriorNames", "hash_8F6DD5C4"))],
            raw=node,
        )

    @property
    def region_names(self) -> list[MetaHash]:
        return [region.name for region in self.region_defs]

    @property
    def group_names(self) -> list[MetaHash]:
        return [group.name for group in self.groups]


def _fields(value: Any) -> dict[str, Any]:
    if isinstance(value, PsoNode):
        return value.fields or {}
    if isinstance(value, dict):
        return value
    return {}


def _field(fields: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in fields:
            return fields[name]
    return default


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _hash_value(value: Any) -> int:
    if isinstance(value, PsoHashedString):
        return value.hash
    if isinstance(value, MetaHash):
        return value.uint
    if isinstance(value, str):
        return MetaHash(value).uint
    return int(value or 0)


def _vec4(value: Any, *, default: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if isinstance(value, tuple | list):
        items = [float(item) for item in value[:4]]
        items.extend(default[len(items) :])
        return (items[0], items[1], items[2], items[3])
    return default


__all__ = [
    "YmtAabb",
    "YmtScenarioPointGroup",
    "YmtScenarioPointManifest",
    "YmtScenarioPointRegionDef",
]
