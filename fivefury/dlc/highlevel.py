from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..rpf import RpfArchive, RpfFileEntry
from .enums import DlcContentGroup, DlcDataFileContents, DlcDataFileType
from .model import (
    DlcContentFile,
    DlcContentXml,
    DlcExtraTitleUpdateData,
    DlcList,
    DlcPack,
    DlcPatchMount,
    DlcSetupData,
)


@dataclass(slots=True)
class DlcValidationIssue:
    code: str
    message: str
    severity: str = "error"
    path: str = ""


@dataclass(slots=True)
class DlcFolderMetadata:
    setup: DlcSetupData
    content: DlcContentXml
    dlc_list: DlcList

    def to_pack(self) -> DlcPack:
        return DlcPack(self.setup.name_hash, setup=self.setup, content=self.content)

    def write(self, folder: str | Path, *, write_dlc_list: bool = False) -> dict[str, Path]:
        root = Path(folder)
        root.mkdir(parents=True, exist_ok=True)
        written: dict[str, Path] = {}
        setup_path = root / "setup2.xml"
        content_path = root / (self.setup.dat_file or "content.xml")
        setup_path.write_bytes(self.setup.to_xml_bytes())
        content_path.write_bytes(self.content.to_xml_bytes())
        written["setup"] = setup_path
        written["content"] = content_path
        if write_dlc_list:
            dlc_list_path = root / "dlclist.xml"
            dlc_list_path.write_bytes(self.dlc_list.to_xml_bytes())
            written["dlclist"] = dlc_list_path
        return written


def _normalize_rel(path: str | Path) -> str:
    return str(path).replace("\\", "/").lstrip("/")


def _device_name(pack_name: str) -> str:
    return f"dlc_{pack_name}"


def _device_path(pack_name: str, device_name: str | None = None) -> str:
    name = device_name or _device_name(pack_name)
    return name if name.endswith(":/") else f"{name}:/"


def _virtual_path(pack_name: str, rel_path: str, *, device_name: str | None = None) -> str:
    return f"{_device_path(pack_name, device_name)}{rel_path}"


def _is_dot_path(path: Path, root: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def _is_map_data_rpf(rel_path: str) -> bool:
    lowered = rel_path.lower()
    if not lowered.endswith(".rpf"):
        return False
    if "levels/gta5" not in lowered:
        return False
    map_tokens = ("metadata", "placement", "ymap", "navmesh", "lodlights", "distantlights")
    return any(token in lowered for token in map_tokens)


def _audio_file_type(rel_path: str) -> DlcDataFileType | None:
    lowered = rel_path.lower()
    if "/audio/" not in f"/{lowered}" or not lowered.endswith(".dat"):
        return None
    stem = Path(lowered).stem
    if stem.endswith("_sounds"):
        return DlcDataFileType.AUDIO_SOUNDDATA
    if stem.endswith("_game"):
        return DlcDataFileType.AUDIO_GAMEDATA
    if stem.endswith("_mix"):
        return DlcDataFileType.AUDIO_DYNAMIXDATA
    if stem.endswith("_speech"):
        return DlcDataFileType.AUDIO_SPEECHDATA
    if stem.endswith("_amp"):
        return DlcDataFileType.AUDIO_SYNTHDATA
    return None


def _infer_content_file(pack_name: str, rel_path: str, *, device_name: str | None = None) -> DlcContentFile | None:
    lowered = rel_path.lower()
    filename = _virtual_path(pack_name, rel_path, device_name=device_name)
    if lowered.endswith(".rpf"):
        return DlcContentFile(
            filename=filename,
            file_type=DlcDataFileType.RPF,
            overlay=_is_map_data_rpf(rel_path) and "navmesh" in lowered,
            persistent=True,
            contents=DlcDataFileContents.DLC_MAP_DATA if _is_map_data_rpf(rel_path) else None,
            load_completely=True if "metadata" in lowered else None,
        )
    if lowered.endswith(".ityp"):
        return DlcContentFile(filename=filename, file_type=DlcDataFileType.DLC_ITYP_REQUEST)
    audio_type = _audio_file_type(rel_path)
    if audio_type is not None:
        return DlcContentFile(filename=filename, file_type=audio_type)
    if lowered.endswith("/audio/sfx") or "/audio/sfx/" in lowered:
        return DlcContentFile(filename=filename, file_type=DlcDataFileType.AUDIO_WAVEPACK)
    if lowered.endswith("overlayinfo.xml"):
        return DlcContentFile(filename=filename, file_type=DlcDataFileType.OVERLAY_INFO)
    if lowered.endswith("interiorproxies.meta"):
        return DlcContentFile(filename=filename, file_type=DlcDataFileType.INTERIOR_PROXY_ORDER)
    if lowered.endswith("dlctext.meta"):
        return DlcContentFile(filename=filename, file_type=DlcDataFileType.TEXTFILE_META)
    if lowered.endswith("gtxd.meta"):
        return DlcContentFile(filename=filename, file_type=DlcDataFileType.GTXD_PARENTING_DATA)
    return None


def iter_dlc_content_candidates(folder: str | Path, *, include_dot_dirs: bool = False) -> Iterable[str]:
    root = Path(folder)
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().lower()):
        if not path.is_file():
            continue
        if not include_dot_dirs and _is_dot_path(path, root):
            continue
        rel = path.relative_to(root).as_posix()
        if rel.lower() in {"setup2.xml", "content.xml"}:
            continue
        yield rel


