from __future__ import annotations

import struct
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..authoring.context import BuildContext
from ..authoring.diagnostics import Diagnostic, DiagnosticSeverity, ValidationReport
from ..game_target import GameTarget, coerce_game_target
from ..resource import RSC7_MAGIC
from ..rpf import RpfArchive, RpfFileEntry, RpfFileSource, RpfResourceFileEntry
from .content import (
    DlcChangeSetData,
    DlcContentChangeSet,
    DlcContentFile,
    DlcContentXml,
    DlcResourceReference,
)
from .enums import DlcContentGroup, DlcDataFileType
from .paths import iter_dlc_folder_files
from .setup import DlcSetupData

_TARGET_AWARE_EXTENSIONS = frozenset(
    {".ybn", ".ycd", ".ydd", ".ydr", ".yed", ".yft", ".ynd", ".ynv", ".ytd"}
)
_ENHANCED_ACCEPTS_LEGACY = frozenset({".ycd"})
_LEGACY_DRAWABLE_VERSIONS = frozenset({165})
_ENHANCED_DRAWABLE_VERSIONS = frozenset({154, 159})
_LEGACY_YFT_VERSIONS = frozenset({162})
_ENHANCED_YFT_VERSIONS = frozenset({171})
_LEGACY_YTD_VERSIONS = frozenset({13, 68, 162, 165})
_ENHANCED_YTD_VERSIONS = frozenset({5, 71, 154, 159, 171})


def _diagnostic(
    code: str,
    message: str,
    severity: str = "error",
    path: str = "",
) -> Diagnostic:
    return Diagnostic(
        code,
        message,
        DiagnosticSeverity.ERROR if severity == "error" else DiagnosticSeverity.WARNING,
        path=path or None,
    )


@dataclass(slots=True)
class _DlcFolderAssets:
    files: dict[str, bytes | RpfArchive]


@dataclass(slots=True)
class _UnreadableAsset:
    error: Exception


def _enum_value_is_valid(enum_type: type[Any], value: object) -> bool:
    try:
        enum_type(getattr(value, "value", value))
    except (TypeError, ValueError):
        return False
    return True


def _validate_resource_reference(
    reference: DlcResourceReference,
    *,
    path: str,
) -> list[Diagnostic]:
    issues: list[Diagnostic] = []
    if not reference.asset_name:
        issues.append(
            _diagnostic(
                "content.resource.empty_asset",
                "resource reference requires AssetName",
                path=path,
            )
        )
    if len(reference.extension.encode("ascii", errors="replace")) > 7:
        issues.append(
            _diagnostic(
                "content.resource.extension_too_long",
                "resource extension exceeds the 7-character runtime field",
                path=path,
            )
        )
    return issues


def _validate_content_file(data_file: DlcContentFile) -> list[Diagnostic]:
    issues: list[Diagnostic] = []
    if not data_file.filename:
        issues.append(
            _diagnostic(
                "content.file.empty_filename",
                "dataFiles item requires filename",
            )
        )
    elif len(data_file.filename.encode("utf-8")) > 127:
        issues.append(
            _diagnostic(
                "content.file.filename_too_long",
                "dataFiles filename exceeds the 127-byte runtime field",
                path=data_file.filename,
            )
        )
    if not data_file.file_type:
        issues.append(
            _diagnostic(
                "content.file.empty_type",
                "dataFiles item requires fileType",
                path=data_file.filename,
            )
        )
    elif not _enum_value_is_valid(DlcDataFileType, data_file.file_type):
        issues.append(
            _diagnostic(
                "content.file.unknown_type",
                f"unknown data file type {data_file.file_type!r}",
                path=data_file.filename,
            )
        )
    return issues


def _change_set_references(
    change_set: DlcContentChangeSet | DlcChangeSetData,
) -> Iterator[str]:
    yield from change_set.files_to_enable
    yield from change_set.files_to_disable
    yield from change_set.files_to_invalidate


def _change_set_resources(
    change_set: DlcContentChangeSet | DlcChangeSetData,
) -> Iterator[DlcResourceReference]:
    yield from change_set.resident_resources
    yield from change_set.unregister_resources


