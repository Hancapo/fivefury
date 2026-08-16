from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..authoring.context import BuildContext
from ..authoring.diagnostics import ValidationReport
from ..game_target import GameTarget, coerce_game_target
from ..rpf import RpfArchive
from ..xml import (
    append_items,
    append_text,
    child_by_name,
    child_items,
    child_text,
    item_texts,
    parse_xml_root,
    xml_bytes,
)
from .content import (
    DlcChangeSetData,
    DlcContentChangeSet,
    DlcContentFile,
    DlcContentFileArray,
    DlcContentXml,
    DlcExecutionCondition,
    DlcExecutionConditions,
    DlcResourceReference,
)
from .enums import DlcContentGroup, DlcRpfEncryption
from .paths import dlc_platform_payload_path, dlc_platform_registration_path
from .setup import DlcContentChangeSetGroup, DlcSetupData


def _device_name(pack_name: str) -> str:
    return f"dlc_{pack_name}"


def _device_path(device_name: str) -> str:
    return device_name if device_name.endswith(":/") else f"{device_name}:/"


@dataclass(slots=True)
class DlcList:
    paths: list[str] = field(default_factory=list)

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> DlcList:
        root = parse_xml_root(source)
        return cls(paths=item_texts(child_by_name(root, "Paths")))

    def include(self, pack_name: str, *, mount: str = "dlcpacks") -> DlcList:
        pack = pack_name.strip("/\\")
        self.paths.append(f"{mount}:/{pack}/")
        return self

    def to_xml_element(self) -> ET.Element:
        root = ET.Element("SMandatoryPacksData")
        append_items(root, "Paths", self.paths)
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
    def for_pack(
        cls, pack_name: str, *, device_name: str | None = None
    ) -> DlcPatchMount:
        return cls(
            device_name=_device_path(device_name or _device_name(pack_name)),
            path=f"update:/dlc_patch/{pack_name}/",
        )

    @classmethod
    def from_xml_element(cls, element: ET.Element) -> DlcPatchMount:
        return cls(
            device_name=child_text(element, "deviceName"),
            path=child_text(element, "path"),
        )

    def to_xml_element(self) -> ET.Element:
        element = ET.Element("Item", {"type": "SExtraTitleUpdateMount"})
        append_text(element, "deviceName", self.device_name)
        append_text(element, "path", self.path)
        return element


