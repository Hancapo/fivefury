from __future__ import annotations

import dataclasses
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from .common import hash_value
from .rbf import RbfStructure, is_rbf, rbf_string_field, read_rbf, read_rbf_bytes
from .xml import child_text, read_xml_text, xml_bytes


@dataclasses.dataclass(slots=True)
class TxdRelationship:
    child: str
    parent: str

    def __post_init__(self) -> None:
        self.child = normalize_txd_name(self.child)
        self.parent = normalize_txd_name(self.parent)

    @property
    def child_hash(self) -> int:
        return hash_value(self.child)

    @property
    def parent_hash(self) -> int:
        return hash_value(self.parent)

    def to_xml_element(self) -> ET.Element:
        item = ET.Element("Item")
        parent = ET.SubElement(item, "parent")
        parent.text = self.parent
        child = ET.SubElement(item, "child")
        child.text = self.child
        return item


def normalize_txd_name(value: str | int | Any) -> str:
    text = str(value or "").replace("\\", "/").strip()
    name = text.rsplit("/", 1)[-1]
    if name.lower().endswith(".ytd"):
        name = name[:-4]
    return name.lower()


@dataclasses.dataclass(slots=True)
class Gtxd:
    relationships: list[TxdRelationship] = dataclasses.field(default_factory=list)
    source: str = "xml"

    def __post_init__(self) -> None:
        self.relationships = [coerce_txd_relationship(item) for item in self.relationships]

    @classmethod
    def from_xml(cls, source: str | bytes | Path) -> "Gtxd":
        text = read_xml_text(source)
        root = ET.fromstring(text)
        relationships: list[TxdRelationship] = []
        seen_children: set[str] = set()
        for item in root.findall(".//txdRelationships/Item") + root.findall(".//txdRelationships/item"):
            parent = child_text(item, "parent")
            child = child_text(item, "child")
            if not parent or not child:
                continue
            relationship = TxdRelationship(child=child, parent=parent)
            if relationship.child in seen_children:
                continue
            seen_children.add(relationship.child)
            relationships.append(relationship)
        return cls(relationships=relationships, source="xml")

    @classmethod
    def from_rbf(cls, source: bytes | str | Path) -> "Gtxd":
        root = read_rbf(source)
        return cls.from_rbf_root(root)

    @classmethod
    def from_rbf_root(cls, root: RbfStructure) -> "Gtxd":
        if root.name != "CMapParentTxds":
            raise ValueError(f"Expected CMapParentTxds RBF root, got {root.name!r}")
        relationships: list[TxdRelationship] = []
        seen_children: set[str] = set()
        for group in root.child_structures("txdRelationships"):
            for item in group.child_structures("item"):
                parent = rbf_string_field(item, "parent")
                child = rbf_string_field(item, "child")
                if not parent or not child:
                    continue
                relationship = TxdRelationship(child=child, parent=parent)
                if relationship.child in seen_children:
                    continue
                seen_children.add(relationship.child)
                relationships.append(relationship)
        return cls(relationships=relationships, source="rbf")

    @classmethod
    def from_mapping(cls, relationships: Mapping[str, str] | Iterable[tuple[str, str]]) -> "Gtxd":
        if isinstance(relationships, Mapping):
            items = relationships.items()
        else:
            items = relationships
        return cls([TxdRelationship(child=child, parent=parent) for child, parent in items])

    def to_xml_element(self) -> ET.Element:
        root = ET.Element("CMapParentTxds")
        items = ET.SubElement(root, "txdRelationships")
        for relationship in self.relationships:
            items.append(relationship.to_xml_element())
        return root

    def to_xml_bytes(self) -> bytes:
        return xml_bytes(self.to_xml_element())

    def to_bytes(self) -> bytes:
        return self.to_xml_bytes()

    def save(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(self.to_bytes())
        return output

    def add_relationship(self, child: str, parent: str) -> TxdRelationship:
        relationship = TxdRelationship(child=child, parent=parent)
        self.remove_child(child)
        self.relationships.append(relationship)
        return relationship

    def add(self, child: str, parent: str) -> TxdRelationship:
        return self.add_relationship(child, parent)

    def remove_child(self, child: str) -> bool:
        normalized = normalize_txd_name(child)
        before = len(self.relationships)
        self.relationships = [relationship for relationship in self.relationships if relationship.child != normalized]
        return len(self.relationships) != before

    def parent_of(self, child: str | int) -> str | None:
        child_hash = hash_value(child) if isinstance(child, int) else hash_value(normalize_txd_name(child))
        for relationship in self.relationships:
            if relationship.child_hash == child_hash:
                return relationship.parent
        return None

    def parent_hash_of(self, child: str | int) -> int | None:
        parent = self.parent_of(child)
        return hash_value(parent) if parent else None

    def to_parent_map(self) -> dict[int, int]:
        return {relationship.child_hash: relationship.parent_hash for relationship in self.relationships}

    def to_name_parent_map(self) -> dict[str, str]:
        return {relationship.child: relationship.parent for relationship in self.relationships}

    def iter_chain(self, child: str | int, *, include_self: bool = True, max_depth: int = 64) -> Iterator[str]:
        current = normalize_txd_name(child) if not isinstance(child, int) else ""
        current_hash = hash_value(child) if isinstance(child, int) else hash_value(current)
        by_child_hash = {relationship.child_hash: relationship for relationship in self.relationships}
        seen: set[int] = set()
        if include_self and current:
            yield current
        for _ in range(max_depth):
            if current_hash in seen:
                break
            seen.add(current_hash)
            relationship = by_child_hash.get(current_hash)
            if relationship is None:
                break
            yield relationship.parent
            current_hash = relationship.parent_hash


def coerce_txd_relationship(value: TxdRelationship | tuple[str, str] | Mapping[str, Any]) -> TxdRelationship:
    if isinstance(value, TxdRelationship):
        return value
    if isinstance(value, Mapping):
        return TxdRelationship(child=str(value.get("child", "")), parent=str(value.get("parent", "")))
    child, parent = value
    return TxdRelationship(child=child, parent=parent)


def read_gtxd_text(source: str | bytes | Path) -> str:
    return read_xml_text(source)


def read_gtxd_bytes(source: str | bytes | Path) -> bytes:
    if isinstance(source, str) and "<" in source:
        return source.encode("utf-8")
    return read_rbf_bytes(source)


def is_gtxd_rbf(source: str | bytes | Path) -> bool:
    return is_rbf(source)


def read_gtxd(source: str | bytes | Path) -> Gtxd:
    if is_gtxd_rbf(source):
        return Gtxd.from_rbf(source)
    return Gtxd.from_xml(source)


def create_gtxd(relationships: Mapping[str, str] | Iterable[tuple[str, str]] | None = None, **kwargs: str) -> Gtxd:
    gtxd = Gtxd()
    if relationships is not None:
        gtxd = Gtxd.from_mapping(relationships)
    for child, parent in kwargs.items():
        gtxd.add_relationship(child, parent)
    return gtxd


def save_gtxd(gtxd: Gtxd, path: str | Path) -> Path:
    return gtxd.save(path)


__all__ = [
    "Gtxd",
    "TxdRelationship",
    "coerce_txd_relationship",
    "create_gtxd",
    "is_gtxd_rbf",
    "normalize_txd_name",
    "read_gtxd",
    "read_gtxd_bytes",
    "save_gtxd",
]