def validate_dlc_setup(
    setup: DlcSetupData,
    content: DlcContentXml | None = None,
    *,
    external_change_sets: Iterable[str] = (),
    require_local_change_sets: bool = False,
) -> ValidationReport:
    issues: list[Diagnostic] = []
    if not setup.device_name:
        issues.append(
            _diagnostic(
                "setup.device_name.empty",
                "setup2.xml requires deviceName",
            )
        )
    if not setup.name_hash:
        issues.append(
            _diagnostic(
                "setup.name_hash.empty",
                "setup2.xml requires nameHash",
            )
        )
    if not setup.dat_file:
        issues.append(
            _diagnostic(
                "setup.dat_file.empty",
                "setup2.xml requires datFile",
            )
        )
    for group in setup.content_change_set_groups:
        if not _enum_value_is_valid(DlcContentGroup, group.name):
            issues.append(
                _diagnostic(
                    "setup.group.unknown",
                    f"unknown content change-set group {group.name!r}",
                    path=str(group.name),
                )
            )
    if content is not None and require_local_change_sets:
        defined = {
            change_set.name.lower() for change_set in content.content_change_sets
        }
        defined.update(str(name).lower() for name in external_change_sets)
        for group in setup.content_change_set_groups:
            for change_set in group.change_sets:
                if change_set.lower() not in defined:
                    issues.append(
                        _diagnostic(
                            "setup.group.missing_change_set",
                            (
                                f"setup group {group.name!r} references undefined "
                                f"content change set {change_set!r}"
                            ),
                            path=str(group.name),
                        )
                    )
    return ValidationReport(issues)


def validate_dlc_content(content: DlcContentXml) -> ValidationReport:
    issues: list[Diagnostic] = []
    all_files = [
        *content.data_files,
        *(
            data_file
            for included in content.included_xml_files
            for data_file in included.data_files
        ),
    ]
    if not all_files:
        issues.append(
            _diagnostic(
                "content.files.empty",
                "content.xml has no dataFiles",
                severity="warning",
            )
        )
    seen: set[str] = set()
    for data_file in all_files:
        issues.extend(_validate_content_file(data_file))
        key = data_file.filename.lower()
        if key in seen:
            issues.append(
                _diagnostic(
                    "content.file.duplicate",
                    f"duplicate data file {data_file.filename!r}",
                    path=data_file.filename,
                )
            )
        seen.add(key)
    for change_set in content.content_change_sets:
        scopes: tuple[DlcContentChangeSet | DlcChangeSetData, ...] = (
            change_set,
            *change_set.map_change_set_data,
        )
        for scope in scopes:
            for filename in _change_set_references(scope):
                if filename.lower() not in seen:
                    issues.append(
                        _diagnostic(
                            "content.change_set.unknown_file",
                            (
                                f"change set {change_set.name!r} references "
                                f"unregistered file {filename!r}"
                            ),
                            severity="warning",
                            path=filename,
                        )
                    )
            for reference in _change_set_resources(scope):
                issues.extend(
                    _validate_resource_reference(
                        reference,
                        path=change_set.name,
                    )
                )
    return ValidationReport(issues)


def _resource_version(data: bytes) -> int:
    if len(data) < 16 or struct.unpack_from("<I", data, 0)[0] != RSC7_MAGIC:
        raise ValueError("asset is not a standalone RSC7 resource")
    return struct.unpack_from("<I", data, 4)[0]


def _version_target(
    version: int,
    *,
    legacy: frozenset[int],
    enhanced: frozenset[int],
) -> GameTarget:
    if version in enhanced:
        return GameTarget.GTA5_ENHANCED
    if version in legacy:
        return GameTarget.GTA5
    raise ValueError(f"unsupported resource version {version}")


def _target_from_resource(path: str, data: bytes) -> GameTarget:
    extension = Path(path).suffix.lower()
    version = _resource_version(data)
    if extension in {".ydr", ".ydd"}:
        return _version_target(
            version,
            legacy=_LEGACY_DRAWABLE_VERSIONS,
            enhanced=_ENHANCED_DRAWABLE_VERSIONS,
        )
    if extension == ".yft":
        return _version_target(
            version,
            legacy=_LEGACY_YFT_VERSIONS,
            enhanced=_ENHANCED_YFT_VERSIONS,
        )
    if extension == ".ytd":
        return _version_target(
            version,
            legacy=_LEGACY_YTD_VERSIONS,
            enhanced=_ENHANCED_YTD_VERSIONS,
        )
    if extension == ".ybn":
        from ..ybn import read_ybn

        return read_ybn(data, path=path).game
    if extension == ".ycd":
        from ..ycd import read_ycd

        return read_ycd(data, path=path).game
    if extension == ".ynd":
        from ..ynd import read_ynd

        return read_ynd(data, path=path).game
    if extension == ".ynv":
        from ..ynv import read_ynv

        return read_ynv(data, path=path).game
    if extension == ".yed":
        from ..yed import read_yed

        return read_yed(data, path=path).game
    raise ValueError(f"unsupported target-aware asset type {extension!r}")


