from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ..authoring import BuildContext, ValidationReport
from ..rel import RelExternalNameTable, RelMetadataChunk
from ..rpf import RpfArchive, RpfFileEntry
from .content import DlcContentFile, DlcContentXml
from .enums import DlcDataFileType
from .paths import dlc_platform_payload_path, dlc_platform_registration_path

if TYPE_CHECKING:
    from .model import DlcPack


@dataclass(frozen=True, slots=True)
class DlcSounddataRegistration:
    metadata: RelMetadataChunk
    logical_registration: str
    runtime_path: str
    release_path: str
    name_table_path: str

    @property
    def payload_paths(self) -> tuple[str, str, str]:
        return self.runtime_path, self.release_path, self.name_table_path


def _file_type(value: DlcContentFile) -> str:
    return str(getattr(value.file_type, "value", value.file_type))


def _content_file(content: DlcContentXml, filename: str) -> DlcContentFile | None:
    key = filename.casefold()
    return next(
        (item for item in content.data_files if item.filename.casefold() == key),
        None,
    )


def _registration(
    pack: DlcPack, metadata: RelMetadataChunk
) -> DlcSounddataRegistration:
    logical = dlc_platform_registration_path(
        PurePosixPath("audio") / metadata.logical_name
    )
    physical_root = dlc_platform_payload_path("audio")
    return DlcSounddataRegistration(
        metadata=metadata,
        logical_registration=pack.path(logical.as_posix()),
        runtime_path=(physical_root / metadata.runtime_name).as_posix(),
        release_path=(physical_root / metadata.release_name).as_posix(),
        name_table_path=(physical_root / metadata.name_table_name).as_posix(),
    )


def mount_dlc_sounddata(
    pack: DlcPack,
    metadata: RelMetadataChunk,
) -> DlcSounddataRegistration:
    if not isinstance(metadata, RelMetadataChunk):
        raise TypeError(f"expected RelMetadataChunk, got {type(metadata).__name__}")
    target = pack.game or metadata.game
    metadata.validate(context=BuildContext(game=target)).raise_for_errors()
    registration = _registration(pack, metadata)
    existing_paths = {path.casefold() for path in pack.files}
    duplicates = [
        path for path in registration.payload_paths if path.casefold() in existing_paths
    ]
    if duplicates:
        raise ValueError(
            "DLC sounddata payload path is already in use: " + duplicates[0]
        )
    if _content_file(pack.content, registration.logical_registration) is not None:
        raise ValueError(
            "DLC sounddata registration is already in use: "
            + registration.logical_registration
        )

    payloads = (
        metadata.runtime_payload,
        metadata.release_payload,
        metadata.name_table.to_bytes(),
    )
    for path, payload in zip(registration.payload_paths, payloads, strict=True):
        pack.file(path, payload)
    pack.content.file(
        registration.logical_registration,
        DlcDataFileType.AUDIO_SOUNDDATA,
    )
    pack.sounddata.append(registration)
    return registration


def validate_dlc_sounddata(pack: DlcPack) -> ValidationReport:
    report = ValidationReport()
    content_files = {item.filename.casefold(): item for item in pack.content.data_files}
    payload_paths = {path.casefold() for path in pack.files}
    sounddata = tuple(getattr(pack, "sounddata", ()))
    registrations = {item.logical_registration.casefold(): item for item in sounddata}
    for content_file in pack.content.data_files:
        if _file_type(content_file) != DlcDataFileType.AUDIO_SOUNDDATA.value:
            continue
        registration = registrations.get(content_file.filename.casefold())
        if registration is None:
            report.issue(
                "dlc.sounddata.unresolved",
                "AUDIO_SOUNDDATA registration has no compiled REL metadata family",
                path=content_file.filename,
            )
            continue
        expected = _registration(pack, registration.metadata)
        if registration != expected:
            report.issue(
                "dlc.sounddata.layout.invalid",
                "Compiled REL metadata paths do not match the logical registration",
                path=content_file.filename,
            )
        for path in expected.payload_paths:
            if path.casefold() not in payload_paths:
                report.issue(
                    "dlc.sounddata.payload.missing",
                    f"Compiled REL metadata payload is missing: {path}",
                    path=content_file.filename,
                )
        report.extend(
            registration.metadata.validate(
                context=BuildContext(game=pack.game or registration.metadata.game)
            ),
            path=content_file.filename,
        )
    for registration in sounddata:
        content_file = content_files.get(registration.logical_registration.casefold())
        if (
            content_file is None
            or _file_type(content_file) != DlcDataFileType.AUDIO_SOUNDDATA.value
        ):
            report.issue(
                "dlc.sounddata.registration.missing",
                "Compiled REL metadata is not registered as AUDIO_SOUNDDATA",
                path=registration.logical_registration,
            )
    for path in pack.files:
        normalized = path.casefold()
        if normalized.startswith("x64/audio/config/") and normalized.endswith(".dat"):
            report.issue(
                "dlc.sounddata.layout.legacy_raw",
                "Raw audio/config DAT files are not retail AUDIO_SOUNDDATA payloads",
                path=path,
            )
    return report


