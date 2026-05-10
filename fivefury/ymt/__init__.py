from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import Any

from ..gtxd import Gtxd
from ..meta import Meta
from ..meta.defs import META_NAME_REVERSE
from ..meta.resource import MetaResource
from ..pso import PsoDocument, PsoNode, PsoReader, is_pso
from ..rbf import RbfStructure, is_rbf, read_rbf
from .ped_metadata import YmtPedInitData, YmtPedMetadata
from .scenario import YmtAabb, YmtScenarioPointGroup, YmtScenarioPointManifest, YmtScenarioPointRegionDef
from .streaming import YmtStreamingRequestCommonSet, YmtStreamingRequestFrame, YmtStreamingRequestRecord

C_SCENARIO_POINT_MANIFEST = 1425675487
C_SCENARIO_POINT_REGION_DEF = 1251976652
C_SCENARIO_POINT_GROUP = 3383680063
C_SCENARIO_POINT_REGION = 1492970064
C_PED_VARIATION_INFO = 376833625
C_PED_MODEL_INFO_INIT_DATA_LIST = 3715594014
C_PED_MODEL_INFO_INIT_DATA = 3949383814
C_STREAMING_REQUEST_RECORD = 135915278
C_STREAMING_REQUEST_FRAME = 999226379
C_STREAMING_REQUEST_COMMON_SET = 1358189812
C_MAP_PARENT_TXDS = 2935248897
RAGE_SPD_AABB = 4084721864

YMT_ROOT_NAMES = {
    C_SCENARIO_POINT_MANIFEST: "CScenarioPointManifest",
    C_SCENARIO_POINT_REGION_DEF: "CScenarioPointRegionDef",
    C_SCENARIO_POINT_GROUP: "CScenarioPointGroup",
    C_SCENARIO_POINT_REGION: "CScenarioPointRegion",
    C_PED_VARIATION_INFO: "CPedVariationInfo",
    C_PED_MODEL_INFO_INIT_DATA_LIST: "CPedModelInfo__InitDataList",
    C_PED_MODEL_INFO_INIT_DATA: "CPedModelInfo__InitData",
    C_STREAMING_REQUEST_RECORD: "CStreamingRequestRecord",
    C_STREAMING_REQUEST_FRAME: "CStreamingRequestFrame",
    C_STREAMING_REQUEST_COMMON_SET: "CStreamingRequestCommonSet",
    C_MAP_PARENT_TXDS: "CMapParentTxds",
    RAGE_SPD_AABB: "rage__spdAABB",
    1292187579: "VersionNumber",
    3713107563: "RegionDefs",
    2500839488: "Groups",
    2406565252: "InteriorNames",
    2901156542: "Name",
    1666779607: "AABB",
    3921215899: "EnabledByDefault",
    376833625: "CPedVariationInfo",
    1235285100: "bHasTexVariations",
    4086479472: "bHasDrawblVariations",
    910099323: "bHasLowLODs",
    315291935: "bIsSuperLOD",
    2996564520: "availComp",
    3796405327: "aComponentData3",
    2131007641: "aSelectionSets",
    592652859: "compInfos",
    2240859608: "propInfo",
    2337697442: "dlcName",
    3538495220: "CPVComponentData",
    1535046754: "CPVDrawblData",
    1036962405: "CPVTextureData",
    2236980467: "CPVDrawblData__CPVClothComponentData",
    3371516811: "numAvailTex",
    1756136273: "aDrawblData3",
    2932859459: "propMask",
    2806194106: "numAlternatives",
    1251090986: "aTexData",
    2464583091: "clothData",
    2828247905: "ownsCloth",
    1785432003: "texId",
    914976023: "distribution",
    2858946626: "CPedPropInfo",
    2598445407: "numAvailProps",
    3902803273: "aPropMetaData",
    162345210: "aAnchors",
    419044527: "Frames",
    4248405899: "CommonSets",
    2333392588: "NewStyle",
    327274266: "AddList",
    3372321331: "RemoveList",
    896120921: "PromoteToHDList",
    357008256: "CamPos",
    210316193: "CamDir",
    1762439591: "CommonAddSets",
    1264718594: "Flags",
    2743119154: "Requests",
    1079754329: "residentTxd",
    2052114030: "residentAnims",
    1512338287: "InitDatas",
    110813075: "txdRelationships",
    3649984070: "multiTxdRelationships",
    3649202799: "CTxdRelationship",
    1261337422: "CMultiTxdRelationship",
    54445749: "child",
    2571958159: "ClipDictionaryName",
    1760551351: "ExpressionDictionaryName",
    2352891724: "ExpressionSetName",
    3052355362: "Pedtype",
    3248325447: "MovementClipSet",
    3295015867: "PedComponentSetName",
    2679581144: "PedComponentClothName",
    851100275: "PedIKSettingsName",
}