def _coerce_asset_bytes(value: object) -> bytes:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, RpfFileSource):
        return value.path.read_bytes()
    to_bytes = getattr(value, "to_bytes", None)
    if callable(to_bytes):
        return bytes(to_bytes())
    raise TypeError(f"asset of type {type(value).__name__} cannot be serialized")


def _iter_archive_assets(
    archive: RpfArchive,
    *,
    prefix: str,
) -> Iterator[tuple[str, bytes | _UnreadableAsset]]:
    for entry in archive.iter_entries():
        if not isinstance(entry, RpfFileEntry):
            continue
        path = f"{prefix}/{entry.path}".strip("/")
        try:
            if isinstance(entry, RpfResourceFileEntry):
                data = archive.read_entry_standalone(entry)
            else:
                data = archive.read_entry_bytes(entry, logical=True)
        except (OSError, TypeError, ValueError) as exc:
            yield path, _UnreadableAsset(exc)
            continue
        if Path(path).suffix.lower() == ".rpf":
            try:
                nested = RpfArchive.from_bytes(
                    data,
                    name=entry.name,
                    crypto=archive.crypto,
                )
            except (OSError, TypeError, ValueError) as exc:
                yield path, _UnreadableAsset(exc)
                continue
            yield from _iter_archive_assets(nested, prefix=path)
        else:
            yield path, data


def _iter_pack_assets(pack: object) -> Iterator[tuple[str, object]]:
    files = getattr(pack, "files", {})
    for path, value in files.items():
        normalized = str(path).replace("\\", "/").lstrip("/")
        if isinstance(value, RpfArchive):
            yield from _iter_archive_assets(value, prefix=normalized)
            continue
        if Path(normalized).suffix.lower() == ".rpf":
            try:
                data = _coerce_asset_bytes(value)
                nested = RpfArchive.from_bytes(data, name=Path(normalized).name)
            except (OSError, TypeError, ValueError) as exc:
                yield normalized, _UnreadableAsset(exc)
                continue
            yield from _iter_archive_assets(nested, prefix=normalized)
            continue
        yield normalized, value


def validate_dlc_asset_targets(
    pack: object,
    game: str | GameTarget,
) -> ValidationReport:
    target = coerce_game_target(game)
    issues: list[Diagnostic] = []
    for path, value in _iter_pack_assets(pack):
        if isinstance(value, _UnreadableAsset):
            issues.append(
                _diagnostic(
                    "pack.asset.invalid_resource",
                    str(value.error),
                    path=path,
                )
            )
            continue
        if Path(path).suffix.lower() not in _TARGET_AWARE_EXTENSIONS:
            continue
        try:
            asset_game = getattr(value, "game", None)
            if asset_game is not None:
                asset_target = coerce_game_target(asset_game)
            else:
                asset_target = _target_from_resource(path, _coerce_asset_bytes(value))
        except (OSError, TypeError, ValueError) as exc:
            issues.append(
                _diagnostic(
                    "pack.asset.invalid_resource",
                    str(exc),
                    path=path,
                )
            )
            continue
        extension = Path(path).suffix.lower()
        legacy_is_compatible = (
            target is GameTarget.GTA5_ENHANCED
            and asset_target is GameTarget.GTA5
            and extension in _ENHANCED_ACCEPTS_LEGACY
        )
        if asset_target is not target and not legacy_is_compatible:
            issues.append(
                _diagnostic(
                    "pack.asset.target_mismatch",
                    (
                        f"asset targets {asset_target.value}, but the DLC targets "
                        f"{target.value}"
                    ),
                    path=path,
                )
            )
    return ValidationReport(issues)


