from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ..xml import (
    add_items,
    add_text,
    add_value,
    child_by_name,
    child_items,
    child_text,
    child_value,
    coerce_enum_value,
    item_texts,
    parse_bool,
    parse_xml_root,
    xml_bytes,
)
from .enums import DlcContentGroup, DlcPackType


def _device_name(pack_name: str) -> str:
    return f"dlc_{pack_name}"


def _device_path(name: str) -> str:
    return name if name.endswith(":/") else f"{name}:/"


def _int_text(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class DlcContentChangeSetGroup:
    name: DlcContentGroup | str
    change_sets: list[str] = field(default_factory=list)

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> DlcContentChangeSetGroup:
        return cls(
            name=child_text(element, "NameHash"),
            change_sets=item_texts(child_by_name(element, "ContentChangeSets")),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        add_text(element, "NameHash", self.name)
        add_items(element, "ContentChangeSets", self.change_sets)
        return element

    def include(self, *change_sets: str) -> DlcContentChangeSetGroup:
        self.change_sets.extend(str(name) for name in change_sets)
        return self


@dataclass(slots=True)
class DlcSetupData:
    device_name: str
    name_hash: str
    dat_file: str = "content.xml"
    time_stamp: str = ""
    content_change_sets: list[str] = field(default_factory=list)
    content_change_set_groups: list[DlcContentChangeSetGroup] = field(default_factory=list)
    startup_script: str = ""
    script_callstack_size: int = 0
    pack_type: DlcPackType | str = DlcPackType.COMPAT
    order: int = 0
    minor_order: int = 0
    is_level_pack: bool = False
    dependency_pack_hash: str = ""
    required_version: str = ""
    sub_pack_count: int = 0

    @classmethod
    def compat_pack(
        cls,
        name: str,
        *,
        order: int = 0,
        device_name: str | None = None,
    ) -> DlcSetupData:
        return cls(
            device_name=device_name or _device_name(name),
            name_hash=name,
            order=order,
        )

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> DlcSetupData:
        root = parse_xml_root(source)
        return cls(
            device_name=child_text(root, "deviceName"),
            dat_file=child_text(root, "datFile", "content.xml"),
            time_stamp=child_text(root, "timeStamp"),
            name_hash=child_text(root, "nameHash"),
            content_change_sets=item_texts(child_by_name(root, "contentChangeSets")),
            content_change_set_groups=[
                DlcContentChangeSetGroup.from_xml_element(item)
                for item in child_items(root, "contentChangeSetGroups")
            ],
            startup_script=child_text(root, "startupScript"),
            script_callstack_size=_int_text(child_value(root, "scriptCallstackSize")),
            pack_type=child_text(root, "type", DlcPackType.COMPAT.value),
            order=_int_text(child_value(root, "order")),
            minor_order=_int_text(child_value(root, "minorOrder")),
            is_level_pack=parse_bool(child_value(root, "isLevelPack")),
            dependency_pack_hash=child_text(root, "dependencyPackHash"),
            required_version=child_text(root, "requiredVersion"),
            sub_pack_count=_int_text(child_value(root, "subPackCount")),
        )

    @property
    def device_path(self) -> str:
        return _device_path(self.device_name)

    def group(
        self,
        name: DlcContentGroup | str,
        *change_sets: str,
    ) -> DlcContentChangeSetGroup:
        target = coerce_enum_value(name)
        for group in self.content_change_set_groups:
            if coerce_enum_value(group.name).lower() == target.lower():
                return group.include(*change_sets)
        group = DlcContentChangeSetGroup(
            name=name,
            change_sets=[str(item) for item in change_sets],
        )
        self.content_change_set_groups.append(group)
        return group

    def startup(self, *change_sets: str) -> DlcContentChangeSetGroup:
        return self.group(DlcContentGroup.STARTUP, *change_sets)

    def map(self, *change_sets: str) -> DlcContentChangeSetGroup:
        return self.group(DlcContentGroup.MAP, *change_sets)

    def to_xml_element(self) -> ET.Element:
        root = ET.Element("SSetupData")
        add_text(root, "deviceName", self.device_name)
        add_text(root, "datFile", self.dat_file)
        add_text(root, "timeStamp", self.time_stamp)
        add_text(root, "nameHash", self.name_hash)
        add_items(root, "contentChangeSets", self.content_change_sets)
        groups = ET.SubElement(root, "contentChangeSetGroups")
        for group in self.content_change_set_groups:
            groups.append(group.to_xml_element())
        add_text(root, "startupScript", self.startup_script)
        add_value(root, "scriptCallstackSize", self.script_callstack_size)
        add_text(root, "type", self.pack_type)
        add_value(root, "order", self.order)
        add_value(root, "minorOrder", self.minor_order)
        add_value(root, "isLevelPack", self.is_level_pack)
        add_text(root, "dependencyPackHash", self.dependency_pack_hash)
        add_text(root, "requiredVersion", self.required_version)
        add_value(root, "subPackCount", self.sub_pack_count)
        return root

    def to_xml_bytes(self) -> bytes:
        return xml_bytes(self.to_xml_element())

    def to_bytes(self) -> bytes:
        return self.to_xml_bytes()


__all__ = [
    "DlcContentChangeSetGroup",
    "DlcSetupData",
]
