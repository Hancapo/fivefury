from __future__ import annotations

import dataclasses
from typing import Any

from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..meta.defs import meta_name


@dataclasses.dataclass(slots=True)
class PhysicsDictionary(MetaHashFieldsMixin):
    """YMAP physics dictionary reference."""

    _hash_fields = ("name",)

    name: MetaHash | HashLike = 0

    def to_meta(self) -> MetaHash:
        return self.name

    @classmethod
    def from_meta(cls, value: MetaHash | HashLike) -> "PhysicsDictionary":
        return cls(name=value)

    def __int__(self) -> int:
        return int(self.name)

    def __str__(self) -> str:
        return str(self.name)


@dataclasses.dataclass(slots=True)
class BlockDesc:
    version: int = 0
    flags: int = 0
    name: str = ""
    exported_by: str = ""
    owner: str = ""
    time: str = ""

    def to_meta(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "flags": self.flags,
            "name": self.name,
            "exportedBy": self.exported_by,
            "owner": self.owner,
            "time": self.time,
            "_meta_name_hash": meta_name("CBlockDesc"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "BlockDesc":
        if not isinstance(value, dict):
            return cls()
        return cls(
            version=int(value.get("version", 0)),
            flags=int(value.get("flags", 0)),
            name=str(value.get("name", "")),
            exported_by=str(value.get("exportedBy", "")),
            owner=str(value.get("owner", "")),
            time=str(value.get("time", "")),
        )


@dataclasses.dataclass(slots=True)
class ContainerLodDef(MetaHashFieldsMixin):
    """rage__fwContainerLodDef: 8 bytes (name hash + parentIndex)."""

    _hash_fields = ("name",)

    name: MetaHash | HashLike = 0
    parent_index: int = 0

    def to_meta(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parentIndex": self.parent_index,
            "_meta_name_hash": meta_name("rage__fwContainerLodDef"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "ContainerLodDef":
        if not isinstance(value, dict):
            return cls()
        return cls(
            name=value.get("name", 0),
            parent_index=int(value.get("parentIndex", 0)),
        )


__all__ = ["BlockDesc", "ContainerLodDef", "PhysicsDictionary"]
