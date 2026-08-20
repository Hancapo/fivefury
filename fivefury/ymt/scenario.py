from __future__ import annotations

import dataclasses
from typing import Any

from ..metahash import MetaHash
from ..pso import PsoNode
from ..pso_values import field as _field
from ..pso_values import fields as _fields
from ..pso_values import hash_value as _hash_value
from ..pso_values import list_value as _list
from ..pso_values import vector
from ..vector import Aabb3, Vector3


@dataclasses.dataclass(slots=True, frozen=True)
class YmtAabb:
    minimum: Vector3 = dataclasses.field(default_factory=Vector3)
    maximum: Vector3 = dataclasses.field(default_factory=Vector3)
    minimum_w: float = 0.0
    maximum_w: float = 0.0

    @classmethod
    def from_value(cls, value: Any) -> YmtAabb:
        if isinstance(value, PsoNode):
            return cls.from_mapping(value.fields or {})
        if isinstance(value, dict):
            return cls.from_mapping(value)
        return cls()

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> YmtAabb:
        minimum_x, minimum_y, minimum_z, minimum_w = vector(
            _field(value, "min", "hash_FE2F0903"), 4
        )
        maximum_x, maximum_y, maximum_z, maximum_w = vector(
            _field(value, "max", "hash_606EDCC4"), 4
        )
        return cls(
            minimum=Vector3(minimum_x, minimum_y, minimum_z),
            maximum=Vector3(maximum_x, maximum_y, maximum_z),
            minimum_w=minimum_w,
            maximum_w=maximum_w,
        )

    @property
    def bounds(self) -> Aabb3:
        return Aabb3(self.minimum, self.maximum)


@dataclasses.dataclass(slots=True, frozen=True)
class YmtScenarioPointRegionDef:
    name: MetaHash = dataclasses.field(default_factory=MetaHash)
    aabb: YmtAabb = dataclasses.field(default_factory=YmtAabb)

    @classmethod
    def from_value(cls, value: Any) -> YmtScenarioPointRegionDef:
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
    def from_value(cls, value: Any) -> YmtScenarioPointGroup:
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
    def from_pso_node(cls, node: PsoNode) -> YmtScenarioPointManifest:
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


__all__ = [
    "YmtAabb",
    "YmtScenarioPointGroup",
    "YmtScenarioPointManifest",
    "YmtScenarioPointRegionDef",
]
