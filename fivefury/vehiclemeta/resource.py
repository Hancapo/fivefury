from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import Any

from ..hashing import jenk_hash
from ..meta.resource import MetaResource
from ..pso import PsoDocument, PsoReader, is_pso
from ..pso_values import make_name_resolver
from .carcols import VehicleCarCols, VehicleModColors
from .handling import HandlingDataManager
from .variations import VehicleModelInfoVariation
from .vehicles import VehicleInitDataList

C_VEHICLE_INIT_DATA_LIST = jenk_hash("CVehicleModelInfo::InitDataList")
C_HANDLING_DATA_MANAGER = jenk_hash("CHandlingDataMgr")
C_VEHICLE_MODEL_INFO_VARIATION = jenk_hash("CVehicleModelInfoVariation")
C_VEHICLE_MODEL_INFO_VAR_GLOBAL = jenk_hash("CVehicleModelInfoVarGlobal")
C_VEHICLE_MOD_COLORS = jenk_hash("CVehicleModColors")

_TYPE_NAMES = (
    "CVehicleModelInfo::InitDataList",
    "CVehicleModelInfo::InitData",
    "CDriverInfo",
    "CDoorStiffnessInfo",
    "CVfxExtraInfo",
    "CMobilePhoneSeatIKOffset",
    "CVehicleModelInfo::CVehicleOverrideRagdollThreshold",
    "CAdditionalVfxWaterSample",
    "CTxdRelationship",
    "CHandlingDataMgr",
    "CHandlingData",
    "CBoatHandlingData",
    "CSeaPlaneHandlingData",
    "CFlyingHandlingData",
    "CVehicleWeaponHandlingData",
    "CBikeHandlingData",
    "CSubmarineHandlingData",
    "CTrailerHandlingData",
    "CCarHandlingData",
    "CSpecialFlightHandlingData",
    "CVehicleModelInfoVariation",
    "CVehicleVariationData",
    "CVehicleModelColorIndices",
    "CVehicleModelPlateProbabilities",
    "LicensePlateProbabilityNamed",
    "CVehicleModelInfoVarGlobal",
    "CVehicleModelInfoPlates",
    "CVehicleModelInfoPlateTextureSet",
    "CVehicleModelColor",
    "CVehicleMetallicSetting",
    "CVehicleWindowColor",
    "CVehicleVariationGlobalData",
    "CVehicleXenonLightColor",
    "vehicleLight",
    "vehicleCorona",
    "vehicleLightSettings",
    "sirenCorona",
    "sirenRotation",
    "sirenLight",
    "sirenSettings::sequencerData",
    "sirenSettings",
    "CVehicleKit",
    "CVehicleModVisible",
    "CVehicleModLink",
    "CVehicleModStat",
    "CVehicleWheel",
    "CVehicleKit::sSlotNameOverride",
    "CVehicleModColors",
    "CVehicleModColor",
    "CVehicleModPearlescentColors",
)
_resolve_name = make_name_resolver(_TYPE_NAMES)


class VehicleMetaFormat(enum.Enum):
    PSO = "pso"
    RSC = "rsc"


class VehicleMetaContentType(enum.Enum):
    UNKNOWN = "unknown"
    VEHICLES = "vehicles"
    HANDLING = "handling"
    CAR_VARIATIONS = "carvariations"
    CAR_COLS = "carcols"
    CAR_MOD_COLS = "carmodcols"


_ROOT_CONTENT_TYPES = {
    C_VEHICLE_INIT_DATA_LIST: VehicleMetaContentType.VEHICLES,
    C_HANDLING_DATA_MANAGER: VehicleMetaContentType.HANDLING,
    C_VEHICLE_MODEL_INFO_VARIATION: VehicleMetaContentType.CAR_VARIATIONS,
    C_VEHICLE_MODEL_INFO_VAR_GLOBAL: VehicleMetaContentType.CAR_COLS,
    C_VEHICLE_MOD_COLORS: VehicleMetaContentType.CAR_MOD_COLS,
}

