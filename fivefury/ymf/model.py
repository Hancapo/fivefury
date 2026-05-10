from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from ..meta import Meta
from ..meta.defs import meta_name
from ..metahash import HashLike, MetaHash, MetaHashFieldsMixin
from ..xml import add_element_items, child_int, child_text, flag_text, parse_flag_names, parse_xml_root, xml_bytes
from .enums import (
    ManifestFlags,
    PackFileMetaDataAssetType,
    PackFileMetaDataImapGroupType,
    YmfRelationship,
    YmfRelationshipType,
)
from .utils import _append_hash_items, _get, _get_hash, _get_hash_list, _get_list, _hash_items, _hash_text


def _ymf_struct_infos():
    from .schema import YMF_STRUCT_INFOS

    return YMF_STRUCT_INFOS


def _ymf_enum_infos():
    from .schema import YMF_ENUM_INFOS

    return YMF_ENUM_INFOS


@dataclasses.dataclass(slots=True)
class HdTxdAssetBinding(MetaHashFieldsMixin):
    _hash_fields = ("target_asset", "hd_txd")

    asset_type: PackFileMetaDataAssetType | int = PackFileMetaDataAssetType.AT_TXD
    target_asset: MetaHash | HashLike = 0
    hd_txd: MetaHash | HashLike = 0

    def __post_init__(self) -> None:
        self.asset_type = PackFileMetaDataAssetType(int(self.asset_type))

    def to_meta(self) -> dict[str, Any]:
        return {
            "assetType": int(self.asset_type),
            "targetAsset": _hash_text(self.target_asset),
            "HDTxd": _hash_text(self.hd_txd),
            "_meta_name_hash": meta_name("CHDTxdAssetBinding"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "HdTxdAssetBinding":
        return cls(
            asset_type=_get(value, "assetType", "m_assetType", default=0),
            target_asset=_get_hash(value, "targetAsset", "m_targetAsset"),
            hd_txd=_get_hash(value, "HDTxd", "hdTxd", "m_HDTxd"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        ET.SubElement(element, "assetType").text = self.asset_type.name
        ET.SubElement(element, "targetAsset").text = _hash_text(self.target_asset)
        ET.SubElement(element, "HDTxd").text = _hash_text(self.hd_txd)
        return element

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "HdTxdAssetBinding":
        asset_type = child_text(element, "assetType")
        return cls(
            asset_type=PackFileMetaDataAssetType[asset_type] if asset_type else PackFileMetaDataAssetType.AT_TXD,
            target_asset=child_text(element, "targetAsset"),
            hd_txd=child_text(element, "HDTxd"),
        )


@dataclasses.dataclass(slots=True)
class MapDataGroup(MetaHashFieldsMixin):
    _hash_fields = ("name",)
    _hash_list_fields = ("bounds", "weather_types")

    name: MetaHash | HashLike = 0
    bounds: list[MetaHash | HashLike] = dataclasses.field(default_factory=list)
    flags: PackFileMetaDataImapGroupType | int = PackFileMetaDataImapGroupType.NONE
    weather_types: list[MetaHash | HashLike] = dataclasses.field(default_factory=list)
    hours_on_off: int = 0

    def __post_init__(self) -> None:
        self.flags = PackFileMetaDataImapGroupType(int(self.flags))

    def to_meta(self) -> dict[str, Any]:
        return {
            "Name": self.name,
            "Bounds": self.bounds,
            "Flags": int(self.flags),
            "WeatherTypes": self.weather_types,
            "HoursOnOff": int(self.hours_on_off),
            "_meta_name_hash": meta_name("CMapDataGroup"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "MapDataGroup":
        return cls(
            name=_get_hash(value, "Name", "m_Name"),
            bounds=_get_hash_list(value, "Bounds", "m_Bounds"),
            flags=_get(value, "Flags", "m_Flags", default=0),
            weather_types=_get_hash_list(value, "WeatherTypes", "m_WeatherTypes"),
            hours_on_off=int(_get(value, "HoursOnOff", "m_HoursOnOff", default=0) or 0),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        ET.SubElement(element, "Name").text = _hash_text(self.name)
        _append_hash_items(element, "Bounds", self.bounds)
        if self.flags:
            ET.SubElement(element, "Flags").text = flag_text(self.flags)
        _append_hash_items(element, "WeatherTypes", self.weather_types)
        if self.hours_on_off:
            ET.SubElement(element, "HoursOnOff").set("value", str(int(self.hours_on_off)))
        return element

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "MapDataGroup":
        return cls(
            name=child_text(element, "Name"),
            bounds=_hash_items(element, "Bounds"),
            flags=parse_flag_names(PackFileMetaDataImapGroupType, child_text(element, "Flags")),
            weather_types=_hash_items(element, "WeatherTypes"),
            hours_on_off=child_int(element, "HoursOnOff"),
        )


@dataclasses.dataclass(slots=True)
class ImapDependency(MetaHashFieldsMixin):
    _hash_fields = ("imap_name", "ityp_name", "pack_file_name")

    imap_name: MetaHash | HashLike = 0
    ityp_name: MetaHash | HashLike = 0
    pack_file_name: MetaHash | HashLike = 0

    def to_meta(self) -> dict[str, Any]:
        return {
            "imapName": self.imap_name,
            "itypName": self.ityp_name,
            "packFileName": self.pack_file_name,
            "_meta_name_hash": meta_name("CImapDependency"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "ImapDependency":
        return cls(
            imap_name=_get_hash(value, "imapName", "m_imapName"),
            ityp_name=_get_hash(value, "itypName", "m_itypName"),
            pack_file_name=_get_hash(value, "packFileName", "m_packFileName"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        ET.SubElement(element, "imapName").text = _hash_text(self.imap_name)
        ET.SubElement(element, "itypName").text = _hash_text(self.ityp_name)
        if self.pack_file_name:
            ET.SubElement(element, "packFileName").text = _hash_text(self.pack_file_name)
        return element

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "ImapDependency":
        return cls(
            imap_name=child_text(element, "imapName"),
            ityp_name=child_text(element, "itypName"),
            pack_file_name=child_text(element, "packFileName"),
        )


@dataclasses.dataclass(slots=True)
class ImapDependencies(MetaHashFieldsMixin):
    _hash_fields = ("imap_name",)
    _hash_list_fields = ("ityp_dependencies",)

    imap_name: MetaHash | HashLike = 0
    ityp_dependencies: list[MetaHash | HashLike] = dataclasses.field(default_factory=list)
    flags: ManifestFlags | int = ManifestFlags.NONE

    def __post_init__(self) -> None:
        self.flags = ManifestFlags(int(self.flags))

    def to_meta(self) -> dict[str, Any]:
        return {
            "imapName": self.imap_name,
            "manifestFlags": int(self.flags),
            "itypDepArray": self.ityp_dependencies,
            "_meta_name_hash": meta_name("CImapDependencies"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "ImapDependencies":
        return cls(
            imap_name=_get_hash(value, "imapName", "m_imapName"),
            flags=_get(value, "manifestFlags", "m_manifestFlags", default=0),
            ityp_dependencies=_get_hash_list(value, "itypDepArray", "m_itypDepArray"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        ET.SubElement(element, "imapName").text = _hash_text(self.imap_name)
        ET.SubElement(element, "manifestFlags").text = flag_text(self.flags)
        _append_hash_items(element, "itypDepArray", self.ityp_dependencies)
        return element

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "ImapDependencies":
        return cls(
            imap_name=child_text(element, "imapName"),
            flags=parse_flag_names(ManifestFlags, child_text(element, "manifestFlags")),
            ityp_dependencies=_hash_items(element, "itypDepArray"),
        )


@dataclasses.dataclass(slots=True)
class ItypDependencies(MetaHashFieldsMixin):
    _hash_fields = ("ityp_name",)
    _hash_list_fields = ("ityp_dependencies",)

    ityp_name: MetaHash | HashLike = 0
    ityp_dependencies: list[MetaHash | HashLike] = dataclasses.field(default_factory=list)
    flags: ManifestFlags | int = ManifestFlags.NONE

    def __post_init__(self) -> None:
        self.flags = ManifestFlags(int(self.flags))

    def to_meta(self) -> dict[str, Any]:
        return {
            "itypName": self.ityp_name,
            "manifestFlags": int(self.flags),
            "itypDepArray": self.ityp_dependencies,
            "_meta_name_hash": meta_name("CItypDependencies"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "ItypDependencies":
        return cls(
            ityp_name=_get_hash(value, "itypName", "m_itypName"),
            flags=_get(value, "manifestFlags", "m_manifestFlags", default=0),
            ityp_dependencies=_get_hash_list(value, "itypDepArray", "m_itypDepArray"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        ET.SubElement(element, "itypName").text = _hash_text(self.ityp_name)
        ET.SubElement(element, "manifestFlags").text = flag_text(self.flags)
        _append_hash_items(element, "itypDepArray", self.ityp_dependencies)
        return element

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "ItypDependencies":
        return cls(
            ityp_name=child_text(element, "itypName"),
            flags=parse_flag_names(ManifestFlags, child_text(element, "manifestFlags")),
            ityp_dependencies=_hash_items(element, "itypDepArray"),
        )


@dataclasses.dataclass(slots=True)
class InteriorBoundsFile(MetaHashFieldsMixin):
    _hash_fields = ("name",)
    _hash_list_fields = ("bounds",)

    name: MetaHash | HashLike = 0
    bounds: list[MetaHash | HashLike] = dataclasses.field(default_factory=list)

    def to_meta(self) -> dict[str, Any]:
        return {
            "Name": self.name,
            "Bounds": self.bounds,
            "_meta_name_hash": meta_name("CInteriorBoundsFiles"),
        }

    @classmethod
    def from_meta(cls, value: Any) -> "InteriorBoundsFile":
        return cls(
            name=_get_hash(value, "Name", "m_Name"),
            bounds=_get_hash_list(value, "Bounds", "m_Bounds"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        ET.SubElement(element, "Name").text = _hash_text(self.name)
        _append_hash_items(element, "Bounds", self.bounds)
        return element

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "InteriorBoundsFile":
        return cls(name=child_text(element, "Name"), bounds=_hash_items(element, "Bounds"))


@dataclasses.dataclass(slots=True)
class PackFileMetaData:
    map_data_groups: list[MapDataGroup] = dataclasses.field(default_factory=list)
    hd_txd_bindings: list[HdTxdAssetBinding] = dataclasses.field(default_factory=list)
    imap_dependencies: list[ImapDependency] = dataclasses.field(default_factory=list)
    imap_dependencies_2: list[ImapDependencies] = dataclasses.field(default_factory=list)
    ityp_dependencies_2: list[ItypDependencies] = dataclasses.field(default_factory=list)
    interiors: list[InteriorBoundsFile] = dataclasses.field(default_factory=list)

    def to_meta_root(self) -> dict[str, Any]:
        return {
            "MapDataGroups": [item.to_meta() for item in self.map_data_groups],
            "HDTxdBindingArray": [item.to_meta() for item in self.hd_txd_bindings],
            "imapDependencies": [item.to_meta() for item in self.imap_dependencies],
            "imapDependencies_2": [item.to_meta() for item in self.imap_dependencies_2],
            "itypDependencies_2": [item.to_meta() for item in self.ityp_dependencies_2],
            "Interiors": [item.to_meta() for item in self.interiors],
            "_meta_name_hash": meta_name("CPackFileMetaData"),
        }

    def to_meta(self, *, name: str = "") -> Meta:
        return Meta(
            Name=name,
            root_name_hash=meta_name("CPackFileMetaData"),
            root_value=self.to_meta_root(),
            struct_infos=_ymf_struct_infos(),
            enum_infos=_ymf_enum_infos(),
            resource_version=2,
        )

    def to_xml_element(self) -> ET.Element:
        root = ET.Element("CPackFileMetaData")
        add_element_items(root, "MapDataGroups", (item.to_xml_element() for item in self.map_data_groups))
        add_element_items(root, "HDTxdBindingArray", (item.to_xml_element() for item in self.hd_txd_bindings))
        add_element_items(root, "imapDependencies", (item.to_xml_element() for item in self.imap_dependencies))
        add_element_items(root, "imapDependencies_2", (item.to_xml_element() for item in self.imap_dependencies_2))
        add_element_items(root, "itypDependencies_2", (item.to_xml_element() for item in self.ityp_dependencies_2))
        add_element_items(root, "Interiors", (item.to_xml_element() for item in self.interiors))
        return root

    def to_xml_bytes(self) -> bytes:
        return xml_bytes(self.to_xml_element())

    def iter_relationships(self) -> list[YmfRelationship]:
        relationships: list[YmfRelationship] = []
        for source_index, dependency in enumerate(self.imap_dependencies):
            relationships.append(
                YmfRelationship(
                    kind=YmfRelationshipType.LEGACY_IMAP_TO_ITYP,
                    source=dependency.imap_name,
                    target=dependency.ityp_name,
                    source_index=source_index,
                )
            )
        for source_index, dependency in enumerate(self.imap_dependencies_2):
            for target_index, target in enumerate(dependency.ityp_dependencies):
                relationships.append(
                    YmfRelationship(
                        kind=YmfRelationshipType.IMAP_TO_ITYP,
                        source=dependency.imap_name,
                        target=target,
                        flags=dependency.flags,
                        source_index=source_index,
                        target_index=target_index,
                    )
                )
        for source_index, dependency in enumerate(self.ityp_dependencies_2):
            for target_index, target in enumerate(dependency.ityp_dependencies):
                relationships.append(
                    YmfRelationship(
                        kind=YmfRelationshipType.ITYP_TO_ITYP,
                        source=dependency.ityp_name,
                        target=target,
                        flags=dependency.flags,
                        source_index=source_index,
                        target_index=target_index,
                    )
                )
        for source_index, group in enumerate(self.map_data_groups):
            for target_index, target in enumerate(group.bounds):
                relationships.append(
                    YmfRelationship(
                        kind=YmfRelationshipType.IMAP_GROUP_TO_BOUND,
                        source=group.name,
                        target=target,
                        source_index=source_index,
                        target_index=target_index,
                        data=group.flags,
                    )
                )
        for source_index, interior in enumerate(self.interiors):
            for target_index, target in enumerate(interior.bounds):
                relationships.append(
                    YmfRelationship(
                        kind=YmfRelationshipType.INTERIOR_TO_BOUND,
                        source=interior.name,
                        target=target,
                        source_index=source_index,
                        target_index=target_index,
                    )
                )
        for source_index, binding in enumerate(self.hd_txd_bindings):
            relationships.append(
                YmfRelationship(
                    kind=YmfRelationshipType.HD_TXD_BINDING,
                    source=binding.target_asset,
                    target=binding.hd_txd,
                    source_index=source_index,
                    data=binding.asset_type,
                )
            )
        return relationships

    @classmethod
    def from_meta_root(cls, root: Any) -> "PackFileMetaData":
        return cls(
            map_data_groups=[MapDataGroup.from_meta(item) for item in _get_list(root, "MapDataGroups", "m_MapDataGroups")],
            hd_txd_bindings=[
                HdTxdAssetBinding.from_meta(item) for item in _get_list(root, "HDTxdBindingArray", "m_HDTxdBindingArray")
            ],
            imap_dependencies=[
                ImapDependency.from_meta(item) for item in _get_list(root, "imapDependencies", "m_imapDependencies")
            ],
            imap_dependencies_2=[
                ImapDependencies.from_meta(item) for item in _get_list(root, "imapDependencies_2", "m_imapDependencies_2")
            ],
            ityp_dependencies_2=[
                ItypDependencies.from_meta(item) for item in _get_list(root, "itypDependencies_2", "m_itypDependencies_2")
            ],
            interiors=[InteriorBoundsFile.from_meta(item) for item in _get_list(root, "Interiors", "m_Interiors")],
        )

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> "PackFileMetaData":
        root = parse_xml_root(source)
        if root.tag != "CPackFileMetaData":
            raise ValueError(f"Unsupported YMF XML root: {root.tag}")
        return cls(
            map_data_groups=[MapDataGroup.from_xml_element(item) for item in root.findall("./MapDataGroups/Item")],
            hd_txd_bindings=[HdTxdAssetBinding.from_xml_element(item) for item in root.findall("./HDTxdBindingArray/Item")],
            imap_dependencies=[ImapDependency.from_xml_element(item) for item in root.findall("./imapDependencies/Item")],
            imap_dependencies_2=[ImapDependencies.from_xml_element(item) for item in root.findall("./imapDependencies_2/Item")],
            ityp_dependencies_2=[ItypDependencies.from_xml_element(item) for item in root.findall("./itypDependencies_2/Item")],
            interiors=[InteriorBoundsFile.from_xml_element(item) for item in root.findall("./Interiors/Item")],
        )