class YmtFormat(enum.Enum):
    UNKNOWN = "unknown"
    RSC = "rsc"
    META = "rsc"
    RBF = "rbf"
    PSO = "pso"


class YmtContentType(enum.Enum):
    NONE = "none"
    MAP_PARENT_TXDS = "CMapParentTxds"
    SCENARIO_POINT_MANIFEST = "CScenarioPointManifest"
    SCENARIO_POINT_REGION = "CScenarioPointRegion"
    PED_VARIATION = "CPedVariationInfo"
    PED_METADATA = "CPedModelInfo__InitDataList"
    STREAMING_REQUEST_RECORD = "CStreamingRequestRecord"


@dataclasses.dataclass(slots=True)
class Ymt(MetaResource):
    extension = ".ymt"
    rbf: RbfStructure | None = None
    pso: PsoDocument | None = None
    content: Any = None
    format: YmtFormat = YmtFormat.META
    content_type: YmtContentType = YmtContentType.NONE
    raw_bytes: bytes | None = None

    @property
    def gtxd(self) -> Gtxd | None:
        return self.content if isinstance(self.content, Gtxd) else None

    @property
    def scenario_point_manifest(self) -> PsoNode | None:
        if isinstance(self.content, YmtScenarioPointManifest):
            return self.content.raw
        return self.content if self.content_type is YmtContentType.SCENARIO_POINT_MANIFEST else None

    @property
    def scenario_manifest(self) -> YmtScenarioPointManifest | None:
        return self.content if isinstance(self.content, YmtScenarioPointManifest) else None

    @property
    def scenario_point_region(self) -> Any:
        return self.content if self.content_type is YmtContentType.SCENARIO_POINT_REGION else None

    @property
    def ped_variation(self) -> Any:
        return self.content if self.content_type is YmtContentType.PED_VARIATION else None

    @property
    def ped_metadata(self) -> YmtPedMetadata | None:
        return self.content if isinstance(self.content, YmtPedMetadata) else None

    @property
    def streaming_request_record(self) -> YmtStreamingRequestRecord | None:
        return self.content if isinstance(self.content, YmtStreamingRequestRecord) else None

    @property
    def root_type_hash(self) -> int:
        if self.pso is not None:
            return int(self.pso.root.type_hash or 0)
        if self.root_name_hash:
            return int(self.root_name_hash)
        if self.rbf is not None:
            return C_MAP_PARENT_TXDS if self.rbf.name == YmtContentType.MAP_PARENT_TXDS.value else 0
        return 0

    @property
    def root_type_name(self) -> str:
        if self.rbf is not None:
            return self.rbf.name
        return self._name(self.root_type_hash)

    @property
    def is_rsc(self) -> bool:
        return self.format is YmtFormat.RSC

    @property
    def is_rbf(self) -> bool:
        return self.format is YmtFormat.RBF

    @property
    def is_pso(self) -> bool:
        return self.format is YmtFormat.PSO

    @staticmethod
    def _name(hash_value: int) -> str:
        return YMT_ROOT_NAMES.get(hash_value) or META_NAME_REVERSE.get(hash_value) or f"hash_{hash_value:08X}"

    @classmethod
    def _from_rbf_bytes(cls, data: bytes, *, source: str = "") -> "Ymt":
        root = read_rbf(data)
        content: Any = None
        content_type = YmtContentType.NONE
        if root.name == YmtContentType.MAP_PARENT_TXDS.value:
            content = Gtxd.from_rbf_root(root)
            content_type = YmtContentType.MAP_PARENT_TXDS
        return cls(
            meta=Meta(Name=Path(source).stem if source else ""),
            source=source,
            rbf=root,
            content=content,
            format=YmtFormat.RBF,
            content_type=content_type,
            raw_bytes=bytes(data),
        )

    @classmethod
    def _from_pso_bytes(cls, data: bytes, *, source: str = "") -> "Ymt":
        pso = PsoReader(data, name_resolver=cls._name).read()
        content: Any = None
        content_type = YmtContentType.NONE
        if pso.root.type_hash == C_SCENARIO_POINT_MANIFEST:
            content = YmtScenarioPointManifest.from_pso_node(pso.root)
            content_type = YmtContentType.SCENARIO_POINT_MANIFEST
        elif pso.root.type_hash == C_PED_VARIATION_INFO:
            content = pso.root
            content_type = YmtContentType.PED_VARIATION
        elif pso.root.type_hash == C_PED_MODEL_INFO_INIT_DATA_LIST:
            content = YmtPedMetadata.from_value(pso.root)
            content_type = YmtContentType.PED_METADATA
        elif pso.root.type_hash == C_STREAMING_REQUEST_RECORD:
            content = YmtStreamingRequestRecord.from_value(pso.root)
            content_type = YmtContentType.STREAMING_REQUEST_RECORD
        return cls(
            meta=Meta(Name=Path(source).stem if source else ""),
            source=source,
            pso=pso,
            content=content,
            format=YmtFormat.PSO,
            content_type=content_type,
            raw_bytes=bytes(data),
        )

    @classmethod
    def _from_meta_resource(cls, resource: MetaResource, *, source: str = "") -> "Ymt":
        content_type = YmtContentType.NONE
        content: Any = None
        if resource.root_name_hash == C_SCENARIO_POINT_REGION:
            content = resource.root_value
            content_type = YmtContentType.SCENARIO_POINT_REGION
        elif resource.root_name_hash == C_PED_VARIATION_INFO:
            content = resource.root_value
            content_type = YmtContentType.PED_VARIATION
        elif resource.root_name_hash == C_PED_MODEL_INFO_INIT_DATA_LIST:
            content = YmtPedMetadata.from_value(resource.root_value)
            content_type = YmtContentType.PED_METADATA
        elif resource.root_name_hash == C_STREAMING_REQUEST_RECORD:
            content = YmtStreamingRequestRecord.from_value(resource.root_value)
            content_type = YmtContentType.STREAMING_REQUEST_RECORD
        return cls(
            meta=resource.to_meta(),
            source=source or resource.source,
            content=content,
            format=YmtFormat.RSC,
            content_type=content_type,
        )

    def to_bytes(self) -> bytes:
        if self.raw_bytes is not None and self.format in {YmtFormat.RBF, YmtFormat.PSO}:
            return bytes(self.raw_bytes)
        return super().to_bytes()

    @classmethod
    def from_bytes(cls, data: bytes, *, source: str = "") -> "Ymt":
        if is_rbf(data):
            return cls._from_rbf_bytes(data, source=source)
        if is_pso(data):
            return cls._from_pso_bytes(data, source=source)
        return cls._from_meta_resource(MetaResource.from_bytes(data, source=source), source=source)

    @classmethod
    def from_meta(cls, meta: Meta, *, source: str = "") -> "Ymt":
        return cls._from_meta_resource(MetaResource.from_meta(meta, source=source), source=source)