_FILE_CONTENT_TYPES = {
    "vehicles.meta": VehicleMetaContentType.VEHICLES,
    "handling.meta": VehicleMetaContentType.HANDLING,
    "carvariations.meta": VehicleMetaContentType.CAR_VARIATIONS,
    "carcols.meta": VehicleMetaContentType.CAR_COLS,
    "carmodcols.meta": VehicleMetaContentType.CAR_MOD_COLS,
}


def _map_content(root: Any, content_type: VehicleMetaContentType) -> Any:
    model_type = {
        VehicleMetaContentType.VEHICLES: VehicleInitDataList,
        VehicleMetaContentType.HANDLING: HandlingDataManager,
        VehicleMetaContentType.CAR_VARIATIONS: VehicleModelInfoVariation,
        VehicleMetaContentType.CAR_COLS: VehicleCarCols,
        VehicleMetaContentType.CAR_MOD_COLS: VehicleModColors,
    }.get(content_type)
    return model_type.from_value(root) if model_type is not None else root


@dataclasses.dataclass(slots=True)
class VehicleMeta:
    format: VehicleMetaFormat
    content_type: VehicleMetaContentType
    content: Any
    source: str = ""
    pso: PsoDocument | None = None
    meta: MetaResource | None = None
    raw_bytes: bytes = b""

    @property
    def root_type_hash(self) -> int:
        if self.pso is not None:
            return int(self.pso.root.type_hash or 0)
        return int(self.meta.root_name_hash) if self.meta is not None else 0

    @property
    def vehicles(self) -> VehicleInitDataList | None:
        return self.content if isinstance(self.content, VehicleInitDataList) else None

    @property
    def handling(self) -> HandlingDataManager | None:
        return self.content if isinstance(self.content, HandlingDataManager) else None

    @property
    def variations(self) -> VehicleModelInfoVariation | None:
        return (
            self.content
            if isinstance(self.content, VehicleModelInfoVariation)
            else None
        )

    @property
    def carcols(self) -> VehicleCarCols | None:
        return self.content if isinstance(self.content, VehicleCarCols) else None

    @property
    def mod_colors(self) -> VehicleModColors | None:
        return self.content if isinstance(self.content, VehicleModColors) else None

    def to_bytes(self) -> bytes:
        return bytes(self.raw_bytes)

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.write_bytes(self.to_bytes())
        return target

    @classmethod
    def from_bytes(cls, data: bytes, *, source: str = "") -> VehicleMeta:
        raw = bytes(data)
        filename_type = _FILE_CONTENT_TYPES.get(Path(source).name.casefold())
        if is_pso(raw):
            pso = PsoReader(raw, name_resolver=_resolve_name).read()
            content_type = _ROOT_CONTENT_TYPES.get(
                int(pso.root.type_hash or 0),
                filename_type or VehicleMetaContentType.UNKNOWN,
            )
            return cls(
                format=VehicleMetaFormat.PSO,
                content_type=content_type,
                content=_map_content(pso.root, content_type),
                source=source,
                pso=pso,
                raw_bytes=raw,
            )
        meta = MetaResource.from_bytes(raw, source=source)
        content_type = _ROOT_CONTENT_TYPES.get(
            int(meta.root_name_hash),
            filename_type or VehicleMetaContentType.UNKNOWN,
        )
        return cls(
            format=VehicleMetaFormat.RSC,
            content_type=content_type,
            content=_map_content(meta.root_value, content_type),
            source=source,
            meta=meta,
            raw_bytes=raw,
        )

    @classmethod
    def from_path(cls, path: str | Path) -> VehicleMeta:
        target = Path(path)
        return cls.from_bytes(target.read_bytes(), source=str(target))


def read_vehicle_meta(data: bytes | str | Path, *, source: str = "") -> VehicleMeta:
    if isinstance(data, (str, Path)):
        return VehicleMeta.from_path(data)
    return VehicleMeta.from_bytes(data, source=source)


__all__ = [
    "C_HANDLING_DATA_MANAGER",
    "C_VEHICLE_INIT_DATA_LIST",
    "C_VEHICLE_MODEL_INFO_VARIATION",
    "C_VEHICLE_MODEL_INFO_VAR_GLOBAL",
    "C_VEHICLE_MOD_COLORS",
    "VehicleMeta",
    "VehicleMetaContentType",
    "VehicleMetaFormat",
    "read_vehicle_meta",
]
