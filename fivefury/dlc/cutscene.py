from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from ..authoring import ValidationReport
from ..cut.scene import CutsceneAssets
from ..rpf import RpfArchive, RpfFileEntry
from .content import DlcContentFile, DlcContentXml
from .enums import DlcDataFileType

if TYPE_CHECKING:
    from .model import DlcPack


@dataclass(slots=True)
class DlcCutsceneRegistration:
    assets: CutsceneAssets
    archive_path: str
    cutscene_names: tuple[str, ...]
    sounddata_paths: tuple[str, ...]
    awc_paths: tuple[str, ...]
    sounddata_registrations: tuple[str, ...]
    wavepack_registrations: tuple[str, ...]
    change_set_name: str


def _file_type(value: DlcContentFile) -> str:
    return str(getattr(value.file_type, "value", value.file_type))


def _content_file(
    content: DlcContentXml,
    filename: str,
) -> DlcContentFile | None:
    key = filename.casefold()
    return next(
        (item for item in content.data_files if item.filename.casefold() == key),
        None,
    )


def _change_set_name(pack: DlcPack, cut_name: str) -> str:
    stem = PurePosixPath(cut_name).stem
    value = f"{pack.name}_{stem}_CUTSCENE"
    return "".join(character if character.isalnum() else "_" for character in value).upper()


def _preflight_registration(
    pack: DlcPack,
    *,
    archive_path: str,
    sounddata_paths: tuple[str, ...],
    awc_paths: tuple[str, ...],
    sounddata_registrations: tuple[str, ...],
    wavepack_registrations: tuple[str, ...],
) -> ValidationReport:
    report = ValidationReport()
    existing_paths = {path.casefold() for path in pack.files}
    for path in (archive_path, *sounddata_paths, *awc_paths):
        if path.casefold() in existing_paths:
            report.issue(
                "cut.audio.name.duplicate",
                f"DLC payload path is already in use: {path}",
                path=path,
            )
    for path in sounddata_registrations:
        existing = _content_file(pack.content, path)
        if existing is not None:
            report.issue(
                "cut.audio.sounddata.unregistered",
                f"DLC content path is already registered: {path}",
                path=path,
            )
    for path in wavepack_registrations:
        existing = _content_file(pack.content, path)
        if existing is not None and _file_type(existing) != DlcDataFileType.AUDIO_WAVEPACK.value:
            report.issue(
                "cut.audio.wavepack.unregistered",
                f"DLC content path is not registered as AUDIO_WAVEPACK: {path}",
                path=path,
            )
    return report


def register_dlc_cutscene(
    pack: DlcPack,
    assets: CutsceneAssets,
) -> DlcCutsceneRegistration:
    if not isinstance(assets, CutsceneAssets):
        raise TypeError(f"expected CutsceneAssets, got {type(assets).__name__}")
    assets.validate().raise_for_errors()
    files = assets.build_files()
    audio_names = {
        name.casefold()
        for audio in assets.audio
        for name in (audio.sounds_name, audio.awc_name)
    }
    cutscene_files = {
        name: data for name, data in files.items() if name.casefold() not in audio_names
    }
    invalid_cutscene_names = [
        name for name in cutscene_files if PurePosixPath(name).suffix.casefold() not in {".cut", ".ycd"}
    ]
    if invalid_cutscene_names:
        raise ValueError(
            "CUT DLC archives only accept CUT and YCD payloads: "
            + ", ".join(invalid_cutscene_names)
        )

    cut_stem = PurePosixPath(assets.output_name).stem.casefold()
    archive_path = f"x64/cutscenes/{cut_stem}.rpf"
    sounddata_paths = tuple(
        f"x64/audio/config/{audio.sounds_name}" for audio in assets.audio
    )
    awc_paths = tuple(
        f"x64/audio/sfx/{audio.wavepack_name}/{audio.awc_name}"
        for audio in assets.audio
    )
    sounddata_registrations = tuple(pack.path(path) for path in sounddata_paths)
    wavepack_registrations = tuple(
        dict.fromkeys(
            pack.path(f"x64/audio/sfx/{audio.wavepack_name}")
            for audio in assets.audio
        )
    )
    _preflight_registration(
        pack,
        archive_path=archive_path,
        sounddata_paths=sounddata_paths,
        awc_paths=awc_paths,
        sounddata_registrations=sounddata_registrations,
        wavepack_registrations=wavepack_registrations,
    ).raise_for_errors()

    archive = RpfArchive.empty(PurePosixPath(archive_path).name)
    for name, data in cutscene_files.items():
        archive.file(name, data)
    archive_registration = pack.rpf(archive_path, archive)
    for audio, path, registration_path in zip(
        assets.audio,
        sounddata_paths,
        sounddata_registrations,
        strict=True,
    ):
        pack.file(path, files[audio.sounds_name])
        pack.content.file(registration_path, DlcDataFileType.AUDIO_SOUNDDATA)
    for audio, path in zip(assets.audio, awc_paths, strict=True):
        pack.file(path, files[audio.awc_name])
    for registration_path in wavepack_registrations:
        if _content_file(pack.content, registration_path) is None:
            pack.content.file(registration_path, DlcDataFileType.AUDIO_WAVEPACK)

    change_set_name = _change_set_name(pack, assets.output_name)
    change_set = pack.change_set(change_set_name, enable_all=False)
    change_set.enable(
        archive_registration.filename,
        *sounddata_registrations,
        *wavepack_registrations,
    )
    registration = DlcCutsceneRegistration(
        assets=assets,
        archive_path=archive_path,
        cutscene_names=tuple(cutscene_files),
        sounddata_paths=sounddata_paths,
        awc_paths=awc_paths,
        sounddata_registrations=sounddata_registrations,
        wavepack_registrations=wavepack_registrations,
        change_set_name=change_set_name,
    )
    pack.cutscenes.append(registration)
    return registration


