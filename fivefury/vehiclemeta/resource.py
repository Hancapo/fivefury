from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import Any

from ..authoring import BuildContext, ValidationReport
from ..common import atomic_write_bytes
from ..hashing import jenk_hash
from ..meta.resource import MetaResource
from ..pso import PsoDocument, PsoReader, is_pso
from ..pso_values import make_name_resolver
from ..xml import element_data, looks_like_xml, parse_xml_root
from .carcols import VehicleCarCols, VehicleModColors
from .handling import HandlingDataManager
from .variations import VehicleModelInfoVariation
from .vehicles import VehicleInitDataList

C_VEHICLE_INIT_DATA_LIST = jenk_hash("CVehicleModelInfo::InitDataList")
C_HANDLING_DATA_MANAGER = jenk_hash("CHandlingDataMgr")
C_VEHICLE_MODEL_INFO_VARIATION = jenk_hash("CVehicleModelInfoVariation")
C_VEHICLE_MODEL_INFO_VAR_GLOBAL = jenk_hash("CVehicleModelInfoVarGlobal")
C_VEHICLE_MOD_COLORS = jenk_hash("CVehicleModColors")

YMT_C_VEHICLE_MODEL_INFO_VARIATION = 0x2C7C954B
YMT_C_VEHICLE_MODEL_INFO_VAR_GLOBAL = 0xBDD20BCF

_YMT_NAMES = {
    YMT_C_VEHICLE_MODEL_INFO_VARIATION: "CVehicleModelInfoVariation",
    YMT_C_VEHICLE_MODEL_INFO_VAR_GLOBAL: "CVehicleModelInfoVarGlobal",
    0xCEAE9967: "m_variationData",
    0x0B939623: "m_modelName",
    0x08676A67: "m_colors",
    0x6DDF749B: "m_kits",
    0xAA0856BB: "m_windowsWithExposedEdges",
    0x2D3FBA3F: "m_plateProbabilities",
    0x8DB32D08: "m_lightSettings",
    0x84EB9B0D: "m_sirenSettings",
    0x99885DD2: "CVehicleModelColorIndices",
    0xE9BF9F2D: "m_indices",
    0xA6648434: "m_liveries",
    0x235D1478: "m_VehiclePlates",
    0x2B020DDD: "m_Colors",
    0x54FB4B4E: "m_MetallicSettings",
    0x370D5711: "m_WindowColors",
    0xAA246E0E: "m_Lights",
    0x9AF814F5: "m_Sirens",
    0x593BC9C3: "m_Kits",
    0xD244FA73: "m_Wheels",
    0xF8A65F1A: "m_GlobalVariationData",
    0x99D3B662: "m_XenonLightColors",
    0xFB22670E: "CVehicleModelColor",
    0xE953FD29: "m_color",
    0x99B074F9: "m_metallicID",
    0x69B6E89B: "m_audioColor",
    0x8D37E9F7: "m_audioPrefix",
    0x8A35AB87: "m_audioColorHash",
    0x130D0072: "m_audioPrefixHash",
    0xD8BC1C53: "m_colorName",
}

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


def _resolve_vehicle_name(hash_value: int) -> str:
    return _YMT_NAMES.get(hash_value, _resolve_name(hash_value))


class VehicleMetaFormat(enum.Enum):
    XML = "xml"
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
    YMT_C_VEHICLE_MODEL_INFO_VARIATION: VehicleMetaContentType.CAR_VARIATIONS,
    YMT_C_VEHICLE_MODEL_INFO_VAR_GLOBAL: VehicleMetaContentType.CAR_COLS,
}

_XML_ROOT_CONTENT_TYPES = {
    "cvehiclemodelinfo__initdatalist": VehicleMetaContentType.VEHICLES,
    "chandlingdatamgr": VehicleMetaContentType.HANDLING,
    "cvehiclemodelinfovariation": VehicleMetaContentType.CAR_VARIATIONS,
    "cvehiclemodelinfovarglobal": VehicleMetaContentType.CAR_COLS,
    "cvehiclemodcolors": VehicleMetaContentType.CAR_MOD_COLS,
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


def _handling_xml_data(root: Any) -> Any:
    data = element_data(root)
    if not isinstance(data, dict):
        return data
    values = data.get("HandlingData", [])
    if isinstance(values, dict):
        values = [values]
    container = root.find("HandlingData")
    elements = [] if container is None else container.findall("Item")
    for value, element in zip(values, elements, strict=False):
        if not isinstance(value, dict):
            continue
        for tag in ("strModelFlags", "strHandlingFlags", "strDamageFlags"):
            child = element.find(tag)
            if child is None:
                value.pop(tag, None)
            else:
                value[tag] = (child.text or "").strip()
    return data


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

    def validate(self, *, context: BuildContext | None = None) -> ValidationReport:
        validator = getattr(self.content, "validate", None)
        if validator is None:
            report = ValidationReport()
            report.issue(
                "vehicle.meta.content.unsupported",
                "The vehicle metadata root is not available as a typed authoring model",
                asset=self.source or None,
            )
            return report
        return validator(context=context)

    def to_bytes(
        self,
        *,
        context: BuildContext | None = None,
        validate: bool = True,
    ) -> bytes:
        if self.format is VehicleMetaFormat.XML:
            serializer = getattr(self.content, "to_bytes", None)
            if serializer is None:
                raise TypeError("Unknown vehicle metadata XML roots are not writable")
            return serializer(context=context, validate=validate)
        return bytes(self.raw_bytes)

    def save(
        self,
        path: str | Path,
        *,
        context: BuildContext | None = None,
        validate: bool = True,
    ) -> Path:
        if self.format is not VehicleMetaFormat.XML:
            raise ValueError("PSO and RSC vehicle metadata projections are read-only")
        return atomic_write_bytes(
            path,
            self.to_bytes(context=context, validate=validate),
        )

    @classmethod
    def from_bytes(cls, data: bytes, *, source: str = "") -> VehicleMeta:
        raw = bytes(data)
        if looks_like_xml(raw):
            root = parse_xml_root(raw)
            root_name = root.tag.rsplit("}", 1)[-1]
            content_type = _XML_ROOT_CONTENT_TYPES.get(
                root_name.casefold(),
                VehicleMetaContentType.UNKNOWN,
            )
            return cls(
                format=VehicleMetaFormat.XML,
                content_type=content_type,
                content=_map_content(
                    _handling_xml_data(root)
                    if content_type is VehicleMetaContentType.HANDLING
                    else element_data(root),
                    content_type,
                ),
                source=source,
                raw_bytes=raw,
            )
        if is_pso(raw):
            pso = PsoReader(raw, name_resolver=_resolve_vehicle_name).read()
            content_type = _ROOT_CONTENT_TYPES.get(
                int(pso.root.type_hash or 0),
                VehicleMetaContentType.UNKNOWN,
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
            VehicleMetaContentType.UNKNOWN,
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
    "YMT_C_VEHICLE_MODEL_INFO_VARIATION",
    "YMT_C_VEHICLE_MODEL_INFO_VAR_GLOBAL",
    "VehicleMeta",
    "VehicleMetaContentType",
    "VehicleMetaFormat",
    "read_vehicle_meta",
]