def read_ymt(data: bytes | str | Path) -> Ymt:
    if isinstance(data, (str, Path)):
        return Ymt.from_path(data)
    return Ymt.from_bytes(data)


def save_ymt(ymt: Ymt | Meta, path: str | Path | None = None) -> Path:
    resource = ymt if isinstance(ymt, Ymt) else Ymt.from_meta(ymt)
    return resource.save(path)


from .ped_variation import (  # noqa: E402
    PedComponent,
    PedDrawableVariation,
    coerce_ped_component,
    iter_ped_drawables,
    ped_drawable_file_stem,
    set_ped_drawable_cloth,
)


__all__ = [
    "PedComponent",
    "PedDrawableVariation",
    "Ymt",
    "YmtAabb",
    "YmtContentType",
    "YmtFormat",
    "YmtPedInitData",
    "YmtPedMetadata",
    "YmtScenarioPointGroup",
    "YmtScenarioPointManifest",
    "YmtScenarioPointRegionDef",
    "YmtStreamingRequestCommonSet",
    "YmtStreamingRequestFrame",
    "YmtStreamingRequestRecord",
    "coerce_ped_component",
    "iter_ped_drawables",
    "ped_drawable_file_stem",
    "read_ymt",
    "save_ymt",
    "set_ped_drawable_cloth",
]