def validate_dlc_cutscenes(pack: DlcPack) -> ValidationReport:
    report = ValidationReport()
    content_files = {item.filename.casefold(): item for item in pack.content.data_files}
    change_sets = {
        item.name: {path.casefold() for path in item.files_to_enable}
        for item in pack.content.content_change_sets
    }
    payload_paths = {path.casefold() for path in pack.files}
    for index, registration in enumerate(pack.cutscenes):
        path = f"cutscenes[{index}]"
        report.extend(registration.assets.validate(), path=path)
        enabled = change_sets.get(registration.change_set_name, set())
        archive_registration = pack.path(registration.archive_path)
        archive_content = content_files.get(archive_registration.casefold())
        if (
            registration.archive_path.casefold() not in payload_paths
            or archive_content is None
            or _file_type(archive_content) != DlcDataFileType.RPF.value
            or archive_registration.casefold() not in enabled
        ):
            report.issue(
                "cut.package.unregistered",
                f"CUT archive is not mounted as an RPF: {archive_registration}",
                path=path,
            )
        for physical, virtual in zip(
            registration.sounddata_paths,
            registration.sounddata_registrations,
            strict=True,
        ):
            content_file = content_files.get(virtual.casefold())
            if (
                physical.casefold() not in payload_paths
                or content_file is None
                or _file_type(content_file) != DlcDataFileType.AUDIO_SOUNDDATA.value
                or virtual.casefold() not in enabled
            ):
                report.issue(
                    "cut.audio.sounddata.unregistered",
                    f"CUT sound metadata is not mounted as AUDIO_SOUNDDATA: {virtual}",
                    path=path,
                )
        for physical in registration.awc_paths:
            if physical.casefold() not in payload_paths:
                report.issue(
                    "cut.audio.container.unresolved",
                    f"CUT AWC payload is missing from the DLC: {physical}",
                    path=path,
                )
        for virtual in registration.wavepack_registrations:
            content_file = content_files.get(virtual.casefold())
            if (
                content_file is None
                or _file_type(content_file) != DlcDataFileType.AUDIO_WAVEPACK.value
                or virtual.casefold() not in enabled
            ):
                report.issue(
                    "cut.audio.wavepack.unregistered",
                    f"CUT wavepack folder is not mounted as AUDIO_WAVEPACK: {virtual}",
                    path=path,
                )
        if any(
            item.filename.casefold().endswith(".awc")
            and _file_type(item) == DlcDataFileType.RPF.value
            for item in pack.content.data_files
        ):
            report.issue(
                "cut.audio.wavepack.unregistered",
                "CUT AWC files must not be mounted as generic RPF_FILE entries",
                path=path,
            )
    return report


