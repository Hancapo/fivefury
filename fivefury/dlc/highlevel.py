from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..authoring.context import BuildContext
from ..authoring.diagnostics import ValidationReport
from ..common import atomic_write_bytes
from ..game_target import GameTarget, coerce_game_target
from ..rpf import RpfArchive, RpfFileEntry
from ..rpf.entries import RpfResourceFileEntry
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
from .paths import iter_dlc_folder_files
from .validation import validate_dlc_folder_assets, validate_dlc_pack


@dataclass(slots=True)
class DlcFolderMetadata:
    setup: DlcSetupData
    content: DlcContentXml
    dlc_list: DlcList
    game: GameTarget | None = None

    def __post_init__(self) -> None:
        if self.game is not None:
            self.game = coerce_game_target(self.game)

    def to_pack(self) -> DlcPack:
        return DlcPack(
            self.setup.name_hash,
            setup=self.setup,
            content=self.content,
            game=self.game,
        )

    def validate(
        self,
        folder: str | Path | None = None,
        *,
        context: BuildContext | None = None,
        validate_assets: bool | None = None,
    ) -> ValidationReport:
        issues = validate_dlc_pack(self.to_pack(), context=context)
        target_game = (
            self.game
            if self.game is not None
            else (context.game if context is not None else None)
        )
        check_assets = (
            target_game is not None if validate_assets is None else validate_assets
        )
        if check_assets:
            if target_game is None:
                issues.issue(
                    "folder.game.missing",
                    "asset validation requires an explicit game target",
                )
            elif folder is None:
                issues.issue(
                    "folder.path.missing",
                    "asset validation requires the DLC folder path",
                )
            else:
                issues.extend(validate_dlc_folder_assets(folder, target_game))
        return issues

    def write(
        self,
        folder: str | Path,
        *,
        write_dlc_list: bool = False,
        validate: bool = True,
        validate_assets: bool | None = None,
    ) -> dict[str, Path]:
        root = Path(folder)
        if validate:
            self.validate(root, validate_assets=validate_assets).raise_for_errors()

        setup_data = self.setup.to_xml_bytes()
        content_data = self.content.to_xml_bytes()
        dlc_list_data = self.dlc_list.to_xml_bytes() if write_dlc_list else None
        written: dict[str, Path] = {}
        setup_path = root / "setup2.xml"
        content_path = root / (self.setup.dat_file or "content.xml")
        atomic_write_bytes(setup_path, setup_data)
        atomic_write_bytes(content_path, content_data)
        written["setup"] = setup_path
        written["content"] = content_path
        if dlc_list_data is not None:
            dlc_list_path = root / "dlclist.xml"
            atomic_write_bytes(dlc_list_path, dlc_list_data)
            written["dlclist"] = dlc_list_path
        return written


def _device_name(pack_name: str) -> str:
    return f"dlc_{pack_name}"


def _device_path(pack_name: str, device_name: str | None = None) -> str:
    name = device_name or _device_name(pack_name)
    return name if name.endswith(":/") else f"{name}:/"


def _virtual_path(
    pack_name: str, rel_path: str, *, device_name: str | None = None
) -> str:
    return f"{_device_path(pack_name, device_name)}{rel_path}"


def _is_map_data_rpf(rel_path: str) -> bool:
    lowered = rel_path.lower()
    if not lowered.endswith(".rpf"):
        return False
    if "levels/gta5" not in lowered:
        return False
    map_tokens = (
        "metadata",
        "placement",
        "ymap",
        "navmesh",
        "lodlights",
        "distantlights",
    )
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


def _infer_content_file(
    pack_name: str, rel_path: str, *, device_name: str | None = None
) -> DlcContentFile | None:
    lowered = rel_path.lower()
    filename = _virtual_path(pack_name, rel_path, device_name=device_name)
    if lowered.endswith(".rpf"):
        return DlcContentFile(
            filename=filename,
            file_type=DlcDataFileType.RPF,
            overlay=_is_map_data_rpf(rel_path) and "navmesh" in lowered,
            persistent=True,
            contents=DlcDataFileContents.DLC_MAP_DATA
            if _is_map_data_rpf(rel_path)
            else None,
            load_completely=True if "metadata" in lowered else None,
        )
    if lowered.endswith(".ityp"):
        return DlcContentFile(
            filename=filename, file_type=DlcDataFileType.DLC_ITYP_REQUEST
        )
    audio_type = _audio_file_type(rel_path)
    if audio_type is not None:
        return DlcContentFile(filename=filename, file_type=audio_type)
    if lowered.endswith("/audio/sfx") or "/audio/sfx/" in lowered:
        return DlcContentFile(
            filename=filename, file_type=DlcDataFileType.AUDIO_WAVEPACK
        )
    if lowered.endswith("overlayinfo.xml"):
        return DlcContentFile(filename=filename, file_type=DlcDataFileType.OVERLAY_INFO)
    if lowered.endswith("interiorproxies.meta"):
        return DlcContentFile(
            filename=filename, file_type=DlcDataFileType.INTERIOR_PROXY_ORDER
        )
    if lowered.endswith("dlctext.meta"):
        return DlcContentFile(
            filename=filename, file_type=DlcDataFileType.TEXTFILE_META
        )
    if lowered.endswith("gtxd.meta"):
        return DlcContentFile(
            filename=filename, file_type=DlcDataFileType.GTXD_PARENTING_DATA
        )
    return None


