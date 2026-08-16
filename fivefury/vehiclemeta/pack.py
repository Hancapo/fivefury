from __future__ import annotations

import copy
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..authoring import AssetSet, BuildContext, ValidationReport
from ..common import atomic_write_bytes
from ..dlc import (
    DlcDataFileType,
    DlcPack,
    DlcSetupData,
    read_dlc_pack,
)
from ..game_target import GameTarget, coerce_game_target
from ..rpf import RpfArchive, RpfFileEntry
from ..yft import Yft, build_yft_bytes
from ..ytd import Ytd, read_ytd
from .carcols import VehicleCarCols
from .enums import VehicleType
from .fragment_pair import validate_vehicle_yft_pair
from .handling import HandlingDataManager
from .pack_layout import (
    CARCOLS_META_PATH,
    HANDLING_META_PATH,
    VARIATIONS_META_PATH,
    VEHICLE_STREAM_PAYLOAD_PATH,
    VEHICLE_STREAM_RELATIVE_PATH,
    VEHICLES_META_PATH,
    validate_enhanced_vehicle_pack_layout,
    validate_enhanced_vehicle_setup,
)
from .resource import read_vehicle_meta
from .variations import VehicleModelInfoVariation
from .vehicles import VehicleInitDataList
from .xml_validation import validate_vehicle_meta_xml


@dataclass(slots=True)
class VehicleStreamAsset:
    name: str
    fragment: Yft | bytes
    high_fragment: Yft | bytes | None = None
    textures: Ytd | bytes | None = None
    texture_name: str | None = None

    def __post_init__(self) -> None:
        self.name = PurePosixPath(self.name).stem
        if self.texture_name is not None:
            self.texture_name = PurePosixPath(self.texture_name).stem

    @property
    def txd_name(self) -> str:
        return self.texture_name or self.name


@dataclass(frozen=True, slots=True)
class VehiclePackPaths:
    dlc_rpf: Path
    vehicles_meta: PurePosixPath
    handling_meta: PurePosixPath
    variations_meta: PurePosixPath
    carcols_meta: PurePosixPath
    streamed_rpf: PurePosixPath


@dataclass(frozen=True, slots=True)
class VehiclePackOutput:
    paths: VehiclePackPaths
    report: ValidationReport