def _entry_bytes(archive: RpfArchive, path: str) -> bytes | None:
    entry = archive.find_entry(path)
    if not isinstance(entry, RpfFileEntry):
        return None
    return entry.read_standalone()


def validate_dlc_cutscene_archive(
    pack: DlcPack,
    archive: RpfArchive,
) -> ValidationReport:
    from ..authoring import BuildContext
    from ..awc import read_awc
    from ..cut.audio_authoring import CutsceneAudioAssets
    from ..rel import read_rel

    report = ValidationReport()
    assert pack.setup is not None
    content_name = pack.setup.dat_file or "content.xml"
    content_data = _entry_bytes(archive, content_name)
    if content_data is None:
        report.issue(
            "cut.audio.package.invalid",
            f"Generated DLC is missing {content_name}",
            path=content_name,
        )
        return report
    try:
        content = DlcContentXml.from_xml(content_data)
    except (TypeError, ValueError) as exc:
        report.issue(
            "cut.audio.package.invalid",
            str(exc),
            path=content_name,
        )
        return report
    content_files = {item.filename.casefold(): item for item in content.data_files}
    change_sets = {
        item.name: {path.casefold() for path in item.files_to_enable}
        for item in content.content_change_sets
    }
    for index, registration in enumerate(pack.cutscenes):
        path = f"cutscenes[{index}]"
        source_archive = pack.files.get(registration.archive_path)
        if not isinstance(source_archive, RpfArchive):
            report.issue(
                "cut.audio.package.invalid",
                f"CUT archive payload is unavailable: {registration.archive_path}",
                path=path,
            )
            continue
        expected_payloads: list[tuple[str, bytes]] = []
        for name in registration.cutscene_names:
            source_entry = source_archive.find_entry(name)
            if isinstance(source_entry, RpfFileEntry):
                expected_payloads.append(
                    (
                        f"{registration.archive_path}/{name}",
                        source_entry.read_standalone(),
                    )
                )
        for payload_path in (
            *registration.sounddata_paths,
            *registration.awc_paths,
        ):
            value = pack.files.get(payload_path)
            if isinstance(value, (bytes, bytearray, memoryview)):
                expected_payloads.append((payload_path, bytes(value)))
        for payload_path, data in expected_payloads:
            if _entry_bytes(archive, payload_path) != data:
                report.issue(
                    "cut.audio.package.invalid",
                    f"Generated DLC payload did not survive its RPF round-trip: {payload_path}",
                    path=path,
                )
        for audio, sounds_path, awc_path in zip(
            registration.assets.audio,
            registration.sounddata_paths,
            registration.awc_paths,
            strict=True,
        ):
            sounds_data = _entry_bytes(archive, sounds_path)
            awc_data = _entry_bytes(archive, awc_path)
            if sounds_data is None or awc_data is None:
                continue
            try:
                rebuilt_audio = CutsceneAudioAssets(
                    reference=audio.reference,
                    awc=read_awc(awc_data, path=audio.awc_name),
                    sounds=read_rel(sounds_data, path=audio.sounds_name),
                    awc_name=audio.awc_name,
                    sounds_name=audio.sounds_name,
                    wavepack_name=audio.wavepack_name,
                    game=audio.game,
                    channels=audio.channels,
                )
            except (TypeError, ValueError) as exc:
                report.issue(
                    "cut.audio.package.invalid",
                    f"Generated DLC audio cannot be read: {exc}",
                    path=path,
                )
            else:
                report.extend(
                    rebuilt_audio.validate(context=BuildContext(game=audio.game)),
                    path=path,
                )
        enabled = change_sets.get(registration.change_set_name, set())
        for virtual, expected_type in (
            ((pack.path(registration.archive_path), DlcDataFileType.RPF),)
            + tuple(
                (name, DlcDataFileType.AUDIO_SOUNDDATA)
                for name in registration.sounddata_registrations
            )
            + tuple(
                (name, DlcDataFileType.AUDIO_WAVEPACK)
                for name in registration.wavepack_registrations
            )
        ):
            item = content_files.get(virtual.casefold())
            if (
                item is None
                or _file_type(item) != expected_type.value
                or virtual.casefold() not in enabled
            ):
                report.issue(
                    "cut.audio.package.invalid",
                    f"Generated DLC lost its {expected_type.value} registration: {virtual}",
                    path=path,
                )
    return report


__all__ = ["DlcCutsceneRegistration"]
