from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ..xml import (
    append_items,
    append_text,
    append_value,
    child_by_name,
    child_text,
    child_value,
    item_elements,
    item_texts,
    parse_bool,
    parse_xml_root,
    xml_bytes,
)
from .enums import (
    DlcDataFileContents,
    DlcDataFileType,
    DlcInstallPartition,
    DlcLoadingScreenContext,
)


def _optional_bool(element: ET.Element, name: str) -> bool | None:
    child = child_by_name(element, name)
    if child is None:
        return None
    return parse_bool(child.attrib.get("value", child.text or ""))


def _add_optional_value(
    parent: ET.Element,
    tag: str,
    value: bool | str | None,
) -> None:
    if value is not None:
        append_value(parent, tag, value)


@dataclass(slots=True)
class DlcResourceReference:
    asset_name: str
    extension: str = ""

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> DlcResourceReference:
        return cls(
            asset_name=child_text(element, "AssetName"),
            extension=child_text(element, "Extension"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        append_text(element, "AssetName", self.asset_name)
        append_text(element, "Extension", self.extension)
        return element


@dataclass(slots=True)
class DlcExecutionCondition:
    name: str
    condition: bool = True

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> DlcExecutionCondition:
        return cls(
            name=child_text(element, "name"),
            condition=parse_bool(child_value(element, "condition"), False),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        append_text(element, "name", self.name)
        append_value(element, "condition", self.condition)
        return element


@dataclass(slots=True)
class DlcExecutionConditions:
    active_change_set_conditions: list[DlcExecutionCondition] = field(default_factory=list)
    generic_conditions: str = ""

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> DlcExecutionConditions:
        active = child_by_name(element, "activeChangesetConditions")
        return cls(
            active_change_set_conditions=[
                DlcExecutionCondition.from_xml_element(item)
                for item in item_elements(active)
            ],
            generic_conditions=child_text(element, "genericConditions"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("executionConditions")
        active = ET.SubElement(element, "activeChangesetConditions")
        for condition in self.active_change_set_conditions:
            active.append(condition.to_xml_element())
        append_text(element, "genericConditions", self.generic_conditions)
        return element


@dataclass(slots=True)
class DlcChangeSetData:
    associated_map: str = ""
    files_to_enable: list[str] = field(default_factory=list)
    files_to_disable: list[str] = field(default_factory=list)
    files_to_invalidate: list[str] = field(default_factory=list)
    txd_to_load: list[str] = field(default_factory=list)
    txd_to_unload: list[str] = field(default_factory=list)
    resident_resources: list[DlcResourceReference] = field(default_factory=list)
    unregister_resources: list[DlcResourceReference] = field(default_factory=list)
    data_files_to_load: list[str] = field(default_factory=list)

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> DlcChangeSetData:
        return cls(
            associated_map=child_text(element, "associatedMap"),
            files_to_enable=item_texts(child_by_name(element, "filesToEnable")),
            files_to_disable=item_texts(child_by_name(element, "filesToDisable")),
            files_to_invalidate=item_texts(child_by_name(element, "filesToInvalidate")),
            txd_to_load=item_texts(child_by_name(element, "txdToLoad")),
            txd_to_unload=item_texts(child_by_name(element, "txdToUnload")),
            resident_resources=[
                DlcResourceReference.from_xml_element(item)
                for item in item_elements(child_by_name(element, "residentResources"))
            ],
            unregister_resources=[
                DlcResourceReference.from_xml_element(item)
                for item in item_elements(child_by_name(element, "unregisterResources"))
            ],
            data_files_to_load=item_texts(child_by_name(element, "dataFilesToLoad")),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        append_text(element, "associatedMap", self.associated_map)
        append_items(element, "filesToInvalidate", self.files_to_invalidate)
        append_items(element, "filesToDisable", self.files_to_disable)
        append_items(element, "filesToEnable", self.files_to_enable)
        append_items(element, "txdToLoad", self.txd_to_load)
        append_items(element, "txdToUnload", self.txd_to_unload)
        _add_resource_references(element, "residentResources", self.resident_resources)
        _add_resource_references(element, "unregisterResources", self.unregister_resources)
        append_items(element, "dataFilesToLoad", self.data_files_to_load)
        return element


def _add_resource_references(
    parent: ET.Element,
    tag: str,
    resources: list[DlcResourceReference],
) -> None:
    element = ET.SubElement(parent, tag)
    for resource in resources:
        element.append(resource.to_xml_element())


@dataclass(slots=True)
class DlcContentChangeSet:
    name: str
    map_change_set_data: list[DlcChangeSetData] = field(default_factory=list)
    files_to_enable: list[str] = field(default_factory=list)
    files_to_disable: list[str] = field(default_factory=list)
    files_to_invalidate: list[str] = field(default_factory=list)
    txd_to_load: list[str] = field(default_factory=list)
    txd_to_unload: list[str] = field(default_factory=list)
    resident_resources: list[DlcResourceReference] = field(default_factory=list)
    unregister_resources: list[DlcResourceReference] = field(default_factory=list)
    data_files_to_load: list[str] = field(default_factory=list)
    requires_loading_screen: bool | None = None
    loading_screen_context: DlcLoadingScreenContext | str | None = None
    execution_conditions: DlcExecutionConditions | None = None
    use_cache_loader: bool | None = None

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> DlcContentChangeSet:
        map_data = child_by_name(element, "mapChangeSetData")
        conditions = child_by_name(element, "executionConditions")
        return cls(
            name=child_text(element, "changeSetName"),
            map_change_set_data=[
                DlcChangeSetData.from_xml_element(item)
                for item in item_elements(map_data)
            ],
            files_to_enable=item_texts(child_by_name(element, "filesToEnable")),
            files_to_disable=item_texts(child_by_name(element, "filesToDisable")),
            files_to_invalidate=item_texts(child_by_name(element, "filesToInvalidate")),
            txd_to_load=item_texts(child_by_name(element, "txdToLoad")),
            txd_to_unload=item_texts(child_by_name(element, "txdToUnload")),
            resident_resources=[
                DlcResourceReference.from_xml_element(item)
                for item in item_elements(child_by_name(element, "residentResources"))
            ],
            unregister_resources=[
                DlcResourceReference.from_xml_element(item)
                for item in item_elements(child_by_name(element, "unregisterResources"))
            ],
            data_files_to_load=item_texts(child_by_name(element, "dataFilesToLoad")),
            requires_loading_screen=_optional_bool(element, "requiresLoadingScreen"),
            loading_screen_context=child_text(element, "loadingScreenContext") or None,
            execution_conditions=(
                DlcExecutionConditions.from_xml_element(conditions)
                if conditions is not None
                else None
            ),
            use_cache_loader=_optional_bool(element, "useCacheLoader"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        append_text(element, "changeSetName", self.name)
        map_data = ET.SubElement(element, "mapChangeSetData")
        for item in self.map_change_set_data:
            map_data.append(item.to_xml_element())
        append_items(element, "filesToInvalidate", self.files_to_invalidate)
        append_items(element, "filesToDisable", self.files_to_disable)
        append_items(element, "filesToEnable", self.files_to_enable)
        append_items(element, "txdToLoad", self.txd_to_load)
        append_items(element, "txdToUnload", self.txd_to_unload)
        _add_resource_references(element, "residentResources", self.resident_resources)
        _add_resource_references(element, "unregisterResources", self.unregister_resources)
        append_items(element, "dataFilesToLoad", self.data_files_to_load)
        _add_optional_value(element, "requiresLoadingScreen", self.requires_loading_screen)
        if self.loading_screen_context is not None:
            append_text(element, "loadingScreenContext", self.loading_screen_context)
        if self.execution_conditions is not None:
            element.append(self.execution_conditions.to_xml_element())
        _add_optional_value(element, "useCacheLoader", self.use_cache_loader)
        return element

    def enable(self, *filenames: str) -> DlcContentChangeSet:
        self.files_to_enable.extend(str(name) for name in filenames)
        return self

    def disable(self, *filenames: str) -> DlcContentChangeSet:
        self.files_to_disable.extend(str(name) for name in filenames)
        return self

    def invalidate(self, *filenames: str) -> DlcContentChangeSet:
        self.files_to_invalidate.extend(str(name) for name in filenames)
        return self


@dataclass(slots=True)
class DlcContentFile:
    filename: str
    file_type: DlcDataFileType | str
    overlay: bool | None = False
    disabled: bool | None = True
    persistent: bool | None = False
    contents: DlcDataFileContents | str | None = None
    load_completely: bool | None = None
    register_as: str = ""
    locked: bool | None = None
    patch_file: bool | None = None
    enforce_lsn_sorting: bool | None = None
    install_partition: DlcInstallPartition | str | None = None
    platform: str = ""

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> DlcContentFile:
        return cls(
            filename=child_text(element, "filename"),
            file_type=child_text(element, "fileType"),
            overlay=_optional_bool(element, "overlay"),
            disabled=_optional_bool(element, "disabled"),
            persistent=_optional_bool(element, "persistent"),
            contents=child_text(element, "contents") or None,
            load_completely=_optional_bool(element, "loadCompletely"),
            register_as=child_text(element, "registerAs"),
            locked=_optional_bool(element, "locked"),
            patch_file=_optional_bool(element, "patchFile"),
            enforce_lsn_sorting=_optional_bool(element, "enforceLsnSorting"),
            install_partition=child_text(element, "installPartition") or None,
            platform=element.attrib.get("platform", ""),
        )

    def to_xml_element(self) -> ET.Element:
        attributes = {"platform": self.platform} if self.platform else {}
        element = ET.Element("Item", attributes)
        append_text(element, "filename", self.filename)
        append_text(element, "fileType", self.file_type)
        if self.register_as:
            append_text(element, "registerAs", self.register_as)
        _add_optional_value(element, "locked", self.locked)
        _add_optional_value(element, "loadCompletely", self.load_completely)
        _add_optional_value(element, "overlay", self.overlay)
        _add_optional_value(element, "patchFile", self.patch_file)
        _add_optional_value(element, "disabled", self.disabled)
        _add_optional_value(element, "persistent", self.persistent)
        _add_optional_value(element, "enforceLsnSorting", self.enforce_lsn_sorting)
        if self.contents is not None:
            append_text(element, "contents", self.contents)
        if self.install_partition is not None:
            append_text(element, "installPartition", self.install_partition)
        return element


@dataclass(slots=True)
class DlcContentFileArray:
    data_files: list[DlcContentFile] = field(default_factory=list)

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> DlcContentFileArray:
        data_files = child_by_name(element, "dataFiles")
        return cls(
            data_files=[
                DlcContentFile.from_xml_element(item)
                for item in item_elements(data_files)
            ]
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        data_files = ET.SubElement(element, "dataFiles")
        for data_file in self.data_files:
            data_files.append(data_file.to_xml_element())
        return element


@dataclass(slots=True)
class DlcContentXml:
    disabled_files: list[str] = field(default_factory=list)
    included_xml_files: list[DlcContentFileArray] = field(default_factory=list)
    included_data_files: list[str] = field(default_factory=list)
    data_files: list[DlcContentFile] = field(default_factory=list)
    content_change_sets: list[DlcContentChangeSet] = field(default_factory=list)
    patch_files: list[str] = field(default_factory=list)
    allowed_folders: list[str] = field(default_factory=list)

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> DlcContentXml:
        root = parse_xml_root(source)
        included_xml = child_by_name(root, "includedXmlFiles")
        data_files = child_by_name(root, "dataFiles")
        change_sets = child_by_name(root, "contentChangeSets")
        return cls(
            disabled_files=item_texts(child_by_name(root, "disabledFiles")),
            included_xml_files=[
                DlcContentFileArray.from_xml_element(item)
                for item in item_elements(included_xml)
            ],
            included_data_files=item_texts(child_by_name(root, "includedDataFiles")),
            data_files=[
                DlcContentFile.from_xml_element(item)
                for item in item_elements(data_files)
            ],
            content_change_sets=[
                DlcContentChangeSet.from_xml_element(item)
                for item in item_elements(change_sets)
            ],
            patch_files=item_texts(child_by_name(root, "patchFiles")),
            allowed_folders=item_texts(child_by_name(root, "allowedFolders")),
        )

    def file(
        self,
        filename: str,
        file_type: DlcDataFileType | str,
        *,
        overlay: bool | None = False,
        disabled: bool | None = True,
        persistent: bool | None = False,
        contents: DlcDataFileContents | str | None = None,
        load_completely: bool | None = None,
        register_as: str = "",
        locked: bool | None = None,
        patch_file: bool | None = None,
        enforce_lsn_sorting: bool | None = None,
        install_partition: DlcInstallPartition | str | None = None,
        platform: str = "",
    ) -> DlcContentFile:
        item = DlcContentFile(
            filename=filename,
            file_type=file_type,
            overlay=overlay,
            disabled=disabled,
            persistent=persistent,
            contents=contents,
            load_completely=load_completely,
            register_as=register_as,
            locked=locked,
            patch_file=patch_file,
            enforce_lsn_sorting=enforce_lsn_sorting,
            install_partition=install_partition,
            platform=platform,
        )
        self.data_files.append(item)
        return item

    def rpf(
        self,
        filename: str,
        *,
        map_data: bool = False,
        overlay: bool = False,
        load_completely: bool | None = None,
    ) -> DlcContentFile:
        return self.file(
            filename,
            DlcDataFileType.RPF,
            overlay=overlay,
            persistent=True,
            contents=DlcDataFileContents.DLC_MAP_DATA if map_data else None,
            load_completely=load_completely,
        )

    def ityp(self, filename: str) -> DlcContentFile:
        return self.file(filename, DlcDataFileType.DLC_ITYP_REQUEST)

    def change_set(self, name: str, *, enable_all: bool = False) -> DlcContentChangeSet:
        files = [item.filename for item in self.data_files] if enable_all else []
        change_set = DlcContentChangeSet(name=name, files_to_enable=files)
        self.content_change_sets.append(change_set)
        return change_set

    def to_xml_element(self) -> ET.Element:
        root = ET.Element("CDataFileMgr__ContentsOfDataFileXml")
        append_items(root, "disabledFiles", self.disabled_files)
        included_xml = ET.SubElement(root, "includedXmlFiles")
        for item in self.included_xml_files:
            included_xml.append(item.to_xml_element())
        append_items(root, "includedDataFiles", self.included_data_files)
        files = ET.SubElement(root, "dataFiles")
        for data_file in self.data_files:
            files.append(data_file.to_xml_element())
        change_sets = ET.SubElement(root, "contentChangeSets")
        for change_set in self.content_change_sets:
            change_sets.append(change_set.to_xml_element())
        append_items(root, "patchFiles", self.patch_files)
        append_items(root, "allowedFolders", self.allowed_folders)
        return root

    def to_xml_bytes(self) -> bytes:
        return xml_bytes(self.to_xml_element())

    def to_bytes(self) -> bytes:
        return self.to_xml_bytes()


__all__ = [
    "DlcChangeSetData",
    "DlcContentChangeSet",
    "DlcContentFile",
    "DlcContentFileArray",
    "DlcContentXml",
    "DlcExecutionCondition",
    "DlcExecutionConditions",
    "DlcResourceReference",
]