@dataclass(slots=True)
class VehiclePackBuilder:
    name: str
    vehicles_meta: VehicleInitDataList
    handling_meta: HandlingDataManager
    variations_meta: VehicleModelInfoVariation
    carcols_meta: VehicleCarCols
    setup: DlcSetupData
    vehicles: list[VehicleStreamAsset] = field(default_factory=list)
    unregistered_files: dict[str, bytes] = field(default_factory=dict)
    game: GameTarget | str = GameTarget.GTA5_ENHANCED

    VEHICLES_META = VEHICLES_META_PATH
    HANDLING_META = HANDLING_META_PATH
    VARIATIONS_META = VARIATIONS_META_PATH
    CARCOLS_META = CARCOLS_META_PATH
    STREAMED_RPF = VEHICLE_STREAM_PAYLOAD_PATH

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.game = coerce_game_target(self.game)

    def vehicle(
        self,
        name: str,
        fragment: Yft | bytes,
        *,
        high_fragment: Yft | bytes | None = None,
        textures: Ytd | bytes | None = None,
        texture_name: str | None = None,
    ) -> VehicleStreamAsset:
        asset = VehicleStreamAsset(
            name=name,
            fragment=fragment,
            high_fragment=high_fragment,
            textures=textures,
            texture_name=texture_name,
        )
        self.vehicles.append(asset)
        return asset

    def _context(self, context: BuildContext | None) -> BuildContext:
        assets = AssetSet()
        if context is not None:
            for path, asset in context.assets.items():
                assets[path] = asset
        assets.replace(self.VEHICLES_META, self.vehicles_meta)
        assets.replace(self.HANDLING_META, self.handling_meta)
        assets.replace(self.VARIATIONS_META, self.variations_meta)
        assets.replace(self.CARCOLS_META, self.carcols_meta)
        return BuildContext(
            game=self.game,
            assets=assets,
            cache=context.cache if context is not None else None,
            strict=context.strict if context is not None else True,
        )

    @staticmethod
    def _textures(asset: VehicleStreamAsset) -> Ytd | None:
        if asset.textures is None:
            return None
        return (
            asset.textures
            if isinstance(asset.textures, Ytd)
            else read_ytd(asset.textures)
        )

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        report = ValidationReport()
        if not self.name:
            report.issue(
                "vehicle.pack.name.required",
                "Vehicle pack name cannot be empty",
                path="name",
            )
        if self.game is not GameTarget.GTA5_ENHANCED:
            report.issue(
                "vehicle.pack.game.invalid",
                "Vehicle pack authoring requires the GTA V Enhanced target",
                path="game",
            )
        if context is not None and context.game is not self.game:
            report.issue(
                "vehicle.pack.context.game_mismatch",
                "Build context and vehicle pack targets must match",
                path="game",
            )
        if self.setup.name_hash.casefold() != self.name.casefold():
            report.issue(
                "vehicle.pack.setup.name_mismatch",
                "Vehicle pack setup name must match the builder name",
                path="setup.name_hash",
            )
        report.extend(
            validate_enhanced_vehicle_setup(self.setup, self.name),
            path="setup",
        )

        build_context = self._context(context)
        documents = (
            ("vehicles_meta", self.vehicles_meta),
            ("handling_meta", self.handling_meta),
            ("variations_meta", self.variations_meta),
            ("carcols_meta", self.carcols_meta),
        )
        for path, document in documents:
            report.extend(document.validate(context=build_context), path=path)
            report.extend(
                validate_vehicle_meta_xml(
                    document.to_xml_element(),
                    expected_root=document.ROOT_TAG,
                ),
                path=path,
            )

        metadata_names = {
            vehicle.model_name.casefold()
            for vehicle in self.vehicles_meta.vehicles
            if vehicle.model_name
        }
        stream_names: dict[str, int] = {}
        texture_names: dict[str, int] = {}
        metadata_by_name = {
            vehicle.model_name.casefold(): vehicle
            for vehicle in self.vehicles_meta.vehicles
            if vehicle.model_name
        }
        for index, asset in enumerate(self.vehicles):
            path = f"vehicles[{index}]"
            key = asset.name.casefold()
            if not key:
                report.issue(
                    "vehicle.pack.asset.name.required",
                    "Streamed vehicle name cannot be empty",
                    path=f"{path}.name",
                )
            elif key in stream_names:
                report.issue(
                    "vehicle.pack.asset.name.duplicate",
                    f"Duplicate streamed vehicle {asset.name!r}",
                    path=f"{path}.name",
                )
            else:
                stream_names[key] = index
            if key and key not in metadata_names:
                report.issue(
                    "vehicle.pack.asset.metadata_missing",
                    f"Streamed vehicle {asset.name!r} has no vehicles.meta entry",
                    path=f"{path}.name",
                )
            metadata = metadata_by_name.get(key)
            report.extend(
                validate_vehicle_yft_pair(
                    asset.name,
                    asset.fragment,
                    asset.high_fragment,
                    vehicle_type=(
                        metadata.vehicle_type
                        if metadata is not None
                        else VehicleType.CAR
                    ),
                ),
                path=path,
            )

            try:
                textures = self._textures(asset)
            except (
                IndexError,
                KeyError,
                TypeError,
                ValueError,
                struct.error,
                zlib.error,
            ) as exc:
                report.issue(
                    "vehicle.pack.ytd.invalid", str(exc), path=f"{path}.textures"
                )
            else:
                if textures is not None:
                    txd_key = asset.txd_name.casefold()
                    if txd_key in texture_names:
                        report.issue(
                            "vehicle.pack.ytd.name.duplicate",
                            f"Duplicate streamed texture dictionary {asset.txd_name!r}",
                            path=f"{path}.texture_name",
                        )
                    else:
                        texture_names[txd_key] = index
                    report.extend(
                        textures.validate(context=build_context),
                        path=f"{path}.textures",
                    )

        for index, vehicle in enumerate(self.vehicles_meta.vehicles):
            key = vehicle.model_name.casefold()
            if key and key not in stream_names:
                report.issue(
                    "vehicle.pack.metadata.fragment_missing",
                    f"vehicles.meta entry {vehicle.model_name!r} has no streamed YFT",
                    path=f"vehicles_meta.vehicles[{index}].model_name",
                )
            asset_index = stream_names.get(key)
            if asset_index is not None:
                asset = self.vehicles[asset_index]
                if (
                    asset.textures is not None
                    and vehicle.txd_name.casefold() != asset.txd_name.casefold()
                ):
                    report.issue(
                        "vehicle.pack.metadata.txd_mismatch",
                        f"vehicles.meta references {vehicle.txd_name!r}, but the streamed YTD is {asset.txd_name!r}",
                        path=f"vehicles_meta.vehicles[{index}].txd_name",
                    )

        for path in self.unregistered_files:
            normalized = str(PurePosixPath(path))
            if normalized.startswith(("../", "/")):
                report.issue(
                    "vehicle.pack.file.path.invalid",
                    f"Pack file path must be relative: {path!r}",
                    path=f"unregistered_files[{path!r}]",
                )
        return report

    def build(self, *, context: BuildContext | None = None) -> DlcPack:
        self.validate(context=context).raise_for_errors()
        pack = self._build(context)
        validate_enhanced_vehicle_pack_layout(pack).raise_for_errors()
        return pack

    def _build(self, context: BuildContext | None) -> DlcPack:
        build_context = self._context(context)
        streamed = RpfArchive.empty(self.STREAMED_RPF.name)
        for asset in self.vehicles:
            fragment = (
                build_yft_bytes(asset.fragment)
                if isinstance(asset.fragment, Yft)
                else bytes(asset.fragment)
            )
            streamed.file(f"{asset.name}.yft", fragment)
            if asset.high_fragment is not None:
                high_fragment = (
                    build_yft_bytes(asset.high_fragment)
                    if isinstance(asset.high_fragment, Yft)
                    else bytes(asset.high_fragment)
                )
                streamed.file(f"{asset.name}_hi.yft", high_fragment)
            if asset.textures is not None:
                textures = (
                    asset.textures.to_bytes(game=self.game)
                    if isinstance(asset.textures, Ytd)
                    else bytes(asset.textures)
                )
                streamed.file(f"{asset.txd_name}.ytd", textures)

        pack = DlcPack(
            self.name,
            setup=copy.deepcopy(self.setup),
            game=self.game,
        )
        metadata = (
            (self.VEHICLES_META, self.vehicles_meta, DlcDataFileType.VEHICLE_METADATA),
            (self.HANDLING_META, self.handling_meta, DlcDataFileType.HANDLING),
            (
                self.VARIATIONS_META,
                self.variations_meta,
                DlcDataFileType.VEHICLE_VARIATION,
            ),
            (self.CARCOLS_META, self.carcols_meta, DlcDataFileType.CARCOLS),
        )
        for path, document, file_type in metadata:
            pack.file(str(path), document.to_bytes(context=build_context))
            pack.content.file(pack.path(str(path)), file_type)
        pack.platform_rpf(str(VEHICLE_STREAM_RELATIVE_PATH), streamed)
        for path, payload in self.unregistered_files.items():
            pack.file(path, payload)
        change_set = pack.change_set(
            f"{self.name.upper()}_VEHICLES",
            enable_all=True,
        )
        change_set.requires_loading_screen = False
        return pack

    def _validate_pack_bytes(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        try:
            reread = read_dlc_pack(data, game=self.game, load_files=True)
            report.extend(reread.validate(game=self.game), path="dlc")
            report.extend(
                validate_enhanced_vehicle_pack_layout(reread),
                path="dlc",
            )
            report.raise_for_errors()
            archive = RpfArchive.from_bytes(data, name="dlc.rpf", load_nested=True)
            for path, document in (
                (self.VEHICLES_META, self.vehicles_meta),
                (self.HANDLING_META, self.handling_meta),
                (self.VARIATIONS_META, self.variations_meta),
                (self.CARCOLS_META, self.carcols_meta),
            ):
                entry = archive.find_entry(path)
                if not isinstance(entry, RpfFileEntry):
                    raise FileNotFoundError(f"Built DLC is missing {path}")
                payload = entry.read()
                validate_vehicle_meta_xml(
                    payload,
                    expected_root=document.ROOT_TAG,
                ).raise_for_errors()
                reread_document = read_vehicle_meta(payload).content
                reread_document.validate().raise_for_errors()
                if reread_document != document:
                    raise ValueError(
                        f"Built DLC changed vehicle metadata semantics in {path}"
                    )
            for asset in self.vehicles:
                fragment_payloads: dict[str, bytes] = {}
                for role, filename in (
                    ("fragment", f"{asset.name}.yft"),
                    ("high_fragment", f"{asset.name}_hi.yft"),
                ):
                    if role == "high_fragment" and asset.high_fragment is None:
                        continue
                    yft_entry = archive.find_entry(self.STREAMED_RPF / filename)
                    if (
                        not isinstance(yft_entry, RpfFileEntry)
                        or yft_entry._archive is None
                    ):
                        raise FileNotFoundError(f"Built DLC is missing {filename}")
                    fragment_payloads[role] = yft_entry._archive.read_entry_standalone(
                        yft_entry
                    )
                metadata = self.vehicles_meta.get(asset.name)
                report.extend(
                    validate_vehicle_yft_pair(
                        asset.name,
                        fragment_payloads["fragment"],
                        fragment_payloads.get("high_fragment"),
                        vehicle_type=(
                            metadata.vehicle_type
                            if metadata is not None
                            else VehicleType.CAR
                        ),
                    ),
                    path=f"dlc.{asset.name}",
                )
                report.raise_for_errors()
                if asset.textures is not None:
                    ytd_entry = archive.find_entry(
                        self.STREAMED_RPF / f"{asset.txd_name}.ytd"
                    )
                    if (
                        not isinstance(ytd_entry, RpfFileEntry)
                        or ytd_entry._archive is None
                    ):
                        raise FileNotFoundError(
                            f"Built DLC is missing {asset.txd_name}.ytd"
                        )
                    textures = read_ytd(
                        ytd_entry._archive.read_entry_standalone(ytd_entry)
                    )
                    if (
                        coerce_game_target(textures.game)
                        is not GameTarget.GTA5_ENHANCED
                    ):
                        raise ValueError(
                            f"Built DLC changed the target of {asset.txd_name}.ytd"
                        )
        except (
            FileNotFoundError,
            IndexError,
            KeyError,
            TypeError,
            ValueError,
            struct.error,
            zlib.error,
        ) as exc:
            report.issue("vehicle.pack.reread.invalid", str(exc), path="dlc_rpf")
        return report

    def save(
        self,
        destination: str | Path,
        *,
        context: BuildContext | None = None,
    ) -> VehiclePackOutput:
        target = Path(destination)
        if target.is_dir() or not target.suffix:
            target = target / self.name / "dlc.rpf"
        report = self.validate(context=context)
        report.raise_for_errors()
        pack = self._build(context)
        report.extend(validate_enhanced_vehicle_pack_layout(pack))
        report.raise_for_errors()
        data = pack.to_bytes(game=self.game)
        report.extend(self._validate_pack_bytes(data))
        report.raise_for_errors()
        atomic_write_bytes(target, data)
        return VehiclePackOutput(
            paths=VehiclePackPaths(
                dlc_rpf=target,
                vehicles_meta=self.VEHICLES_META,
                handling_meta=self.HANDLING_META,
                variations_meta=self.VARIATIONS_META,
                carcols_meta=self.CARCOLS_META,
                streamed_rpf=self.STREAMED_RPF,
            ),
            report=report,
        )


__all__ = [
    "VehiclePackBuilder",
    "VehiclePackOutput",
    "VehiclePackPaths",
    "VehicleStreamAsset",
]
