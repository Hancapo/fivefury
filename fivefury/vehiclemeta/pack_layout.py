from __future__ import annotations

from pathlib import PurePosixPath
from time import strptime

from ..authoring import ValidationReport
from ..dlc.content import DlcContentFile
from ..dlc.enums import DlcContentGroup, DlcDataFileType
from ..dlc.model import DlcPack
from ..dlc.paths import dlc_platform_path
from ..dlc.setup import DlcSetupData

VEHICLES_META_PATH = PurePosixPath("common/data/levels/gta5/vehicles.meta")
HANDLING_META_PATH = PurePosixPath("common/data/handling.meta")
VARIATIONS_META_PATH = PurePosixPath("common/data/carvariations.meta")
CARCOLS_META_PATH = PurePosixPath("common/data/carcols.meta")
VEHICLE_STREAM_RELATIVE_PATH = PurePosixPath("levels/gta5/vehicles/vehicles.rpf")
VEHICLE_STREAM_PATH = dlc_platform_path(VEHICLE_STREAM_RELATIVE_PATH)

_METADATA_TYPES = {
    VEHICLES_META_PATH: DlcDataFileType.VEHICLE_METADATA,
    HANDLING_META_PATH: DlcDataFileType.HANDLING,
    VARIATIONS_META_PATH: DlcDataFileType.VEHICLE_VARIATION,
    CARCOLS_META_PATH: DlcDataFileType.CARCOLS,
}


def _registration_map(pack: DlcPack) -> dict[str, DlcContentFile]:
    return {item.filename.casefold(): item for item in pack.content.data_files}


def validate_enhanced_vehicle_setup(
    setup: DlcSetupData,
    pack_name: str,
) -> ValidationReport:
    report = ValidationReport()
    if not setup.time_stamp.strip():
        report.issue(
            "vehicle.pack.layout.timestamp.required",
            "Enhanced vehicle packs require an explicit setup timestamp",
            path="setup.time_stamp",
        )
    else:
        try:
            strptime(setup.time_stamp, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            report.issue(
                "vehicle.pack.layout.timestamp.invalid",
                "Enhanced vehicle pack timestamps must use DD/MM/YYYY HH:MM:SS",
                path="setup.time_stamp",
            )
    if setup.order <= 0:
        report.issue(
            "vehicle.pack.layout.order.invalid",
            "Enhanced vehicle pack load order must be greater than zero",
            path="setup.order",
        )
    if setup.dat_file.casefold() != "content.xml":
        report.issue(
            "vehicle.pack.layout.content_file.invalid",
            "Enhanced vehicle packs must use content.xml as their data file",
            path="setup.dat_file",
        )

    expected_device = f"dlc_{pack_name}:/"
    if setup.device_path.casefold() != expected_device.casefold():
        report.issue(
            "vehicle.pack.layout.device.invalid",
            f"Vehicle pack device must be {expected_device!r}",
            path="setup.device_name",
        )
    return report


def validate_enhanced_vehicle_pack_layout(pack: DlcPack) -> ValidationReport:
    report = ValidationReport()
    setup = pack.setup
    if setup is None:
        report.issue(
            "vehicle.pack.layout.setup.missing",
            "Enhanced vehicle packs require setup metadata",
            path="setup",
        )
        return report
    report.extend(validate_enhanced_vehicle_setup(setup, pack.name), path="setup")

    registrations = _registration_map(pack)
    expected: dict[str, DlcDataFileType] = {
        pack.path(str(path)).casefold(): file_type
        for path, file_type in _METADATA_TYPES.items()
    }
    stream_filename = pack.path(str(VEHICLE_STREAM_PATH))
    expected[stream_filename.casefold()] = DlcDataFileType.RPF
    if set(registrations) != set(expected):
        report.issue(
            "vehicle.pack.layout.registrations.invalid",
            "Vehicle pack registrations do not match the Enhanced vehicle layout",
            path="content.data_files",
        )
    for filename, file_type in expected.items():
        registration = registrations.get(filename)
        if registration is None:
            continue
        if str(registration.file_type) != str(file_type):
            report.issue(
                "vehicle.pack.layout.registration.type.invalid",
                f"Registration must use {file_type}",
                path=registration.filename,
            )

    stream = registrations.get(stream_filename.casefold())
    if stream is None:
        stream = next(
            (
                registration
                for registration in registrations.values()
                if str(registration.file_type) == str(DlcDataFileType.RPF)
                and PurePosixPath(registration.filename).name.casefold()
                == "vehicles.rpf"
            ),
            None,
        )
    if stream is not None:
        if stream.disabled is not True:
            report.issue(
                "vehicle.pack.layout.stream.disabled.invalid",
                "The streamed vehicle archive must start disabled",
                path=f"{stream.filename}.disabled",
            )
        if stream.persistent is not True:
            report.issue(
                "vehicle.pack.layout.stream.persistent.invalid",
                "The streamed vehicle archive must be persistent",
                path=f"{stream.filename}.persistent",
            )
        if stream.contents is not None:
            report.issue(
                "vehicle.pack.layout.stream.contents.invalid",
                "The streamed vehicle archive must not declare a contents classification",
                path=f"{stream.filename}.contents",
            )
        if (
            stream.filename.casefold() != stream_filename.casefold()
            or pack.resolve_content_path(stream) != str(VEHICLE_STREAM_PATH)
        ):
            report.issue(
                "vehicle.pack.layout.stream.mount.invalid",
                "The streamed vehicle registration does not resolve to its platform archive",
                path=stream.filename,
            )

    startup_names = {
        change_set.casefold()
        for group in setup.content_change_set_groups
        if str(group.name).casefold() == str(DlcContentGroup.STARTUP).casefold()
        for change_set in group.change_sets
    }
    startup = [
        change_set
        for change_set in pack.content.content_change_sets
        if change_set.name.casefold() in startup_names
    ]
    if not startup:
        report.issue(
            "vehicle.pack.layout.startup.missing",
            "GROUP_STARTUP must reference a local vehicle change set",
            path="setup.content_change_set_groups",
        )
    else:
        registered_files = set(registrations)
        if not any(
            change_set.requires_loading_screen is False
            and {name.casefold() for name in change_set.files_to_enable}
            == registered_files
            for change_set in startup
        ):
            report.issue(
                "vehicle.pack.layout.startup.invalid",
                "The startup change set must enable every registration without a loading screen",
                path="content.content_change_sets",
            )

    files = {str(path).casefold() for path in pack.files}
    if files and str(VEHICLE_STREAM_PATH).casefold() not in files:
        report.issue(
            "vehicle.pack.layout.stream.file_missing",
            "The platform vehicle archive is not present in the DLC payload",
            path=str(VEHICLE_STREAM_PATH),
        )
    return report


__all__ = [
    "CARCOLS_META_PATH",
    "HANDLING_META_PATH",
    "VARIATIONS_META_PATH",
    "VEHICLES_META_PATH",
    "VEHICLE_STREAM_PATH",
    "VEHICLE_STREAM_RELATIVE_PATH",
    "validate_enhanced_vehicle_pack_layout",
    "validate_enhanced_vehicle_setup",
]