@dataclass(slots=True)
class DlcExtraTitleUpdateData:
    mounts: list[DlcPatchMount] = field(default_factory=list)

    @classmethod
    def from_xml(cls, source: bytes | str | Path) -> DlcExtraTitleUpdateData:
        root = parse_xml_root(source)
        return cls(
            mounts=[
                DlcPatchMount.from_xml_element(item)
                for item in child_items(root, "Mounts")
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
    game: GameTarget | None = None
    rpf_encryption: DlcRpfEncryption = DlcRpfEncryption.OPEN

    def __post_init__(self) -> None:
        if self.setup is None:
            self.setup = DlcSetupData.compat_pack(self.name)
        if self.game is not None:
            self.game = coerce_game_target(self.game)
        self.rpf_encryption = DlcRpfEncryption(self.rpf_encryption)

    @property
    def device_path(self) -> str:
        assert self.setup is not None
        return self.setup.device_path

    def path(self, relative_path: str) -> str:
        return f"{self.device_path}{relative_path.lstrip('/')}"

    def resolve_content_path(self, registration: DlcContentFile | str) -> str | None:
        filename = (
            registration.filename
            if isinstance(registration, DlcContentFile)
            else str(registration)
        )
        if not filename.casefold().startswith(self.device_path.casefold()):
            return None
        return filename[len(self.device_path) :].lstrip("/")

    def file(self, path: str, value: bytes | bytearray | memoryview | Any) -> DlcPack:
        self.files[path.replace("\\", "/").lstrip("/")] = value
        return self

    def rpf(
        self,
        relative_path: str,
        archive: RpfArchive,
        *,
        map_data: bool = False,
        overlay: bool = False,
    ) -> DlcContentFile:
        path = self.path(relative_path)
        self.files[relative_path.replace("\\", "/").lstrip("/")] = archive
        return self.content.rpf(path, map_data=map_data, overlay=overlay)

    def platform_rpf(
        self,
        relative_path: str,
        archive: RpfArchive,
        *,
        map_data: bool = False,
        overlay: bool = False,
    ) -> DlcContentFile:
        registration_path = dlc_platform_registration_path(relative_path)
        payload_path = dlc_platform_payload_path(relative_path)
        self.files[payload_path.as_posix()] = archive
        return self.content.rpf(
            self.path(registration_path.as_posix()),
            map_data=map_data,
            overlay=overlay,
        )

    def ityp(self, relative_path: str) -> DlcContentFile:
        return self.content.ityp(self.path(relative_path))

    def change_set(
        self,
        name: str,
        *,
        group: DlcContentGroup | str = DlcContentGroup.STARTUP,
        enable_all: bool = True,
    ) -> DlcContentChangeSet:
        change_set = self.content.change_set(name, enable_all=enable_all)
        assert self.setup is not None
        self.setup.group(group, name)
        return change_set

    def validate(
        self,
        *,
        context: BuildContext | None = None,
        game: str | GameTarget | None = None,
        external_change_sets: Iterable[str] = (),
        require_local_change_sets: bool = False,
    ) -> ValidationReport:
        from .validation import validate_dlc_pack

        return validate_dlc_pack(
            self,
            context=context,
            game=game,
            external_change_sets=external_change_sets,
            require_local_change_sets=require_local_change_sets,
        )

    def to_rpf(
        self,
        *,
        game: str | GameTarget | None = None,
        encryption: DlcRpfEncryption | int | None = None,
        validate: bool = True,
    ) -> RpfArchive:
        if validate:
            self.validate(game=game).raise_for_errors()
        archive = RpfArchive.empty("dlc.rpf")
        archive.encryption = int(
            self.rpf_encryption if encryption is None else DlcRpfEncryption(encryption)
        )
        assert self.setup is not None
        archive.file("setup2.xml", self.setup.to_xml_bytes())
        archive.file(self.setup.dat_file or "content.xml", self.content.to_xml_bytes())
        for path, value in self.files.items():
            archive.file(path, value)
        return archive

    def to_bytes(
        self,
        *,
        game: str | GameTarget | None = None,
        encryption: DlcRpfEncryption | int | None = None,
        validate: bool = True,
    ) -> bytes:
        return self.to_rpf(
            game=game,
            encryption=encryption,
            validate=validate,
        ).to_bytes()

    def save_dlc_rpf(
        self,
        path: str | Path,
        *,
        game: str | GameTarget | None = None,
        encryption: DlcRpfEncryption | int | None = None,
        validate: bool = True,
    ) -> Path:
        target = Path(path)
        if target.is_dir() or not target.suffix:
            target = target / self.name / "dlc.rpf"
        target.parent.mkdir(parents=True, exist_ok=True)
        self.to_rpf(
            game=game,
            encryption=encryption,
            validate=validate,
        ).save(target)
        return target


@dataclass(slots=True)
class DlcPatch:
    name: str
    setup: DlcSetupData | None = None
    content: DlcContentXml = field(default_factory=DlcContentXml)
    files: dict[str, bytes | bytearray | memoryview | Any] = field(default_factory=dict)
    device_name: str | None = None
    game: GameTarget | None = None
    rpf_encryption: DlcRpfEncryption = DlcRpfEncryption.OPEN

    def __post_init__(self) -> None:
        if self.setup is None:
            self.setup = DlcSetupData.compat_pack(
                self.name, device_name=self.device_name
            )
        if self.device_name is None and self.setup is not None:
            self.device_name = self.setup.device_name
        if self.game is not None:
            self.game = coerce_game_target(self.game)
        self.rpf_encryption = DlcRpfEncryption(self.rpf_encryption)

    @property
    def patch_mount(self) -> DlcPatchMount:
        return DlcPatchMount.for_pack(self.name, device_name=self.device_name)

    @property
    def patch_root(self) -> str:
        return f"dlc_patch/{self.name}"

    def file(self, path: str, value: bytes | bytearray | memoryview | Any) -> DlcPatch:
        self.files[path.replace("\\", "/").lstrip("/")] = value
        return self

    def change_set(
        self,
        name: str,
        *,
        group: DlcContentGroup | str = DlcContentGroup.MAP,
        enable_all: bool = True,
    ) -> DlcContentChangeSet:
        change_set = self.content.change_set(name, enable_all=enable_all)
        assert self.setup is not None
        self.setup.group(group, name)
        return change_set

    def install_into(
        self,
        archive: RpfArchive,
        *,
        include_mount_manifest: bool = True,
    ) -> RpfArchive:
        assert self.setup is not None
        root = self.patch_root
        archive.file(f"{root}/setup2.xml", self.setup.to_xml_bytes())
        archive.file(
            f"{root}/{self.setup.dat_file or 'content.xml'}",
            self.content.to_xml_bytes(),
        )
        for path, value in self.files.items():
            archive.file(f"{root}/{path}", value)
        if include_mount_manifest:
            manifest = DlcExtraTitleUpdateData(mounts=[self.patch_mount])
            archive.file(
                "common/data/extratitleupdatedata.meta",
                manifest.to_xml_bytes(),
            )
        return archive

    def validate(
        self,
        *,
        context: BuildContext | None = None,
        game: str | GameTarget | None = None,
        external_change_sets: Iterable[str] = (),
        require_local_change_sets: bool = False,
    ) -> ValidationReport:
        from .validation import validate_dlc_pack

        return validate_dlc_pack(
            self,
            context=context,
            game=game,
            external_change_sets=external_change_sets,
            require_local_change_sets=require_local_change_sets,
        )

    def to_update_rpf(
        self,
        *,
        game: str | GameTarget | None = None,
        encryption: DlcRpfEncryption | int | None = None,
        validate: bool = True,
    ) -> RpfArchive:
        if validate:
            self.validate(game=game).raise_for_errors()
        archive = RpfArchive.empty("update.rpf")
        archive.encryption = int(
            self.rpf_encryption if encryption is None else DlcRpfEncryption(encryption)
        )
        self.install_into(archive)
        return archive

    def to_bytes(
        self,
        *,
        game: str | GameTarget | None = None,
        encryption: DlcRpfEncryption | int | None = None,
        validate: bool = True,
    ) -> bytes:
        return self.to_update_rpf(
            game=game,
            encryption=encryption,
            validate=validate,
        ).to_bytes()

    def save_update_rpf(
        self,
        path: str | Path,
        *,
        game: str | GameTarget | None = None,
        encryption: DlcRpfEncryption | int | None = None,
        validate: bool = True,
    ) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.to_update_rpf(
            game=game,
            encryption=encryption,
            validate=validate,
        ).save(target)
        return target


def read_dlc_setup(source: bytes | str | Path) -> DlcSetupData:
    return DlcSetupData.from_xml(source)


def read_dlc_content(source: bytes | str | Path) -> DlcContentXml:
    return DlcContentXml.from_xml(source)


def read_dlc_list(source: bytes | str | Path) -> DlcList:
    return DlcList.from_xml(source)


def read_dlc_extra_title_update_data(
    source: bytes | str | Path,
) -> DlcExtraTitleUpdateData:
    return DlcExtraTitleUpdateData.from_xml(source)


def build_dlc_setup_xml(setup: DlcSetupData) -> bytes:
    return setup.to_xml_bytes()


def build_dlc_content_xml(content: DlcContentXml) -> bytes:
    return content.to_xml_bytes()


def build_dlc_list_xml(dlc_list: DlcList) -> bytes:
    return dlc_list.to_xml_bytes()


def build_dlc_extra_title_update_data_xml(data: DlcExtraTitleUpdateData) -> bytes:
    return data.to_xml_bytes()


__all__ = [
    "DlcChangeSetData",
    "DlcContentChangeSet",
    "DlcContentChangeSetGroup",
    "DlcContentFile",
    "DlcContentFileArray",
    "DlcContentXml",
    "DlcExecutionCondition",
    "DlcExecutionConditions",
    "DlcExtraTitleUpdateData",
    "DlcList",
    "DlcPack",
    "DlcPatch",
    "DlcPatchMount",
    "DlcResourceReference",
    "DlcSetupData",
    "build_dlc_content_xml",
    "build_dlc_extra_title_update_data_xml",
    "build_dlc_list_xml",
    "build_dlc_setup_xml",
    "read_dlc_content",
    "read_dlc_extra_title_update_data",
    "read_dlc_list",
    "read_dlc_setup",
]