def iter_dlc_content_candidates(
    folder: str | Path, *, include_dot_dirs: bool = False
) -> Iterable[str]:
    for rel, _path in iter_dlc_folder_files(
        folder,
        include_dot_dirs=include_dot_dirs,
    ):
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
    game: str | GameTarget | None = None,
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
    return DlcFolderMetadata(
        setup=setup,
        content=content,
        dlc_list=DlcList().include(pack_name, mount=mount),
        game=game,
    )


def write_dlc_folder_metadata(
    folder: str | Path,
    *,
    pack_name: str | None = None,
    order: int = 0,
    device_name: str | None = None,
    dat_file: str = "content.xml",
    write_dlc_list: bool = False,
    game: str | GameTarget | None = None,
    validate: bool = True,
    validate_assets: bool | None = None,
) -> DlcFolderMetadata:
    root = Path(folder)
    metadata = create_dlc_folder_metadata(
        pack_name or root.name,
        root,
        order=order,
        device_name=device_name,
        dat_file=dat_file,
        game=game,
    )
    metadata.write(
        root,
        write_dlc_list=write_dlc_list,
        validate=validate,
        validate_assets=validate_assets,
    )
    return metadata


def create_dlc_list_for_packs(*pack_names: str, mount: str = "dlcpacks") -> DlcList:
    dlc_list = DlcList()
    for pack_name in pack_names:
        dlc_list.include(pack_name, mount=mount)
    return dlc_list


def create_dlc_patch_manifest(
    *pack_names: str, device_prefix: str = "dlc_"
) -> DlcExtraTitleUpdateData:
    data = DlcExtraTitleUpdateData()
    for pack_name in pack_names:
        data.mounts.append(
            DlcPatchMount.for_pack(pack_name, device_name=f"{device_prefix}{pack_name}")
        )
    return data


def read_dlc_pack(
    source: str | Path | bytes | RpfArchive,
    *,
    game: str | GameTarget | None = None,
    load_files: bool = False,
) -> DlcPack:
    if not isinstance(source, (RpfArchive, bytes)):
        path = Path(source)
        with RpfArchive.from_path(
            path / "dlc.rpf" if path.is_dir() else path
        ) as archive:
            return read_dlc_pack(
                archive,
                game=game,
                load_files=load_files,
            )
    if isinstance(source, RpfArchive):
        archive = source
    else:
        archive = RpfArchive.from_bytes(source, name="dlc.rpf")
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
    content_entry = entries.get(
        (setup.dat_file or "content.xml").lower().replace("\\", "/")
    )
    if content_entry is None:
        raise ValueError(
            f"DLC archive does not contain {setup.dat_file or 'content.xml'}"
        )
    content = DlcContentXml.from_xml(
        archive.read_entry_bytes(content_entry, logical=True)
    )
    metadata_paths = {
        "setup2.xml",
        (setup.dat_file or "content.xml").lower().replace("\\", "/"),
    }
    files: dict[str, bytes] = {}
    if load_files:
        for normalized, entry in entries.items():
            if normalized in metadata_paths:
                continue
            files[entry.path] = (
                archive.read_entry_standalone(entry)
                if isinstance(entry, RpfResourceFileEntry)
                else archive.read_entry_bytes(entry, logical=True)
            )
    return DlcPack(
        setup.name_hash,
        setup=setup,
        content=content,
        files=files,
        game=game,
    )


__all__ = [
    "DlcFolderMetadata",
    "create_dlc_folder_metadata",
    "create_dlc_list_for_packs",
    "create_dlc_patch_manifest",
    "infer_dlc_content_from_folder",
    "iter_dlc_content_candidates",
    "read_dlc_pack",
    "write_dlc_folder_metadata",
]
