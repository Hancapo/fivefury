from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import copy
import xml.etree.ElementTree as ET

from ..rpf import RpfArchive
from .enums import DlcContentGroup, DlcDataFileContents, DlcDataFileType, DlcPackType
from .xml import (
    add_items,
    add_text,
    add_value,
    child_by_name,
    child_text,
    child_value,
    coerce_enum_value,
    item_texts,
    parse_bool,
    read_xml_text,
    xml_bytes,
)


def _device_name(pack_name: str) -> str:
    return f"dlc_{pack_name}"


def _device_path(device_name: str) -> str:
    return device_name if device_name.endswith(":/") else f"{device_name}:/"


def _int_text(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class DlcContentChangeSet:
    name: str
    files_to_enable: list[str] = field(default_factory=list)
    files_to_disable: list[str] = field(default_factory=list)
    files_to_invalidate: list[str] = field(default_factory=list)
    map_change_set_data: ET.Element | None = None

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "DlcContentChangeSet":
        map_data = child_by_name(element, "mapChangeSetData")
        return cls(
            name=child_text(element, "changeSetName"),
            files_to_enable=item_texts(child_by_name(element, "filesToEnable")),
            files_to_disable=item_texts(child_by_name(element, "filesToDisable")),
            files_to_invalidate=item_texts(child_by_name(element, "filesToInvalidate")),
            map_change_set_data=copy.deepcopy(map_data) if map_data is not None and len(map_data) else None,
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        add_text(element, "changeSetName", self.name)
        if self.map_change_set_data is not None:
            element.append(copy.deepcopy(self.map_change_set_data))
        else:
            ET.SubElement(element, "mapChangeSetData")
        add_items(element, "filesToInvalidate", self.files_to_invalidate)
        add_items(element, "filesToDisable", self.files_to_disable)
        add_items(element, "filesToEnable", self.files_to_enable)
        return element

    def enable(self, *filenames: str) -> "DlcContentChangeSet":
        self.files_to_enable.extend(str(name) for name in filenames)
        return self

    def disable(self, *filenames: str) -> "DlcContentChangeSet":
        self.files_to_disable.extend(str(name) for name in filenames)
        return self

    def invalidate(self, *filenames: str) -> "DlcContentChangeSet":
        self.files_to_invalidate.extend(str(name) for name in filenames)
        return self


@dataclass(slots=True)
class DlcContentChangeSetGroup:
    name: DlcContentGroup | str
    change_sets: list[str] = field(default_factory=list)

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "DlcContentChangeSetGroup":
        return cls(
            name=child_text(element, "NameHash"),
            change_sets=item_texts(child_by_name(element, "ContentChangeSets")),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        add_text(element, "NameHash", self.name)
        add_items(element, "ContentChangeSets", self.change_sets)
        return element

    def include(self, *change_sets: str) -> "DlcContentChangeSetGroup":
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
    def compat_pack(cls, name: str, *, order: int = 0, device_name: str | None = None) -> "DlcSetupData":
        return cls(device_name=device_name or _device_name(name), name_hash=name, order=order)

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> "DlcSetupData":
        root = ET.fromstring(read_xml_text(source))
        groups = child_by_name(root, "contentChangeSetGroups")
        group_items = list(groups) if groups is not None else []
        return cls(
            device_name=child_text(root, "deviceName"),
            dat_file=child_text(root, "datFile", "content.xml"),
            time_stamp=child_text(root, "timeStamp"),
            name_hash=child_text(root, "nameHash"),
            content_change_sets=item_texts(child_by_name(root, "contentChangeSets")),
            content_change_set_groups=[
                DlcContentChangeSetGroup.from_xml_element(item)
                for item in group_items
                if item.tag.lower() == "item"
            ],
            startup_script=child_text(root, "startupScript"),
            script_callstack_size=_int_text(child_value(root, "scriptCallstackSize"), 0),
            pack_type=child_text(root, "type", DlcPackType.COMPAT.value),
            order=_int_text(child_value(root, "order"), 0),
            minor_order=_int_text(child_value(root, "minorOrder"), 0),
            is_level_pack=parse_bool(child_value(root, "isLevelPack"), False),
            dependency_pack_hash=child_text(root, "dependencyPackHash"),
            required_version=child_text(root, "requiredVersion"),
            sub_pack_count=_int_text(child_value(root, "subPackCount"), 0),
        )

    @property
    def device_path(self) -> str:
        return _device_path(self.device_name)

    def group(self, name: DlcContentGroup | str, *change_sets: str) -> DlcContentChangeSetGroup:
        target = coerce_enum_value(name)
        for group in self.content_change_set_groups:
            if coerce_enum_value(group.name).lower() == target.lower():
                return group.include(*change_sets)
        group = DlcContentChangeSetGroup(name=name, change_sets=[str(item) for item in change_sets])
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


@dataclass(slots=True)
class DlcContentFile:
    filename: str
    file_type: DlcDataFileType | str
    overlay: bool = False
    disabled: bool = True
    persistent: bool = False
    contents: DlcDataFileContents | str | None = None
    load_completely: bool | None = None
    register_as: str = ""

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "DlcContentFile":
        return cls(
            filename=child_text(element, "filename"),
            file_type=child_text(element, "fileType"),
            overlay=parse_bool(child_value(element, "overlay"), False),
            disabled=parse_bool(child_value(element, "disabled"), True),
            persistent=parse_bool(child_value(element, "persistent"), False),
            contents=child_text(element, "contents") or None,
            load_completely=(
                parse_bool(child_value(element, "loadCompletely"), False)
                if child_by_name(element, "loadCompletely") is not None
                else None
            ),
            register_as=child_text(element, "registerAs"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item")
        add_text(element, "filename", self.filename)
        add_text(element, "fileType", self.file_type)
        if self.load_completely is not None:
            add_value(element, "loadCompletely", self.load_completely)
        add_value(element, "overlay", self.overlay)
        add_value(element, "disabled", self.disabled)
        add_value(element, "persistent", self.persistent)
        if self.contents is not None:
            add_text(element, "contents", self.contents)
        if self.register_as:
            add_text(element, "registerAs", self.register_as)
        return element


@dataclass(slots=True)
class DlcContentXml:
    disabled_files: list[str] = field(default_factory=list)
    included_data_files: list[str] = field(default_factory=list)
    data_files: list[DlcContentFile] = field(default_factory=list)
    content_change_sets: list[DlcContentChangeSet] = field(default_factory=list)
    patch_files: list[str] = field(default_factory=list)

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> "DlcContentXml":
        root = ET.fromstring(read_xml_text(source))
        data_files = child_by_name(root, "dataFiles")
        change_sets = child_by_name(root, "contentChangeSets")
        data_file_items = list(data_files) if data_files is not None else []
        change_set_items = list(change_sets) if change_sets is not None else []
        return cls(
            disabled_files=item_texts(child_by_name(root, "disabledFiles")),
            included_data_files=item_texts(child_by_name(root, "includedDataFiles")),
            data_files=[
                DlcContentFile.from_xml_element(item)
                for item in data_file_items
                if item.tag.lower() == "item"
            ],
            content_change_sets=[
                DlcContentChangeSet.from_xml_element(item)
                for item in change_set_items
                if item.tag.lower() == "item"
            ],
            patch_files=item_texts(child_by_name(root, "patchFiles")),
        )

    def file(
        self,
        filename: str,
        file_type: DlcDataFileType | str,
        *,
        overlay: bool = False,
        disabled: bool = True,
        persistent: bool = False,
        contents: DlcDataFileContents | str | None = None,
        load_completely: bool | None = None,
    ) -> DlcContentFile:
        item = DlcContentFile(
            filename=filename,
            file_type=file_type,
            overlay=overlay,
            disabled=disabled,
            persistent=persistent,
            contents=contents,
            load_completely=load_completely,
        )
        self.data_files.append(item)
        return item

    def rpf(self, filename: str, *, map_data: bool = False, overlay: bool = False, load_completely: bool | None = None) -> DlcContentFile:
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
        add_items(root, "disabledFiles", self.disabled_files)
        ET.SubElement(root, "includedXmlFiles")
        add_items(root, "includedDataFiles", self.included_data_files)
        files = ET.SubElement(root, "dataFiles")
        for data_file in self.data_files:
            files.append(data_file.to_xml_element())
        change_sets = ET.SubElement(root, "contentChangeSets")
        for change_set in self.content_change_sets:
            change_sets.append(change_set.to_xml_element())
        add_items(root, "patchFiles", self.patch_files)
        return root

    def to_xml_bytes(self) -> bytes:
        return xml_bytes(self.to_xml_element())

    def to_bytes(self) -> bytes:
        return self.to_xml_bytes()


@dataclass(slots=True)
class DlcList:
    paths: list[str] = field(default_factory=list)

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> "DlcList":
        root = ET.fromstring(read_xml_text(source))
        return cls(paths=item_texts(child_by_name(root, "Paths")))

    def include(self, pack_name: str, *, mount: str = "dlcpacks") -> "DlcList":
        pack = pack_name.strip("/\\")
        self.paths.append(f"{mount}:/{pack}/")
        return self

    def to_xml_element(self) -> ET.Element:
        root = ET.Element("SMandatoryPacksData")
        add_items(root, "Paths", self.paths)
        return root

    def to_xml_bytes(self) -> bytes:
        return xml_bytes(self.to_xml_element())

    def to_bytes(self) -> bytes:
        return self.to_xml_bytes()


@dataclass(slots=True)
class DlcPatchMount:
    device_name: str
    path: str

    @classmethod
    def for_pack(cls, pack_name: str, *, device_name: str | None = None) -> "DlcPatchMount":
        return cls(device_name=_device_path(device_name or _device_name(pack_name)), path=f"update:/dlc_patch/{pack_name}/")

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> "DlcPatchMount":
        return cls(device_name=child_text(element, "deviceName"), path=child_text(element, "path"))

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item", {"type": "SExtraTitleUpdateMount"})
        add_text(element, "deviceName", self.device_name)
        add_text(element, "path", self.path)
        return element


@dataclass(slots=True)
class DlcExtraTitleUpdateData:
    mounts: list[DlcPatchMount] = field(default_factory=list)

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> "DlcExtraTitleUpdateData":
        root = ET.fromstring(read_xml_text(source))
        mounts = child_by_name(root, "Mounts")
        mount_items = list(mounts) if mounts is not None else []
        return cls(
            mounts=[
                DlcPatchMount.from_xml_element(item)
                for item in mount_items
                if item.tag.lower() == "item"
            ]
        )

    def mount(self, pack_name: str, *, device_name: str | None = None) -> DlcPatchMount:
        mount = DlcPatchMount.for_pack(pack_name, device_name=device_name)
        self.mounts.append(mount)
        return mount

    def to_xml_element(self) -> ET.Element:
        root = ET.Element("SExtraTitleUpdateData")
        mounts = ET.SubElement(root, "Mounts")
        for mount in self.mounts:
            mounts.append(mount.to_xml_element())
        return root

    def to_xml_bytes(self) -> bytes:
        return xml_bytes(self.to_xml_element())

    def to_bytes(self) -> bytes:
        return self.to_xml_bytes()


@dataclass(slots=True)
class DlcPack:
    name: str
    setup: DlcSetupData | None = None
    content: DlcContentXml = field(default_factory=DlcContentXml)
    files: dict[str, bytes | bytearray | memoryview | Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.setup is None:
            self.setup = DlcSetupData.compat_pack(self.name)

    @property
    def device_path(self) -> str:
        assert self.setup is not None
        return self.setup.device_path

    def path(self, relative_path: str) -> str:
        return f"{self.device_path}{relative_path.lstrip('/')}"

    def file(self, path: str, value: bytes | bytearray | memoryview | Any) -> "DlcPack":
        self.files[path.replace("\\", "/").lstrip("/")] = value
        return self

    def rpf(self, relative_path: str, archive: RpfArchive, *, map_data: bool = False, overlay: bool = False) -> DlcContentFile:
        path = self.path(relative_path)
        self.files[relative_path.replace("\\", "/").lstrip("/")] = archive
        return self.content.rpf(path, map_data=map_data, overlay=overlay)

    def ityp(self, relative_path: str) -> DlcContentFile:
        return self.content.ityp(self.path(relative_path))

    def change_set(self, name: str, *, group: DlcContentGroup | str = DlcContentGroup.STARTUP, enable_all: bool = True) -> DlcContentChangeSet:
        change_set = self.content.change_set(name, enable_all=enable_all)
        assert self.setup is not None
        self.setup.group(group, name)
        return change_set

    def to_rpf(self) -> RpfArchive:
        archive = RpfArchive.empty("dlc.rpf")
        assert self.setup is not None
        archive.add_file("setup2.xml", self.setup.to_xml_bytes())
        archive.add_file(self.setup.dat_file or "content.xml", self.content.to_xml_bytes())
        for path, value in self.files.items():
            archive.add_file(path, value)
        return archive

    def to_bytes(self) -> bytes:
        return self.to_rpf().to_bytes()

    def save_dlc_rpf(self, path: str | Path) -> Path:
        target = Path(path)
        if target.is_dir() or not target.suffix:
            target = target / self.name / "dlc.rpf"
        target.parent.mkdir(parents=True, exist_ok=True)
        self.to_rpf().save(target)
        return target


@dataclass(slots=True)
class DlcPatch:
    name: str
    setup: DlcSetupData | None = None
    content: DlcContentXml = field(default_factory=DlcContentXml)
    files: dict[str, bytes | bytearray | memoryview | Any] = field(default_factory=dict)
    device_name: str | None = None

    def __post_init__(self) -> None:
        if self.setup is None:
            self.setup = DlcSetupData.compat_pack(self.name, device_name=self.device_name)
        if self.device_name is None and self.setup is not None:
            self.device_name = self.setup.device_name

    @property
    def patch_mount(self) -> DlcPatchMount:
        return DlcPatchMount.for_pack(self.name, device_name=self.device_name)

    @property
    def patch_root(self) -> str:
        return f"dlc_patch/{self.name}"

    def file(self, path: str, value: bytes | bytearray | memoryview | Any) -> "DlcPatch":
        self.files[path.replace("\\", "/").lstrip("/")] = value
        return self

    def change_set(self, name: str, *, group: DlcContentGroup | str = DlcContentGroup.MAP, enable_all: bool = True) -> DlcContentChangeSet:
        change_set = self.content.change_set(name, enable_all=enable_all)
        assert self.setup is not None
        self.setup.group(group, name)
        return change_set

    def install_into(self, archive: RpfArchive, *, include_mount_manifest: bool = True) -> RpfArchive:
        assert self.setup is not None
        root = self.patch_root
        archive.add_file(f"{root}/setup2.xml", self.setup.to_xml_bytes())
        archive.add_file(f"{root}/{self.setup.dat_file or 'content.xml'}", self.content.to_xml_bytes())
        for path, value in self.files.items():
            archive.add_file(f"{root}/{path}", value)
        if include_mount_manifest:
            manifest = DlcExtraTitleUpdateData(mounts=[self.patch_mount])
            archive.add_file("common/data/extratitleupdatedata.meta", manifest.to_xml_bytes())
        return archive

    def to_update_rpf(self) -> RpfArchive:
        archive = RpfArchive.empty("update.rpf")
        self.install_into(archive)
        return archive

    def to_bytes(self) -> bytes:
        return self.to_update_rpf().to_bytes()

    def save_update_rpf(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.to_update_rpf().save(target)
        return target


def read_dlc_setup(source: bytes | str | Path) -> DlcSetupData:
    return DlcSetupData.from_xml(source)


def read_dlc_content(source: bytes | str | Path) -> DlcContentXml:
    return DlcContentXml.from_xml(source)


def read_dlc_list(source: bytes | str | Path) -> DlcList:
    return DlcList.from_xml(source)


def read_dlc_extra_title_update_data(source: bytes | str | Path) -> DlcExtraTitleUpdateData:
    return DlcExtraTitleUpdateData.from_xml(source)


def build_dlc_setup_xml(setup: DlcSetupData) -> bytes:
    return setup.to_xml_bytes()


def build_dlc_content_xml(content: DlcContentXml) -> bytes:
    return content.to_xml_bytes()


def build_dlc_list_xml(dlc_list: DlcList) -> bytes:
    return dlc_list.to_xml_bytes()


def build_dlc_extra_title_update_data_xml(data: DlcExtraTitleUpdateData) -> bytes:
    return data.to_xml_bytes()