def infer_dlc_content_from_folder(
    pack_name: str,
    folder: str | Path,
    *,
    device_name: str | None = None,
    dat_file: str = "content.xml",
    change_set_name: str | None = None,
    group: DlcContentGroup | str = DlcContentGroup.STARTUP,
) -> tuple[DlcContentXml, DlcSetupData]:
    content = DlcContentXml()
    setup = DlcSetupData.compat_pack(pack_name, device_name=device_name)
    setup.dat_file = dat_file
    for rel in iter_dlc_content_candidates(folder):
        item = _infer_content_file(pack_name, rel, device_name=device_name)
        if item is not None:
            content.data_files.append(item)
    if content.data_files:
        name = change_set_name or f"{pack_name.upper()}_AUTOGEN"
        content.change_set(name, enable_all=True)
        setup.group(group, name)
    return content, setup


def create_dlc_folder_metadata(
    pack_name: str,
    folder: str | Path,
    *,
    order: int = 0,
    device_name: str | None = None,
    dat_file: str = "content.xml",
    mount: str = "dlcpacks",
    change_set_name: str | None = None,
    group: DlcContentGroup | str = DlcContentGroup.STARTUP,
) -> DlcFolderMetadata:
    content, setup = infer_dlc_content_from_folder(
        pack_name,
        folder,
        device_name=device_name,
        dat_file=dat_file,
        change_set_name=change_set_name,
        group=group,
    )
    setup.order = int(order)
    return DlcFolderMetadata(setup=setup, content=content, dlc_list=DlcList().include(pack_name, mount=mount))


def write_dlc_folder_metadata(
    folder: str | Path,
    *,
    pack_name: str | None = None,
    order: int = 0,
    device_name: str | None = None,
    dat_file: str = "content.xml",
    write_dlc_list: bool = False,
) -> DlcFolderMetadata:
    root = Path(folder)
    metadata = create_dlc_folder_metadata(
        pack_name or root.name,
        root,
        order=order,
        device_name=device_name,
        dat_file=dat_file,
    )
    metadata.write(root, write_dlc_list=write_dlc_list)
    return metadata


def create_dlc_list_for_packs(*pack_names: str, mount: str = "dlcpacks") -> DlcList:
    dlc_list = DlcList()
    for pack_name in pack_names:
        dlc_list.include(pack_name, mount=mount)
    return dlc_list


def create_dlc_patch_manifest(*pack_names: str, device_prefix: str = "dlc_") -> DlcExtraTitleUpdateData:
    data = DlcExtraTitleUpdateData()
    for pack_name in pack_names:
        data.mounts.append(DlcPatchMount.for_pack(pack_name, device_name=f"{device_prefix}{pack_name}"))
    return data