def validate_dlc_folder_assets(
    folder: str | Path,
    game: str | GameTarget,
    *,
    include_dot_dirs: bool = False,
) -> ValidationReport:
    files: dict[str, bytes | RpfArchive] = {}
    issues: list[Diagnostic] = []
    for relative, path in iter_dlc_folder_files(
        folder,
        include_dot_dirs=include_dot_dirs,
    ):
        extension = path.suffix.lower()
        if extension not in _TARGET_AWARE_EXTENSIONS and extension != ".rpf":
            continue
        try:
            files[relative] = (
                RpfArchive.from_path(path) if extension == ".rpf" else path.read_bytes()
            )
        except (OSError, TypeError, ValueError) as exc:
            issues.append(
                _diagnostic(
                    "folder.asset.unreadable",
                    str(exc),
                    path=relative,
                )
            )
    if files:
        issues.extend(validate_dlc_asset_targets(_DlcFolderAssets(files), game))
    return ValidationReport(issues)


def validate_dlc_folder(
    folder: str | Path,
    *,
    game: str | GameTarget | None = None,
    external_change_sets: Iterable[str] = (),
    require_local_change_sets: bool = False,
    include_dot_dirs: bool = False,
) -> ValidationReport:
    root = Path(folder)
    setup_path = root / "setup2.xml"
    if not setup_path.is_file():
        return ValidationReport(
            [
                _diagnostic(
                    "folder.setup.missing",
                    "DLC folder does not contain setup2.xml",
                    path="setup2.xml",
                )
            ]
        )
    try:
        setup = DlcSetupData.from_xml(setup_path.read_bytes())
    except (OSError, TypeError, ValueError) as exc:
        return ValidationReport(
            [
                _diagnostic(
                    "folder.setup.invalid",
                    str(exc),
                    path="setup2.xml",
                )
            ]
        )

    content_name = setup.dat_file or "content.xml"
    content_path = root / content_name
    if not content_path.is_file():
        return ValidationReport(
            [
                _diagnostic(
                    "folder.content.missing",
                    f"DLC folder does not contain {content_name}",
                    path=content_name,
                )
            ]
        )
    try:
        content = DlcContentXml.from_xml(content_path.read_bytes())
    except (OSError, TypeError, ValueError) as exc:
        return ValidationReport(
            [
                _diagnostic(
                    "folder.content.invalid",
                    str(exc),
                    path=content_name,
                )
            ]
        )

    issues = validate_dlc_setup(
        setup,
        content,
        external_change_sets=external_change_sets,
        require_local_change_sets=require_local_change_sets,
    )
    issues.extend(validate_dlc_content(content))
    if game is not None:
        issues.extend(
            validate_dlc_folder_assets(
                root,
                game,
                include_dot_dirs=include_dot_dirs,
            )
        )
    return issues


def validate_dlc_pack(
    pack: object,
    *,
    context: BuildContext | None = None,
    game: str | GameTarget | None = None,
    external_change_sets: Iterable[str] = (),
    require_local_change_sets: bool = False,
) -> ValidationReport:
    if game is None and context is not None:
        game = context.game
    setup = getattr(pack, "setup", None)
    content = getattr(pack, "content", None)
    if setup is None:
        return ValidationReport(
            [
                _diagnostic(
                    "pack.setup.missing",
                    "DLC pack has no setup metadata",
                )
            ]
        )
    if not isinstance(content, DlcContentXml):
        return ValidationReport(
            [
                _diagnostic(
                    "pack.content.missing",
                    "DLC pack has no content metadata",
                )
            ]
        )
    issues = validate_dlc_setup(
        setup,
        content,
        external_change_sets=external_change_sets,
        require_local_change_sets=require_local_change_sets,
    )
    issues.extend(validate_dlc_content(content))
    target = game if game is not None else getattr(pack, "game", None)
    if target is not None:
        issues.extend(validate_dlc_asset_targets(pack, target))
    from .audio import validate_dlc_sounddata

    issues.extend(validate_dlc_sounddata(pack))
    cutscenes = getattr(pack, "cutscenes", ())
    if cutscenes:
        from .cutscene import validate_dlc_cutscenes

        issues.extend(validate_dlc_cutscenes(pack))
    return issues


__all__ = [
    "validate_dlc_asset_targets",
    "validate_dlc_content",
    "validate_dlc_folder",
    "validate_dlc_folder_assets",
    "validate_dlc_pack",
    "validate_dlc_setup",
]