def _entry_bytes(archive: RpfArchive, path: str) -> bytes | None:
    entry = archive.find_entry(path)
    if not isinstance(entry, RpfFileEntry):
        return None
    return entry.read_standalone()


def validate_dlc_sounddata_archive(
    pack: DlcPack,
    archive: RpfArchive,
    content: DlcContentXml | None = None,
) -> ValidationReport:
    report = ValidationReport()
    if content is None:
        assert pack.setup is not None
        content_name = pack.setup.dat_file or "content.xml"
        content_data = _entry_bytes(archive, content_name)
        if content_data is None:
            report.issue(
                "dlc.sounddata.package.invalid",
                f"Generated DLC is missing {content_name}",
                path=content_name,
            )
            return report
        try:
            content = DlcContentXml.from_xml(content_data)
        except (TypeError, ValueError) as exc:
            report.issue(
                "dlc.sounddata.package.invalid",
                str(exc),
                path=content_name,
            )
            return report
    registrations = {
        item.logical_registration.casefold(): item for item in pack.sounddata
    }
    for content_file in content.data_files:
        if _file_type(content_file) != DlcDataFileType.AUDIO_SOUNDDATA.value:
            continue
        registration = registrations.get(content_file.filename.casefold())
        if registration is None:
            report.issue(
                "dlc.sounddata.unresolved",
                "AUDIO_SOUNDDATA registration cannot be resolved to a typed metadata family",
                path=content_file.filename,
            )
            continue
        expected = _registration(pack, registration.metadata)
        if content_file.filename.casefold() != expected.logical_registration.casefold():
            report.issue(
                "dlc.sounddata.layout.invalid",
                "AUDIO_SOUNDDATA must be registered under %PLATFORM%/audio",
                path=content_file.filename,
            )
            continue
        runtime = _entry_bytes(archive, expected.runtime_path)
        release = _entry_bytes(archive, expected.release_path)
        names = _entry_bytes(archive, expected.name_table_path)
        missing = [
            path
            for path, payload in zip(
                expected.payload_paths,
                (runtime, release, names),
                strict=True,
            )
            if payload is None
        ]
        for path in missing:
            report.issue(
                "dlc.sounddata.payload.missing",
                f"Generated DLC is missing compiled REL metadata payload: {path}",
                path=content_file.filename,
            )
        if missing:
            continue
        assert runtime is not None and release is not None and names is not None
        try:
            rebuilt = RelMetadataChunk(
                logical_name=registration.metadata.logical_name,
                schema=registration.metadata.schema,
                runtime_payload=runtime,
                release_payload=release,
                name_table=RelExternalNameTable.from_bytes(names),
                game=registration.metadata.game,
            )
        except (TypeError, ValueError) as exc:
            report.issue(
                "dlc.sounddata.payload.invalid",
                f"Compiled REL metadata family cannot be read: {exc}",
                path=content_file.filename,
            )
        else:
            report.extend(
                rebuilt.validate(context=BuildContext(game=pack.game or rebuilt.game)),
                path=content_file.filename,
            )
    for entry in archive.iter_entries():
        path = entry.full_path.casefold()
        if path.startswith("x64/audio/config/") and path.endswith(".dat"):
            report.issue(
                "dlc.sounddata.layout.legacy_raw",
                "Generated DLC contains a raw audio/config DAT payload",
                path=entry.full_path,
            )
    return report


__all__ = [
    "DlcSounddataRegistration",
    "mount_dlc_sounddata",
    "validate_dlc_sounddata",
    "validate_dlc_sounddata_archive",
]