def read_dlc_pack(source: str | Path | bytes | RpfArchive) -> DlcPack:
    if isinstance(source, RpfArchive):
        archive = source
    elif isinstance(source, bytes):
        archive = RpfArchive.from_bytes(source, name="dlc.rpf")
    else:
        path = Path(source)
        archive = RpfArchive.from_path(path / "dlc.rpf" if path.is_dir() else path)
    entries: dict[str, RpfFileEntry] = {}
    for entry in archive.iter_entries():
        if not isinstance(entry, RpfFileEntry):
            continue
        normalized = entry.path.lower().replace("\\", "/")
        entries[normalized] = entry
    setup_entry = entries.get("setup2.xml")
    if setup_entry is None:
        raise ValueError("DLC archive does not contain setup2.xml")
    setup = DlcSetupData.from_xml(archive.read_entry_bytes(setup_entry, logical=True))
    content_entry = entries.get((setup.dat_file or "content.xml").lower().replace("\\", "/"))
    if content_entry is None:
        raise ValueError(f"DLC archive does not contain {setup.dat_file or 'content.xml'}")
    content = DlcContentXml.from_xml(archive.read_entry_bytes(content_entry, logical=True))
    return DlcPack(setup.name_hash, setup=setup, content=content)


def validate_dlc_setup(setup: DlcSetupData, content: DlcContentXml | None = None) -> list[DlcValidationIssue]:
    issues: list[DlcValidationIssue] = []
    if not setup.device_name:
        issues.append(DlcValidationIssue("setup.device_name.empty", "setup2.xml requires deviceName"))
    if not setup.name_hash:
        issues.append(DlcValidationIssue("setup.name_hash.empty", "setup2.xml requires nameHash"))
    if not setup.dat_file:
        issues.append(DlcValidationIssue("setup.dat_file.empty", "setup2.xml requires datFile"))
    if content is not None:
        defined = {change_set.name.lower() for change_set in content.content_change_sets}
        for group in setup.content_change_set_groups:
            for change_set in group.change_sets:
                if change_set.lower() not in defined:
                    issues.append(
                        DlcValidationIssue(
                            "setup.group.missing_change_set",
                            f"setup group {group.name!r} references undefined content change set {change_set!r}",
                            path=str(group.name),
                        )
                    )
    return issues


def validate_dlc_content(content: DlcContentXml) -> list[DlcValidationIssue]:
    issues: list[DlcValidationIssue] = []
    if not content.data_files:
        issues.append(DlcValidationIssue("content.files.empty", "content.xml has no dataFiles", severity="warning"))
    seen: set[str] = set()
    for data_file in content.data_files:
        key = data_file.filename.lower()
        if not data_file.filename:
            issues.append(DlcValidationIssue("content.file.empty_filename", "dataFiles item requires filename"))
        if not data_file.file_type:
            issues.append(DlcValidationIssue("content.file.empty_type", "dataFiles item requires fileType", path=data_file.filename))
        if key in seen:
            issues.append(DlcValidationIssue("content.file.duplicate", f"duplicate data file {data_file.filename!r}", path=data_file.filename))
        seen.add(key)
    for change_set in content.content_change_sets:
        for filename in change_set.files_to_enable + change_set.files_to_disable + change_set.files_to_invalidate:
            if filename.lower() not in seen:
                issues.append(
                    DlcValidationIssue(
                        "content.change_set.unknown_file",
                        f"change set {change_set.name!r} references unregistered file {filename!r}",
                        severity="warning",
                        path=filename,
                    )
                )
    return issues


def validate_dlc_pack(pack: DlcPack) -> list[DlcValidationIssue]:
    if pack.setup is None:
        return [DlcValidationIssue("pack.setup.missing", "DLC pack has no setup metadata")]
    return validate_dlc_setup(pack.setup, pack.content) + validate_dlc_content(pack.content)
